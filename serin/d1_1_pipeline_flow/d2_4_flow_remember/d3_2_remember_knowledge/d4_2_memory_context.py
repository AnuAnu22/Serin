"""
Enhanced Memory Context Module
Handles advanced memory context processing and system prompt enhancement
"""

from typing import Any


class EnhancedMemoryContext:
    """Handles enhanced memory context for the bot"""

    def __init__(self, memory_system: Any | None = None) -> None:
        self.memory_system: Any | None = memory_system
        self.context_history: list[dict[str, Any]] = []
        self.temporal_context: dict[str, Any] = {}

class ImprovedSystemPrompt:
    """Handles improved system prompt generation"""

    @staticmethod
    def get_enhanced_system_prompt() -> str:
        """Generate human-like system prompt that doesn't sound robotic"""
        base_prompt = """Hey there! I'm Serin. I've got a pretty good memory - I tend to remember the stuff we talk about, things people like or dislike, and I can usually tell when someone's in a good mood or not.

I try to be helpful when people ask for stuff, but honestly I'm more fun just chatting and getting to know people. I like keeping conversations natural and flowing - no need to be all formal and stiff, you know?

When we talk, I'll respond based on what's been happening in our conversation and what I remember about you. Sometimes I'll mention things we discussed before if it fits naturally, and I'll try to match the vibe of whatever's going on."""

        return base_prompt


