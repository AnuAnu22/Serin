"""
PersonalityStage
----------------
Injects Serin's personality context, tone modifier, and conversation mood
into the pipeline. Reads from BotPersonality and any conversation analysis.
Populates ctx.personality_context and ctx.tone_modifier.
"""
from __future__ import annotations

from serin.config.logger import logger
from serin.state.message_context import MessageContext
from serin.pipeline.act.stages_init import PipelineStage


class PersonalityStage(PipelineStage):
    """Applies personality traits, tone, and conversation mood."""

    def __init__(self, personality, mood_state=None):
        self.personality = personality
        self.mood_state = mood_state

    async def _run(self, ctx: MessageContext) -> MessageContext:
        # Get tone modifier from mood state (PersonalityState) if available
        if self.mood_state is not None and hasattr(self.mood_state, "get_tone_modifier"):
            ctx.tone_modifier = self.mood_state.get_tone_modifier()
        elif hasattr(self.personality, "get_tone_modifier"):
            ctx.tone_modifier = self.personality.get_tone_modifier()

        # Get personality context (preferences/opinions from BotPersonality)
        if hasattr(self.personality, "get_personality_context"):
            ctx.personality_context = self.personality.get_personality_context()

        logger.debug("pipeline.personality", extra={
            "user": ctx.username,
            "tone_modifier": ctx.tone_modifier,
            "has_personality_context": bool(ctx.personality_context),
        })

        return ctx
