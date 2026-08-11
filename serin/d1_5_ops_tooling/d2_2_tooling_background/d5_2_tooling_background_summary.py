"""
Background Processor Summarization Mixin
-----------------------------------------
Summarization methods for BackgroundProcessor, extracted to keep files under 500 lines.
"""
# --- Imports ---
from __future__ import annotations

from typing import Any

from serin.d1_3_state_core.d2_3_model_system.d3_4_system_interface import (
    ModelInterface,
)
from serin.d1_3_state_core.d2_3_model_system.d3_5_model_helpers.d6_1_thinking_filter import (
    filter_thinking,
)
from serin.d1_4_config_base.d2_2_debug_logger import log_summary
from serin.d1_4_config_base.d2_3_core_logger import logger

# --- Types ---
# (none)

# --- Constants ---
# (none)

# --- Entry ---


class BackgroundProcessorSummarizationMixin:
    """Summarization methods for BackgroundProcessor."""

    # Attributes provided by the composing host class (BackgroundProcessor).
    extractor_llm: ModelInterface | None
    stats: dict[str, int]
    memory: Any

# --- Core ---
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
            prompt = f"""Summarize this conversation in 2-3 sentences. Include:
- WHO is talking and their relationship (friends, strangers, rivals)
- WHAT they are discussing or doing
- WHAT LANGUAGE they use (English, Romanji, Bangla, mixed — note code-switching)
- The TONE between them (playful, hostile, helpful, casual)

Conversation:
{conversation_text}

Summary:"""

            # Query LLM for summary
            if is_thinking_model:
                max_tokens = 800  # Allow room for thinking
            else:
                max_tokens = 300  # Richer summaries need more tokens

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
                "### FINAL", "[the ", "template", "example",
                "Please provide", "conversation_text", "I cannot",
                "I can't", "there is no content", "no conversation",
                "I am unable", "did not provide", "has not provided",
                "I will write", "once you paste", "I am ready",
                "please include", "so I cannot generate"
            ]
            is_garbage = any(pattern.lower() in summary.lower() for pattern in garbage_patterns)

            # Ensure summary is valid
            if summary and len(summary) > 15 and len(summary) < 500 and not is_garbage:
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

# --- Helpers ---
# (none)

# --- Errors ---
# (none)
