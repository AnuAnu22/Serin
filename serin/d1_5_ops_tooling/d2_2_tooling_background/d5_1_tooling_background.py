"""
Background Processor - Creates Natural Memory Summaries
Uses the main model to create conversational summaries from RAW message batches.

FIXED: Now uses RAW messages only, not vector memories
FIXED: Proper username attribution in summaries
"""
# --- Imports ---
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any

from serin.d1_3_state_core.d2_3_model_system.d3_3_system_factory import (
    get_model_connector,
)
from serin.d1_3_state_core.d2_3_model_system.d3_4_system_interface import ModelInterface
from serin.d1_4_config_base.d2_3_core_logger import logger
from serin.d1_5_ops_tooling.d2_2_tooling_background.d5_2_tooling_background_summary import (
    BackgroundProcessorSummarizationMixin,
)

# --- Types ---
# (none)

# --- Constants ---
# (none)

# --- Entry ---


class BackgroundProcessor(BackgroundProcessorSummarizationMixin):
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

        # Dynamics engine for physics-based conversation state (set externally)
        self.dynamics_engine: Any | None = None

        logger.info(" Background processor initialized")

# --- Core ---
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
        username: str,
        user_id: str,
        channel_id: str,
        message_id: str | None = None,
        server_id: str = "",
        timestamp: str | datetime = "",
    ) -> None:
        """
        Queue a RAW message for background processing.

        Args:
            content: Message content
            username: Display name
            user_id: Discord user ID
            channel_id: Discord channel ID
            message_id: Discord message ID
            server_id: Discord guild ID
            timestamp: ISO timestamp or datetime
        """
        try:
            message = {
                'content': content,
                'username': username,
                'user_id': user_id,
                'channel_id': channel_id,
                'message_id': message_id,
                'server_id': server_id,
                'timestamp': timestamp,
            }

            with self._queue_lock:
                self.processing_queue.append(message)

            self.stats['total_queued'] += 1
            self.last_message_time = datetime.now()
            logger.debug(f" Queued RAW message from {username}: '{content[:50]}...' (queue: {len(self.processing_queue)})")
        except Exception as e:
            logger.error(f" Error queuing message: {e}")
            self.stats['queue_drops'] += 1

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
                        batch_size = min(10, queue_size)
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

# --- Helpers ---
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
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00')).replace(tzinfo=None)
            return timestamp.replace(tzinfo=None)

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

    async def run_maintenance(self) -> None:
        """Periodic maintenance — process any remaining queue items + decay facts."""
        if not self.is_running:
            return
        queue_size = len(self.processing_queue)
        if queue_size > 0:
            logger.info(f"Maintenance: processing {queue_size} queued messages")
            with self._queue_lock:
                batch = [self.processing_queue.popleft() for _ in range(queue_size)]
            await self._process_batch(batch)

        # Clean up stale channel state via dynamics engine
        try:
            if self.dynamics_engine:
                self.dynamics_engine.allocate_attention()
        except Exception as e:
            logger.debug(f" Dynamics engine maintenance failed: {e}")

        # Generate LLM impressions for users due for one
        await self._run_impression_batch()

    async def _run_impression_batch(self) -> None:
        """Generate LLM impressions for users who are due (≥25 messages since last, ≥10 total)."""
        try:
            from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
                get_users_due_impression,
            )
            affect_engine = getattr(self.memory, 'affect_engine', None)
            if not affect_engine:
                return

            # Get up to 3 users due for an impression
            users = get_users_due_impression(self.memory.store, limit=3)
            if not users:
                return

            logger.info(f"🧠 Generating impressions for {len(users)} user(s)")

            for user_row in users:
                user_id = user_row['user_id']
                try:
                    # Get recent messages from this user
                    recent = self.memory.store.query_messages(
                        user_id=user_id,
                        limit=30,
                        order_by='timestamp DESC'
                    )
                    if not recent:
                        logger.debug(f"No messages found for {user_id}, skipping impression")
                        # Reset counter anyway so we don't keep trying
                        await affect_engine.apply_impression(user_id, "", 0.0)
                        continue

                    # Get current affect snapshot
                    snap = affect_engine.snapshot_cached(user_id)
                    username = recent[0].get('username', 'User')
                    messages = [f"{m.get('username', '?')}: {m.get('content', '')}" for m in recent]

                    # Build prompt and call LLM
                    prompt = affect_engine.build_impression_prompt(username, messages, snap.valence)
                    if not self.extractor_llm or not self.extractor_llm.is_connected:
                        logger.debug("Extractor LLM not connected, skipping impressions")
                        return

                    response = await asyncio.to_thread(
                        self.extractor_llm.blocking_send_input,
                        prompt,
                        max_tokens=200,
                        temperature=0.7
                    )

                    # Parse and apply
                    parsed = affect_engine.parse_impression(response)
                    if parsed:
                        text, delta = parsed
                        await affect_engine.apply_impression(user_id, text, delta)
                        logger.info(f"✓ Impression for {username}: valence Δ{delta:+.2f}")
                    else:
                        # Malformed JSON — reset counter to avoid retry loop
                        await affect_engine.apply_impression(user_id, "", 0.0)
                        logger.debug(f"Malformed impression JSON for {username}, counter reset")

                except Exception as e:
                    logger.error(f"Failed to generate impression for {user_id}: {e}")
                    # Reset counter on error too
                    try:
                        await affect_engine.apply_impression(user_id, "", 0.0)
                    except Exception as reset_err:
                        logger.debug(f"Failed to reset impression counter for {user_id}: {reset_err}")

        except Exception as e:
            logger.debug(f"Impression batch failed: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Return background processor statistics."""
        return {
            "is_running": self.is_running,
            "queue_size": len(self.processing_queue),
            **self.stats,
        }

# --- Errors ---
# (none)
