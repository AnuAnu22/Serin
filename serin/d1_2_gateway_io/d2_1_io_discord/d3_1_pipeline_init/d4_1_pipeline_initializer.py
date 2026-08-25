"""
Pipeline Initializer
--------------------
Encapsulates all Discord bot pipeline initialization logic.
Extracted from __init__.py to keep files under 500 lines.
"""
# --- Imports ---
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

import serin.d1_2_gateway_io.d2_1_io_discord.d3_2_discord_bot as bot_module
from serin.d1_1_serin_di import (
    build_message_pipeline,
    create_mention_translator,
    create_message_crawler,
    create_message_manager,
    create_qdrant_memory_system,
    create_sync_monitor,
    get_llama_connector,
    get_response_generator_fn,
    get_small_llm_connector,
    get_thinking_filter_instance,
    init_root,
    initialize_llama_connector,
    set_crawler,
    set_mention_translator,
    set_message_manager,
    set_qdrant,
)
from serin.d1_2_gateway_io.d2_1_io_discord.d3_2_discord_bot import (
    db_protector,
    init_database_protection,
    stats,
)
from serin.d1_2_gateway_io.d2_4_io_di import get_logger
from serin.d1_4_config_base.d2_1_base_config import config

# --- Types ---
# (none)

# --- Constants ---
# (none)

# --- Entry ---


class PipelineInitializer:
    """Encapsulates all Discord bot pipeline initialization logic."""

    def __init__(self, client: Any, bot_state: dict[str, Any]) -> None:
        self.client = client
        self.bot_state = bot_state
        self.message_manager: Any | None = None
        self.background_processor: Any | None = None
        self.passive_monitor: Any | None = None
        self.message_crawler: Any | None = None
        self.voice_listener: Any | None = None
        self.audio_processor: Any | None = None
        self.voice_pipeline: Any | None = None
        self.tts_engine: Any | None = None
        self.voice_output_manager: Any | None = None
        self.voice_manager: Any | None = None
        self.voice_behavior_manager: Any | None = None

