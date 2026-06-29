"""
Message Crawler - Retroactive Memory System
Continuously syncs with Discord to ensure no messages are missed.

Features:
1. Quick Sync (every 15 min) - Check latest message
2. Deep Validation (every 1 hour) - Check every 100th message for gaps
3. Backfill - Fills missing messages with context-aware processing
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import discord
from logger_config import logger



class MessageCrawler:
    def __init__(self, client,memory_system, background_processor, mention_translator):
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
        self.is_running = False
        self.quick_sync_task = None
        self.deep_validation_task = None
        
        # Stats
        self.stats = {
            'quick_syncs': 0,
            'deep_validations': 0,
            'messages_backfilled': 0,
            'gaps_found': 0,
            'channels_synced': set(),
            'errors': 0
        }
        
        logger.info("✅ Message crawler initialized")
        logger.info(f"   ⚡ Quick sync: every {self.quick_sync_interval/60} minutes")
        logger.info(f"   🔍 Deep validation: every {self.deep_validation_interval/60} minutes")
        logger.info(f"   📊 Max messages per channel: {self.max_messages_per_channel}")
    
    async def start(self):
        """Start crawler tasks"""
        if self.is_running:
            logger.warning("⚠️ Message crawler already running")
            return
        
        self.is_running = True
        
        # Start both tasks
        self.quick_sync_task = asyncio.create_task(self._quick_sync_loop())
        self.deep_validation_task = asyncio.create_task(self._deep_validation_loop())
        
        logger.info("🚀 Message crawler started")
    
    async def stop(self):
        """Stop crawler tasks"""
        self.is_running = False
        
        if self.quick_sync_task:
            self.quick_sync_task.cancel()
        if self.deep_validation_task:
            self.deep_validation_task.cancel()
        
        logger.info("🛑 Message crawler stopped")
    
    async def _quick_sync_loop(self):
        """
        Quick sync loop - checks latest message every 15 minutes.
        If latest Discord message matches latest SQL message, sleep.
        Otherwise, backfill missing messages.
        """
        logger.info("⚡ Quick sync loop started")
        
        while self.is_running:
            try:
                await asyncio.sleep(self.quick_sync_interval)
                
                logger.info("=" * 60)
                logger.info("⚡ QUICK SYNC - Checking for new messages")
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
                            logger.error(f"❌ Error syncing #{channel.name}: {e}")
                            self.stats['errors'] += 1
                
                self.stats['quick_syncs'] += 1
                logger.info(f"✅ Quick sync complete - {synced_count} messages backfilled")
                logger.info("=" * 60)
                
            except asyncio.CancelledError:
                logger.info("🛑 Quick sync loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in quick sync loop: {e}")
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
                logger.info(f"📥 First sync for #{channel.name} - backfilling up to {self.max_messages_per_channel} messages")
                return await self._backfill_channel(channel, limit=self.max_messages_per_channel)
            
            # Compare message IDs (ensure proper type conversion)
            if str(latest_sql['message_id']) == str(latest_discord.id):
                logger.debug(f"✓ #{channel.name} - Up to date")
                return 0
            
            # Messages are different - backfill from latest SQL to latest Discord
            logger.info(f"📥 #{channel.name} - New messages detected, backfilling...")
            
            # Get SQL timestamp - handle both string and datetime formats
            def safe_datetime_convert(timestamp):
                """Safely convert timestamp to datetime, handling both string and datetime inputs"""
                if isinstance(timestamp, str):
                    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return timestamp
            
            sql_timestamp = safe_datetime_convert(latest_sql['timestamp'])
            
            # Fetch messages after SQL timestamp
            backfilled = await self._backfill_from_timestamp(channel, sql_timestamp)
            
            return backfilled
            
        except Exception as e:
            logger.error(f"❌ Error in quick sync for #{channel.name}: {e}")
            return 0
    
    async def _deep_validation_loop(self):
        """
        Deep validation loop - checks every 100th message every hour.
        Processes channels sequentially with delays to avoid rate limits.
        """
        logger.info("🔍 Deep validation loop started")
        
        # Wait 10 minutes before first deep validation (let quick sync run first)
        await asyncio.sleep(10 * 60)
        
        while self.is_running:
            try:
                await asyncio.sleep(self.deep_validation_interval)
                
                logger.info("=" * 60)
                logger.info("🔍 DEEP VALIDATION - Checking for gaps")
                logger.info("=" * 60)
                
                total_gaps = 0
                total_backfilled = 0
                channel_count = 0
                
                # ✅ Process guilds and channels SEQUENTIALLY
                for guild in self.client.guilds:
                    logger.info(f"🔍 Validating server: {guild.name}")
                    
                    for channel in guild.text_channels:
                        try:
                            channel_count += 1
                            logger.info(f"   Channel {channel_count}: #{channel.name}")
                            
                            gaps, backfilled = await self._deep_validate_channel(channel)
                            total_gaps += gaps
                            total_backfilled += backfilled
                            
                            # ✅ 10 second delay between channels
                            await asyncio.sleep(10)
                            
                        except Exception as e:
                            logger.error(f"❌ Error validating #{channel.name}: {e}")
                            self.stats['errors'] += 1
                
                self.stats['deep_validations'] += 1
                self.stats['gaps_found'] += total_gaps
                self.stats['messages_backfilled'] += total_backfilled
                
                logger.info(f"✅ Deep validation complete - {total_gaps} gaps found, {total_backfilled} messages backfilled")
                logger.info("=" * 60)
                
            except asyncio.CancelledError:
                logger.info("🛑 Deep validation loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in deep validation loop: {e}")
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
            
            logger.debug(f"🔍 Validating #{channel.name} - {len(check_points)} checkpoints")
            
            # ✅ BATCH PROCESSING: Process 10 checkpoints at a time with delays
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
                        discord_msg = await channel.fetch_message(int(sql_msg['message_id']))
                        # Message exists, continue
                    except Exception:
                        # Message doesn't exist or deleted - this is a gap
                        gaps_found += 1
                        logger.warning(f"⚠️ Gap found at position {checkpoint} in #{channel.name}")
                        
                        # Backfill around this gap (±50 messages)
                        backfilled = await self._backfill_around_position(channel, sql_msg['timestamp'], 50)
                        messages_backfilled += backfilled
                
                # ✅ Delay between batches to avoid rate limit
                if i + batch_size < len(check_points):
                    await asyncio.sleep(10)  # 10 second delay between batches
            
            return gaps_found, messages_backfilled
            
        except Exception as e:
            logger.error(f"❌ Error in deep validation for #{channel.name}: {e}")
            return 0, 0

    async def _backfill_channel(self, channel: discord.TextChannel, limit: int = None) -> int:
        """
        Backfill entire channel up to limit.
        Robust implementation with rate limiting and batching.
        """
        if limit is None:
            limit = self.max_messages_per_channel
        
        try:
            logger.info(f"📥 Backfilling #{channel.name} (up to {limit} messages)")
            
            backfilled = 0
            batch = []
            batch_size = 100  # Process in chunks of 100
            
            # Use an iterator to control the flow manually
            history_iterator = channel.history(limit=limit, oldest_first=True)
            
            while True:
                try:
                    # Fetch next message with retry logic for rate limits
                    try:
                        message = await anext(history_iterator)
                    except StopAsyncIteration:
                        break
                    except discord.HTTPException as e:
                        if e.status == 429:
                            retry_after = float(e.response.headers.get('Retry-After', 5))
                            logger.warning(f"⚠️ Rate limited in #{channel.name}. Sleeping for {retry_after}s...")
                            await asyncio.sleep(retry_after + 1)
                            continue
                        else:
                            raise e
                    
                    # Skip bot messages
                    if message.author.bot:
                        continue
                    
                    # Clean content
                    cleaned_content = self.mention_translator.clean_for_bot(message.content, message)
                    cleaned_content = self.mention_translator.clean_bot_self_mention(cleaned_content)
                    
                    # Store in SQL (Fast)
                    self.memory.store_recent_message(
                        user_id=str(message.author.id),
                        username=message.author.display_name,
                        channel_id=str(channel.id),
                        content=cleaned_content,
                        message_id=str(message.id),
                        timestamp=message.created_at
                    )
                    
                    # Add to batch
                    batch.append({
                        'content': cleaned_content,
                        'user_id': str(message.author.id),
                        'username': message.author.display_name,
                        'channel_id': str(channel.id),
                        'server_id': str(channel.guild.id),
                        'timestamp': message.created_at
                    })
                    
                    backfilled += 1
                    
                    # Process batch when full
                    if len(batch) >= batch_size:
                        logger.debug(f"📥 Processing batch of {len(batch)} messages...")
                        # Process batch (this queues them for background work)
                        for msg in batch:
                            self.bg_processor.queue_message(**msg)
                        
                        batch = []
                        
                        # Explicit Rate Limit Delay
                        # Discord allows ~50 requests/sec, but history is expensive.
                        # We sleep 2 seconds every 100 messages to be safe.
                        await asyncio.sleep(2.0)
                        logger.info(f"📥 Backfilled {backfilled} messages from #{channel.name}...")
                
                except Exception as e:
                    logger.error(f"❌ Error processing message in backfill: {e}")
                    continue
            
            # Process remaining batch
            if batch:
                for msg in batch:
                    self.bg_processor.queue_message(**msg)
            
            logger.info(f"✅ Backfilled {backfilled} messages from #{channel.name}")
            return backfilled
            
        except Exception as e:
            logger.error(f"❌ Error backfilling #{channel.name}: {e}")
            return 0
    
    async def _backfill_from_timestamp(self, channel: discord.TextChannel, after: datetime) -> int:
        """
        Backfill messages after a specific timestamp.
        
        Returns:
            Number of messages backfilled
        """
        try:
            backfilled = 0
            batch = []
            
            async for message in channel.history(after=after, oldest_first=True):
                if message.author.bot:
                    continue
                
                # Clean content
                cleaned_content = self.mention_translator.clean_for_bot(message.content, message)
                cleaned_content = self.mention_translator.clean_bot_self_mention(cleaned_content)
                
                # Store in SQL
                self.memory.store_recent_message(
                    user_id=str(message.author.id),
                    username=message.author.display_name,
                    channel_id=str(channel.id),
                    content=cleaned_content,
                    message_id=str(message.id),
                    timestamp=message.created_at
                )
                
                # Add to batch
                batch.append({
                    'content': cleaned_content,
                    'user_id': str(message.author.id),
                    'username': message.author.display_name,
                    'channel_id': str(channel.id),
                    'server_id': str(channel.guild.id),
                    'timestamp': message.created_at
                })
                
                backfilled += 1
                
                # Process batch of 5
                if len(batch) >= 5:
                    await self._process_batch_with_context(batch)
                    batch = []
            
            # Process remaining
            if batch:
                await self._process_batch_with_context(batch)
            
            return backfilled
            
        except Exception as e:
            logger.error(f"❌ Error backfilling from timestamp: {e}")
            return 0
    
    async def _backfill_around_position(self, channel: discord.TextChannel, timestamp: str, radius: int = 50) -> int:
        """
        Backfill messages around a specific timestamp (±radius messages).
        
        Returns:
            Number of messages backfilled
        """
        try:
            # Handle both string and datetime timestamps
            def safe_datetime_convert(ts_input):
                """Safely convert timestamp to datetime, handling both string and datetime inputs"""
                if isinstance(ts_input, str):
                    return datetime.fromisoformat(ts_input.replace('Z', '+00:00'))
                return ts_input
            
            ts = safe_datetime_convert(timestamp)
            before_ts = ts + timedelta(seconds=1)
            after_ts = ts - timedelta(seconds=1)
            
            backfilled = 0
            
            # Get messages before
            async for message in channel.history(before=before_ts, limit=radius):
                if message.author.bot:
                    continue
                
                cleaned_content = self.mention_translator.clean_for_bot(message.content, message)
                
                self.memory.store_recent_message(
                    user_id=str(message.author.id),
                    username=message.author.display_name,
                    channel_id=str(channel.id),
                    content=cleaned_content,
                    message_id=str(message.id),
                    timestamp=message.created_at
                )
                
                backfilled += 1
            
            # Get messages after
            async for message in channel.history(after=after_ts, limit=radius):
                if message.author.bot:
                    continue
                
                cleaned_content = self.mention_translator.clean_for_bot(message.content, message)
                
                self.memory.store_recent_message(
                    user_id=str(message.author.id),
                    username=message.author.display_name,
                    channel_id=str(channel.id),
                    content=cleaned_content,
                    message_id=str(message.id),
                    timestamp=message.created_at
                )
                
                backfilled += 1
            
            return backfilled
            
        except Exception as e:
            logger.error(f"❌ Error backfilling around position: {e}")
            return 0
    
    async def _process_batch_with_context(self, batch: List[Dict]):
        """
        Process a batch of messages with 5-message context for summarization.
        
        For old messages (like 1500th), gets surrounding messages (1498-1502)
        and creates summary with context.
        """
        try:
            if len(batch) < 3:
                # Not enough for summarization, just queue individually
                for msg in batch:
                    self.bg_processor.queue_message(**msg)
                return
            
            # Get surrounding messages for context
            center_msg = batch[len(batch) // 2]
            channel_id = center_msg['channel_id']
            timestamp = center_msg['timestamp']
            
            # Get ±2 messages from SQL for context
            context_messages = self.memory.get_messages_around_timestamp(
                channel_id=channel_id,
                timestamp=timestamp,
                radius=2
            )
            
            # Combine with batch
            all_messages = context_messages + batch
            
            # Remove duplicates by message_id
            seen = set()
            unique_messages = []
            for msg in all_messages:
                msg_id = f"{msg['user_id']}_{msg['timestamp']}"
                if msg_id not in seen:
                    seen.add(msg_id)
                    unique_messages.append(msg)
            
            # Sort by timestamp (handle both datetime and string formats)
            def get_sort_key(msg):
                timestamp = msg['timestamp']
                if isinstance(timestamp, str):
                    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return timestamp
            
            unique_messages.sort(key=get_sort_key)
            
            # Queue all for background processing (filter out non-compatible parameters)
            for msg in unique_messages:
                # Only pass parameters that are compatible with queue_message
                compatible_msg = {
                    'content': msg.get('content', ''),
                    'user_id': msg.get('user_id', ''),
                    'username': msg.get('username', ''),
                    'channel_id': msg.get('channel_id', ''),
                    'server_id': msg.get('server_id', ''),
                    'timestamp': msg.get('timestamp')
                }
                self.bg_processor.queue_message(**compatible_msg)
            
        except Exception as e:
            logger.error(f"❌ Error processing batch with context: {e}")
    
    def get_stats(self) -> Dict:
        """Get crawler statistics"""
        return {
            'quick_syncs': self.stats['quick_syncs'],
            'deep_validations': self.stats['deep_validations'],
            'messages_backfilled': self.stats['messages_backfilled'],
            'gaps_found': self.stats['gaps_found'],
            'channels_synced': len(self.stats['channels_synced']),  # Convert set to int
            'channels_list': list(self.stats['channels_synced']),  # Add list version
            'errors': self.stats['errors'],
            'is_running': self.is_running
        }