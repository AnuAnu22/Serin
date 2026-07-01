"""
Thinking Tag Filter - Remove reasoning/thinking tags from model outputs
Prevents <think>, [Thinking], etc. from appearing in responses or memory
"""
from __future__ import annotations

import re
from re import Pattern

from serin.state.logger import logger


class ThinkingFilter:
    """
    Filters out thinking/reasoning tags from LLM outputs.
    Supports multiple formats used by different models.
    """

    # Common thinking tag patterns
    THINKING_PATTERNS = [
        # Gemma 4 channel-based thinking (official format)
        r'<\|channel\|>thought\n.*?\n<channel\|>',

        # XML-style tags
        r'<think>.*?</think>',
        r'<thinking>.*?</thinking>',
        r'<thought>.*?</thought>',
        r'<reasoning>.*?</reasoning>',
        r'<analysis>.*?</analysis>',

        # Markdown-style
        r'\[Thinking:.*?\]',
        r'\[Think:.*?\]',
        r'\[Thought:.*?\]',
        r'\[Reasoning:.*?\]',

        # Parenthetical
        r'\(thinking:.*?\)',
        r'\(think:.*?\)',

        # Special model tokens
        r'<\|thinking\|>.*?<\|/thinking\|>',
        r'<\|think\|>.*?<\|/think\|>',
    ]

    def __init__(self) -> None:
        # Compile patterns for performance
        self.compiled_patterns: list[Pattern[str]] = [
            re.compile(pattern, re.IGNORECASE | re.DOTALL)
            for pattern in self.THINKING_PATTERNS
        ]
        logger.info(" Thinking filter initialized")

    def filter(self, text: str) -> str:
        """
        Remove all thinking tags from text.

        Args:
            text: Input text that may contain thinking tags

        Returns:
            Cleaned text with thinking tags removed
        """
        if not text:
            return text

        try:
            import serin_core
            return serin_core.filter_thinking(text)
        except ImportError:
            original_length = len(text)
            cleaned = text

            for pattern in self.compiled_patterns:
                cleaned = pattern.sub('', cleaned)

            cleaned = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned)
            cleaned = re.sub(r'  +', ' ', cleaned)
            cleaned = cleaned.strip()

            if len(cleaned) < original_length:
                removed = original_length - len(cleaned)
                logger.debug(f" Filtered {removed} chars of thinking tags")

            return cleaned

    def has_thinking_tags(self, text: str) -> bool:
        """
        Check if text contains thinking tags.
        Useful for debugging/monitoring.

        Args:
            text: Text to check

        Returns:
            True if thinking tags detected
        """
        if not text:
            return False

        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return True

        return False

    def extract_thinking(self, text: str) -> tuple[str, str]:
        """
        Extract thinking content separately from main response.
        Useful for debugging or logging internal reasoning.

        Args:
            text: Text potentially containing thinking tags

        Returns:
            (thinking_content, cleaned_response)
        """
        thinking_parts = []
        cleaned = text

        for pattern in self.compiled_patterns:
            matches = pattern.findall(text)
            thinking_parts.extend(matches)
            cleaned = pattern.sub('', cleaned)

        # Clean up
        cleaned = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned)
        cleaned = cleaned.strip()

        thinking_content = ' '.join(thinking_parts) if thinking_parts else ''

        return thinking_content, cleaned


# Global instance
_thinking_filter = None

def get_thinking_filter() -> ThinkingFilter:
    """Get or create global thinking filter instance"""
    global _thinking_filter
    if _thinking_filter is None:
        _thinking_filter = ThinkingFilter()
    return _thinking_filter


def filter_thinking(text: str) -> str:
    """
    Convenience function to filter thinking tags.

    Usage:
        cleaned = filter_thinking(model_output)

    IMPORTANT: Call this on:
    - All LLM responses before sending to Discord
    - All content before storing in memory
    - Any text that might contain thinking tags
    """
    return get_thinking_filter().filter(text)


def filter_for_memory(content: str) -> str:
    """
    Special function for cleaning content before memory storage.
    Ensures no thinking tags pollute the memory database.

    Usage in memory_system.py:
        from serin.state.thinking_filter import filter_for_memory

        def add_memory(self, content, ...):
            content = filter_for_memory(content)  # Clean first!
            # ... rest of storage logic
    """
    return filter_thinking(content)
