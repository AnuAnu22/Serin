"""
LLMCallStage
------------
Calls the LLM with the assembled prompt. Sets ctx.raw_response.
This is the most expensive stage — always check timings here.
"""
from __future__ import annotations

import time
from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from serin.d1_4_config_base.d2_3_logger import logger


class LLMCallStage(PipelineStage):
    """Invokes the LLM and stores the raw response."""

    def __init__(self, response_generator: Any) -> None:
        self.generator = response_generator

    async def _run(self, ctx: MessageContext) -> MessageContext:
        started_at = time.perf_counter()
        ctx.raw_response = await self.generator(
            current_messages=ctx.built_messages,
            context=ctx.context_block,
            tone_modifier=ctx.tone_modifier,
        )

        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_11_debug_routes import (
                update_last_prompt_debug,
            )
            update_last_prompt_debug(
                ctx.raw_response, round((time.perf_counter() - started_at) * 1000, 1)
            )
        except Exception as exc:
            logger.debug("Failed to update prompt debug entry: %s", exc)

        logger.info("pipeline.llm_response", extra={
            "user": ctx.username,
            "response_len": len(ctx.raw_response),
        })

        return ctx
