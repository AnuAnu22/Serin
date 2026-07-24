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
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import discord
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_1_ingest_context.d4_1_context_builder import (
    ConversationContextBuilder,
)
from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_1_ingest_context.d4_3_mention_translator import (
    MentionTranslator,
)
from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_3_correction_handler import (
    CorrectionDetector,
    MemoryCorrector,
)
from serin.d1_1_pipeline_flow.d2_3_flow_perceive.d3_2_bot_personality import (
    BotPersonality,
)
from serin.d1_1_pipeline_flow.d2_3_flow_perceive.d3_3_conversation_analyzer import (
    ConversationAnalyzer,
)
from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_2_remember_knowledge.d4_2_memory_context import (
    EnhancedMemoryContext,
    ImprovedSystemPrompt,
)
from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_3_remember_qdrant import (
    QdrantMemorySystem,
)
from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_1_think_personality.d4_2_personality_state import (
    PersonalityState,
)
from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_2_response_controller import (
    ResponseController,
)
from serin.d1_3_state_core.d2_3_model_system.d3_3_system_factory import (
    get_model_connector,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_1_dynamics_engine import (
    ConversationDynamicsEngine,
)
from serin.d1_4_config_base.d2_1_base_config import config
from serin.d1_4_config_base.d2_3_logger import logger


@dataclass
class EnhancedMessageManagerV3:
    """
    Message manager that handles pre-processing (corrections, vision, batching)
    and delegates core response generation to MessagePipeline.
    """

    def __init__(
        self,
        client: discord.Client,
        mention_translator: MentionTranslator,
        memory_system: QdrantMemorySystem | None = None,
        sub_timeout: int = 1,
        voice_output_manager: Any = None,
    ) -> None:
        self.client = client
        self.mention_translator = mention_translator
        self.current_batch: list[discord.Message] = []
        self.flush_task: asyncio.Task[None] | None = None
        self.sub_timeout = sub_timeout
        self.voice_output_manager = voice_output_manager

        # TIER 8: Observable Brain State
        self.current_state: dict[str, Any] = {
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

        # Initialize LLM connector for image analysis + fact extraction
        self.llm = get_model_connector()
        try:
            self.llm.load_model()
        except Exception:
            logger.debug("LLM connector will load in background")

        # Initialize separate vision model (SmolVLM) if enabled
        self.vision_llm: Any = None
        supports_vision = config.LLM_SUPPORTS_VISION
        vision_model = config.VISION_MODEL
        if supports_vision:
            try:
                from serin.d1_3_state_core.d2_3_model_system.d3_2_system_connector import (
                    LLMConnector,
                )
                self.vision_llm = LLMConnector(model_name=vision_model)
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
        try:
            self.personality.load_from_db(self.memory.conn)
        except Exception as exc:
            logger.debug("Could not load personality from DB: %s", exc)

        # TIER 3: Advanced features
        self.conversation_analyzer = ConversationAnalyzer()
        self.bot_personality = BotPersonality()

        # TIER 5: Correction + Voice systems
        self.correction_detector = CorrectionDetector()
        self.memory_corrector = MemoryCorrector(self.memory)
        from serin.d1_3_state_core.d2_4_core_voice.d3_4_voice_tracker import (
            VoiceTracker,
        )
        self.voice_tracker = VoiceTracker(self.memory)

        # Dynamics engine for physics-based conversation state
        self.dynamics_engine = ConversationDynamicsEngine()

        # Pipeline instance (set externally by discord_bot.py after building)
        self.pipeline: Any = None

        # Voice action decider
        self.voice_action_decider: Any = None
        self.voice_action_callback: Any = None

        # Visual Cortex
        self.visual_memory: VisualMemorySystem | None = None
        if hasattr(self.memory, "qdrant_client") and self.memory.qdrant_client:
            from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_2_core_vision.d5_1_visual_memory import (
                VisualMemorySystem,
            )
            self.visual_memory = VisualMemorySystem(self.memory.qdrant_client)
        else:
            self.visual_memory = None
            logger.warning("Visual Cortex disabled (requires Qdrant)")

        self.last_bot_response: str | None = None
        self.last_bot_response_channel: str | None = None
        self.system_prompt = ImprovedSystemPrompt.get_enhanced_system_prompt()

        self.stats: dict[str, int] = {
            "messages_processed": 0,
            "responses_generated": 0,
            "corrections_detected": 0,
            "errors": 0,
            "context_improvements": 0,
            "voice_responses": 0,
        }

        # Cache for visual contexts between processing and flushing
        self.pending_visual_contexts: dict[int, str] = {}

        # Voice pipeline (set externally if available)
        self.voice_pipeline: Any = None

        # Voice Action Decider
        from serin.d1_3_state_core.d2_4_core_voice.d3_2_voice_decider import (
            VoiceActionDecider,
        )
        try:
            va_connector = get_model_connector(model_name=config.LLM_MODEL)
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

    def update_state(self, status: str, prompt: str | None = None, user_message: str | None = None) -> None:
        """Update the observable brain state"""
        self.current_state["status"] = status
        self.current_state["last_activity"] = datetime.now().isoformat()
        if prompt is not None:
            self.current_state["current_prompt"] = prompt
        if user_message is not None:
            self.current_state["current_user_message"] = user_message

    async def process_message(self, message: discord.Message) -> None:
        """Process incoming message via MessagePipeline (backwards compatibility)."""
        if self.pipeline is None:
            from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
                MessagePipeline,
            )
            from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator import (
                get_response_natural,
            )
            from serin.d1_3_state_core.d2_3_model_system.d3_5_thinking_filter import (
                get_thinking_filter,
            )
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
                client=self.client,
                small_llm=self.llm,
                dynamics_engine=self.dynamics_engine,
            )

        # Process image attachments — store for LLM vision, fire description in background
        image_description = ""
        if message.attachments:
            import base64
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    logger.info("Processing image from %s...", message.author.display_name)
                    try:
                        image_bytes = await attachment.read()
                        if image_bytes:
                            mime = attachment.content_type or "image/jpeg"
                            b64 = base64.b64encode(image_bytes).decode("utf-8")
                            image_data_url = f"data:{mime};base64,{b64}"
                            self.pending_visual_contexts[message.id] = image_data_url
                            logger.info("Stored image for LLM vision (%s bytes)", len(image_bytes))

                            # Fire vision description in background — don't block the response
                            # Use semaphore to limit parallel vision calls (max 2)
                            if not hasattr(self, '_vision_semaphore'):
                                self._vision_semaphore = asyncio.Semaphore(2)

                            async def _rate_limited_describe() -> None:
                                async with self._vision_semaphore:
                                    await self._describe_image_background(message, image_data_url, attachment.filename)
                                    await asyncio.sleep(0.3)  # small delay between calls

                            asyncio.create_task(_rate_limited_describe())
                            image_description = f"an image ({attachment.filename})"  # placeholder until background completes
                        else:
                            self.pending_visual_contexts[message.id] = attachment.url
                            image_description = f"an image ({attachment.filename})"
                    except Exception as e:
                        logger.warning("Failed to process image: %s", e)
                        self.pending_visual_contexts[message.id] = attachment.url
                        image_description = "an image"

        # Store message in recent_messages for context
        message_content = message.content
        if image_description:
            message_content = f"{message.content} [Image: {image_description}]" if message.content else f"[Image: {image_description}]"

        try:
            self.memory.store_recent_message(
                user_id=str(message.author.id),
                username=message.author.display_name,
                channel_id=str(message.channel.id),
                content=message_content,
                message_id=str(message.id),
                timestamp=message.created_at,
            )
        except Exception as e:
            logger.debug("Failed to store recent message: %s", e)

        from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
            MessageContext,
        )

        is_mentioned = bool(
            message.guild and message.guild.me and message.guild.me in message.mentions
        ) if message.guild else False

        ctx = MessageContext(
            message=message,
            user_id=str(message.author.id),
            username=message.author.display_name,
            channel_id=str(message.channel.id),
            guild_id=str(message.guild.id) if message.guild else None,
            raw_content=message.content,
            is_mentioned=is_mentioned,
            metadata={
                "pending_visual_contexts": self.pending_visual_contexts,
                "abort_flag": self.current_state.get("abort_flag", False),
            },
        )
        ctx = await self.pipeline.process(ctx)
        if ctx.final_response:
            self.last_bot_response = ctx.final_response
            self.last_bot_response_channel = str(message.channel.id)
            self.stats["responses_generated"] += 1

        await self._check_voice_action(ctx)

    async def _check_voice_action(self, ctx: Any) -> None:
        if not self.voice_action_decider or not self.voice_action_callback:
            return
        decision = await self.voice_action_decider.decide(
            user_message=ctx.raw_content,
            context=ctx.final_response or "",
            personality_state={
                "energy": getattr(self.personality, "energy_level", 0.5),
                "sass": getattr(self.personality, "sass_level", 0.5),
            },
        )
        action = decision.get("action")
        if action in ("join", "leave"):
            guild_id = int(ctx.guild_id) if ctx.guild_id else 0
            await self.voice_action_callback(decision, ctx.user_id, guild_id)

    async def _describe_image_background(self, message: Any, image_data_url: str, filename: str) -> None:
        """Generate image description in background, then update SQLite record."""
        try:
            from typing import cast
            vision_prompt = cast(list[dict[str, str]], [{"role": "user", "content": [
                {"type": "text", "text": "Describe this image in 1-2 sentences. What is it? Be specific about what you see."},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ]}])
            description = await self.llm.chat_completion(vision_prompt, max_tokens=100)
            logger.info("Image description (background): %s", description[:80])

            # Update the SQLite record with actual description
            original = message.content or ""
            updated_content = f"{original} [Image: {description}]" if original else f"[Image: {description}]"
            try:
                cursor = self.memory.conn.cursor()
                cursor.execute(
                    "UPDATE recent_messages SET content = ? WHERE message_id = ?",
                    (updated_content, str(message.id)),
                )
                self.memory.conn.commit()
            except Exception as e:
                logger.debug("Failed to update image description in SQLite: %s", e)

        except Exception as e:
            logger.exception("Background image description failed: %s", e)

    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """Get user profile from memory"""
        return self.memory.get_user_profile(user_id)

    def get_memory_stats(self) -> dict[str, Any]:
        """Get memory statistics"""
        stats = self.memory.get_stats()
        stats["manager_stats"] = dict(self.stats)
        return stats

    def abort_current_generation(self) -> None:
        """Signal to abort current generation"""
        logger.warning("Abort signal received!")
        self.current_state["abort_flag"] = True
        self.current_state["status"] = "ABORTING"

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
            from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
                MessagePipeline,
            )
            from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
                MessageContext,
            )

            # Build context once if pipeline not yet built
            if self.pipeline is None:
                from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator import (
                    get_response_natural,
                )
                from serin.d1_3_state_core.d2_3_model_system.d3_5_thinking_filter import (
                    get_thinking_filter,
                )

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
                    client=self.client,
                    small_llm=self.llm,
                    dynamics_engine=self.dynamics_engine,
                )

            is_mentioned = bool(
                trigger_message.guild and trigger_message.guild.me
                and trigger_message.guild.me in trigger_message.mentions
            ) if trigger_message.guild else False

            ctx = MessageContext(
                message=trigger_message,
                user_id=str(trigger_message.author.id),
                username=trigger_message.author.display_name,
                channel_id=str(trigger_message.channel.id),
                guild_id=str(trigger_message.guild.id) if trigger_message.guild else None,
                raw_content=trigger_message.content,
                is_mentioned=is_mentioned,
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

            await self._check_voice_action(ctx)

            self.update_state(status="IDLE")

        except Exception as e:
            self.stats["errors"] += 1
            logger.exception("Error in enhanced batch flush: %s", e)
            try:
                await channel.send("Sorry, had a brain fart. Try again?")
            except Exception:
                logger.exception("Failed to send error recovery message to channel")

    _EVIDENCE_PATTERNS = [
        r'\|.*\|.*\|',        # Board states (pipes with separators)
        r'https?://\S+',       # URLs
        r'```[\s\S]*?```',     # Code blocks
        r'"[^"]{20,}"',        # Long quotes (20+ chars)
    ]
