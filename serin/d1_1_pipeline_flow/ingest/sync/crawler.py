"""
Message Crawler - Retroactive Memory System
Continuously syncs with Discord to ensure no messages are missed.

Features:
1. Quick Sync (every 15 min) - Check latest message
2. Deep Validation (every 1 hour) - Check every 100th message for gaps
3. Backfill - Fills missing messages with context-aware processing
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

import discord

from serin.d1_1_pipeline_flow.ingest.sync.backfill import BackfillMixin
from serin.d1_3_state_core.logger import logger

if TYPE_CHECKING:
    from serin.d1_1_pipeline_flow.ingest.context.mention_translator import (
        MentionTranslator,
    )



class MessageCrawler(BackfillMixin):
    def __init__(
        self,
        client: discord.Client,
        memory_system: Any,
        background_processor: Any,
        mention_translator: MentionTranslator,
    ) -> None:
        """
        Initialize message crawler.

        Args:
            client: Discord client
            memory_system: UnifiedMemorySystem instance
            background_processor: BackgroundProcessor instance
            mention_translator: MentionTranslator instance
        """
        self.client = client
        self.memory = memory_system
        self.bg_processor = background_processor
        self.mention_translator = mention_translator

        # Crawler settings
        self.quick_sync_interval = 15 * 60  # 15 minutes
        self.deep_validation_interval = 60 * 60  # 1 hour
        self.max_messages_per_channel = 20000
        self.validation_step = 100  # Check every 100th message

        # Tracking
        self.is_running: bool = False
        self.quick_sync_task: asyncio.Task[None] | None = None
        self.deep_validation_task: asyncio.Task[None] | None = None

        # Stats
        self.stats: dict[str, Any] = {
            'quick_syncs': 0,
            'deep_validations': 0,
            'messages_backfilled': 0,
            'gaps_found': 0,
            'channels_synced': set(),
            'errors': 0
        }

        logger.info(" Message crawler initialized")
        logger.info(f"    Quick sync: every {self.quick_sync_interval/60} minutes")
        logger.info(f"    Deep validation: every {self.deep_validation_interval/60} minutes")
        logger.info(f"    Max messages per channel: {self.max_messages_per_channel}")

    def get_stats(self) -> dict[str, Any]:
        return {
            'quick_syncs': self.stats['quick_syncs'],
            'deep_validations': self.stats['deep_validations'],
            'messages_backfilled': self.stats['messages_backfilled'],
            'gaps_found': self.stats['gaps_found'],
            'channels_synced': len(self.stats['channels_synced']),
            'errors': self.stats['errors'],
        }

    async def start(self) -> None:
        """Start crawler tasks"""
        if self.is_running:
            logger.warning(" Message crawler already running")
            return

        self.is_running = True

        # Start both tasks
        self.quick_sync_task = asyncio.create_task(self._quick_sync_loop())
        self.deep_validation_task = asyncio.create_task(self._deep_validation_loop())

        logger.info(" Message crawler started")

    async def stop(self) -> None:
        """Stop crawler tasks"""
        self.is_running = False

        if self.quick_sync_task:
            self.quick_sync_task.cancel()
        if self.deep_validation_task:
            self.deep_validation_task.cancel()

        logger.info(" Message crawler stopped")

    async def _quick_sync_loop(self) -> None:
        """
        Quick sync loop - checks latest message every 15 minutes.
        If latest Discord message matches latest SQL message, sleep.
        Otherwise, backfill missing messages.
        """
        logger.info(" Quick sync loop started")

        while self.is_running:
            try:
                await asyncio.sleep(self.quick_sync_interval)

                logger.info("=" * 60)
                logger.info(" QUICK SYNC - Checking for new messages")
                logger.info("=" * 60)

                synced_count = 0

                # Check all guilds
                for guild in self.client.guilds:
                    for channel in guild.text_channels:
                        try:
                            synced = await self._quick_sync_channel(channel)
                            if synced > 0:
                                synced_count += synced
                                self.stats['channels_synced'].add(str(channel.id))
                        except Exception as e:
                            logger.error(f" Error syncing #{channel.name}: {e}")
                            self.stats['errors'] += 1

                self.stats['quick_syncs'] += 1
                logger.info(f" Quick sync complete - {synced_count} messages backfilled")
                logger.info("=" * 60)

            except asyncio.CancelledError:
                logger.info(" Quick sync loop cancelled")
                break
            except Exception as e:
                logger.error(f" Error in quick sync loop: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(60)

    async def _quick_sync_channel(self, channel: discord.channel.TextChannel) -> int:
        """
        Quick sync a single channel.

        Returns:
            Number of messages backfilled
        """
        try:
            # Get latest message from Discord
            discord_messages = [msg async for msg in channel.history(limit=1)]

            if not discord_messages:
                return 0  # Empty channel

            latest_discord = discord_messages[0]

            # Get latest message from SQL
            latest_sql = self.memory.get_latest_message(str(channel.id))

            # If no SQL message, this is first sync
            if not latest_sql:
                logger.info(f" First sync for #{channel.name} - backfilling up to {self.max_messages_per_channel} messages")
                return await self._backfill_channel(channel, limit=self.max_messages_per_channel)

            # Compare message IDs (ensure proper type conversion)
            if str(latest_sql['message_id']) == str(latest_discord.id):
                logger.debug(f"✓ #{channel.name} - Up to date")
                return 0

            # Messages are different - backfill from latest SQL to latest Discord
            logger.info(f" #{channel.name} - New messages detected, backfilling...")

            # Get SQL timestamp - handle both string and datetime formats
            def safe_datetime_convert(timestamp: str | datetime) -> datetime:
                """Safely convert timestamp to datetime, handling both string and datetime inputs"""
                if isinstance(timestamp, str):
                    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return timestamp

            sql_timestamp = safe_datetime_convert(latest_sql['timestamp'])

            # Fetch messages after SQL timestamp
            backfilled = await self._backfill_from_timestamp(channel, sql_timestamp)

            return backfilled

        except Exception as e:
            logger.error(f" Error in quick sync for #{channel.name}: {e}")
            return 0

    async def _deep_validation_loop(self) -> None:
        """
        Deep validation loop - checks every 100th message every hour.
        Processes channels sequentially with delays to avoid rate limits.
        """
        logger.info(" Deep validation loop started")

        # Wait 10 minutes before first deep validation (let quick sync run first)
        await asyncio.sleep(10 * 60)

        while self.is_running:
            try:
                await asyncio.sleep(self.deep_validation_interval)

                logger.info("=" * 60)
                logger.info(" DEEP VALIDATION - Checking for gaps")
                logger.info("=" * 60)

                total_gaps = 0
                total_backfilled = 0
                channel_count = 0

                #  Process guilds and channels SEQUENTIALLY
                for guild in self.client.guilds:
                    logger.info(f" Validating server: {guild.name}")

                    for channel in guild.text_channels:
                        try:
                            channel_count += 1
                            logger.info(f"   Channel {channel_count}: #{channel.name}")

                            gaps, backfilled = await self._deep_validate_channel(channel)
                            total_gaps += gaps
                            total_backfilled += backfilled

                            #  10 second delay between channels
                            await asyncio.sleep(10)

                        except Exception as e:
                            logger.error(f" Error validating #{channel.name}: {e}")
                            self.stats['errors'] += 1

                self.stats['deep_validations'] += 1
                self.stats['gaps_found'] += total_gaps
                self.stats['messages_backfilled'] += total_backfilled

                logger.info(f" Deep validation complete - {total_gaps} gaps found, {total_backfilled} messages backfilled")
                logger.info("=" * 60)

            except asyncio.CancelledError:
                logger.info(" Deep validation loop cancelled")
                break
            except Exception as e:
                logger.error(f" Error in deep validation loop: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(60)

    async def _deep_validate_channel(self, channel: discord.TextChannel) -> tuple[int, int]:
        """
        Deep validate a channel by checking every 100th message.
        Uses batched requests to avoid rate limits.

        Returns:
            (gaps_found, messages_backfilled)
        """
        try:
            gaps_found = 0
            messages_backfilled = 0

            # Get message count from SQL
            sql_count = self.memory.get_message_count(str(channel.id))

            if sql_count == 0:
                return 0, 0

            # Check every 100th message
            check_points = list(range(0, min(sql_count, self.max_messages_per_channel), self.validation_step))

            logger.debug(f" Validating #{channel.name} - {len(check_points)} checkpoints")

            #  BATCH PROCESSING: Process 10 checkpoints at a time with delays
            batch_size = 10
            for i in range(0, len(check_points), batch_size):
                batch = check_points[i:i+batch_size]

                logger.debug(f"   Checking batch {i//batch_size + 1}/{len(check_points)//batch_size + 1}")

                for checkpoint in batch:
                    # Get message at checkpoint from SQL
                    sql_msg = self.memory.get_message_at_position(str(channel.id), checkpoint)

                    if not sql_msg:
                        continue

                    # Check if this message exists in Discord
                    try:
                        discord_msg = await channel.fetch_message(int(sql_msg['message_id']))  # noqa: F841 — used implicitly in try/except flow
                    except Exception:
                        # Message doesn't exist or deleted - this is a gap
                        gaps_found += 1
                        logger.warning(f" Gap found at position {checkpoint} in #{channel.name}")

                        # Backfill around this gap (±50 messages)
                        backfilled = await self._backfill_around_position(channel, sql_msg['timestamp'], 50)
                        messages_backfilled += backfilled

                #  Delay between batches to avoid rate limit
                if i + batch_size < len(check_points):
                    await asyncio.sleep(10)  # 10 second delay between batches

            return gaps_found, messages_backfilled

        except Exception as e:
            logger.error(f" Error in deep validation for #{channel.name}: {e}")
            return 0, 0
