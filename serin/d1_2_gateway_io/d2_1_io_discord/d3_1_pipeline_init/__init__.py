"""MessagePipeline and behavior manager initialization.

This package is the folder form of the former ``bot_pipeline_init.py`` (Rule 2:
a file over 500 lines becomes a folder). ``on_ready``, ``on_message`` and the
module-level subsystem globals stay here so their ``global`` bindings resolve in
the package namespace; ``main`` lives in ``main_entry.py`` and is re-exported.
"""

import asyncio
from datetime import datetime
from typing import Any

import discord

import serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator
import serin.d1_2_gateway_io.d2_1_io_discord.d3_2_discord_bot as bot_module
from serin.d1_2_gateway_io.d2_1_io_discord.d3_2_discord_bot import (
    background_processor,
    client,
    db_protector,
    init_database_protection,
    message_crawler,
    message_manager,
    passive_monitor,
    stats,
)
from serin.d1_2_gateway_io.d2_1_io_discord.d3_3_command_handlers import (
    handle_help_command,
    handle_profile_command,
    handle_stats_command,
)
from serin.d1_2_gateway_io.d2_4_io_di import get_logger
from serin.d1_4_config_base.d2_1_base_config import config
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import bot_state
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_3_panel_lifecycle import (
    init_bot_state,
    start_server,
)

from .d4_1_main_entry import main

__all__ = [
    "audio_processor",
    "background_processor",
    "db_protector",
    "main",
    "message_manager",
    "message_crawler",
    "on_message",
    "on_ready",
    "passive_monitor",
    "tts_engine",
    "voice_behavior_manager",
    "voice_listener",
    "voice_manager",
    "voice_output_manager",
    "voice_pipeline",
]

audio_processor: Any | None = None
tts_engine: Any | None = None
voice_behavior_manager: Any | None = None
voice_listener: Any | None = None
voice_manager: Any | None = None
voice_output_manager: Any | None = None
voice_pipeline: Any | None = None


