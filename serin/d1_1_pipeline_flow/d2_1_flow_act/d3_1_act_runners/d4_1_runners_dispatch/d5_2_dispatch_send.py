"""
SendStage
---------
Sends the final response to Discord with typing simulation.
Uses Hawkes-inspired timing from ConversationDynamicsEngine.
Sets ctx.metadata["message_sent"] = True after successful send.
"""
from __future__ import annotations

import asyncio
from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from serin.d1_4_config_base.d2_3_core_logger import logger


class SendStage(PipelineStage):
    """Sends the final response with realistic typing delay."""

    def __init__(self, dynamics: Any | None = None) -> None:
        self.dynamics = dynamics

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

        # Absolute floor: Serin never replies *literally* instantly, even for
        # the creator override (vision: "It never replies instantly (unless a
        # human would)"). The dev loop still gets a near-instant reply.
        min_send_delay = 0.4

        if ctx.metadata.get("instant_reply"):
            # Creator override — the dev is testing live, skip the Hawkes delay.
            delay = min_send_delay
        elif self.dynamics:
            delay = self.dynamics.sample_delay(ctx.channel_id)
        else:
            delay = min(len(response) * 0.01, 3.0) + 0.5

        if delay > 0:
            async with channel.typing():
                await asyncio.sleep(delay)

        await channel.send(response)

        ctx.metadata["message_sent"] = True

        logger.info("pipeline.response_sent", extra={
            "user": ctx.username,
            "user_id": ctx.user_id,
            "channel_id": ctx.channel_id,
            "response_len": len(response),
        })

        return ctx
