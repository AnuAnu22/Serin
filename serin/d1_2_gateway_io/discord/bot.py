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

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, cast

import discord
from dotenv import load_dotenv

from serin.d1_2_gateway_io._di import get_logger, init_gateway
from serin.d1_3_state_core.logger import logger as _default_logger

# Initialize gateway DI immediately so module-level get_logger() calls work
try:
    get_logger()
except RuntimeError:
    init_gateway(_default_logger)

if TYPE_CHECKING:
    from serin.d1_1_pipeline_flow.ingest.context.mention_translator import (
        MentionTranslator,
    )
    from serin.d1_1_pipeline_flow.ingest.core.manager import EnhancedMessageManagerV3
    from serin.d1_1_pipeline_flow.ingest.sync.crawler import MessageCrawler
    from serin.d1_5_ops_tooling.tts_voice_manager import TTSVoiceManager

from serin.d1_2_gateway_io.voice_system.tts_engine import TTSEngine
from serin.d1_3_state_core.db_protect import (
    DatabaseProtector,
    DatabaseRecoveryError,
    DatabaseValidationError,
    get_database_protector,
)
from serin.d1_4_config_base.config import config
from serin.d1_5_ops_tooling.background import BackgroundProcessor
from serin.d1_5_ops_tooling.passive_monitor import PassiveMonitor

# Voice components — may not be available
voice_available = False
try:
    from serin.d1_2_gateway_io.voice_system.audio.process.audio_processor import (
        AudioStreamProcessor,
    )
    from serin.d1_2_gateway_io.voice_system.audio.process.voice_behavior import (
        VoiceBehaviorManager,
    )
    from serin.d1_2_gateway_io.voice_system.listener import VoiceListener
    from serin.d1_2_gateway_io.voice_system.output import VoiceOutputManager
    from serin.d1_2_gateway_io.voice_transcribe.pipeline import VoiceMemoryPipeline
    from serin.d1_2_gateway_io.voice_transcribe.transcriber import WhisperTranscriber
    voice_available = True
except Exception:
    VoiceListener = AudioStreamProcessor = WhisperTranscriber = None  # type: ignore[assignment,misc]
    VoiceMemoryPipeline = VoiceOutputManager = VoiceBehaviorManager = None  # type: ignore[assignment,misc]

load_dotenv()

get_logger().info("Loading Discord.py...")
get_logger().info("Loading AI components...")

# Validate token
if not config.DISCORD_TOKEN:
    raise OSError("DISCORD_TOKEN environment variable not set")

if not config.ALLOWED_CHANNEL_IDS:
    config.ALLOWED_CHANNEL_IDS = {
        1298593950436954143,
        937365486172254220,
        917111337128165398,
        1383412857164791811
    }
    get_logger().warning("No ALLOWED_CHANNEL_IDS in .env, using defaults")

get_logger().info(f"Starting bot in {'DEBUG' if config.DEBUG_MODE else 'PRODUCTION'} mode")
get_logger().info(f"Will RESPOND in {len(config.ALLOWED_CHANNEL_IDS)} channels")
get_logger().info("Will MONITOR all channels (passive learning)")
get_logger().info(f"Voice input: {'ENABLED' if config.ENABLE_VOICE else 'DISABLED'} ({config.VOICE_RECEIVER_MODE} mode)")
get_logger().info(f"Voice output: {'ENABLED' if config.ENABLE_TTS else 'DISABLED'}")
get_logger().info(f"Control panel: http://127.0.0.1:{config.CONTROL_PANEL_PORT}")

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.presences = True
intents.voice_states = True

# Client - single instance
client = discord.Client(intents=intents)

# mention_translator is initialized in on_ready() via root DI, not at import time
mention_translator: MentionTranslator | None = None

# Global State
start_time: datetime = datetime.now()
message_manager: EnhancedMessageManagerV3 | None = None
background_processor: BackgroundProcessor | None = None
passive_monitor: PassiveMonitor | None = None
message_crawler: MessageCrawler | None = None
voice_listener: VoiceListener | None = None
audio_processor: AudioStreamProcessor | None = None
voice_pipeline: VoiceMemoryPipeline | None = None
tts_engine: TTSEngine | None = None
voice_output_manager: VoiceOutputManager | None = None
voice_manager: TTSVoiceManager | None = None
voice_behavior_manager: VoiceBehaviorManager | None = None

# Database Protector
db_protector = DatabaseProtector("./bot_data")


def init_database_protection() -> None:
    """Validate databases and set up shutdown handlers. Called from on_ready()."""
    get_logger().info("Initializing Database Protection System...")
    database_protector: DatabaseProtector = cast(DatabaseProtector, get_database_protector())

    try:
        get_logger().info("Validating database integrity...")
        validation_results = database_protector.validate_all_databases()

        if validation_results['overall_status'] == 'critical':
            get_logger().error("CRITICAL database corruption detected!")
            get_logger().error("Available backups:")
            for backup in database_protector.list_backups()[:5]:
                get_logger().error(f"  {backup['created_at']}: {backup['backup_type']}")
            raise DatabaseValidationError("Critical database corruption detected - cannot start")

        elif validation_results['overall_status'] == 'recoverable':
            get_logger().warning("Recoverable database issues detected - attempting recovery...")
            recovery_success = database_protector.recover_from_corruption(validation_results)
            if not recovery_success:
                get_logger().error("Database recovery failed!")
                raise DatabaseRecoveryError("Database recovery failed - cannot start")
            get_logger().info("Database recovery successful!")

        else:
            get_logger().info("Database validation passed")

    except Exception as e:
        get_logger().error(f"Database validation failed: {e}")
        get_logger().error("Try restoring from a backup manually")
        raise

    database_protector.setup_graceful_shutdown()


# Bot statistics
stats: dict[str, int | float] = {
    'messages_received': 0,
    'messages_processed': 0,
    'messages_ignored': 0,
    'passive_messages': 0,
    'commands_executed': 0,
    'corrections_detected': 0,
    'voice_events': 0,
    'voice_messages': 0,
    'errors': 0,
    'start_time': 0,
}
