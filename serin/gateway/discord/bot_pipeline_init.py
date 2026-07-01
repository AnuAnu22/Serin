"""MessagePipeline and behavior manager initialization."""
import asyncio
from datetime import datetime
from typing import Any, cast

import aiohttp
import discord

import serin.pipeline.think.response_generator
from serin.config.config import config
from serin.gateway.discord.bot import (
    background_processor,
    client,
    db_protector,
    mention_translator,
    message_crawler,
    message_manager,
    passive_monitor,
    stats,
    voice_behavior_manager,
    voice_listener,
)
from serin.logger import logger
from serin.ops.control_panel.panel_lifecycle import init_bot_state, start_server
from serin.ops.control_panel.server import bot_state
from serin.state.db_protect import DatabaseRecoveryError, DatabaseValidationError


@client.event
async def on_ready() -> None:
    """Bot connected to Discord — initialize all subsystems."""
    global message_manager, background_processor, passive_monitor, message_crawler
    global voice_listener, audio_processor, voice_pipeline, tts_engine
    global voice_behavior_manager, voice_output_manager, voice_manager

    from serin.gateway.discord.bot import voice_available
    from serin.gateway.voice_system.tts_engine import TTSEngine
    from serin.logger import logger
    from serin.pipeline.remember.qdrant import QdrantMemorySystem

    stats['start_time'] = asyncio.get_running_loop().time()

    # ── Server info ──────────────────────────────────────────────────────
    logger.success("=" * 60)
    logger.success(f"Logged in as {client.user} (ID: {client.user.id})")
    logger.success(f"Connected to {len(client.guilds)} guild(s)")
    logger.success("=" * 60)
    total_channels = 0
    total_voice_channels = 0
    for guild in client.guilds:
        logger.info(f"  Server: {guild.name} (ID: {guild.id})")
        cached = mention_translator.cache_guild_members(guild)
        logger.info(f"    Cached {cached} members")
        allowed = [ch for ch in guild.text_channels if ch.id in config.ALLOWED_CHANNEL_IDS]
        total_channels += len(guild.text_channels)
        total_voice_channels += len(guild.voice_channels)
        logger.info(f"    Response channels: {len(allowed)}")
        logger.info(f"    Monitoring: {len(guild.text_channels)} text channels")
        logger.info(f"    Voice channels: {len(guild.voice_channels)}")
    logger.info(f"  Total: {total_channels} text, {total_voice_channels} voice channels")
    logger.info("-" * 60)

    # ── LLM ───────────────────────────────────────────────────────────────
    logger.info("Initializing LLM model...")
    await serin.pipeline.think.response_generator.initialize_llama()
    if serin.pipeline.think.response_generator.llama.is_connected:
        logger.success("LLM model ready!")
    else:
        logger.info("LLM will retry in background every 15s")

    # ── Memory System (Qdrant) ────────────────────────────────────────────
    logger.info("Initializing memory system (Qdrant)...")
    try:
        memory_system = QdrantMemorySystem(
            data_dir="./bot_data",
            qdrant_host=config.QDRANT_HOST,
            qdrant_port=config.QDRANT_PORT,
        )
        logger.success("Memory system ready!")
    except Exception as e:
        logger.exception(f"Memory system failed: {e}")
        raise

    # ── Background Processor ──────────────────────────────────────────────
    logger.info("Initializing background processor...")
    try:
        from serin.ops.background import BackgroundProcessor
        background_processor = BackgroundProcessor(memory_system)
        await background_processor.start()
        logger.success("Background processor started!")
    except Exception as e:
        logger.error(f"Background processor failed: {e}")

    # ── Passive Monitor ───────────────────────────────────────────────────
    logger.info("Initializing passive monitor...")
    from serin.ops.passive_monitor import PassiveMonitor
    passive_monitor = PassiveMonitor(
        memory_system,
        background_processor,
        config.ALLOWED_CHANNEL_IDS,
        mention_translator,
    )
    logger.success("Passive monitor ready!")

    # ── Message Crawler ──────────────────────────────────────────────────
    logger.info("Initializing message crawler...")
    from serin.pipeline.ingest.sync.crawler import MessageCrawler
    message_crawler = MessageCrawler(client, memory_system, background_processor, mention_translator)
    await message_crawler.start()
    logger.success("Message crawler started!")

    # ── Memory Sync Monitor ───────────────────────────────────────────────
    logger.info("Initializing memory sync monitor...")
    try:
        from serin.pipeline.remember.sync_monitor import MemorySyncMonitor
        sync_monitor = MemorySyncMonitor(memory_system, background_processor, message_crawler)
        await sync_monitor.start_monitoring()
        logger.success("Memory sync monitor started!")
    except Exception as e:
        logger.error(f"Sync monitor failed: {e}")

    # ── Voice System ──────────────────────────────────────────────────────
    if config.ENABLE_VOICE and voice_available:
        logger.info("Initializing voice input...")
        try:
            from serin.gateway.voice_system.listener import VoiceListener
            from serin.gateway.voice_system.processor import (
                AudioStreamProcessor,
                VoiceBehaviorManager,
            )
            from serin.gateway.voice_transcribe.pipeline import VoiceMemoryPipeline
            from serin.gateway.voice_transcribe.transcriber import WhisperTranscriber

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
                llm_connector=serin.pipeline.think.response_generator.llama,
            )
            voice_listener = VoiceListener(client, audio_processor)
            await audio_processor.start()
            logger.success(f"Voice input ready! (mode: {config.VOICE_RECEIVER_MODE})")
        except Exception as e:
            logger.error(f"Voice init failed: {e}")

        # ── TTS ────────────────────────────────────────────────────────────
        if config.ENABLE_TTS:
            logger.info("Initializing TTS output...")
            try:
                from serin.gateway.voice_system.output import VoiceOutputManager
                from serin.ops.tts_voice_manager import TTSVoiceManager

                tts_engine = TTSEngine()
                voice_manager = TTSVoiceManager()
                if voice_listener:
                    voice_output_manager = VoiceOutputManager(tts_engine, voice_listener)
                    await voice_output_manager.start()
                    if audio_processor:
                        audio_processor.voice_output_manager = voice_output_manager
                    logger.success("TTS output ready!")
                else:
                    logger.warning("TTS requires VoiceListener — skipping")
            except Exception as e:
                logger.error(f"TTS init failed: {e}")
                config.ENABLE_TTS = False

    # ── Message Manager ──────────────────────────────────────────────────
    logger.info("Initializing message manager...")
    from serin.pipeline.ingest.core.manager import EnhancedMessageManagerV3
    message_manager = EnhancedMessageManagerV3(
        client,
        mention_translator,
        memory_system,
        voice_output_manager=voice_output_manager if 'voice_output_manager' in dir() else None,
    )
    logger.success("Message manager ready!")

    # ── Startup backup ────────────────────────────────────────────────────
    try:
        await asyncio.to_thread(db_protector.create_backup, "startup", True)
        logger.info("Startup backup created")
    except Exception as e:
        logger.warning(f"Startup backup failed: {e}")

    # ── Build MessagePipeline ─────────────────────────────────────────────
    logger.info("Building MessagePipeline...")
    try:
        from serin.pipeline.act.runners.pipeline import MessagePipeline
        from serin.pipeline.think.response_generator import get_response_natural
        from serin.state.thinking_filter import get_thinking_filter
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
        logger.success("MessagePipeline built and attached!")
    except Exception as e:
        logger.error(f"Pipeline build failed: {e}")

    # ── Voice Behavior Manager ─────────────────────────────────────────────
    if voice_listener and message_manager and hasattr(message_manager, 'personality'):
        try:
            from serin.gateway.voice_system.processor import VoiceBehaviorManager
            voice_behavior_manager = VoiceBehaviorManager(
                personality=message_manager.personality,
                voice_listener=voice_listener,
                voice_tracker=getattr(message_manager, 'voice_tracker', None),
            )
            await voice_behavior_manager.start()
            logger.success("Voice behavior manager started!")
        except Exception as e:
            logger.warning(f"Voice behavior manager failed: {e}")

    # ── Voice Action Callback ──────────────────────────────────────────────
    if voice_listener and message_manager and hasattr(message_manager, 'voice_action_callback'):
        async def _handle_voice_action(decision: dict, user_id: str, guild_id: int) -> dict:
            action = decision.get('action')
            result = {'executed': False, 'message': ''}
            if action == 'join' and voice_listener:
                tracker = getattr(message_manager, 'voice_tracker', None)
                if tracker and tracker.is_in_voice(user_id):
                    info = tracker.get_voice_info(user_id)
                    if info:
                        success = await voice_listener.join_channel(guild_id, int(info['channel_id']))
                        if success and voice_behavior_manager:
                            voice_behavior_manager._vc_join_time[guild_id] = datetime.now()
                            voice_behavior_manager._voice_session_guilds.add(guild_id)
                            voice_behavior_manager.stats['auto_joins'] += 1
                            voice_behavior_manager._pending_joins.pop(guild_id, None)
                        result = {'executed': True, 'message': 'joined'}
                if not result['executed']:
                    result = {'executed': False, 'message': 'user_not_in_vc'}
            elif action == 'leave' and voice_listener:
                await voice_listener.leave_channel(guild_id)
                if voice_behavior_manager:
                    voice_behavior_manager.stats['auto_leaves'] += 1
                result = {'executed': True, 'message': 'left'}
            return result
        message_manager.voice_action_callback = _handle_voice_action
        logger.success("Voice action callback wired")

    # ── Wire pipeline references ──────────────────────────────────────────
    if 'voice_pipeline' in dir() and voice_pipeline:
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
        from serin.ops.control_panel.server import broadcast_event
        message_manager.response_controller.set_broadcaster(broadcast_event)
        logger.success("Decision broadcaster connected")

    try:
        asyncio.create_task(start_server(port=config.CONTROL_PANEL_PORT))
        logger.success(f"Control panel: http://127.0.0.1:{config.CONTROL_PANEL_PORT}")
    except Exception as e:
        logger.error(f"Control panel failed: {e}")

    # ── Done ──────────────────────────────────────────────────────────────
    logger.success("=" * 60)
    logger.success(f"Serin fully initialized — listening on {len(client.guilds)} guild(s)")
    logger.success("Press Ctrl+C to stop")
    logger.success("=" * 60)

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
            logger.debug(
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
        content_lower = content.lower()

        # !profile command
        if content_lower.startswith("!profile"):
            stats['commands_executed'] += 1
            logger.info(f"Command: !profile from {message.author.display_name}")

            try:
                mentioned_users = message.mentions
                target_id = str(mentioned_users[0].id) if mentioned_users else str(message.author.id)
                target_name = mentioned_users[0].display_name if mentioned_users else message.author.display_name

                profile = message_manager.get_user_profile(target_id)

                if profile:
                    traits = profile.get('personality_traits', [])[:5]
                    interests = profile.get('interests', [])[:5]

                    response = (
                        f"**Profile: {target_name}**\n"
                        f"Traits: {', '.join(traits) or 'None detected'}\n"
                        f"Interests: {', '.join(interests) or 'None detected'}\n"
                        f"Messages: {profile.get('total_messages', 0)}\n"
                        f"Avg. Length: {round(profile.get('avg_message_length', 0), 1)} chars\n"
                        f"Last seen: {profile.get('last_seen', 'Unknown')}"
                    )
                else:
                    response = f"No profile data found for {target_name}."

                await message.channel.send(response)

            except Exception as e:
                logger.error(f"Error in !profile command: {e}")
                await message.channel.send("Error retrieving profile.")

            return

        # !stats command
        if content_lower.startswith("!stats"):
            stats['commands_executed'] += 1
            logger.info(f"Command: !stats from {message.author.display_name}")

            try:
                uptime = asyncio.get_running_loop().time() - stats['start_time']
                hours = int(uptime // 3600)
                minutes = int((uptime % 3600) // 60)

                mem_stats = message_manager.get_memory_stats()
                mgr_stats = mem_stats.get('manager_stats', {})

                bg_stats = background_processor.get_stats() if background_processor else {}
                passive_stats = passive_monitor.get_stats() if passive_monitor else {}
                voice_stats = message_manager.voice_tracker.get_stats()
                crawler_stats = message_crawler.get_stats() if message_crawler else {}

                response = (
                    "**Bot Statistics**\n"
                    f"Uptime: {hours}h {minutes}m\n"
                    f"Messages Received: {stats['messages_received']}\n"
                    f"Active Processed: {stats['messages_processed']}\n"
                    f"Passive Monitored: {stats['passive_messages']}\n"
                    f"Responses Generated: {mgr_stats.get('responses_generated', 0)}\n"
                    f"Corrections Learned: {mgr_stats.get('corrections_detected', 0)}\n\n"
                    "**Memory System**\n"
                    f"Total Memories: {mem_stats.get('total_memories', 0)}\n"
                    f"Total Users: {mem_stats.get('total_users', 0)}\n"
                    f"Strong Relationships: {mem_stats.get('strong_relationships', 0)}\n\n"
                    "**Background Processing**\n"
                    f"Queue Size: {bg_stats.get('queue_size', 0)}\n"
                    f"Summaries Created: {bg_stats.get('summaries_created', 0)}\n"
                    f"Processed: {bg_stats.get('total_processed', 0)}\n\n"
                    "**Voice Tracking**\n"
                    f"Users in Voice: {voice_stats.get('users_in_voice', 0)}\n"
                    f"Active Sessions: {voice_stats.get('active_sessions', 0)}\n\n"
                    "**Cross-Server**\n"
                    f"Servers: {passive_stats.get('servers_monitored', 0)}\n"
                    f"Channels: {passive_stats.get('channels_monitored', 0)}\n\n"
                    "**Message Crawler**\n"
                    f"Quick Syncs: {crawler_stats.get('quick_syncs', 0)}\n"
                    f"Deep Validations: {crawler_stats.get('deep_validations', 0)}\n"
                    f"Messages Backfilled: {crawler_stats.get('messages_backfilled', 0)}\n"
                    f"Gaps Found: {crawler_stats.get('gaps_found', 0)}\n\n"
                )

                await message.channel.send(response)

            except Exception as e:
                logger.error(f"Error in !stats command: {e}")
                await message.channel.send("Error retrieving stats.")

            return

        # !help command
        if content_lower.startswith("!help"):
            stats['commands_executed'] += 1

            response = (
                "**Serin Bot Commands**\n"
                "`!profile [@user]` - View personality profile\n"
                "`!stats` - View bot statistics\n"
                "`!help` - Show this help message\n\n"
                "**How I Work:**\n"
                "- I monitor ALL channels across ALL servers (one shared memory)\n"
                "- I learn from everything I see\n"
                "- I only respond in allowed channels\n"
                "- Mention me with @ for immediate responses\n\n"
                "**Features:**\n"
                "Multi-Model Support - Works with any LLM\n"
                "Temporal Awareness - Understands 'last Tuesday'\n"
                "Correction Learning - Learns when you correct me\n"
                "Voice Tracking - Aware of voice channel activity"
            )
            await message.channel.send(response)
            return

        # === PROCESS REGULAR MESSAGE ===
        logger.debug(f"Processing message from {message.author.display_name}")

        if message_manager is None:
            logger.error("MessageManager not initialized!")
            stats['errors'] += 1
            return

        # Pass to message manager for response generation
        await message_manager.process_message(message)

    except Exception as e:
        stats['errors'] += 1
        logger.exception(f"Error in on_message: {e}")

@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    """Handle voice state changes - track + auto-join decisions"""
    global stats, voice_behavior_manager

    try:
        stats['voice_events'] += 1

        if message_manager and hasattr(message_manager, 'voice_tracker'):
            await message_manager.voice_tracker.on_voice_update(member, before, after)

        # Trigger auto-join when user joins a voice channel
        if after.channel and not before.channel:
            if voice_behavior_manager and voice_listener:
                await voice_behavior_manager.on_user_joined_vc(
                    user_id=str(member.id),
                    username=member.display_name,
                    guild_id=after.channel.guild.id,
                    channel_id=after.channel.id,
                    channel_name=after.channel.name,
                )

    except Exception as e:
        logger.exception(f"Error in voice state update: {e}")


@client.event
async def on_error(event: str, *args: Any, **kwargs: Any) -> None:
    """Handle Discord.py errors"""
    stats['errors'] += 1
    logger.exception(f"Discord error in event '{event}'")


async def maintenance_task() -> None:
    """Periodic maintenance task"""
    maintenance_count = 0
    while True:
        try:
            await asyncio.sleep(config.MAINTENANCE_INTERVAL_HOURS * 3600)
            maintenance_count += 1
            logger.info("Running periodic maintenance...")

            if background_processor:
                await background_processor.run_maintenance()

            # Database backup
            try:
                backup_path = db_protector.create_backup(backup_type="scheduled")
                logger.info(f"Scheduled backup created: {backup_path}")
            except Exception as e:
                logger.error(f"Backup failed: {e}")

            # Memory cleanup
            if message_manager:
                try:
                    stats_before = message_manager.get_memory_stats()
                    logger.info(f"Before: {stats_before.get('total_memories', 0)} memories")

                    if hasattr(message_manager.memory, 'cleanup_old_memories'):
                        cleaned = message_manager.memory.cleanup_old_memories(days_old=90, min_importance=0.3)
                        logger.info(f"Removed {cleaned} old memories")

                    stats_after = message_manager.get_memory_stats()
                    logger.info(f"After: {stats_after.get('total_memories', 0)} memories")
                except Exception as e:
                    logger.error(f"Memory cleanup failed: {e}")

            logger.info(f"Maintenance task #{maintenance_count} complete!")

        except Exception as e:
            logger.error(f"Error in maintenance task: {e}")
            await asyncio.sleep(3600)

async def main() -> None:
    """Main async function with database protection"""
    try:
        logger.info("=" * 60)
        logger.info("Serin Discord Bot")
        logger.info("WITH DATABASE PROTECTION")
        logger.info("=" * 60)

        if config.DEBUG_MODE:
            logger.info("Debug mode enabled - verbose logging active")

        logger.info("Configuration:")
        logger.info(f"   Trace messages: {config.TRACE_MESSAGES}")
        logger.info(f"   Response channels: {len(config.ALLOWED_CHANNEL_IDS)}")
        logger.info("   Monitoring: ALL channels (passive learning)")
        logger.info(f"   Maintenance interval: {config.MAINTENANCE_INTERVAL_HOURS}h")
        logger.info("   Cross-server memory: ENABLED")
        logger.info(f"   Voice tracking: {config.ENABLE_VOICE}")
        logger.info("   Multi-model: ENABLED (via factory)")
        logger.info("   Temporal awareness: ENABLED")
        logger.info("   Correction learning: ENABLED")
        logger.info("   Database Protection: ENABLED")
        logger.info("=" * 60)

        # Set up discord client reference
        serin.pipeline.think.response_generator.discord_client = client
        logger.debug("Discord client reference set")

        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
            try:
                async with client:
                    # Start maintenance task (only here, not in on_ready)
                    logger.info("Starting maintenance task...")
                    asyncio.create_task(maintenance_task())
                    logger.debug("Maintenance task scheduled")

                    # Start Discord client with retry
                    logger.info(f"Connecting to Discord (Attempt {retry_count + 1}/{max_retries})...")
                    await client.start(cast(str, config.DISCORD_TOKEN))
                    break

            except (aiohttp.ClientError, discord.ConnectionClosed, discord.GatewayNotFound) as e:
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = min(30, 2 ** retry_count)
                    logger.warning(f"Connection attempt {retry_count} failed: {e}")
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect after {max_retries} attempts: {e}")
                    raise

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt (Ctrl+C)")

    except DatabaseValidationError as e:
        logger.error(f"Database validation failed: {e}")
        logger.error("Manual intervention required")

    except DatabaseRecoveryError as e:
        logger.error(f"Database recovery failed: {e}")
        logger.error("Try restoring from backup manually")

    except Exception as e:
        logger.exception(f"Fatal error in main: {e}")
    finally:
        logger.info("Bot shutdown complete")
        if not client.is_closed():
            await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
