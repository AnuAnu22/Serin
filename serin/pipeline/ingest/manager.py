"""
serin.messaging.manager
-----------------------
EnhancedMessageManagerV3 owns all message pre-processing (corrections, vision,
memory storage, batching) and delegates the core response flow to MessagePipeline.

This class exists for backwards compatibility. New code should use
MessagePipeline directly.
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import discord
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from serin.config.logger import logger
from serin.pipeline.remember.qdrant import QdrantMemorySystem
from serin.pipeline.remember.memory_context import EnhancedMemoryContext, ImprovedSystemPrompt
from serin.pipeline.think.response_controller import ResponseController, PersonalityState
from serin.pipeline.think.response_generator import get_response_natural
from serin.personality.bot_personality import BotPersonality
from serin.pipeline.perceive.conversation_analyzer import ConversationAnalyzer
from serin.pipeline.ingest.correction_handler import CorrectionDetector, MemoryCorrector, get_correction_acknowledgment
from serin.pipeline.perceive.active_search import ActiveSearch
from serin.pipeline.ingest.context_builder import ConversationContextBuilder
from serin.pipeline.ingest.mention_translator import MentionTranslator
from serin.config.debug_logger import log_message, log_correction
from serin.state.model_system.factory import get_model_connector


@dataclass
class PerceptionResult:
    """Structured analysis of an incoming message before storage.

    Transforms a raw text string into classified information that the
    memory system can store with proper provenance. Separates:
      - What was *said* (the speech act)
      - What *evidence* was presented (boards, URLs, code, quotes)
      - What *claims* were made (subjective assertions)
      - What *observations* can be extracted (verifiable content)
    """
    speech_act: str  # assertion | question | joke | sarcasm | agreement | disagreement | evidence | statement | instruction
    is_objective: bool  # primarily factual/verifiable?
    evidence_class: str = 'conversation'  # world | conversation | social | system
    intent: str = 'statement'  # seek_validation | seek_explanation | seek_argument | seek_joke | social | question | command | statement
    evidence_blocks: List[Dict] = field(default_factory=list)  # [{type, content, metadata, evidence_class}]
    claims: List[Dict] = field(default_factory=list)  # [{claimant, content, category}]
    observations: List[str] = field(default_factory=list)  # verifiable observations extracted
    extracted_facts: List[Dict] = field(default_factory=list)  # [{content, category, confidence, source_type}]


# ── Perception patterns ──────────────────────────────────────────────────────

# Claim patterns: subjective assertions about self, others, or how things are
_CLAIM_PATTERNS = [
    (r'\bI\s+won\b', 'win_claim'),
    (r'\byou\s+lost\b', 'loss_attribution'),
    (r'\bI\'\w+\s+(?:right|correct|wrong|better|best)\b', 'self_assessment'),
    (r'\byou\s+\'\w+\s+(?:wrong|incorrect|mistaken)\b', 'other_correction'),
    (r'\b(?:actually|honestly|truthfully|literally)\s*,?\s+(?:\w+)', 'emphasis_claim'),
]

# Sarcasm indicators
_SARCASM_MARKERS = [
    'oh sure', 'yeah right', 'obviously', 'clearly',
    'as if', 'sure thing', 'totally', 'no way',
    'big brain', 'galaxy brain',
]

# Joke indicators  
_JOKE_MARKERS = ['lol', 'lmao', 'rofl', 'jk', 'kidding', 'just joking', 'haha', 'hehe', 'xd']

# Argument keywords (for mood-based filtering at retrieval time)
_ARGUMENT_KEYWORDS = ['lose', 'lost', 'win', 'won', 'admit', 'wrong',
                       'cope', 'argue', 'disagree', 'disagreed', 'prove']


class EnhancedMessageManagerV3:
    """
    Message manager that handles pre-processing (corrections, vision, batching)
    and delegates core response generation to MessagePipeline.
    """

    def __init__(
        self,
        client: discord.Client,
        mention_translator: MentionTranslator,
        memory_system: Optional[QdrantMemorySystem] = None,
        sub_timeout: int = 1,
        voice_output_manager: Any = None,
    ) -> None:
        self.client = client
        self.mention_translator = mention_translator
        self.current_batch: list[discord.Message] = []
        self.flush_task: Optional[asyncio.Task[None]] = None
        self.sub_timeout = sub_timeout
        self.voice_output_manager = voice_output_manager

        # TIER 8: Observable Brain State
        self.current_state: Dict[str, Any] = {
            "status": "IDLE",
            "current_prompt": None,
            "current_user_message": None,
            "abort_flag": False,
            "last_activity": datetime.now().isoformat(),
        }

        # Initialize memory system
        if memory_system:
            self.memory = memory_system
        else:
            self.memory = QdrantMemorySystem()

        # Initialize LLM connector for image analysis
        self.llm = get_model_connector()

        # Initialize separate vision model (SmolVLM) if enabled
        self.vision_llm: Any = None
        supports_vision = os.environ.get("LLM_SUPPORTS_VISION", "false").lower() in ("true", "1", "yes")
        vision_model = os.environ.get("VISION_MODEL", "smolvlm256m")
        if supports_vision:
            try:
                from models.vllm import VLLMConnector
                self.vision_llm = VLLMConnector(model_name=vision_model)
                self.vision_llm.load_model()
                logger.info("Vision model loaded: %s", vision_model)
            except Exception as e:
                logger.warning("Vision model '%s' not available: %s", vision_model, e)
                self.vision_llm = None

        # Initialize context systems
        self.enhanced_context = EnhancedMemoryContext(self.memory)
        self.context_builder = ConversationContextBuilder(self.memory)
        self.analyzer = SentimentIntensityAnalyzer()

        # TIER 2: Human-like behavior
        self.response_controller = ResponseController()
        self.personality = PersonalityState()

        # TIER 3: Advanced features
        self.conversation_analyzer = ConversationAnalyzer()
        self.bot_personality = BotPersonality()

        # TIER 5: Correction + Voice systems
        self.correction_detector = CorrectionDetector()
        self.memory_corrector = MemoryCorrector(self.memory)
        from serin.gateway.voice_transcribe.tracker import VoiceTracker
        self.voice_tracker = VoiceTracker(self.memory)

        # Pipeline instance (set externally by discord_bot.py after building)
        self.pipeline: Any = None

        # Voice action decider
        self.voice_action_decider: Any = None
        self.voice_action_callback: Any = None

        # Active Search
        self.active_search: Optional[ActiveSearch] = None
        try:
            model_connector = get_model_connector()
            model_connector.load_model()
            self.active_search = ActiveSearch(model_connector)
            logger.info("Active Search (Thinking) enabled")
        except Exception as e:
            self.active_search = None
            logger.error("Active Search disabled: %s", e)

        # Visual Cortex
        self.visual_memory: Optional[VisualMemorySystem] = None
        if hasattr(self.memory, "qdrant_client") and self.memory.qdrant_client:
            from serin.state.visual_memory import VisualMemorySystem
            self.visual_memory = VisualMemorySystem(self.memory.qdrant_client)
        else:
            self.visual_memory = None
            logger.warning("Visual Cortex disabled (requires Qdrant)")

        self.last_bot_response: Optional[str] = None
        self.last_bot_response_channel: Optional[str] = None
        self.system_prompt = ImprovedSystemPrompt.get_enhanced_system_prompt()

        self.stats: Dict[str, int] = {
            "messages_processed": 0,
            "responses_generated": 0,
            "corrections_detected": 0,
            "errors": 0,
            "context_improvements": 0,
            "voice_responses": 0,
        }

        # Cache for visual contexts between processing and flushing
        self.pending_visual_contexts: Dict[int, str] = {}

        # Voice pipeline (set externally if available)
        self.voice_pipeline: Any = None

        # Voice Action Decider
        from serin.gateway.voice_transcribe.decider import VoiceActionDecider
        try:
            va_connector = get_model_connector()
            va_connector.load_model()
            self.voice_action_decider = VoiceActionDecider(va_connector)
            logger.info("Voice Action Decider enabled")
        except Exception as e:
            self.voice_action_decider = None
            logger.warning("Voice Action Decider disabled: %s", e)

        memory_type = "Qdrant" if hasattr(self.memory, "qdrant_client") else "ChromaDB"
        logger.info("Enhanced MessageManager initialized with %s memory system", memory_type)
        if self.voice_output_manager:
            logger.info("Voice Output Manager connected")

    def update_state(self, status: str, prompt: Optional[str] = None, user_message: Optional[str] = None) -> None:
        """Update the observable brain state"""
        self.current_state["status"] = status
        self.current_state["last_activity"] = datetime.now().isoformat()
        if prompt is not None:
            self.current_state["current_prompt"] = prompt
        if user_message is not None:
            self.current_state["current_user_message"] = user_message

    def abort_current_generation(self) -> None:
        """Signal to abort current generation"""
        logger.warning("Abort signal received!")
        self.current_state["abort_flag"] = True
        self.current_state["status"] = "ABORTING"

    async def process_voice_input(self, user_id: str, username: str, channel_id: str, transcription: str, wav_b64: Optional[str] = None) -> None:
        """Process voice input and generate voice response."""
        try:
            logger.info("Processing voice input from %s: '%s'", username, transcription)

            recent_voice = []
            if self.voice_pipeline:
                recent_voice = self.voice_pipeline.get_recent_context(channel_id, limit=5)

            user_messages = []
            for msg in recent_voice:
                user_messages.append({
                    "user_id": msg["user_id"],
                    "user_name": msg["username"],
                    "content": msg["content"],
                    "timestamp": msg["timestamp"],
                })

            if not any(m["content"] == transcription for m in user_messages):
                user_messages.append({
                    "user_id": user_id,
                    "user_name": username,
                    "content": transcription if not wav_b64 else "[voice input]",
                    "timestamp": datetime.now().isoformat(),
                })

            context = self.context_builder.build_context(
                user_messages=user_messages,
                channel_id=channel_id,
            )
            formatted_context = self.context_builder.format_context_for_llm(context)

            personality_context = self.bot_personality.get_personality_context()
            if personality_context:
                formatted_context += f"\n\n{personality_context}"

            formatted_context += "\n\n[SYSTEM: You are speaking in a voice channel. Keep responses concise, conversational, and natural. Avoid long lists or code blocks. Use fillers like 'Hmm' or 'Let's see' if you need to think.]"

            if wav_b64:
                voice_messages = [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": formatted_context},
                        {"type": "input_audio", "input_audio": {"data": wav_b64, "format": "wav"}},
                    ],
                }]
                from serin.pipeline.think.response_generator import llama as llm_connector
                if llm_connector is None:
                    from serin.pipeline.think.response_generator import initialize_llama
                    await initialize_llama()
                    from serin.pipeline.think.response_generator import llama as llm_connector
                response = await llm_connector.chat_completion(
                    voice_messages,
                    max_tokens=300,
                    temperature=1.0,
                    top_p=0.95,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
            else:
                response = await get_response_natural(
                    current_messages=user_messages,
                    context=formatted_context,
                    resolved_last_message=transcription,
                    tone_modifier=self.personality.get_tone_modifier(),
                    personality_state=self.personality.__dict__,
                    message_complexity="simple",
                    is_instruction=False,
                )

            if response and response.strip():
                logger.info("Voice Response: '%s'", response)
                if self.voice_output_manager:
                    try:
                        guild_id = int(context.get("guild_id", 0))
                        if guild_id == 0:
                            channel = self.client.get_channel(int(channel_id))
                            if channel:
                                guild_id = channel.guild.id
                        if guild_id:
                            await self.voice_output_manager.speak(response, guild_id)
                            self.stats["voice_responses"] += 1
                        else:
                            logger.error("Could not determine guild ID for voice response")
                    except Exception as e:
                        logger.error("Error sending to voice output: %s", e)

        except Exception as e:
            logger.exception("Error processing voice input: %s", e)

    async def start(self) -> None:
        """Start the manager."""
        logger.info("Enhanced MessageManager started")

    async def process_message(self, message: discord.Message) -> None:
        """Process incoming message with all pre-processing, then delegate to pipeline."""
        try:
            user_id = str(message.author.id)
            user_name = message.author.display_name
            content = message.content
            channel_id = str(message.channel.id)

            self.mention_translator.update_cache(message.author)
            cleaned_content = self.mention_translator.clean_for_bot(content, message)
            cleaned_content = self.mention_translator.clean_bot_self_mention(cleaned_content)
            log_message(message, cleaned_content)

            # TIER 5: Check for correction FIRST
            if self.last_bot_response and self.last_bot_response_channel == channel_id:
                correction = self.correction_detector.detect_correction(
                    message=cleaned_content,
                    previous_bot_response=self.last_bot_response,
                    context=[{"content": msg.content} for msg in self.current_batch[-3:]],
                )
                if correction and correction.get("confidence", 0) > 0.7:
                    logger.info("Correction detected!")
                    self.stats["corrections_detected"] += 1
                    log_correction(correction, user_name)
                    self.memory_corrector.apply_correction(correction, user_id, user_name, channel_id)
                    ack = get_correction_acknowledgment(correction)
                    await message.channel.send(ack)
                    self.last_bot_response = None
                    return

            # TIER 6: Visual Memory Processing
            main_llm_has_vision = os.environ.get("LLM_SUPPORTS_VISION", "false").lower() in ("true", "1", "yes")
            if message.attachments and self.visual_memory:
                for attachment in message.attachments:
                    if attachment.content_type and attachment.content_type.startswith("image/"):
                        logger.info("Processing image from %s...", user_name)
                        matches = self.visual_memory.recall_image(attachment.url)
                        if matches:
                            top_match = matches[0]
                            visual_context = f"\n[Visual Memory: I recognize this image! It looks like what {top_match['username']} posted on {top_match['timestamp'][:10]}. Context: '{top_match['context']}']"
                            logger.info("Visual recognition: %s", visual_context)

                        image_data_url = None
                        image_bytes = None
                        try:
                            image_bytes = await attachment.read()
                            if image_bytes:
                                mime = attachment.content_type or "image/jpeg"
                                b64 = base64.b64encode(image_bytes).decode("utf-8")
                                image_data_url = f"data:{mime};base64,{b64}"
                                logger.info("Encoded image as base64 (%s bytes)", len(image_bytes))
                        except Exception as e:
                            logger.warning("Failed to download/encode image: %s", e)

                        self.pending_visual_contexts[message.id] = image_data_url or attachment.url
                        cleaned_content += " [User posted an image]"

                        storage_description = ""
                        if image_data_url and main_llm_has_vision:
                            try:
                                desc_prompt = [{
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": "Describe this image in detail for archival purposes. Include any text you can read."},
                                        {"type": "image_url", "image_url": {"url": image_data_url}},
                                    ],
                                }]
                                storage_description = await self.llm.chat_completion(desc_prompt, max_tokens=300)
                                logger.info("Generated archival description: %s...", storage_description[:100])
                            except Exception as e:
                                logger.warning("gemma12b vision failed for archival: %s", e)
                                storage_description = "Image (vision model error)"
                        elif image_data_url and self.vision_llm:
                            try:
                                desc_prompt = [{
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": "Describe this image in detail for archival purposes. Include any text you can read."},
                                        {"type": "image_url", "image_url": {"url": image_data_url}},
                                    ],
                                }]
                                storage_description = await self.vision_llm.chat_completion(desc_prompt, max_tokens=300)
                                logger.info("Generated archival description (SmolVLM): %s...", storage_description[:100])
                            except Exception as e:
                                logger.warning("SmolVLM not available for archival: %s", e)
                                storage_description = "Image (vision model error)"
                        elif image_data_url:
                            storage_description = "Image (vision model not loaded)"
                        else:
                            storage_description = "Image (could not download)"

                        storage_context = f"{cleaned_content}\n[Image Content: {storage_description}]"
                        if image_bytes:
                            self.visual_memory.store_image_from_bytes(
                                image_bytes=image_bytes,
                                image_url=attachment.url,
                                user_id=user_id,
                                username=user_name,
                                channel_id=channel_id,
                                context_text=storage_context,
                            )
                        else:
                            self.visual_memory.store_image_memory(
                                image_url=attachment.url,
                                user_id=user_id,
                                username=user_name,
                                channel_id=channel_id,
                                context_text=storage_context,
                            )

            # Update user profile
            self.memory.upsert_user(user_id, user_name, user_name)
            self.memory.update_user_activity(user_id, len(cleaned_content))

            sentiment = self.analyzer.polarity_scores(cleaned_content)
            emotional_tone = self._get_emotional_tone(sentiment["compound"])
            participants = list(set([str(m.author.id) for m in self.current_batch] + [user_id]))

            if hasattr(self.memory, "add_memory_enhanced"):
                # ── Perception: analyze before storage ────────────────────
                perception = self._perceive_message(
                    cleaned_content, user_id, user_name
                )

                self.memory.add_memory_enhanced(
                    content=cleaned_content,
                    user_id=user_id,
                    username=user_name,
                    channel_id=channel_id,
                    participants=participants,
                    emotional_tone=emotional_tone,
                    importance=0.8 if perception.is_objective else 0.3,
                    memory_type='evidence' if perception.is_objective else 'utterance',
                    source_message_id=str(message.id),
                    speech_act=perception.speech_act,
                    is_objective=perception.is_objective,
                    evidence_class=perception.evidence_class,
                    extracted_facts=[
                        f['content'] for f in perception.extracted_facts
                    ],
                )

                # ── Store extracted facts in FactStore ────────────────────
                for fact in perception.extracted_facts:
                    try:
                        self.memory.add_fact(
                            content=fact['content'],
                            category=fact['category'],
                            confidence=fact['confidence'],
                            source_message_id=str(message.id),
                            source_user_id=user_id,
                            source_username=user_name,
                            source_type=fact['source_type'],
                        )
                    except Exception as e:
                        logger.debug("Could not store fact: %s", e)

                # ── Infer beliefs from updated facts ───────────────────────
                if perception.extracted_facts:
                    try:
                        beliefs = self.memory.infer_beliefs_from_facts(
                            query=cleaned_content
                        )
                        for belief in beliefs:
                            self.memory.add_or_update_belief(
                                content=belief['content'],
                                category=belief['category'],
                                confidence=belief['confidence'],
                                supporting_fact_ids=belief.get('supporting_fact_ids'),
                                contradicting_fact_ids=belief.get('contradicting_fact_ids'),
                                evidence_count=belief.get('evidence_count', 1),
                                claim_count=belief.get('claim_count', 0),
                            )
                    except Exception as e:
                        logger.debug("Could not infer beliefs: %s", e)
            else:
                raise ValueError("Memory system does not support enhanced memory addition")

            detected_traits = self._analyze_personality(user_id, cleaned_content)
            self.personality.update_from_conversation(
                conversation_mood=emotional_tone,
                user_traits=detected_traits,
                time_of_day=datetime.now().hour,
            )

            try:
                self.memory.store_recent_message(
                    user_id=user_id,
                    username=user_name,
                    channel_id=channel_id,
                    content=cleaned_content,
                    message_id=str(message.id),
                    timestamp=message.created_at,
                )
            except Exception as e:
                logger.debug("Could not store recent message: %s", e)

            try:
                self.memory.update_relationship(str(self.client.user.id), user_id)
            except Exception as e:
                logger.debug("Could not update relationship: %s", e)

            self.memory.log_activity(user_id, channel_id, len(content), sentiment["compound"])

            self.current_batch.append(message)
            self.stats["messages_processed"] += 1

            bot_mentioned = self.client.user.mentioned_in(message)
            if bot_mentioned:
                logger.info("Bot mentioned - responding immediately")
                if self.flush_task and not self.flush_task.done():
                    self.flush_task.cancel()
                await self._flush_batch_with_enhanced_context(immediate=True)
            else:
                if self.flush_task and not self.flush_task.done():
                    self.flush_task.cancel()
                self.flush_task = asyncio.create_task(self._schedule_flush())

        except Exception as e:
            self.stats["errors"] += 1
            logger.exception("Error processing message: %s", e)

    async def _schedule_flush(self) -> None:
        """Schedule batch flush with timeout"""
        try:
            await asyncio.sleep(self.sub_timeout)
            await self._flush_batch_with_enhanced_context(immediate=False)
        except asyncio.CancelledError:
            pass

    async def _flush_batch_with_enhanced_context(self, immediate: bool) -> None:
        """Flush the current message batch through MessagePipeline."""
        batch = self.current_batch
        self.current_batch = []
        self.flush_task = None

        if not batch:
            return

        channel = batch[0].channel
        trigger_message = batch[-1]  # Last message is the one that triggered the flush

        try:
            from serin.state.message_context import MessageContext
            from serin.pipeline.act.pipeline import MessagePipeline

            # Build context once if pipeline not yet built
            if self.pipeline is None:
                from serin.pipeline.think.response_generator import get_response_natural
                from serin.state.thinking_filter import get_thinking_filter

                self.pipeline = MessagePipeline.build(
                    response_controller=self.response_controller,
                    memory_system=self.memory,
                    retrieval=self.context_builder,
                    personality=self.bot_personality,
                    temporal_context=self.enhanced_context,
                    response_generator=get_response_natural,
                    thinking_filter=get_thinking_filter(),
                    mention_translator=self.mention_translator,
                    mood_state=self.personality,
                )

            ctx = MessageContext(
                message=trigger_message,
                user_id=str(trigger_message.author.id),
                username=trigger_message.author.display_name,
                channel_id=str(trigger_message.channel.id),
                guild_id=str(trigger_message.guild.id) if trigger_message.guild else None,
                raw_content=trigger_message.content,
                metadata={
                    "batch_size": len(batch),
                    "bot_mentioned": immediate,
                    "pending_visual_contexts": self.pending_visual_contexts,
                    "abort_flag": self.current_state.get("abort_flag", False),
                },
            )

            ctx = await self.pipeline.process(ctx)

            if ctx.final_response:
                self.last_bot_response = ctx.final_response
                self.last_bot_response_channel = str(channel.id)
                self.stats["responses_generated"] += 1

            self.update_state(status="IDLE")

        except Exception as e:
            self.stats["errors"] += 1
            logger.exception("Error in enhanced batch flush: %s", e)
            try:
                await channel.send("Sorry, had a brain fart. Try again?")
            except Exception:
                pass

    _EVIDENCE_PATTERNS = [
        r'\|.*\|.*\|',        # Board states (pipes with separators)
        r'https?://\S+',       # URLs
        r'```[\s\S]*?```',     # Code blocks
        r'"[^"]{20,}"',        # Long quotes (20+ chars)
    ]

    def _detect_evidence(self, content: str) -> bool:
        """Detect if content contains factual evidence (boards, links, code, quotes)."""
        for pattern in self._EVIDENCE_PATTERNS:
            if re.search(pattern, content):
                return True
        return False

    def _perceive_message(self, content: str, user_id: str, username: str) -> PerceptionResult:
        """Analyze message before storage — classify, extract evidence, claims, facts.

        This is the perception layer. It transforms raw text into structured
        information so the memory system stores *what the message contains*
        rather than just *the text itself*.
        """
        content_lower = content.lower()
        result = PerceptionResult(speech_act='statement', is_objective=False)

        # ── 1. Classify speech act ────────────────────────────────────────
        # Question?
        if content.strip().endswith('?'):
            result.speech_act = 'question'
            result.is_objective = True  # Questions seek truth

        # Joke?
        if any(m in content_lower for m in _JOKE_MARKERS):
            result.speech_act = 'joke'
            result.is_objective = False

        # Sarcasm?
        if any(m in content_lower for m in _SARCASM_MARKERS):
            result.speech_act = 'sarcasm'
            result.is_objective = False

        # Agreement?
        if re.search(r'^(yeah|yes|right|true|agreed|exactly|correct)\b', content_lower):
            result.speech_act = 'agreement'

        # Disagreement?
        if re.search(r'^(no|nah|nope|wrong|nah)\b', content_lower) or \
           re.search(r'\b(?:actually|but)\s+(?:no|that\'?s?\s+wrong|you\'?re?\s+wrong)\b', content_lower):
            result.speech_act = 'disagreement'

        # Evidence?
        if self._detect_evidence(content):
            result.speech_act = 'evidence'
            result.is_objective = True

        # Instruction?
        if re.search(r'^(?:tell|show|explain|describe|list|give|do|say)\b', content_lower):
            result.speech_act = 'instruction'

        # ── 2. Extract evidence blocks with class ─────────────────────────
        # Board states: |...|...|...| across multiple lines
        board_match = re.search(r'(\|.*?\|.*?\|[^\n]*(\n\|.*?\|.*?\|[^\n]*)*)', content, re.DOTALL)
        if board_match:
            result.evidence_blocks.append({
                'type': 'board',
                'content': board_match.group(1).strip(),
                'evidence_class': 'world',
                'metadata': {},
            })

        # URLs
        url_matches = re.findall(r'https?://\S+', content)
        for url in url_matches:
            result.evidence_blocks.append({
                'type': 'url',
                'content': url,
                'evidence_class': 'world',
                'metadata': {},
            })

        # Code blocks
        code_match = re.search(r'```(\w*)\n([\s\S]*?)```', content)
        if code_match:
            result.evidence_blocks.append({
                'type': 'code',
                'content': code_match.group(2).strip(),
                'evidence_class': 'world',
                'metadata': {'language': code_match.group(1)},
            })

        # Long quotes
        quote_matches = re.findall(r'"([^"]{20,})"', content)
        for quote in quote_matches:
            result.evidence_blocks.append({
                'type': 'quote',
                'content': quote,
                'evidence_class': 'world',
                'metadata': {},
            })

        # ── 3. Extract claims (subjective assertions) ─────────────────────
        for pattern, category in _CLAIM_PATTERNS:
            match = re.search(pattern, content_lower)
            if match:
                result.claims.append({
                    'claimant': username or user_id,
                    'content': match.group(0),
                    'category': category,
                })

        # General first-person assertions
        i_assertions = re.findall(r'\bI\s+(?:am|was|have|think|believe|feel|know|can|could|will|would)\s+(.+?)(?:\.|,|$)', content)
        for assertion in i_assertions:
            result.claims.append({
                'claimant': username or user_id,
                'content': f"I {assertion.strip()}",
                'category': 'self_statement',
            })

        # General third-person about bot
        you_assertions = re.findall(r'\byou\'(?:re|ve|are|were)\s+(.+?)(?:\.|,|$)', content_lower)
        for assertion in you_assertions:
            result.claims.append({
                'claimant': username or user_id,
                'content': f"you're {assertion.strip()}",
                'category': 'other_directed',
            })

        # ── 4. Extract observations (verifiable content) ──────────────────
        # Board states are always observations
        for block in result.evidence_blocks:
            if block['type'] == 'board':
                result.observations.append(
                    f"The board shows: {block['content']}"
                )
                # Board states become high-confidence facts
                result.extracted_facts.append({
                    'content': f"The board shows: {block['content']}",
                    'category': 'board_state',
                    'confidence': 0.9,
                    'source_type': 'evidence_extracted',
                })
            elif block['type'] == 'url':
                result.observations.append(f"A reference was shared: {block['content']}")
                result.extracted_facts.append({
                    'content': f"A reference was linked: {block['content']}",
                    'category': 'reference',
                    'confidence': 0.7,
                    'source_type': 'evidence_extracted',
                })
            elif block['type'] == 'code':
                result.observations.append(f"Code was shared: {block['content'][:100]}")
                result.extracted_facts.append({
                    'content': f"Code shown: {block['content'][:200]}",
                    'category': 'code',
                    'confidence': 0.8,
                    'source_type': 'evidence_extracted',
                })

        # If the user is making claims about who won or lost, extract
        # the *claim* as an observation of speech (not a fact about the game)
        for claim in result.claims:
            result.observations.append(
                f"{claim['claimant']} claims: {claim['content']}"
            )
            # Claims become low-confidence facts — the *claim itself* is a fact
            # of speech, but the *content* is not verified
            if claim['category'] in ('win_claim', 'loss_attribution', 'self_assessment'):
                result.extracted_facts.append({
                    'content': f"{claim['claimant']} claimed: {claim['content']}",
                    'category': 'speech_claim',
                    'confidence': 0.2,
                    'source_type': 'user_claim',
                })

        # ── 5. Derive facts from evidence — board parsing + rule application ──
        for block in result.evidence_blocks:
            if block['type'] == 'board':
                derived = self._derive_from_board(block['content'])
                for fact in derived:
                    result.extracted_facts.append(fact)
                    result.observations.append(
                        f"Derived: {fact['content']}"
                    )

        # ── 7. Determine evidence_class ──────────────────────────────────
        if result.evidence_blocks:
            result.evidence_class = 'world'
        elif result.claims:
            result.evidence_class = 'conversation'
        else:
            # Check for highly emotional content
            sentiment = self.analyzer.polarity_scores(content)
            if abs(sentiment['compound']) > 0.7:
                result.evidence_class = 'social'

        # ── 8. Determine intent ───────────────────────────────────────────
        if result.speech_act == 'question':
            result.intent = 'question'
        elif any(m in content_lower for m in ['why', 'how', 'explain', 'what']):
            result.intent = 'seek_explanation'
        elif any(m in content_lower for m in ['am i right', 'did i', 'check', 'rate']):
            result.intent = 'seek_validation'
        elif result.speech_act == 'joke':
            result.intent = 'seek_joke'
        elif result.speech_act == 'disagreement':
            result.intent = 'seek_argument'
        elif result.speech_act == 'instruction':
            result.intent = 'command'
        elif result.speech_act in ('agreement', 'statement'):
            result.intent = 'social'

        # ── 9. Determine objectivity ──────────────────────────────────────
        if result.evidence_blocks:
            result.is_objective = True
        elif result.claims:
            result.is_objective = False

        return result

    def _parse_board(self, board_text: str) -> Optional[list[list[str]]]:
        """Parse a pipe-delimited board into a 2D grid.

        Handles:
          Connect 4: 6 rows × 7 cols, |X|O| | | | | |
          Tic-tac-toe: 3 rows × 3 cols, |X|O|X| or |X|O|X|
        Returns None if not parseable.
        """
        lines = [l.strip() for l in board_text.split('\n') if l.strip()]
        if not lines:
            return None

        grid = []
        for line in lines:
            # Strip leading/trailing pipes, split on |
            cells = [c.strip() for c in line.strip('|').split('|')]
            if not cells:
                continue
            grid.append(cells)

        if len(grid) < 2:
            return None

        # Validate: all rows same width
        widths = set(len(r) for r in grid)
        if len(widths) > 1:
            return None

        return grid

    def _derive_from_board(self, board_text: str) -> list[Dict]:
        """Derive game-level facts from a parsed board state.

        Applies known game rules:
          - Connect 4: 4 in a row → win condition met
          - Tic-tac-toe: 3 in a row → win condition met
        Returns list of derived facts with confidence and category.
        """
        grid = self._parse_board(board_text)
        if not grid:
            return []

        derived = []
        rows, cols = len(grid), len(grid[0])

        # Detect game type
        is_connect4 = rows == 6 and cols == 7
        is_tictactoe = rows == 3 and cols == 3
        win_length = 4 if is_connect4 else (3 if is_tictactoe else 0)

        if win_length == 0:
            # Generic board: still store it, but can't derive much
            derived.append({
                'content': f"A {rows}×{cols} board was shown",
                'category': 'board_state',
                'confidence': 0.9,
                'source_type': 'derived',
            })
            return derived

        # Check for pieces
        piece_positions = {'.': [], '_': []}
        for r in range(rows):
            for c in range(cols):
                cell = grid[r][c]
                if cell and cell not in ('.', '_', '', ' '):
                    if cell not in piece_positions:
                        piece_positions[cell] = []
                    piece_positions[cell].append((r, c))

        # Check for wins in all directions
        for piece, positions in piece_positions.items():
            pos_set = set(positions)

            # Check horizontal
            for r in range(rows):
                for c in range(cols - win_length + 1):
                    if all((r, c + i) in pos_set for i in range(win_length)):
                        derived.append({
                            'content': f"{piece} has {win_length} in a row horizontally at row {r+1} (columns {c+1}-{c+win_length})",
                            'category': 'game_result',
                            'confidence': 0.95,
                            'source_type': 'derived',
                        })

            # Check vertical
            for r in range(rows - win_length + 1):
                for c in range(cols):
                    if all((r + i, c) in pos_set for i in range(win_length)):
                        derived.append({
                            'content': f"{piece} has {win_length} in a row vertically at column {c+1} (rows {r+1}-{r+win_length})",
                            'category': 'game_result',
                            'confidence': 0.95,
                            'source_type': 'derived',
                        })

            # Check diagonal (down-right)
            for r in range(rows - win_length + 1):
                for c in range(cols - win_length + 1):
                    if all((r + i, c + i) in pos_set for i in range(win_length)):
                        derived.append({
                            'content': f"{piece} has {win_length} in a row diagonally (down-right) from ({r+1},{c+1})",
                            'category': 'game_result',
                            'confidence': 0.95,
                            'source_type': 'derived',
                        })

            # Check diagonal (down-left)
            for r in range(rows - win_length + 1):
                for c in range(win_length - 1, cols):
                    if all((r + i, c - i) in pos_set for i in range(win_length)):
                        derived.append({
                            'content': f"{piece} has {win_length} in a row diagonally (down-left) from ({r+1},{c+1})",
                            'category': 'game_result',
                            'confidence': 0.95,
                            'source_type': 'derived',
                        })

        if not derived:
            derived.append({
                'content': f"Board state captured ({rows}×{cols}) — no win condition detected yet",
                'category': 'board_state',
                'confidence': 0.7,
                'source_type': 'derived',
            })

        return derived

    def _analyze_personality(self, user_id: str, content: str) -> list[str]:
        """Analyze message and update personality traits. Returns detected traits."""
        traits = []
        interests = []
        content_lower = content.lower()

        if any(w in content_lower for w in [            "lol", "haha", "lmao"]):
            traits.append("humorous")
        if any(w in content_lower for w in ["thanks", "please", "sorry"]):
            traits.append("polite")
        if len(content) > 200:
            traits.append("verbose")
        elif len(content) < 20:
            traits.append("concise")
        if content.count("!") > 2:
            traits.append("enthusiastic")

        interest_keywords = {
            "gaming": ["game", "play", "steam", "xbox", "ps5"],
            "anime": ["anime", "manga", "weeb"],
            "music": ["song", "music", "band", "album"],
            "tech": ["code", "programming", "ai", "computer"],
            "art": ["draw", "art", "paint", "sketch"],
        }
        for interest, keywords in interest_keywords.items():
            if any(kw in content_lower for kw in keywords):
                interests.append(interest)

        if traits or interests:
            self.memory.update_user_traits(user_id, traits, interests)

        return traits

    def _get_emotional_tone(self, sentiment_score: float) -> str:
        """Convert sentiment score to emotional tone"""
        if sentiment_score > 0.5:
            return "happy"
        elif sentiment_score > 0.2:
            return "positive"
        elif sentiment_score < -0.5:
            return "sad"
        elif sentiment_score < -0.2:
            return "negative"
        return "neutral"

    def _detect_topic(self, content: str) -> Optional[str]:
        """Simple topic detection"""
        content_lower = content.lower()
        topics = {
            "gaming": ["game", "gaming", "play", "steam", "xbox", "ps5", "nintendo"],
            "anime": ["anime", "manga", "weeb"],
            "music": ["song", "music", "band", "album", "spotify"],
            "food": ["food", "eat", "cooking", "recipe", "restaurant"],
            "work": ["work", "job", "boss", "office", "meeting"],
            "school": ["school", "class", "homework", "exam", "teacher"],
            "movies": ["movie", "film", "cinema", "netflix"],
            "sports": ["sport", "football", "basketball", "soccer", "gym"],
        }
        for topic, keywords in topics.items():
            if any(kw in content_lower for kw in keywords):
                return topic
        return None

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user profile"""
        return self.memory.get_user_profile(user_id)

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        stats = self.memory.get_stats()
        stats["manager_stats"] = self.stats
        stats["enhanced_context"] = {
            "improvements_used": self.stats["context_improvements"],
            "current_source": "enhanced",
        }
        if hasattr(self.memory, "qdrant_client"):
            stats["memory_system"] = "Qdrant"
            stats["memory_features"] = {
                "hybrid_search": True,
                "bm25_available": hasattr(self.memory, "bm25_index"),
                "embedding_available": hasattr(self.memory, "embedding_model"),
            }
        return stats


# Alias for backward compatibility with discord_bot.py
MessageManagerV3 = EnhancedMessageManagerV3