# --- Core ---
    async def initialize(self) -> None:
        """Initialize all subsystems."""
        mention_translator_obj, voice_available = await self._init_mention_translator()
        memory_system = await self._init_database_and_memory()
        self.background_processor, self.passive_monitor, self.message_crawler = await self._init_background_processors(memory_system, mention_translator_obj)
        self.voice_listener, self.audio_processor, self.voice_pipeline, self.tts_engine, self.voice_output_manager, self.voice_manager = await self._init_voice_system(memory_system, mention_translator_obj, voice_available)
        self.message_manager = await self._init_message_manager(mention_translator_obj, memory_system, self.voice_pipeline, self.voice_output_manager)

        asyncio.create_task(self._backfill_recent_images())
        try:
            await asyncio.to_thread(db_protector.create_backup, "startup", True)
        except Exception as e:
            get_logger().warning(f"Startup backup failed: {e}")

        await self._build_pipeline(memory_system, mention_translator_obj)
        self.voice_behavior_manager = await self._init_voice_behavior(self.voice_listener)
        self._wire_voice_action_callback()
        self._wire_pipeline_refs()
        await self._init_control_panel(memory_system, self.voice_listener, self.tts_engine, self.voice_manager, self.voice_behavior_manager)
        self._update_bot_state(memory_system)

        get_logger().success("=" * 60)
        get_logger().success(f"Serin fully initialized — listening on {len(self.client.guilds)} guild(s)")
        get_logger().success("Press Ctrl+C to stop")
        get_logger().success("=" * 60)

    async def _init_mention_translator(self) -> tuple[Any, bool]:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_2_discord_bot import (
            voice_available,
        )

        mention_translator_obj = create_mention_translator(self.client)
        set_mention_translator(mention_translator_obj)
        bot_module.mention_translator = mention_translator_obj
        init_root(get_logger())
        init_database_protection()
        stats['start_time'] = asyncio.get_running_loop().time()
        self._log_server_info(mention_translator_obj)
        return mention_translator_obj, voice_available

    def _log_server_info(self, mention_translator_obj: Any) -> None:
        get_logger().success("=" * 60)
        user_str = f"{self.client.user}" if self.client.user else "Unknown"
        user_id_str = f"{self.client.user.id}" if self.client.user else "N/A"
        get_logger().success(f"Logged in as {user_str} (ID: {user_id_str})")
        get_logger().success(f"Connected to {len(self.client.guilds)} guild(s)")
        get_logger().success("=" * 60)
        total_channels = 0
        total_voice_channels = 0
        for guild in self.client.guilds:
            get_logger().info(f"  Server: {guild.name} (ID: {guild.id})")
            cached = mention_translator_obj.cache_guild_members(guild)
            get_logger().info(f"    Cached {cached} members")
            allowed = [ch for ch in guild.text_channels if ch.id in config.ALLOWED_CHANNEL_IDS]
            total_channels += len(guild.text_channels)
            total_voice_channels += len(guild.voice_channels)
            get_logger().info(f"    Response channels: {len(allowed)}")
            get_logger().info(f"    Monitoring: {len(guild.text_channels)} text channels")
            get_logger().info(f"    Voice channels: {len(guild.voice_channels)}")
        get_logger().info(f"  Total: {total_channels} text, {total_voice_channels} voice channels")
        get_logger().info("-" * 60)

    async def _init_memory_system(self) -> Any:
        get_logger().info("Initializing memory system (Qdrant)...")
        try:
            memory_system = create_qdrant_memory_system(
                data_dir="./bot_data",
                qdrant_host=config.QDRANT_HOST,
                qdrant_port=config.QDRANT_PORT,
            )
            set_qdrant(memory_system)
            get_logger().success("Memory system ready!")
            return memory_system
        except Exception as e:
            get_logger().exception(f"Memory system failed: {e}")
            raise

    async def _init_database_and_memory(self) -> Any:
        get_logger().info("Initializing LLM model...")
        await initialize_llama_connector()
        llama = get_llama_connector()
        if llama is not None and llama.is_connected:
            get_logger().success("LLM model ready!")
        else:
            get_logger().info("LLM will retry in background every 15s")
        memory_system = await self._init_memory_system()
        return memory_system

    async def _init_voice_system(self, memory_system: Any, mention_translator_obj: Any, voice_available: bool) -> tuple[Any, Any, Any, Any, Any, Any]:
        voice_listener = None
        audio_processor = None
        voice_pipeline = None
        tts_engine = None
        voice_output_manager = None
        voice_manager = None

        if config.ENABLE_VOICE and voice_available:
            get_logger().info("Initializing voice input...")
            try:
                from serin.d1_2_gateway_io.d2_2_voice_system.d3_1_system_audio.d4_1_audio_process.d5_1_audio_processor import (
                    AudioStreamProcessor,
                )
                from serin.d1_2_gateway_io.d2_2_voice_system.d3_3_system_listener import (
                    VoiceListener,
                )
                from serin.d1_2_gateway_io.d2_3_voice_transcribe.d3_3_transcribe_pipeline import (
                    VoiceMemoryPipeline,
                )
                from serin.d1_2_gateway_io.d2_3_voice_transcribe.d3_4_transcribe_transcriber import (
                    WhisperTranscriber,
                )
                transcriber = WhisperTranscriber()
                voice_pipeline = VoiceMemoryPipeline(memory_system=memory_system, background_processor=self.background_processor, message_manager=self.message_manager)
                audio_processor = AudioStreamProcessor(transcriber=transcriber, voice_pipeline=voice_pipeline, silence_threshold=1.5, llm_connector=get_llama_connector())
                voice_listener = VoiceListener(self.client, audio_processor)
                await audio_processor.start()
                get_logger().success(f"Voice input ready! (mode: {config.VOICE_RECEIVER_MODE})")
            except Exception as e:
                get_logger().error(f"Voice init failed: {e}")

            if config.ENABLE_TTS:
                get_logger().info("Initializing TTS output...")
                try:
                    from serin.d1_2_gateway_io.d2_2_voice_system.d3_4_system_output import (
                        VoiceOutputManager,
                    )
                    from serin.d1_2_gateway_io.d2_2_voice_system.d3_5_tts_engine import (
                        TTSEngine,
                    )
                    from serin.d1_5_ops_tooling.d2_5_voice_manager import (
                        TTSVoiceManager,
                    )
                    tts_engine = TTSEngine()
                    voice_manager = TTSVoiceManager()
                    if voice_listener:
                        voice_output_manager = VoiceOutputManager(tts_engine, voice_listener)
                        await voice_output_manager.start()
                        if audio_processor:
                            audio_processor.voice_output_manager = voice_output_manager
                        get_logger().success("TTS output ready!")
                    else:
                        get_logger().warning("TTS requires VoiceListener — skipping")
                except Exception as e:
                    get_logger().error(f"TTS init failed: {e}")
                    config.ENABLE_TTS = False

        return voice_listener, audio_processor, voice_pipeline, tts_engine, voice_output_manager, voice_manager

    async def _init_background_processors(self, memory_system: Any, mention_translator_obj: Any) -> tuple[Any, Any, Any]:
        get_logger().info("Initializing background processor...")
        background_processor = None
        try:
            from serin.d1_5_ops_tooling.d2_2_tooling_background.d5_1_tooling_background import (
                BackgroundProcessor,
            )
            background_processor = BackgroundProcessor(memory_system)
            await background_processor.start()
            get_logger().success("Background processor started!")
        except Exception as e:
            get_logger().error(f"Background processor failed: {e}")

        passive_monitor = None
        if background_processor is not None:
            get_logger().info("Initializing passive monitor...")
            from serin.d1_5_ops_tooling.d2_4_passive_monitor import PassiveMonitor
            passive_monitor = PassiveMonitor(memory_system, background_processor, config.ALLOWED_CHANNEL_IDS, mention_translator_obj)
            get_logger().success("Passive monitor ready!")
        else:
            get_logger().warning("Background processor unavailable — skipping passive monitor")

        get_logger().info("Initializing message crawler...")
        message_crawler = create_message_crawler(self.client, memory_system, background_processor, mention_translator_obj)
        set_crawler(message_crawler)
        await message_crawler.start()
        get_logger().success("Message crawler started!")

        get_logger().info("Initializing memory sync monitor...")
        try:
            sync_monitor = create_sync_monitor(memory_system, background_processor, message_crawler)
            await sync_monitor.start_monitoring()
            get_logger().success("Memory sync monitor started!")
        except Exception as e:
            get_logger().error(f"Sync monitor failed: {e}")

        return background_processor, passive_monitor, message_crawler

    async def _init_message_manager(self, mention_translator_obj: Any, memory_system: Any, voice_pipeline: Any, voice_output_manager: Any) -> Any:
        get_logger().info("Initializing message manager...")
        message_manager = create_message_manager(self.client, mention_translator_obj, memory_system, voice_output_manager=voice_output_manager)
        set_message_manager(message_manager)
        if voice_pipeline is not None:
            voice_pipeline.message_manager = message_manager
            message_manager.voice_pipeline = voice_pipeline
        get_logger().success("Message manager ready!")
        return message_manager

