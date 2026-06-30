"""
Main Bot - Control Panel + Voice Input Integration
Adds web control panel and voice channel support.

Features:
- Web control panel (localhost:8080)
- Voice channel joining/listening
- Real-time audio transcription
- Voice message -> Memory pipeline
- Full remote control via web UI

PRODUCTION DATABASE PROTECTION:
- Pre-startup database validation
- Automatic backup with versioning
- Corruption recovery
- Graceful shutdown handlers
"""
import os
from serin.core.logger import logger
import asyncio
import traceback
import aiohttp
from typing import cast, Optional, Set
from dotenv import load_dotenv
logger.info("Loading Discord.py...")
import discord
logger.info("Loading AI components...")
from datetime import datetime, timedelta

# Import centralized config
from serin.core.config import config

# TIER 1: Core Message Processing
from serin.messaging.response_generator import initialize_llama
import serin.messaging.response_generator
from serin.messaging.manager import EnhancedMessageManagerV3
from serin.messaging.mention_translator import MentionTranslator

# TIER 3: Background Processing
from serin.utils.passive_monitor import PassiveMonitor
from serin.utils.background import BackgroundProcessor
from serin.utils.database_protector import get_database_protector

# TIER 4: Message Crawler
from serin.messaging.crawler import MessageCrawler

# TIER 5: Memory System
from serin.memory.qdrant import QdrantMemorySystem
from serin.memory.sync_monitor import MemorySyncMonitor

# TIER 6: Import voice and control panel components
from voice.listener import VoiceListener
from voice.processor import AudioStreamProcessor
from voice.transcriber import WhisperTranscriber
from voice.pipeline import VoiceMemoryPipeline
from voice.output import VoiceOutputManager
from voice.behavior import VoiceBehaviorManager
from serin.control_panel.server import init_bot_state, start_server

# TIER 7: TTS preparation
from tts.tts_engine import TTSEngine

# Database Protection
from serin.utils.database_protector import DatabaseProtector, DatabaseValidationError, DatabaseRecoveryError


# Load environment variables
load_dotenv()

# ==================================================================================
# CONFIGURATION
# ==================================================================================

# Validate token
if not config.DISCORD_TOKEN:
    raise EnvironmentError("DISCORD_TOKEN environment variable not set")

# Allowed channels (where bot can RESPOND)
if not config.ALLOWED_CHANNEL_IDS:
    config.ALLOWED_CHANNEL_IDS = {
        1298593950436954143,
        937365486172254220,
        917111337128165398,
        1383412857164791811
    }
    logger.warning("No ALLOWED_CHANNEL_IDS in .env, using defaults")

logger.info(f"Starting bot in {'DEBUG' if config.DEBUG_MODE else 'PRODUCTION'} mode")
logger.info(f"Will RESPOND in {len(config.ALLOWED_CHANNEL_IDS)} channels")
logger.info(f"Will MONITOR all channels (passive learning)")
logger.info(f"Voice input: {'ENABLED' if config.ENABLE_VOICE else 'DISABLED'} ({config.VOICE_RECEIVER_MODE} mode)")
logger.info(f"Voice output: {'ENABLED' if config.ENABLE_TTS else 'DISABLED'}")
logger.info(f"Control panel: http://127.0.0.1:{config.CONTROL_PANEL_PORT}")

# Intents - single declaration with all required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.presences = True
intents.voice_states = True

# Client - single instance
client = discord.Client(intents=intents)
mention_translator = MentionTranslator(client)

# Global State
start_time = datetime.now()
message_manager = None
background_processor = None
passive_monitor = None
message_crawler = None
voice_listener = None
audio_processor = None
voice_pipeline = None
tts_engine = None
voice_output_manager = None
voice_manager = None
voice_behavior_manager = None

# Database Protector
db_protector = DatabaseProtector("./bot_data")

# Initialize database protection system
logger.info("Initializing Database Protection System...")
database_protector = get_database_protector()

