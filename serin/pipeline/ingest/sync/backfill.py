"""Message backfill — historical message import and batch processing."""
from typing import List, Dict
from serin.state.logger import logger


    async def _backfill_channel(self, channel: discord.TextChannel, limit: int = None) -> int:
        """
        Backfill entire channel up to limit.
        Robust implementation with rate limiting and batching.
        """
        if limit is None:
            limit = self.max_messages_per_channel
        
        try:
            logger.info(f" Backfilling #{channel.name} (up to {limit} messages)")
            
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
                            logger.warning(f" Rate limited in #{channel.name}. Sleeping for {retry_after}s...")
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
                        logger.debug(f" Processing batch of {len(batch)} messages...")
                        # Process batch (this queues them for background work)
                        for msg in batch:
                            self.bg_processor.queue_message(**msg)
                        
                        batch = []
                        
                        # Explicit Rate Limit Delay
                        # Discord allows ~50 requests/sec, but history is expensive.
                        # We sleep 2 seconds every 100 messages to be safe.
                        await asyncio.sleep(2.0)
                        logger.info(f" Backfilled {backfilled} messages from #{channel.name}...")
                
                except Exception as e:
                    logger.error(f" Error processing message in backfill: {e}")
                    continue
            
            # Process remaining batch
            if batch:
                for msg in batch:
                    self.bg_processor.queue_message(**msg)
            
            logger.info(f" Backfilled {backfilled} messages from #{channel.name}")
            return backfilled
            
        except Exception as e:
            logger.error(f" Error backfilling #{channel.name}: {e}")
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
            logger.error(f" Error backfilling from timestamp: {e}")
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
            logger.error(f" Error backfilling around position: {e}")
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
            logger.error(f" Error processing batch with context: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
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