# --- Helpers ---
    async def _backfill_recent_images(self) -> None:
        if self.message_manager is None:
            raise RuntimeError("message_manager not initialized")
        await asyncio.sleep(2)
        vision_semaphore = asyncio.Semaphore(2)

        async def _describe_with_semaphore(msg: Any, image_data_url: str, filename: str) -> None:
            async with vision_semaphore:
                await self.message_manager._describe_image_background(msg, image_data_url, filename)  # type: ignore[union-attr]
                await asyncio.sleep(0.5)

        try:
            for guild in self.client.guilds:
                for channel in guild.text_channels:
                    if not channel.permissions_for(guild.me).read_message_history:
                        continue
                    msg = None
                    try:
                        async for msg in channel.history(limit=15):
                            if msg.author.bot:
                                continue
                            has_image = any(a.content_type and a.content_type.startswith("image/") for a in msg.attachments)
                            if has_image:
                                placeholder = f"{msg.content} [Image: an image]" if msg.content else "[Image: an image]"
                                self.message_manager.memory.store_recent_message(user_id=str(msg.author.id), username=msg.author.display_name, channel_id=str(channel.id), content=placeholder, message_id=str(msg.id), timestamp=msg.created_at)
                                for att in msg.attachments:
                                    if att.content_type and att.content_type.startswith("image/"):
                                        try:
                                            import base64
                                            image_bytes = await att.read()
                                            if image_bytes:
                                                mime = att.content_type or "image/jpeg"
                                                b64 = base64.b64encode(image_bytes).decode("utf-8")
                                                asyncio.create_task(_describe_with_semaphore(msg, f"data:{mime};base64,{b64}", att.filename))
                                        except Exception as e:
                                            get_logger().debug("Image describe failed for %s: %s", att.filename, e)
                            else:
                                self.message_manager.memory.store_recent_message(user_id=str(msg.author.id), username=msg.author.display_name, channel_id=str(channel.id), content=msg.content, message_id=str(msg.id), timestamp=msg.created_at)
                    except Exception as e:
                        if msg is not None:
                            get_logger().debug("Failed to store recent message %s: %s", msg.id, e)
            get_logger().info("Recent messages backfilled with image descriptions")
        except Exception as e:
            get_logger().debug("Backfill failed (non-critical): %s", e)

    async def _build_pipeline(self, memory_system: Any, mention_translator_obj: Any) -> None:
        get_logger().info("Building MessagePipeline...")
        if self.message_manager is None:
            raise RuntimeError("message_manager not initialized")
        try:
            pipeline = build_message_pipeline(
                memory_system=memory_system,
                retrieval=self.message_manager.context_builder,
                personality=self.message_manager.bot_personality,
                temporal_context=self.message_manager.enhanced_context,
                response_generator=get_response_generator_fn(),
                thinking_filter=get_thinking_filter_instance(),
                mention_translator=mention_translator_obj,
                mood_state=self.message_manager.personality,
                client=self.client,
                small_llm=get_small_llm_connector(),
                dynamics_engine=self.message_manager.dynamics_engine,
                affect_engine=getattr(self.message_manager, "affect_engine", None),
            )
            self.message_manager.pipeline = pipeline
            if self.background_processor is not None:
                self.background_processor.dynamics_engine = self.message_manager.dynamics_engine
            get_logger().success("MessagePipeline built and attached!")
        except Exception as e:
            get_logger().error(f"Pipeline build failed: {e}")

    async def _init_voice_behavior(self, voice_listener: Any) -> Any:
        if not voice_listener or not self.message_manager or not hasattr(self.message_manager, 'personality'):
            return None
        try:
            from serin.d1_2_gateway_io.d2_2_voice_system.d3_1_system_audio.d4_1_audio_process.d5_2_voice_behavior import (
                VoiceBehaviorManager,
            )
            vbm = VoiceBehaviorManager(
                personality=self.message_manager.personality,
                voice_listener=voice_listener,
                voice_tracker=getattr(self.message_manager, 'voice_tracker', None),
            )
            await vbm.start()
            get_logger().success("Voice behavior manager started!")
            return vbm
        except Exception as e:
            get_logger().warning(f"Voice behavior manager failed: {e}")
            return None

    def _wire_voice_action_callback(self) -> None:
        if not self.voice_listener or not self.message_manager or not hasattr(self.message_manager, 'voice_action_callback'):
            return

        async def _find_active_channel(guild_id: int) -> int | None:
            guild = self.client.get_guild(guild_id)
            if not guild:
                return None
            for ch in guild.voice_channels:
                if any(not m.bot for m in ch.members):
                    channel_id: int = ch.id
                    return channel_id
            return None

        async def _handle_voice_action(decision: dict[str, Any], user_id: str, guild_id: int) -> dict[str, Any]:
            action = decision.get('action')
            result: dict[str, Any] = {'executed': False, 'message': ''}
            if action == 'join' and self.voice_listener:
                channel_id: int | None = None
                tracker = getattr(self.message_manager, 'voice_tracker', None)
                if tracker and tracker.is_in_voice(user_id):
                    info = tracker.get_voice_info(user_id)
                    if info:
                        channel_id = int(info['channel_id'])
                if channel_id is None:
                    channel_id = await _find_active_channel(guild_id)
                if channel_id is not None:
                    success = await self.voice_listener.join_channel(guild_id, channel_id)
                    if success:
                        vbm = self.bot_state.get('voice_behavior_manager')
                        if vbm:
                            vbm._vc_join_time[guild_id] = datetime.now()
                            vbm._voice_session_guilds.add(guild_id)
                            vbm.stats['auto_joins'] += 1
                            vbm._pending_joins.pop(guild_id, None)
                    result = {'executed': True, 'message': 'joined'}
                if not result['executed']:
                    result = {'executed': False, 'message': 'no_active_channel'}
            elif action == 'leave' and self.voice_listener:
                await self.voice_listener.leave_channel(guild_id)
                vbm = self.bot_state.get('voice_behavior_manager')
                if vbm:
                    vbm.stats['auto_leaves'] += 1
                result = {'executed': True, 'message': 'left'}
            return result
        self.message_manager.voice_action_callback = _handle_voice_action
        get_logger().success("Voice action callback wired")

    def _wire_pipeline_refs(self) -> None:
        if self.voice_pipeline is not None:
            self.voice_pipeline.message_manager = self.message_manager
            self.voice_pipeline.bg_processor = self.background_processor

    async def _init_control_panel(self, memory_system: Any, voice_listener: Any, tts_engine: Any, voice_manager: Any, voice_behavior_manager: Any) -> None:
        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_3_panel_lifecycle import (
            init_bot_state,
            start_server,
        )
        init_bot_state(
            discord_client=self.client,
            message_manager=self.message_manager,
            background_processor=self.background_processor,
            passive_monitor=self.passive_monitor,
            message_crawler=self.message_crawler,
            memory_system=memory_system,
            voice_listener=voice_listener,
            tts_engine=tts_engine,
            voice_manager=voice_manager if config.ENABLE_TTS else None,
        )
        self.bot_state['voice_behavior_manager'] = voice_behavior_manager
        try:
            asyncio.create_task(start_server(port=config.CONTROL_PANEL_PORT))
            get_logger().success(f"Control panel: http://127.0.0.1:{config.CONTROL_PANEL_PORT}")
        except Exception as e:
            get_logger().error(f"Control panel failed: {e}")

    def _update_bot_state(self, memory_system: Any) -> None:
        self.bot_state.update({
            "discord_client": self.client,
            "message_manager": self.message_manager,
            "memory_system": memory_system,
            "background_processor": self.background_processor,
            "passive_monitor": self.passive_monitor,
            "message_crawler": self.message_crawler,
            "voice_listener": self.voice_listener if config.ENABLE_VOICE else None,
            "tts_engine": self.tts_engine if config.ENABLE_TTS else None,
            "voice_manager": self.voice_manager if config.ENABLE_TTS else None,
            "voice_behavior_manager": self.voice_behavior_manager if config.ENABLE_VOICE else None,
            "start_time": time.time(),
        })

# --- Errors ---
# (none)
