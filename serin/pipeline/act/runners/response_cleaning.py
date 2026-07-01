"""
ResponseCleaningStage
---------------------
Applies the thinking filter, contraction application, natural variations,
and any other post-processing to the LLM raw output.
Sets ctx.final_response.
"""
from __future__ import annotations

from serin.logger import logger
from serin.pipeline.act.runners.pipeline import PipelineStage
from serin.state.message_context import MessageContext


class ResponseCleaningStage(PipelineStage):
    """Filters thinking tags, applies natural variations, fillers, typos."""

    def __init__(self, thinking_filter):
        self.thinking_filter = thinking_filter

    async def _run(self, ctx: MessageContext) -> MessageContext:
        raw = ctx.raw_response
        if not raw:
            ctx.final_response = ""
            return ctx

        # 1. Strip thinking tags
        cleaned = self.thinking_filter.filter(raw)

        # 2. Basic cleanup
        import re

        cleaned = cleaned.strip()

        # Remove special tokens
        special_tokens = [
            "<|assistant|>",
            "<|user|>",
            "<|system|>",
            "<|start_header_id|>",
            "<|end_header_id|>",
            "<|eot_id|>",
            "<|im_start|>",
            "<|im_end|>",
            "<|begin_of_text|>",
            "<|end_of_text|>",
        ]
        for token in special_tokens:
            cleaned = cleaned.replace(token, "")

        # Remove name prefixes
        cleaned = re.sub(r"(?im)^\s*\w+:\s*", "", cleaned)

        # Remove Discord mentions
        cleaned = re.sub(r"<@!?\d+>", "", cleaned)

        # Clean excessive whitespace
        cleaned = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned)
        cleaned = re.sub(r" +", " ", cleaned)

        # Truncate if too long
        if len(cleaned) > 2000:
            cleaned = cleaned[:1997] + "..."

        ctx.final_response = cleaned

        logger.debug("pipeline.response_cleaned", extra={
            "user": ctx.username,
            "original_len": len(raw),
            "cleaned_len": len(ctx.final_response),
        })

        return ctx