# Validate databases before startup
try:
    logger.info("Validating database integrity...")
    validation_results = database_protector.validate_all_databases()

    if validation_results['overall_status'] == 'critical':
        logger.error("CRITICAL database corruption detected!")
        logger.error("Available backups:")
        for backup in database_protector.list_backups()[:5]:
            logger.error(f"  {backup['created_at']}: {backup['backup_type']}")

        raise DatabaseValidationError("Critical database corruption detected - cannot start")

    elif validation_results['overall_status'] == 'recoverable':
        logger.warning("Recoverable database issues detected - attempting recovery...")
        recovery_success = database_protector.recover_from_corruption(validation_results)
        if not recovery_success:
            logger.error("Database recovery failed!")
            raise DatabaseRecoveryError("Database recovery failed - cannot start")
        logger.info("Database recovery successful!")

    else:
        logger.info("Database validation passed")

except Exception as e:
    logger.error(f"Database validation failed: {e}")
    logger.error("Try restoring from a backup manually")
    raise

# Set up graceful shutdown handlers
database_protector.setup_graceful_shutdown()

# Bot statistics
stats = {
    'messages_received': 0,
    'messages_processed': 0,
    'messages_ignored': 0,
    'passive_messages': 0,
    'commands_executed': 0,
    'corrections_detected': 0,
    'voice_events': 0,
    'voice_messages': 0,
    'errors': 0,
    'start_time': None
}


