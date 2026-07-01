"""
Debug Logger - Comprehensive debug information system
Shows exactly what bot sees, processes, and stores
"""
from typing import Any

from serin.d1_3_state_core.logger import logger
from serin.d1_4_config_base.config import config


class DebugLogger:
    """Centralized debug logging for bot operations"""

    def __init__(self) -> None:
        self.debug_mode = config.DEBUG_MODE
        self.verbose_memory = config.DEBUG_MEMORY
        self.verbose_llm = config.DEBUG_LLM

    def log_message_received(self, message: Any, cleaned_content: str) -> None:
        """Log when message is received"""
        if not self.debug_mode:
            return

        logger.info("=" * 80)
        logger.info("MESSAGE RECEIVED")
        logger.info("=" * 80)
        logger.info(f"User: {message.author.display_name} ({message.author.id})")
        logger.info(f"Channel: #{message.channel.name} ({message.channel.id})")
        logger.info(f"Server: {message.guild.name if message.guild else 'DM'}")
        logger.info(f"Original: '{message.content}'")
        logger.info(f"Cleaned: '{cleaned_content}'")
        logger.info("=" * 80)

    def log_context_built(self, context: dict[str, Any]) -> None:
        """Log context that will be sent to LLM"""
        if not self.debug_mode:
            return

        logger.info("=" * 80)
        logger.info("CONTEXT BUILT FOR LLM")
        logger.info("=" * 80)
        logger.info(f"Recent messages: {len(context.get('recent_conversation', []))}")
        logger.info(f"Relevant memories: {len(context.get('relevant_memories', []))}")
        logger.info(f"User profiles: {len(context.get('profiles', {}))}")
        logger.info(f"Relationships: {len(context.get('relationships', []))}")

        # Show recent conversation
        if context.get('recent_conversation'):
            logger.info("\nRECENT CONVERSATION (last 5):")
            for msg in context['recent_conversation'][-5:]:
                logger.info(f"  {msg['username']}: {msg['content'][:100]}")

        # Show relevant memories
        if context.get('relevant_memories') and self.verbose_memory:
            logger.info("\nRELEVANT MEMORIES:")
            for i, mem in enumerate(context['relevant_memories'][:3], 1):
                logger.info(f"  {i}. [{mem.get('age_days', 0)}d ago] {mem['content'][:100]}")

        # Show user profiles
        if context.get('profiles'):
            logger.info("\nUSER PROFILES:")
            for user_id, profile in context['profiles'].items():
                traits = profile.get('personality_traits', [])[:3]
                interests = profile.get('interests', [])[:3]
                logger.info(f"  {profile['username']}: traits={traits}, interests={interests}")

        logger.info("=" * 80)

    def log_llm_input(self, messages: list[dict[str, Any]]) -> None:
        """Log exact messages sent to LLM"""
        if not self.verbose_llm:
            return

        logger.info("=" * 80)
        logger.info("EXACT LLM INPUT")
        logger.info("=" * 80)

        for i, msg in enumerate(messages, 1):
            role = msg['role'].upper()
            content = msg['content']

            logger.info(f"\n[Message {i} - {role}]")
            logger.info("-" * 40)

            # Truncate long content but show structure
            if len(content) > 500:
                logger.info(f"{content[:500]}...")
                logger.info(f"... [{len(content) - 500} more characters]")
            else:
                logger.info(content)

        logger.info("=" * 80)

    def log_llm_output(self, raw_response: str, cleaned_response: str) -> None:
        """Log LLM output before and after cleaning"""
        if not self.verbose_llm:
            return

        logger.info("=" * 80)
        logger.info("LLM OUTPUT")
        logger.info("=" * 80)
        logger.info(f"\nRAW OUTPUT ({len(raw_response)} chars):")
        logger.info("-" * 40)
        logger.info(raw_response[:500] if len(raw_response) > 500 else raw_response)

        logger.info(f"\nCLEANED OUTPUT ({len(cleaned_response)} chars):")
        logger.info("-" * 40)
        logger.info(cleaned_response)
        logger.info("=" * 80)

    def log_memory_stored(self, content: str, metadata: dict[str, Any]) -> None:
        """Log when memory is stored"""
        if not self.verbose_memory:
            return

        logger.info("=" * 80)
        logger.info("MEMORY STORED")
        logger.info("=" * 80)
        logger.info(f"Content: '{content}'")
        logger.info(f"User: {metadata.get('username')} ({metadata.get('user_id')})")
        logger.info(f"Channel: {metadata.get('channel_id')}")
        logger.info(f"Participants: {metadata.get('participants', [])}")
        logger.info(f"Importance: {metadata.get('importance', 0.5):.2f}")
        logger.info(f"Emotional tone: {metadata.get('emotional_tone', 'neutral')}")
        logger.info(f"Timestamp: {metadata.get('timestamp')}")
        logger.info("=" * 80)

    def log_background_summary(self, messages: list[dict[str, Any]], summary: str) -> None:
        """Log background processor summary creation"""
        if not self.verbose_memory:
            return

        logger.info("=" * 80)
        logger.info("BACKGROUND SUMMARY CREATED")
        logger.info("=" * 80)
        logger.info(f"From {len(messages)} message(s):")
        for msg in messages:
            logger.info(f"  {msg['username']}: {msg['content'][:80]}")
        logger.info("\nSummary created:")
        logger.info(f"  '{summary}'")
        logger.info("=" * 80)

    def log_correction_detected(self, correction: dict[str, Any], user: str) -> None:
        """Log when correction is detected"""
        if not self.debug_mode:
            return

        logger.info("=" * 80)
        logger.info("CORRECTION DETECTED")
        logger.info("=" * 80)
        logger.info(f"User: {user}")
        logger.info(f"Confidence: {correction.get('confidence', 0):.2f}")
        logger.info(f"Original: '{correction.get('original_statement', '')[:100]}'")
        logger.info(f"Corrected: '{correction.get('corrected_statement', '')[:100]}'")
        logger.info(f"Type: {correction.get('correction_type', 'unknown')}")
        logger.info("=" * 80)

    def log_response_decision(self, should_respond: bool, reason: str, message: str) -> None:
        """Log response decision"""
        if not self.debug_mode:
            return

        status = "RESPONDING" if should_respond else "SKIPPING"
        logger.info("=" * 80)
        logger.info(f"{status}")
        logger.info("=" * 80)
        logger.info(f"Message: '{message[:100]}'")
        logger.info(f"Reason: {reason}")
        logger.info("=" * 80)

    def log_voice_event(self, event_type: str, user: str, channel: str, duration: int | None = None) -> None:
        """Log voice channel events"""
        if not self.debug_mode:
            return

        logger.info("=" * 80)
        logger.info("VOICE EVENT")
        logger.info("=" * 80)
        logger.info(f"Event: {event_type}")
        logger.info(f"User: {user}")
        logger.info(f"Channel: {channel}")
        if duration is not None:
            logger.info(f"Duration: {duration} minutes")
        logger.info("=" * 80)


