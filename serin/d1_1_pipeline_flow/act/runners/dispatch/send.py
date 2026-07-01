"""
SendStage
---------
Sends the final response to Discord with typing simulation.
Uses the channel from ctx.message.channel.
Sets ctx.metadata["message_sent"] = True after successful send.
"""
from __future__ import annotations

import asyncio
import secrets

from serin.d1_1_pipeline_flow.act.runners.pipeline import PipelineStage
from serin.d1_3_state_core.logger import logger
from serin.d1_3_state_core.message_context import MessageContext


def _uniform(a: float, b: float) -> float:
    return a + (b - a) * secrets.randbelow(10_000_000) / 10_000_000


class SendStage(PipelineStage):
    """Sends the final response with realistic typing delay."""

    def __init__(self):
        pass

    async def _run(self, ctx: MessageContext) -> MessageContext:
        response = ctx.final_response
        if not response:
            ctx.metadata["message_sent"] = False
            return ctx

        channel = ctx.message.channel
        if not channel:
            logger.warning("pipeline.send_no_channel", extra={
                "user": ctx.username,
            })
            ctx.metadata["message_sent"] = False
            return ctx

        # Simulate typing
        typing_delay = min(len(response) * 0.01, 3.0)  # ~10ms per char, max 3s
        typing_delay += _uniform(0.2, 0.8)

        async with channel.typing():
            await asyncio.sleep(typing_delay)

        await channel.send(response)

        ctx.metadata["message_sent"] = True

        logger.info("pipeline.response_sent", extra={
            "user": ctx.username,
            "user_id": ctx.user_id,
            "channel_id": ctx.channel_id,
            "response_len": len(response),
        })

        return ctx
