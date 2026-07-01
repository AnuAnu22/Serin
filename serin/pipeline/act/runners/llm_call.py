"""
LLMCallStage
------------
Calls the LLM with the assembled prompt. Sets ctx.raw_response.
This is the most expensive stage — always check timings here.
"""
from __future__ import annotations

from serin.state.logger import logger
from serin.state.message_context import MessageContext
from serin.pipeline.act.runners.pipeline import PipelineStage


class LLMCallStage(PipelineStage):
    """Invokes the LLM and stores the raw response."""

    def __init__(self, response_generator):
        self.generator = response_generator

    async def _run(self, ctx: MessageContext) -> MessageContext:
        ctx.raw_response = await self.generator(
            current_messages=ctx.built_messages,
            context=ctx.context_block,
            tone_modifier=ctx.tone_modifier,
        )

        logger.info("pipeline.llm_response", extra={
            "user": ctx.username,
            "response_len": len(ctx.raw_response),
        })

        return ctx