@client.event
async def on_ready():
    """Called when bot successfully connects to Discord"""
    global message_manager, background_processor, passive_monitor, message_crawler
    global transcriber, audio_processor, voice_listener, voice_pipeline, tts_engine
    global voice_behavior_manager

    try:
        stats['start_time'] = asyncio.get_running_loop().time()

        # Startup banner
        logger.info("serin.startup", extra={
            "version": "1.0.0",
            "voice_enabled": config.ENABLE_VOICE,
            "tts_enabled": config.ENABLE_TTS,
            "voice_mode": config.VOICE_RECEIVER_MODE,
            "llm_model": config.LLM_MODEL,
            "allowed_channels": len(config.ALLOWED_CHANNEL_IDS),
            "qdrant_host": config.QDRANT_HOST,
        })

        # Create startup backup
        try:
            database_protector.create_backup("startup", force=True)
            logger.info("system.startup_backup_created")
        except Exception as e:
            logger.warning("system.startup_backup_failed", extra={"error": str(e)})

        logger.info("=" * 60)
        logger.info(f"Logged in as {client.user}!")
        logger.info(f"Bot ID: {client.user.id}")
        logger.info(f"Connected to {len(client.guilds)} server(s)")
        logger.info("=" * 60)

        # Show server info
        total_channels = 0
        total_voice_channels = 0
        for guild in client.guilds:
            logger.info(f"Server: {guild.name} (ID: {guild.id})")
            cached = mention_translator.cache_guild_members(guild)
            logger.info(f"   Cached {cached} members")
            allowed_channels = [ch for ch in guild.text_channels if ch.id in config.ALLOWED_CHANNEL_IDS]
            total_channels += len(guild.text_channels)
            total_voice_channels += len(guild.voice_channels)
            logger.info(f"   Response channels: {len(allowed_channels)}")
            logger.info(f"   Monitoring: {len(guild.text_channels)} text channels")
            logger.info(f"   Voice channels: {len(guild.voice_channels)}")

        logger.info(f"Total: {total_channels} text, {total_voice_channels} voice channels")
        logger.info("-" * 60)

        # Initialize LLM
        logger.info("Initializing main LLM model...")
        try:
            await initialize_llama()
            logger.info("Main LLM ready!")
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            logger.error("Bot will continue but responses will fail")

        # Initialize Memory System (Qdrant)
        logger.info("Initializing Memory System...")
        try:
            memory_system = QdrantMemorySystem(
                data_dir="./bot_data",
                qdrant_host=config.QDRANT_HOST,
                qdrant_port=config.QDRANT_PORT
            )
            logger.info("Qdrant Memory System initialized!")
        except Exception as e:
            logger.exception(f"Failed to start Memory System: {e}")
            raise

        # Initialize background processor
        logger.info("Initializing background processor...")
        try:
            background_processor = BackgroundProcessor(memory_system)
            await background_processor.start()
            logger.info("Background processor started!")
        except Exception as e:
            logger.error(f"Failed to start background processor: {e}")

        # Initialize passive monitor
        logger.info("Initializing passive monitor...")
        passive_monitor = PassiveMonitor(
            memory_system,
            background_processor,
            config.ALLOWED_CHANNEL_IDS,
            mention_translator
        )
        logger.info("Passive monitor ready!")

        # Initialize message crawler
        logger.info("Initializing message crawler...")
        message_crawler = MessageCrawler(
            client,
            memory_system,
            background_processor,
            mention_translator
        )
        await message_crawler.start()
        logger.info("Message crawler started!")

        # Initialize Memory Sync Monitor
        logger.info("Initializing Memory Sync Monitor...")
        try:
            sync_monitor = MemorySyncMonitor(memory_system, background_processor, message_crawler)
            await sync_monitor.start_monitoring()
            logger.info("Memory Sync Monitor started!")
        except Exception as e:
            logger.error(f"Failed to start sync monitor: {e}")

        # TIER 6: Initialize voice components
        if config.ENABLE_VOICE:
            logger.info("=" * 60)
            logger.info("INITIALIZING VOICE INPUT")
            logger.info("=" * 60)

            # 1. Whisper Transcriber
            transcriber = WhisperTranscriber()

            # 2. Voice Memory Pipeline
            voice_pipeline = VoiceMemoryPipeline(
                memory_system=memory_system,
                background_processor=None,
                message_manager=message_manager
            )

            # 3. Audio Stream Processor
            audio_processor = AudioStreamProcessor(
                transcriber=transcriber,
                voice_pipeline=voice_pipeline,
                silence_threshold=1.5,
                llm_connector=serin.messaging.response_generator.llama
            )

            # 4. Voice Listener
            voice_listener = VoiceListener(client, audio_processor)

            # Start processor
            await audio_processor.start()
            logger.info(f"Voice input system fully initialized! (mode: {config.VOICE_RECEIVER_MODE})")

        # TIER 7: Initialize TTS (if enabled)
        voice_output_manager = None
        if config.ENABLE_TTS:
            logger.info("=" * 60)
            logger.info("INITIALIZING TTS OUTPUT")
            logger.info("=" * 60)

            try:
                tts_engine = TTSEngine()

                # Initialize Voice Manager (for cloning)
                from tts_voice_manager import TTSVoiceManager
                voice_manager = TTSVoiceManager()

                # Initialize Voice Output Manager
                if voice_listener:
                    voice_output_manager = VoiceOutputManager(tts_engine, voice_listener)
                    await voice_output_manager.start()

                    # Attach to Audio Processor (for interrupts)
                    if audio_processor:
                        audio_processor.voice_output_manager = voice_output_manager
                        logger.info("Voice Output Manager attached to Audio Processor")

                    logger.info("Voice Output Manager started!")
                else:
                    logger.warning("Voice Output requires Voice Input (VoiceListener) to be enabled")

            except Exception as e:
                logger.error(f"Failed to initialize TTS: {e}")
                config.ENABLE_TTS = False

        # Initialize MessageManager (SINGLE instance with all dependencies)
        message_manager = EnhancedMessageManagerV3(
            client,
            mention_translator,
            memory_system,
            voice_output_manager=voice_output_manager
        )
        await message_manager.start()

        # Build the MessagePipeline and attach it to the manager
        logger.info("Building MessagePipeline...")
        from serin.messaging.pipeline import MessagePipeline
        from serin.utils.thinking_filter import get_thinking_filter
        from serin.messaging.response_generator import get_response_natural
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
        logger.info("MessagePipeline built and attached to manager!")

        # Initialize Voice Behavior Manager (auto join/leave based on mood)
        if voice_listener and hasattr(message_manager, 'personality'):
            try:
                voice_behavior_manager = VoiceBehaviorManager(
                    personality=message_manager.personality,
                    voice_listener=voice_listener,
                    voice_tracker=message_manager.voice_tracker if hasattr(message_manager, 'voice_tracker') else None,
                )
                await voice_behavior_manager.start()
                logger.info("Voice behavior manager started!")
            except Exception as e:
                logger.error(f"Failed to start voice behavior manager: {e}")
                voice_behavior_manager = None

        # Wire voice action callback (structured output pipeline)
        if voice_listener and message_manager and hasattr(message_manager, 'voice_action_callback'):
            async def _handle_voice_action(decision: dict, user_id: str, guild_id: int) -> dict:
                """Execute voice actions decided by the LLM pipeline."""
                action = decision.get('action')
                result = {'executed': False, 'message': ''}

                if action == 'join' and voice_listener:
                    tracker = message_manager.voice_tracker if hasattr(message_manager, 'voice_tracker') else None
                    if tracker and tracker.is_in_voice(user_id):
                        info = tracker.get_voice_info(user_id)
                        if info:
                            success = await voice_listener.join_channel(
                                guild_id, int(info['channel_id'])
                            )
                            if success:
                                if voice_behavior_manager:
                                    voice_behavior_manager._vc_join_time[guild_id] = datetime.now()
                                    voice_behavior_manager._voice_session_guilds.add(guild_id)
                                    voice_behavior_manager.stats['auto_joins'] += 1
                                    voice_behavior_manager._pending_joins.pop(guild_id, None)
                                result = {'executed': True, 'message': 'joined'}
                                logger.info(" Voice pipeline: joined VC (LLM decided)")
                    if not result['executed']:
                        result = {'executed': False, 'message': 'user_not_in_vc'}
                        logger.info(" Voice pipeline: user not in VC, LLM will respond naturally")

                elif action == 'leave' and voice_listener:
                    await voice_listener.leave_channel(guild_id)
                    if voice_behavior_manager:
                        voice_behavior_manager.stats['auto_leaves'] += 1
                    result = {'executed': True, 'message': 'left'}
                    logger.info(" Voice pipeline: left VC (LLM decided)")

                return result

            message_manager.voice_action_callback = _handle_voice_action
            logger.info("Voice action callback wired to message manager")

        # Attach message manager to voice pipeline
        if voice_pipeline:
            voice_pipeline.message_manager = message_manager

        # Attach background processor to voice pipeline
        if voice_pipeline:
            voice_pipeline.bg_processor = background_processor

        # Initialize control panel state
        logger.info("Initializing control panel...")

        init_bot_state(
            discord_client=client,
            message_manager=message_manager,
            background_processor=background_processor,
            passive_monitor=passive_monitor,
            message_crawler=message_crawler,
            memory_system=memory_system,
            voice_listener=voice_listener,
            tts_engine=tts_engine,
            voice_manager=voice_manager if config.ENABLE_TTS else None
        )

        # Add voice behavior manager to control panel state
        from serin.control_panel.server import bot_state
        bot_state['voice_behavior_manager'] = voice_behavior_manager

        # Inject Broadcaster into ResponseController (for Decision Feed)
        if message_manager and hasattr(message_manager, 'response_controller'):
            from serin.control_panel.server import broadcast_event
            message_manager.response_controller.set_broadcaster(broadcast_event)
            logger.info("Decision broadcaster connected to ResponseController")

        # Start web server
        try:
            asyncio.create_task(start_server(port=config.CONTROL_PANEL_PORT))
            logger.info(f"Control panel started: http://127.0.0.1:{config.CONTROL_PANEL_PORT}")
        except Exception as e:
            logger.exception(f"Failed to start control panel: {e}")

        logger.info("=" * 60)
        logger.info("Bot initialization complete!")
        logger.info("DATABASE PROTECTION: ENABLED")
        logger.info("   Pre-startup validation")
        logger.info("   Automatic backup (1hr intervals)")
        logger.info("   Corruption recovery")
        logger.info("   Graceful shutdown")
        logger.info("FEATURES:")
        logger.info("   Web Control Panel (localhost:8080)")
        logger.info(f"   {'ENABLED' if config.ENABLE_VOICE else 'DISABLED'} Voice Input (Whisper transcription)")
        logger.info(f"   {'ENABLED' if config.ENABLE_TTS else 'DISABLED'} Voice Output (Coqui TTS)")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Critical error in on_ready: {e}")
        traceback.print_exc()
        await client.close()