# Global debug logger instance
debug = DebugLogger()


# Convenience functions
def log_message(message: Any, cleaned_content: str) -> None:
    """Log message received"""
    debug.log_message_received(message, cleaned_content)


def log_context(context: dict[str, Any]) -> None:
    """Log context built"""
    debug.log_context_built(context)


def log_llm_io(
    messages: list[dict[str, Any]] | None = None,
    raw: str | None = None,
    cleaned: str | None = None,
) -> None:
    """Log LLM input/output"""
    if messages:
        debug.log_llm_input(messages)
    if raw and cleaned:
        debug.log_llm_output(raw, cleaned)


def log_memory(content: str, metadata: dict[str, Any]) -> None:
    """Log memory stored"""
    debug.log_memory_stored(content, metadata)


def log_summary(messages: list[dict[str, Any]], summary: str) -> None:
    """Log background summary"""
    debug.log_background_summary(messages, summary)


def log_correction(correction: dict[str, Any], user: str) -> None:
    """Log correction detected"""
    debug.log_correction_detected(correction, user)


def log_response(should_respond: bool, reason: str, message: str) -> None:
    """Log response decision"""
    debug.log_response_decision(should_respond, reason, message)


def log_voice(event_type: str, user: str, channel: str, duration: int | None = None) -> None:
    """Log voice event"""
    debug.log_voice_event(event_type, user, channel, duration)


def log_api_request(endpoint: str, method: str, params: dict[str, Any] | None = None) -> None:
    """Log API request"""
    if not debug.debug_mode:
        return

    logger.info("=" * 80)
    logger.info("API REQUEST")
    logger.info("=" * 80)
    logger.info(f"Endpoint: {endpoint}")
    logger.info(f"Method: {method}")
    if params:
        logger.info(f"Params: {params}")
    logger.info("=" * 80)
