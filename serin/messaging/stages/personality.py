"""
PersonalityStage
----------------
Injects Serin's personality context, tone modifier, and conversation mood
into the pipeline. Reads from BotPersonality and any conversation analysis.
Populates ctx.personality_context and ctx.tone_modifier.
"""
from __future__ import annotations

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage


class PersonalityStage(PipelineStage):
    """Applies personality traits, tone, and conversation mood."""

    def __init__(self, personality):
        self.personality = personality

    async def _run(self, ctx: MessageContext) -> MessageContext:
        # Get tone modifier
        if hasattr(self.personality, "get_tone_modifier"):
            ctx.tone_modifier = self.personality.get_tone_modifier()

        # Get personality context
        if hasattr(self.personality, "get_personality_context"):
            ctx.personality_context = self.personality.get_personality_context()

        logger.debug("pipeline.personality", extra={
            "user": ctx.username,
            "tone_modifier": ctx.tone_modifier,
            "has_personality_context": bool(ctx.personality_context),
        })

        return ctx