@client.event
async def on_message(message):
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
                    f"**Bot Statistics**\n"
                    f"Uptime: {hours}h {minutes}m\n"
                    f"Messages Received: {stats['messages_received']}\n"
                    f"Active Processed: {stats['messages_processed']}\n"
                    f"Passive Monitored: {stats['passive_messages']}\n"
                    f"Responses Generated: {mgr_stats.get('responses_generated', 0)}\n"
                    f"Corrections Learned: {mgr_stats.get('corrections_detected', 0)}\n\n"
                    f"**Memory System**\n"
                    f"Total Memories: {mem_stats.get('total_memories', 0)}\n"
                    f"Total Users: {mem_stats.get('total_users', 0)}\n"
                    f"Strong Relationships: {mem_stats.get('strong_relationships', 0)}\n\n"
                    f"**Background Processing**\n"
                    f"Queue Size: {bg_stats.get('queue_size', 0)}\n"
                    f"Summaries Created: {bg_stats.get('summaries_created', 0)}\n"
                    f"Processed: {bg_stats.get('total_processed', 0)}\n\n"
                    f"**Voice Tracking**\n"
                    f"Users in Voice: {voice_stats.get('users_in_voice', 0)}\n"
                    f"Active Sessions: {voice_stats.get('active_sessions', 0)}\n\n"
                    f"**Cross-Server**\n"
                    f"Servers: {passive_stats.get('servers_monitored', 0)}\n"
                    f"Channels: {passive_stats.get('channels_monitored', 0)}\n\n"
                    f"**Message Crawler**\n"
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
async def on_voice_state_update(member, before, after):
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
async def on_error(event, *args, **kwargs):
    """Handle Discord.py errors"""
    stats['errors'] += 1
    logger.exception(f"Discord error in event '{event}'")


