"""
MemoryWriteStage
----------------
Stores the conversation interaction (user message + bot response) in
Qdrant memory after the response has been sent.
"""
from __future__ import annotations

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage


class MemoryWriteStage(PipelineStage):
    """Writes the interaction to the memory system after sending."""

    def __init__(self, memory_system):
        self.memory = memory_system

    async def _run(self, ctx: MessageContext) -> MessageContext:
        if not ctx.final_response:
            logger.debug("pipeline.memory_write_skipped_no_response", extra={
                "user": ctx.username,
            })
            return ctx

        try:
            # Store the bot's response as a memory
            self.memory.add_memory_enhanced(
                content=ctx.final_response,
                user_id="serin",
                username="Serin",
                channel_id=ctx.channel_id,
                participants=[ctx.user_id],
                emotional_tone="neutral",
                importance=0.5,
            )

            logger.debug("pipeline.memory_written", extra={
                "user": ctx.username,
                "response_len": len(ctx.final_response),
            })
        except Exception as e:
            logger.warning("pipeline.memory_write_failed", extra={
                "user": ctx.username,
                "error": str(e),
            })

        return ctx
