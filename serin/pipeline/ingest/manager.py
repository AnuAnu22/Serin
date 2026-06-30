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
from serin.pipeline.think.response_controller import ResponseController
from serin.pipeline.think.personality_state import PersonalityState
from serin.pipeline.think.response_generator import get_response_natural
from serin.pipeline.perceive.bot_personality import BotPersonality
from serin.pipeline.perceive.conversation_analyzer import ConversationAnalyzer
from serin.pipeline.ingest.correction_handler import CorrectionDetector, MemoryCorrector, get_correction_acknowledgment
from serin.pipeline.perceive.active_search import ActiveSearch
from serin.pipeline.ingest.context_builder import ConversationContextBuilder
from serin.pipeline.ingest.mention_translator import MentionTranslator
from serin.config.debug_logger import log_message, log_correction
from serin.state.model_system.factory import get_model_connector


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
