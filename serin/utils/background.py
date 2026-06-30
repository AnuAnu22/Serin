"""
Background Processor - Creates Natural Memory Summaries
Uses the main model to create conversational summaries from RAW message batches.

FIXED: Now uses RAW messages only, not vector memories
FIXED: Proper username attribution in summaries
"""
from __future__ import annotations

import asyncio
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional, Any
from collections import deque
from models.model_interface import ModelInterface
from models.factory import get_model_connector
from thinking_filter import filter_thinking
from serin.core.logger import logger
from debug_logger import log_summary

class BackgroundProcessor:
    def __init__(self, memory_system: Any, max_queue_size: int = 1000) -> None:
        """
        Initialize background processor for memory summarization.
        
        Args:
            memory_system: UnifiedMemorySystem instance
            max_queue_size: Maximum messages to queue
        """
        self.memory = memory_system
        self.processing_queue: deque[Dict[str, Any]] = deque(maxlen=max_queue_size)
        self.is_running: bool = False
        self.task: Optional[asyncio.Task[None]] = None
        self._queue_lock = threading.Lock()  # Add thread lock for race condition prevention
        
        # Separate LLM connector instance for background processing (same model, different settings)
        self.extractor_llm: Optional[ModelInterface] = None
        
        # Processing stats
        self.stats = {
            'total_queued': 0,
            'total_processed': 0,
            'summaries_created': 0,
            'errors': 0,
            'queue_drops': 0
        }
        
        # Timer for idle processing
        self.last_message_time: Optional[datetime] = None
        
        logger.info("✅ Background processor initialized")
    
    async def start(self) -> None:
        """Start the background processing task"""
        if self.is_running:
            logger.warning("⚠️ Background processor already running")
            return
        
        # Initialize background LLM for summarization
        # Uses the same model as the main bot (SGLang supports concurrent generation)
        logger.info("🧠 Initializing background LLM via factory...")
        try:
            self.extractor_llm = get_model_connector()
            await asyncio.to_thread(
                self.extractor_llm.load_model,
                temperature=0.3,  # Lower temp for factual summaries
                top_p=0.9
            )
            
            # Log model info
            model_info = self.extractor_llm.get_model_info()
            logger.info(f"✅ Background LLM ready: {model_info['model_name']} ({model_info['model_type']})")
            
        except Exception as e:
            logger.exception(f"❌ Failed to initialize background LLM: {e}")
            logger.error("⚠️ Background processing will be disabled")
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._processing_loop())
        logger.info("✅ Background processor started")
    
    async def stop(self) -> None:
        """Stop the background processing task"""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Background processor stopped")
    
    def queue_message(
        self,
        content: str,
        user_id: str,
        username: str,
        channel_id: str,
        server_id: str,
        timestamp: Optional[datetime] = None,
        **kwargs: Any  # Accept any additional parameters for backward compatibility
    ) -> None:
        """
        Queue a RAW message for background processing.
        
        CRITICAL: This receives the ACTUAL message content,
        NOT vector memory results.
        
        Args:
            content: RAW message content from Discord
            user_id: User ID
            username: Username
            channel_id: Channel ID
            server_id: Server/Guild ID
            timestamp: Message timestamp
            **kwargs: Additional parameters for backward compatibility (ignored)
        """
        # VALIDATE CONTENT - Skip empty or meaningless messages
        content = content.strip()
        if not content or len(content) < 10:
            logger.debug(f"⚠️ Skipping empty/short message from {username}: '{content[:30]}...'")
            return
        
        # Filter out common empty patterns
        empty_patterns = [
            'no one said anything',
            'no conversation occurred', 
            'nothing of note',
            'conversation was empty',
            'no one said anything of note',
            'no one said',
            'nothing of substance',
            'no meaningful conversation'
        ]
        content_lower = content.lower()
        if any(pattern in content_lower for pattern in empty_patterns):
            logger.debug(f"⚠️ Skipping empty pattern message from {username}: '{content[:30]}...'")
            return
        
        # Use threading lock to prevent race conditions
        with self._queue_lock:
            if len(self.processing_queue) >= self.processing_queue.maxlen:
                self.stats['queue_drops'] += 1
                logger.debug("⚠️ Processing queue full, dropping oldest message")
            
            self.processing_queue.append({
                'content': content,  # RAW message content
                'user_id': user_id,
                'username': username,
                'channel_id': channel_id,
                'server_id': server_id,
                'timestamp': timestamp or datetime.now()
            })
            
            self.stats['total_queued'] += 1
            self.last_message_time = datetime.now()
            logger.debug(f"📥 Queued RAW message from {username}: '{content[:50]}...' (queue: {len(self.processing_queue)})")
    
    async def _processing_loop(self) -> None:
        """
        Main processing loop.
        
        Process when:
        - 3+ messages available (batch of 3)
        - 1-2 messages and idle for 10s
        """
        logger.info("🔄 Background processing loop started")
        
        last_stats_log = time.time()
        stats_log_interval = 300  # 5 minutes
        
        while self.is_running:
            try:
                queue_size = len(self.processing_queue)
                
                # Log stats periodically
                current_time = time.time()
                if current_time - last_stats_log > stats_log_interval:
                    logger.info("=" * 60)
                    logger.info("📊 BACKGROUND PROCESSOR STATS")
                    logger.info("=" * 60)
                    logger.info(f"Queue size: {queue_size}")
                    logger.info(f"Total queued: {self.stats['total_queued']}")
                    logger.info(f"Total processed: {self.stats['total_processed']}")
                    logger.info(f"Summaries created: {self.stats['summaries_created']}")
                    logger.info(f"Errors: {self.stats['errors']}")
                    logger.info(f"Queue drops: {self.stats['queue_drops']}")
                    elapsed_minutes = (current_time - last_stats_log) / 60
                    rate = self.stats['summaries_created'] / max(1, elapsed_minutes)
                    logger.info(f"Processing rate: {rate:.1f} summaries/min")
                    logger.info("=" * 60)
                    last_stats_log = current_time
                
                # OPTION 1: Have 3+ messages - process batch of 3
                if queue_size >= 3:
                    with self._queue_lock:
                        batch_size = min(3, queue_size)
                        batch = [self.processing_queue.popleft() for _ in range(batch_size)]
                    
                    logger.info(f"📦 Processing batch of {batch_size} RAW messages")
                    await self._process_batch(batch)
                    await asyncio.sleep(2)
                
                # OPTION 2: Have 1-2 messages and been idle for 10s
                elif queue_size > 0 and self.last_message_time:
                    idle_seconds = (datetime.now() - self.last_message_time).total_seconds()
                    
                    if idle_seconds >= 10:
                        with self._queue_lock:
                            batch = [self.processing_queue.popleft() for _ in range(queue_size)]
                        logger.info(f"⏰ Idle timeout - processing {len(batch)} message(s)")
                        await self._process_batch(batch)
                        self.last_message_time = None
                        await asyncio.sleep(2)
                    else:
                        await asyncio.sleep(2)
                
                # OPTION 3: Queue empty
                else:
                    await asyncio.sleep(5)
                    
            except asyncio.CancelledError:
                logger.info("🛑 Background processing loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in background processing loop: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(5)
    
    async def _process_batch(self, batch: List[Dict]):
        """
        Process a batch of RAW messages.
        FIXED: Works with raw messages, not vector search results.
        """
        try:
            # Group messages by conversation context
            grouped = self._group_by_conversation(batch)
            
            for conversation_batch in grouped:
                await self._create_conversation_summary(conversation_batch)
                self.stats['total_processed'] += len(conversation_batch)
                
        except Exception as e:
            logger.error(f"❌ Error processing batch: {e}")
            self.stats['errors'] += 1
    
    def _group_by_conversation(self, batch: List[Dict]) -> List[List[Dict]]:
        """
        Group RAW messages into conversation chunks.
        Same channel + within 5 minutes = one conversation.
        """
        if not batch:
            return []
        
        def get_datetime(timestamp):
            """Convert timestamp to datetime object, handling both string and datetime inputs"""
            if isinstance(timestamp, str):
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return timestamp
        
        # Sort by timestamp
        sorted_batch = sorted(batch, key=lambda x: get_datetime(x['timestamp']))
        
        groups = []
        current_group = [sorted_batch[0]]
        
        for msg in sorted_batch[1:]:
            prev_msg = current_group[-1]
            
            # Convert timestamps to datetime for comparison
            msg_time = get_datetime(msg['timestamp'])
            prev_time = get_datetime(prev_msg['timestamp'])
            
            # Same channel and within 5 minutes?
            time_diff = (msg_time - prev_time).total_seconds()
            same_channel = msg['channel_id'] == prev_msg['channel_id']
            
            if same_channel and time_diff < 300:  # 5 minutes
                current_group.append(msg)
            else:
                # Start new group
                groups.append(current_group)
                current_group = [msg]
        
        # Add last group
        if current_group:
            groups.append(current_group)
        
        return groups
    
    async def _create_conversation_summary(self, messages: List[Dict[str, Any]]) -> None:
        """
        Create ONE natural memory from RAW conversation batch.
        
        FIXED: Now uses JSON prompt to handle thinking models
        """
        try:
            # Build conversation context from RAW messages
            conversation_lines = []
            for msg in messages:
                conversation_lines.append(f"{msg['username']}: {msg['content']}")
            
            conversation_text = "\n".join(conversation_lines)
            
            logger.debug(f"📝 Creating summary from conversation:\n{conversation_text[:200]}...")
            
            # Check if this is a thinking model
            model_info = self.extractor_llm.get_model_info()
            model_name = model_info.get('model_name', '').lower()
            is_thinking_model = 'thinking' in model_name or 'think' in model_name
            
            # Build a simple, natural prompt - no meta-instructions that could leak
            usernames = list(set(msg['username'] for msg in messages))
            prompt = f"""Summarize this conversation in ONE sentence, mentioning who said what:

{conversation_text}

Summary:"""
            
            # Query LLM for summary
            if is_thinking_model:
                max_tokens = 800  # Allow room for thinking
            else:
                max_tokens = 150  # Normal token limit for instruct models
            
            response = await self.extractor_llm.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You write brief summaries. Always write in third person."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=max_tokens
            )
            
            # Extract summary based on model type
            summary = ""
            if is_thinking_model:
                # Look for content after </think> tag
                if '</think>' in response:
                    summary = response.split('</think>')[-1].strip()
                else:
                    # Fallback: apply thinking filter
                    summary = filter_thinking(response.strip())
            else:
                # Normal instruct model - just filter thinking tags if any
                summary = filter_thinking(response.strip())
            
            # CRITICAL FIX: Remove username prefix if present
            for msg in messages:
                username = msg['username']
                if summary.startswith(f"{username}: "):
                    summary = summary[len(username) + 2:].strip()
                    break
            
            # Validation: Check for garbage patterns that indicate the model failed
            garbage_patterns = [
                "We are given", "We must write", "CRITICAL", "RULES",
                "one sentence", "Summary:", "Task:", "INSTRUCTIONS",
                "### FINAL", "[the ", "template", "example"
            ]
            is_garbage = any(pattern.lower() in summary.lower() for pattern in garbage_patterns)
            
            # Ensure summary is valid
            if summary and len(summary) > 15 and len(summary) < 300 and not is_garbage:
                # Store as natural memory
                await self._store_summary(summary, messages)
                self.stats['summaries_created'] += 1
                logger.info(f"💾 Created summary: {summary[:80]}...")
            else:
                logger.warning(f"⚠️ Summary rejected (garbage or invalid): '{summary[:50]}...'")

            log_summary(messages, summary)
            
        except Exception as e:
            logger.exception(f"❌ Error creating summary: {e}")
            self.stats['errors'] += 1
    
    
    async def _store_summary(self, summary: str, messages: List[Dict[str, Any]]) -> None:
        """
        Store summary as a natural memory.
        """
        try:
            # Get all participants
            participants = list(set(msg['user_id'] for msg in messages))
            
            # Use first message's context
            first_msg = messages[0]
            
            # Calculate importance
            importance = self._calculate_importance(summary, messages)
            
            # Store as summary (distinct from real messages to avoid duplicates in context)
            self.memory.add_memory_enhanced(
                content=summary,
                user_id=first_msg['user_id'],
                username=first_msg['username'],
                channel_id=first_msg['channel_id'],
                participants=participants,
                emotional_tone='neutral',
                importance=importance,
                source_message_id=None,
                memory_type='summary'
            )
            
            logger.debug(f"💾 Stored summary: {summary[:60]}...")
            
        except Exception as e:
            logger.error(f"❌ Error storing summary: {e}")
    
    def _calculate_importance(self, summary: str, messages: List[Dict[str, Any]]) -> float:
        """Calculate natural importance (0.0 to 1.0)"""
        importance = 0.5  # Base
        
        # Longer conversations = more important
        if len(messages) >= 5:
            importance += 0.1
        
        # Multiple participants = more important
        unique_users = len(set(msg['user_id'] for msg in messages))
        if unique_users >= 3:
            importance += 0.1
        
        # Personal information = more important
        personal_keywords = ['name', 'like', 'love', 'hate', 'plan', 'going to', 'want', 'getting']
        if any(kw in summary.lower() for kw in personal_keywords):
            importance += 0.15
        
        # Questions/answers = more important
        if '?' in ''.join(msg['content'] for msg in messages):
            importance += 0.1
        
        return min(1.0, importance)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return {
            **self.stats,
            'queue_size': len(self.processing_queue),
            'is_running': self.is_running
        }