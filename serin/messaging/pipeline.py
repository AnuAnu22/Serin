"""
serin.messaging.pipeline
-----------------------
MessagePipeline is the entry point for all text message processing.
It runs stages in order, passing MessageContext through each.

Stages signal early exit via ctx.should_halt = True.
Unexpected exceptions are caught, logged, and halt the pipeline.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from serin.core.logger import logger

if TYPE_CHECKING:
    from serin.messaging.context import MessageContext
    from serin.messaging.stages import PipelineStage
    from serin.messaging.manager import PipelineDeps


class MessagePipeline:
    """
    Iterates through pipeline stages, passing (ctx, deps) to each.
    Halts early if ctx.should_halt is set by any stage.
    """

    def __init__(self, stages: list[PipelineStage], deps: PipelineDeps):
        self.stages = stages
        self.deps = deps

    async def process(self, ctx: MessageContext) -> MessageContext:
        logger.info("pipeline.start", extra={
            "user_count": len(ctx.user_messages),
            "bot_mentioned": ctx.bot_mentioned,
        })

        for stage in self.stages:
            try:
                await stage.run(ctx, self.deps)
            except Exception as e:
                logger.error(f"pipeline.stage_error", extra={
                    "stage": stage.name,
                    "error": str(e),
                }, exc_info=True)
                ctx.should_halt = True
                break

            if ctx.should_halt:
                logger.debug("pipeline.halted", extra={
                    "stage": stage.name,
                })
                break

        logger.info("pipeline.complete", extra={
            "responded": bool(ctx.response),
            "halted": ctx.should_halt,
            "stage_timings": ctx.stage_timings,
        })
        return ctx
