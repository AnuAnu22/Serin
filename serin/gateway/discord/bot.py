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

from datetime import datetime

import discord
from dotenv import load_dotenv

# Import centralized config
from serin.config.config import config

# TIER 1: Core Message Processing
from serin.gateway.voice_system.tts_engine import TTSEngine
from serin.ops.background import BackgroundProcessor

# TIER 3: Background Processing
from serin.ops.passive_monitor import PassiveMonitor
from serin.pipeline.ingest.context.mention_translator import MentionTranslator
from serin.pipeline.ingest.core.manager import EnhancedMessageManagerV3

# TIER 4: Message Crawler
from serin.pipeline.ingest.sync.crawler import MessageCrawler
from serin.state.db_protect import (
    DatabaseProtector,
    DatabaseRecoveryError,
    DatabaseValidationError,
    get_database_protector,
)
from serin.state.logger import logger

# TIER 6: Import voice and control panel components
voice_available = False
try:
    from serin.gateway.voice_system.listener import VoiceListener
    from serin.gateway.voice_system.output import VoiceOutputManager
    from serin.gateway.voice_system.processor import (
        AudioStreamProcessor,
        VoiceBehaviorManager,
    )
    from serin.gateway.voice_transcribe.pipeline import VoiceMemoryPipeline
    from serin.gateway.voice_transcribe.transcriber import WhisperTranscriber
    voice_available = True
except Exception:
    VoiceListener = AudioStreamProcessor = WhisperTranscriber = None  # type: ignore[assignment,misc]
    VoiceMemoryPipeline = VoiceOutputManager = VoiceBehaviorManager = None  # type: ignore[assignment,misc]
    logger.warning("Voice dependencies not available. Voice features disabled.")

# Load environment variables
load_dotenv()

logger.info("Loading Discord.py...")
logger.info("Loading AI components...")

# ==================================================================================
# CONFIGURATION
# ==================================================================================

# Validate token
if not config.DISCORD_TOKEN:
    raise OSError("DISCORD_TOKEN environment variable not set")

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
logger.info("Will MONITOR all channels (passive learning)")
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
start_time: datetime = datetime.now()
message_manager: EnhancedMessageManagerV3 | None = None
background_processor: BackgroundProcessor | None = None
passive_monitor: PassiveMonitor | None = None
message_crawler: MessageCrawler | None = None
voice_listener: "VoiceListener | None" = None
audio_processor: "AudioStreamProcessor | None" = None
voice_pipeline: "VoiceMemoryPipeline | None" = None
tts_engine: TTSEngine | None = None
voice_output_manager: "VoiceOutputManager | None" = None
voice_manager: "VoiceMemoryPipeline | None" = None
voice_behavior_manager: "VoiceBehaviorManager | None" = None

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
stats: dict[str, int | float | None] = {
    'messages_received': 0,
    'messages_processed': 0,
    'messages_ignored': 0,
    'passive_messages': 0,
    'commands_executed': 0,
    'corrections_detected': 0,
    'voice_events': 0,
    'voice_messages': 0,
    'errors': 0,
    'start_time': None,
}
