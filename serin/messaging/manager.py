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
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import discord
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from serin.core.logger import logger
from serin.memory.qdrant import QdrantMemorySystem
from serin.memory.context import EnhancedMemoryContext, ImprovedSystemPrompt
from serin.messaging.response_controller import ResponseController, PersonalityState
from serin.messaging.response_generator import get_response_natural
from serin.personality.bot_personality import BotPersonality
from serin.personality.conversation_analyzer import ConversationAnalyzer
from serin.messaging.correction_handler import CorrectionDetector, MemoryCorrector, get_correction_acknowledgment
from serin.active_search import ActiveSearch
from serin.messaging.context_builder import ConversationContextBuilder
from serin.messaging.mention_translator import MentionTranslator
from serin.utils.debug_logger import log_message, log_correction
from models.factory import get_model_connector


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
        from voice.tracker import VoiceTracker
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
            from serin.visual_memory_system import VisualMemorySystem
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
        from voice.decider import VoiceActionDecider
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
                from serin.messaging.response_generator import llama as llm_connector
                if llm_connector is None:
                    from serin.messaging.response_generator import initialize_llama
                    await initialize_llama()
                    from serin.messaging.response_generator import llama as llm_connector
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
                self.memory.add_memory_enhanced(
                    content=cleaned_content,
                    user_id=user_id,
                    username=user_name,
                    channel_id=channel_id,
                    participants=participants,
                    emotional_tone=emotional_tone,
                    importance=0.5,
                    source_message_id=str(message.id),
                )
            else:
                raise ValueError("Memory system does not support enhanced memory addition")

            self._analyze_personality(user_id, cleaned_content)

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
            from serin.messaging.context import MessageContext
            from serin.messaging.pipeline import MessagePipeline

            # Build context once if pipeline not yet built
            if self.pipeline is None:
                from serin.messaging.response_generator import get_response_natural
                from serin.utils.thinking_filter import get_thinking_filter

                self.pipeline = MessagePipeline.build(
                    response_controller=self.response_controller,
                    memory_system=self.memory,
                    retrieval=self.context_builder,
                    personality=self.bot_personality,
                    temporal_context=self.enhanced_context,
                    response_generator=get_response_natural,
                    thinking_filter=get_thinking_filter(),
                    mention_translator=self.mention_translator,
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

    def _analyze_personality(self, user_id: str, content: str) -> None:
        """Analyze message and update personality traits"""
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
