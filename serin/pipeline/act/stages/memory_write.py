"""
MemoryWriteStage
----------------
Stores the conversation interaction (user message + bot response) in
Qdrant memory after the response has been sent.
"""
from __future__ import annotations

from serin.logger import logger
from serin.pipeline.act.stages_base import PipelineStage
from serin.state.message_context import MessageContext


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
            # Store the bot's response as a low-importance memory
            # Tagged as type 'bot_response' so it ranks below user traits and
            # conversation facts in retrieval, reducing self-reinforcement loops.
            self.memory.add_memory_enhanced(
                content=ctx.final_response,
                user_id="serin",
                username="Serin",
                channel_id=ctx.channel_id,
                participants=[ctx.user_id],
                emotional_tone="neutral",
                importance=0.1,
                memory_type="bot_response",
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
