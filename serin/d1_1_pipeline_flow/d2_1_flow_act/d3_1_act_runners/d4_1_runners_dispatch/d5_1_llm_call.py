"""
LLMCallStage
------------
Calls the LLM with the assembled prompt. Sets ctx.raw_response.
This is the most expensive stage — always check timings here.
"""
from __future__ import annotations

from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_3_state_core.d2_5_core_logger import logger
from serin.d1_3_state_core.d2_5_message_context import MessageContext


class LLMCallStage(PipelineStage):
    """Invokes the LLM and stores the raw response."""

    def __init__(self, response_generator: Any) -> None:
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
