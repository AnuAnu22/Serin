"""
ResponseCleaningStage
---------------------
Applies the thinking-tag filter, then delegates ALL text cleanup to the single
canonical `clean_response` (d2_5_flow_think/d3_3_response_generator) with its
single MAX_RESPONSE_LENGTH guardrail (Discord's 2000-char hard limit).

Critique §5 fix (2026-08-18): this stage used to duplicate the special-token /
name-prefix / mention / whitespace logic with a DIFFERENT truncation cap (2000
here vs 400 in the generator) — two cleaning paths that could disagree. Now one
implementation, one constant, one mouth.
Sets ctx.final_response.
"""
from __future__ import annotations

from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator import (
    clean_response,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from serin.d1_4_config_base.d2_3_core_logger import logger


class ResponseCleaningStage(PipelineStage):
    """Strips thinking tags, then applies the shared canonical cleaner."""

    def __init__(self, thinking_filter: Any) -> None:
        self.thinking_filter = thinking_filter

    async def _run(self, ctx: MessageContext) -> MessageContext:
        raw = ctx.raw_response
        if not raw:
            ctx.final_response = ""
            return ctx

        # 1. Strip thinking tags (model-specific, injected here)
        filtered = self.thinking_filter.filter(raw)

        # 2. Shared canonical cleanup (special tokens, name prefixes, mentions,
        #    whitespace, and the single MAX_RESPONSE_LENGTH truncation).
        cleaned = clean_response(filtered)

        ctx.final_response = cleaned

        logger.debug("pipeline.response_cleaned", extra={
            "user": ctx.username,
            "original_len": len(raw),
            "cleaned_len": len(ctx.final_response),
        })

        return ctx
