"""Bot startup — on_ready initialization sequence."""
import asyncio
import traceback
from datetime import datetime
from serin.state.logger import logger


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