@client.event
async def on_ready() -> None:
    """Bot connected to Discord — initialize all subsystems."""
    global message_manager, background_processor, passive_monitor, message_crawler
    global voice_listener, audio_processor, voice_pipeline, tts_engine
    global voice_behavior_manager, voice_output_manager, voice_manager

    # Create MentionTranslator (needs the discord.Client instance)
    from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_1_ingest_context.d4_3_mention_translator import (
        MentionTranslator,
    )
    from serin.d1_1_serin_di import (
        init_root,
        set_crawler,
        set_mention_translator,
        set_message_manager,
        set_qdrant,
    )
    from serin.d1_2_gateway_io.d2_1_io_discord.d3_2_discord_bot import voice_available
    from serin.d1_2_gateway_io.d2_2_voice_system.d3_5_tts_engine import TTSEngine
    from serin.d1_2_gateway_io.d2_4_io_di import get_logger

    mention_translator = MentionTranslator(client)
    set_mention_translator(mention_translator)
    bot_module.mention_translator = mention_translator

    # Initialize root DI with the gateway logger
    init_root(get_logger())

    # Validate databases
    init_database_protection()

    stats['start_time'] = asyncio.get_running_loop().time()

    # ── Server info ──────────────────────────────────────────────────────
    get_logger().success("=" * 60)
    user_str = f"{client.user}" if client.user else "Unknown"
    user_id_str = f"{client.user.id}" if client.user else "N/A"
    get_logger().success(f"Logged in as {user_str} (ID: {user_id_str})")
    get_logger().success(f"Connected to {len(client.guilds)} guild(s)")
    get_logger().success("=" * 60)
    total_channels = 0
    total_voice_channels = 0
    for guild in client.guilds:
        get_logger().info(f"  Server: {guild.name} (ID: {guild.id})")
        cached = mention_translator.cache_guild_members(guild)
        get_logger().info(f"    Cached {cached} members")
        allowed = [ch for ch in guild.text_channels if ch.id in config.ALLOWED_CHANNEL_IDS]
        total_channels += len(guild.text_channels)
        total_voice_channels += len(guild.voice_channels)
        get_logger().info(f"    Response channels: {len(allowed)}")
        get_logger().info(f"    Monitoring: {len(guild.text_channels)} text channels")
        get_logger().info(f"    Voice channels: {len(guild.voice_channels)}")
    get_logger().info(f"  Total: {total_channels} text, {total_voice_channels} voice channels")
    get_logger().info("-" * 60)

    # ── LLM ───────────────────────────────────────────────────────────────
    get_logger().info("Initializing LLM model...")
    await serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator.initialize_llama()
    if serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator.llama is not None and serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator.llama.is_connected:
        get_logger().success("LLM model ready!")
    else:
        get_logger().info("LLM will retry in background every 15s")

    # ── Memory System (Qdrant) ────────────────────────────────────────────
    get_logger().info("Initializing memory system (Qdrant)...")
    try:
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_3_remember_qdrant import (
            QdrantMemorySystem,
        )
        memory_system = QdrantMemorySystem(
            data_dir="./bot_data",
            qdrant_host=config.QDRANT_HOST,
            qdrant_port=config.QDRANT_PORT,
        )
        set_qdrant(memory_system)
        get_logger().success("Memory system ready!")
    except Exception as e:
        get_logger().exception(f"Memory system failed: {e}")
        raise

    # ── Background Processor ──────────────────────────────────────────────
    get_logger().info("Initializing background processor...")
    try:
        from serin.d1_5_ops_tooling.d2_2_tooling_background import BackgroundProcessor
        background_processor = BackgroundProcessor(memory_system)
        await background_processor.start()
        get_logger().success("Background processor started!")
    except Exception as e:
        get_logger().error(f"Background processor failed: {e}")

    # ── Passive Monitor ───────────────────────────────────────────────────
    if background_processor is not None:
        get_logger().info("Initializing passive monitor...")
        from serin.d1_5_ops_tooling.d2_4_passive_monitor import PassiveMonitor
        passive_monitor = PassiveMonitor(
            memory_system,
            background_processor,
            config.ALLOWED_CHANNEL_IDS,
            mention_translator,
        )
        get_logger().success("Passive monitor ready!")
    else:
        get_logger().warning("Background processor unavailable — skipping passive monitor")

    # ── Message Crawler ──────────────────────────────────────────────────
    get_logger().info("Initializing message crawler...")
    from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_3_ingest_sync.d4_2_sync_crawler import (
        MessageCrawler,
    )
    message_crawler = MessageCrawler(client, memory_system, background_processor, mention_translator)
    set_crawler(message_crawler)
    await message_crawler.start()
    get_logger().success("Message crawler started!")

    # ── Memory Sync Monitor ───────────────────────────────────────────────
    get_logger().info("Initializing memory sync monitor...")
    try:
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_4_sync_monitor import (
            MemorySyncMonitor,
        )
        sync_monitor = MemorySyncMonitor(memory_system, background_processor, message_crawler)
        await sync_monitor.start_monitoring()
        get_logger().success("Memory sync monitor started!")
    except Exception as e:
        get_logger().error(f"Sync monitor failed: {e}")

    # ── Voice System ──────────────────────────────────────────────────────
    if config.ENABLE_VOICE and voice_available:
        get_logger().info("Initializing voice input...")
        try:
            from serin.d1_2_gateway_io.d2_2_voice_system.d3_1_system_audio.d4_1_audio_process.d5_1_audio_processor import (
                AudioStreamProcessor,
            )
            from serin.d1_2_gateway_io.d2_2_voice_system.d3_1_system_audio.d4_1_audio_process.d5_2_voice_behavior import (
                VoiceBehaviorManager,
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
            voice_pipeline = VoiceMemoryPipeline(
                memory_system=memory_system,
                background_processor=background_processor,
                message_manager=message_manager,
            )
            audio_processor = AudioStreamProcessor(
                transcriber=transcriber,
                voice_pipeline=voice_pipeline,
                silence_threshold=1.5,
                llm_connector=serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator.llama,
            )
            voice_listener = VoiceListener(client, audio_processor)
            await audio_processor.start()
            get_logger().success(f"Voice input ready! (mode: {config.VOICE_RECEIVER_MODE})")
        except Exception as e:
            get_logger().error(f"Voice init failed: {e}")

        # ── TTS ────────────────────────────────────────────────────────────
        if config.ENABLE_TTS:
            get_logger().info("Initializing TTS output...")
            try:
                from serin.d1_2_gateway_io.d2_2_voice_system.d3_4_system_output import (
                    VoiceOutputManager,
                )
                from serin.d1_5_ops_tooling.d2_5_voice_manager import TTSVoiceManager

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

    # ── Message Manager ──────────────────────────────────────────────────
    get_logger().info("Initializing message manager...")
    from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_4_core_manager import (
        EnhancedMessageManagerV3,
    )
    message_manager = EnhancedMessageManagerV3(
        client,
        mention_translator,
        memory_system,
        voice_output_manager=voice_output_manager,
    )
    set_message_manager(message_manager)
    if voice_pipeline is not None:
        voice_pipeline.message_manager = message_manager
        message_manager.voice_pipeline = voice_pipeline
    get_logger().success("Message manager ready!")

    # ── Startup backup ────────────────────────────────────────────────────
    try:
        await asyncio.to_thread(db_protector.create_backup, "startup", True)
        get_logger().info("Startup backup created")
    except Exception as e:
        get_logger().warning(f"Startup backup failed: {e}")

    # ── Build MessagePipeline ─────────────────────────────────────────────
    get_logger().info("Building MessagePipeline...")
    try:
        from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
            MessagePipeline,
        )
        from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator import (
            get_response_natural,
        )
        from serin.d1_3_state_core.d2_5_thinking_filter import get_thinking_filter
        pipeline = MessagePipeline.build(
            response_controller=message_manager.response_controller,
            memory_system=memory_system,
            retrieval=message_manager.context_builder,
            personality=message_manager.bot_personality,
            temporal_context=message_manager.enhanced_context,
            response_generator=get_response_natural,
            thinking_filter=get_thinking_filter(),
            mention_translator=mention_translator,
        )
        message_manager.pipeline = pipeline
        get_logger().success("MessagePipeline built and attached!")
    except Exception as e:
        get_logger().error(f"Pipeline build failed: {e}")

    # ── Voice Behavior Manager ─────────────────────────────────────────────
    if voice_listener and message_manager and hasattr(message_manager, 'personality'):
        try:
            from serin.d1_2_gateway_io.d2_2_voice_system.d3_1_system_audio.d4_1_audio_process.d5_2_voice_behavior import (
                VoiceBehaviorManager,
            )
            voice_behavior_manager = VoiceBehaviorManager(
                personality=message_manager.personality,
                voice_listener=voice_listener,
                voice_tracker=getattr(message_manager, 'voice_tracker', None),
            )
            await voice_behavior_manager.start()
            get_logger().success("Voice behavior manager started!")
        except Exception as e:
            get_logger().warning(f"Voice behavior manager failed: {e}")

    # ── Voice Action Callback ──────────────────────────────────────────────
    if voice_listener and message_manager and hasattr(message_manager, 'voice_action_callback'):
        async def _find_active_channel(guild_id: int) -> int | None:
            guild = client.get_guild(guild_id)
            if not guild:
                return None
            for ch in guild.voice_channels:
                human_members = [m for m in ch.members if not m.bot]
                if human_members:
                    return ch.id
            return None

        async def _handle_voice_action(decision: dict[str, Any], user_id: str, guild_id: int) -> dict[str, Any]:
            action = decision.get('action')
            result: dict[str, Any] = {'executed': False, 'message': ''}
            if action == 'join' and voice_listener:
                channel_id: int | None = None
                tracker = getattr(message_manager, 'voice_tracker', None)
                if tracker and tracker.is_in_voice(user_id):
                    info = tracker.get_voice_info(user_id)
                    if info:
                        channel_id = int(info['channel_id'])
                if channel_id is None:
                    channel_id = await _find_active_channel(guild_id)
                if channel_id is not None:
                    success = await voice_listener.join_channel(guild_id, channel_id)
                    if success and voice_behavior_manager:
                        voice_behavior_manager._vc_join_time[guild_id] = datetime.now()
                        voice_behavior_manager._voice_session_guilds.add(guild_id)
                        voice_behavior_manager.stats['auto_joins'] += 1
                        voice_behavior_manager._pending_joins.pop(guild_id, None)
                    result = {'executed': True, 'message': 'joined'}
                if not result['executed']:
                    result = {'executed': False, 'message': 'no_active_channel'}
            elif action == 'leave' and voice_listener:
                await voice_listener.leave_channel(guild_id)
                if voice_behavior_manager:
                    voice_behavior_manager.stats['auto_leaves'] += 1
                result = {'executed': True, 'message': 'left'}
            return result
        message_manager.voice_action_callback = _handle_voice_action
        get_logger().success("Voice action callback wired")

    # ── Wire pipeline references ──────────────────────────────────────────
    if voice_pipeline is not None:
        voice_pipeline.message_manager = message_manager
        voice_pipeline.bg_processor = background_processor

    # ── Control Panel ─────────────────────────────────────────────────────
    init_bot_state(
        discord_client=client,
        message_manager=message_manager,
        background_processor=background_processor,
        passive_monitor=passive_monitor,
        message_crawler=message_crawler,
        memory_system=memory_system,
        voice_listener=voice_listener,
        tts_engine=tts_engine,
        voice_manager=voice_manager if config.ENABLE_TTS else None,
    )
    bot_state['voice_behavior_manager'] = voice_behavior_manager

    if message_manager and hasattr(message_manager, 'response_controller'):
        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
            broadcast_event,
        )
        message_manager.response_controller.set_broadcaster(broadcast_event)
        get_logger().success("Decision broadcaster connected")

    try:
        asyncio.create_task(start_server(port=config.CONTROL_PANEL_PORT))
        get_logger().success(f"Control panel: http://127.0.0.1:{config.CONTROL_PANEL_PORT}")
    except Exception as e:
        get_logger().error(f"Control panel failed: {e}")

    # ── Done ──────────────────────────────────────────────────────────────
    get_logger().success("=" * 60)
    get_logger().success(f"Serin fully initialized — listening on {len(client.guilds)} guild(s)")
    get_logger().success("Press Ctrl+C to stop")
    get_logger().success("=" * 60)