async def maintenance_task():
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

async def main():
    """Main async function with database protection"""
    try:
        logger.info("=" * 60)
        logger.info("Serin Discord Bot")
        logger.info("WITH DATABASE PROTECTION")
        logger.info("=" * 60)

        if config.DEBUG_MODE:
            logger.info("Debug mode enabled - verbose logging active")

        logger.info(f"Configuration:")
        logger.info(f"   Trace messages: {config.TRACE_MESSAGES}")
        logger.info(f"   Response channels: {len(config.ALLOWED_CHANNEL_IDS)}")
        logger.info(f"   Monitoring: ALL channels (passive learning)")
        logger.info(f"   Maintenance interval: {config.MAINTENANCE_INTERVAL_HOURS}h")
        logger.info(f"   Cross-server memory: ENABLED")
        logger.info(f"   Voice tracking: {config.ENABLE_VOICE}")
        logger.info(f"   Multi-model: ENABLED (via factory)")
        logger.info(f"   Temporal awareness: ENABLED")
        logger.info(f"   Correction learning: ENABLED")
        logger.info(f"   Database Protection: ENABLED")
        logger.info("=" * 60)

        # Set up discord client reference
        serin.messaging.response_generator.discord_client = client
        logger.debug("Discord client reference set")

        MAX_RETRIES = 5
        retry_count = 0

        while retry_count < MAX_RETRIES:
            try:
                async with client:
                    # Start maintenance task (only here, not in on_ready)
                    logger.info("Starting maintenance task...")
                    asyncio.create_task(maintenance_task())
                    logger.debug("Maintenance task scheduled")

                    # Start Discord client with retry
                    logger.info(f"Connecting to Discord (Attempt {retry_count + 1}/{MAX_RETRIES})...")
                    await client.start(cast(str, config.DISCORD_TOKEN))
                    break

            except (aiohttp.ClientError, discord.ConnectionClosed, discord.GatewayNotFound) as e:
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    wait_time = min(30, 2 ** retry_count)
                    logger.warning(f"Connection attempt {retry_count} failed: {e}")
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect after {MAX_RETRIES} attempts: {e}")
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
