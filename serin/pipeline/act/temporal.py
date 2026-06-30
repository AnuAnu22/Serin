"""
TemporalStage
-------------
Resolves natural time references in the user's message (e.g. "last Tuesday",
"this morning", "a few days ago"). Populates ctx.temporal_refs with
resolved date strings.
"""
from __future__ import annotations

from serin.config.logger import logger
from serin.state.message_context import MessageContext
from serin.pipeline.act.stages_init import PipelineStage


class TemporalStage(PipelineStage):
    """Parses and resolves temporal references in user input."""

    def __init__(self, temporal_context):
        self.temporal = temporal_context

    async def _run(self, ctx: MessageContext) -> MessageContext:
        if not hasattr(self.temporal, "resolve_dates"):
            return ctx

        resolved = self.temporal.resolve_dates(ctx.raw_content)
        if resolved:
            ctx.temporal_refs = resolved
            logger.debug("pipeline.temporal_resolved", extra={
                "user": ctx.username,
                "refs_found": len(resolved),
                "refs": resolved,
            })
        else:
            ctx.temporal_refs = []

        return ctx
