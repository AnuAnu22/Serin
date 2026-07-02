"""
Background Processor - Creates Natural Memory Summaries
Uses the main model to create conversational summaries from RAW message batches.

FIXED: Now uses RAW messages only, not vector memories
FIXED: Proper username attribution in summaries
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any

from serin.d1_3_state_core.logger import logger
from serin.d1_3_state_core.model_system.factory import get_model_connector
from serin.d1_3_state_core.model_system.interface import ModelInterface
from serin.d1_3_state_core.thinking_filter import filter_thinking
from serin.d1_4_config_base.debug_logger import log_summary


class BackgroundProcessor:
    def __init__(self, memory_system: Any, max_queue_size: int = 1000) -> None:
        """
        Initialize background processor for memory summarization.

        Args:
            memory_system: UnifiedMemorySystem instance
            max_queue_size: Maximum messages to queue
        """
        self.memory = memory_system
        self.processing_queue: deque[dict[str, Any]] = deque(maxlen=max_queue_size)
        self.is_running: bool = False
        self.task: asyncio.Task[None] | None = None
        self._queue_lock = threading.Lock()  # Add thread lock for race condition prevention

        # Separate LLM connector instance for background processing (same model, different settings)
        self.extractor_llm: ModelInterface | None = None

        # Processing stats
        self.stats = {
            'total_queued': 0,
            'total_processed': 0,
            'summaries_created': 0,
            'errors': 0,
            'queue_drops': 0
        }

        # Timer for idle processing
        self.last_message_time: datetime | None = None

        logger.info(" Background processor initialized")

    async def start(self) -> None:
        """Start the background processing task"""
        if self.is_running:
            logger.warning(" Background processor already running")
            return

        # Initialize background LLM for summarization
        # Uses the same model as the main bot (SGLang supports concurrent generation)
        logger.info(" Initializing background LLM via factory...")
        self.extractor_llm = get_model_connector()
        await asyncio.to_thread(
            self.extractor_llm.load_model,
            temperature=0.3,
            top_p=0.9
        )

        if self.extractor_llm.is_connected:
            model_info = self.extractor_llm.get_model_info()
            logger.info(f" Background LLM ready: {model_info['model_name']} ({model_info['model_type']})")
        else:
            logger.info(" Background LLM not connected — will retry in background")

        self.is_running = True
        self.task = asyncio.create_task(self._processing_loop())
        logger.success(" Background processor started")

    async def stop(self) -> None:
        """Stop the background processing task"""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info(" Background processor stopped")

    def queue_message(
        self,
        content: str,
        user_id: str,
        username: str,
        channel_id: str,
        server_id: str,
        timestamp: datetime | None = None,
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
            **kwargs: Additional parameters — message_id is extracted when available
        """
        # VALIDATE CONTENT - Skip empty or meaningless messages
        content = content.strip()
        if not content or len(content) < 10:
            logger.debug(f" Skipping empty/short message from {username}: '{content[:30]}...'")
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
            logger.debug(f" Skipping empty pattern message from {username}: '{content[:30]}...'")
            return

        # Use threading lock to prevent race conditions
        with self._queue_lock:
            if self.processing_queue.maxlen is not None and len(self.processing_queue) >= self.processing_queue.maxlen:
                self.stats['queue_drops'] += 1
                logger.debug(" Processing queue full, dropping oldest message")

            self.processing_queue.append({
                'content': content,
                'user_id': user_id,
                'username': username,
                'channel_id': channel_id,
                'server_id': server_id,
                'message_id': kwargs.get('message_id', ''),
                'timestamp': timestamp or datetime.now()
            })

            self.stats['total_queued'] += 1
            self.last_message_time = datetime.now()
            logger.debug(f" Queued RAW message from {username}: '{content[:50]}...' (queue: {len(self.processing_queue)})")

    async def _processing_loop(self) -> None:
        """
        Main processing loop.

        Process when:
        - 3+ messages available (batch of 3)
        - 1-2 messages and idle for 10s
        """
        logger.info(" Background processing loop started")

        last_stats_log = time.time()
        stats_log_interval = 300  # 5 minutes

        while self.is_running:
            try:
                queue_size = len(self.processing_queue)

                # Log stats periodically
                current_time = time.time()
                if current_time - last_stats_log > stats_log_interval:
                    logger.info("=" * 60)
                    logger.info(" BACKGROUND PROCESSOR STATS")
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

                    logger.info(f" Processing batch of {batch_size} RAW messages")
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
                logger.info(" Background processing loop cancelled")
                break
            except Exception as e:
                logger.error(f" Error in background processing loop: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(5)

    async def _process_batch(self, batch: list[dict[str, Any]]) -> None:
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
            logger.error(f" Error processing batch: {e}")
            self.stats['errors'] += 1

    def _group_by_conversation(self, batch: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """
        Group RAW messages into conversation chunks.
        Same channel + within 5 minutes = one conversation.
        """
        if not batch:
            return []

        def get_datetime(timestamp: str | datetime) -> datetime:
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

    async def _create_conversation_summary(self, messages: list[dict[str, Any]]) -> None:
        """
        Create ONE natural memory from RAW conversation batch.

        FIXED: Now uses JSON prompt to handle thinking models
        """
        if self.extractor_llm is None:
            logger.warning("Background LLM not initialized, skipping summary")
            return
        try:
            # Build conversation context from RAW messages
            conversation_lines = []
            for msg in messages:
                conversation_lines.append(f"{msg['username']}: {msg['content']}")

            conversation_text = "\n".join(conversation_lines)

            logger.debug(f" Creating summary from conversation:\n{conversation_text[:200]}...")

            # Check if this is a thinking model
            model_info = self.extractor_llm.get_model_info()
            model_name = model_info.get('model_name', '').lower()
            is_thinking_model = 'thinking' in model_name or 'think' in model_name

            # Build a structured prompt that distinguishes observations from claims
            prompt = """Write a one-sentence memory based on what occurred.

CRITICAL — distinguish these three types of information:
  • Observations: objective content shown (board states, links, code, quoted text).
    These are things actually SEEN, not just claimed.
  • Claims: subjective assertions someone made ("I won", "you lost", etc.).
    These are things someone SAID, not things that happened.
  • Events: actual conversation events (topic changes, agreements, etc.).

When a board state was shown, describe what was OBSERVED, not what someone claimed about it.
Example: "Serin observed a board showing X has 4 in a row" NOT "NekoNeko claimed victory."

Conversation:
{conversation_text}

Memory:"""

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
                logger.info(f" Created summary: {summary[:80]}...")
            else:
                logger.warning(f" Summary rejected (garbage or invalid): '{summary[:50]}...'")

            log_summary(messages, summary)

        except Exception as e:
            logger.exception(f" Error creating summary: {e}")
            self.stats['errors'] += 1


    async def _store_summary(self, summary: str, messages: list[dict[str, Any]]) -> None:
        """
        Store summary as a disposable index — linked to its source messages
        and marked as compressed. Raw evidence is always preferred over summaries
        during retrieval. Summaries are fallbacks, not sources of truth.
        """
        try:
            # Get all participants
            participants = list(set(msg['user_id'] for msg in messages))

            # Use first message's context
            first_msg = messages[0]

            # Collect source message IDs for traceability
            source_ids = [
                msg['message_id'] for msg in messages
                if msg.get('message_id')
            ]

            # Calculate importance
            importance = self._calculate_importance(summary, messages)

            # Store as summary with source links + compressed flag
            self.memory.add_memory_enhanced(
                content=summary,
                user_id=first_msg['user_id'],
                username=first_msg['username'],
                channel_id=first_msg['channel_id'],
                participants=participants,
                emotional_tone='neutral',
                importance=importance,
                source_message_id=None,
                memory_type='summary',
                compressed=True,
                source_message_count=len(messages),
                linked_ids=source_ids,
            )

            logger.debug(
                f" Stored summary: {summary[:60]}... "
                f"(compressed from {len(messages)} messages, "
                f"{len(source_ids)} linked)"
            )

        except Exception as e:
            logger.error(f" Error storing summary: {e}")

    def _calculate_importance(self, summary: str, messages: list[dict[str, Any]]) -> float:
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

    async def run_maintenance(self) -> None:
        """Periodic maintenance — process any remaining queue items."""
        if not self.is_running:
            return
        queue_size = len(self.processing_queue)
        if queue_size > 0:
            logger.info(f"Maintenance: processing {queue_size} queued messages")
            with self._queue_lock:
                batch = [self.processing_queue.popleft() for _ in range(queue_size)]
            await self._process_batch(batch)

    def get_stats(self) -> dict[str, Any]:
        """Get processing statistics"""
        return {
            **self.stats,
            'queue_size': len(self.processing_queue),
            'is_running': self.is_running
        }