@client.event
async def on_message(message: discord.Message) -> None:
    """Handle incoming messages from ALL channels"""
    global stats

    try:
        stats['messages_received'] += 1

        # Filter 1: Ignore bot's own messages
        if message.author == client.user:
            return

        # Filter 2: Only text channels
        if not isinstance(message.channel, discord.TextChannel):
            return

        # Filter 3: Ignore empty messages (unless they have attachments)
        content = message.content.strip()
        if not content and not message.attachments:
            return

        # Check if in allowed channel
        is_allowed_channel = message.channel.id in config.ALLOWED_CHANNEL_IDS

        if config.TRACE_MESSAGES:
            channel_type = "ACTIVE" if is_allowed_channel else "PASSIVE"
            get_logger().debug(
                f"[{channel_type}] Message #{stats['messages_received']}: "
                f"'{content[:50]}...' from {message.author.display_name} "
                f"in #{message.channel.name}"
            )

        # === PASSIVE MONITORING (ALL CHANNELS) ===
        if passive_monitor:
            await passive_monitor.process_message(message, is_allowed_channel)

        if is_allowed_channel:
            stats['messages_processed'] += 1
        else:
            stats['passive_messages'] += 1
            return

        # === HANDLE COMMANDS ===
        if await handle_profile_command(message, message_manager, stats):
            return
        if await handle_stats_command(message, message_manager, background_processor, passive_monitor, message_crawler, stats):
            return
        if await handle_help_command(message, stats):
            return

        # === PROCESS REGULAR MESSAGE ===
        get_logger().debug(f"Processing message from {message.author.display_name}")

        if message_manager is None:
            get_logger().error("MessageManager not initialized!")
            stats['errors'] += 1
            return

        # Pass to message manager for response generation
        await message_manager.process_message(message)

    except Exception as e:
        stats['errors'] += 1
        get_logger().exception(f"Error in on_message: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        get_logger().info("Received shutdown signal")
    except Exception as e:
        get_logger().exception(f"Fatal error: {e}")
