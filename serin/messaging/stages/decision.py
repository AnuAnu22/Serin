"""
ResponseDecisionStage
---------------------
Decides whether Serin should respond to this message at all.
Sets ctx.should_respond. If False, sets ctx.halt_reason and pipeline halts.
"""
from __future__ import annotations

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage


class ResponseDecisionStage(PipelineStage):
    """Decides whether to respond based on mention, rate limits, and DM rules."""

    def __init__(self, response_controller):
        self.controller = response_controller

    async def _run(self, ctx: MessageContext) -> MessageContext:
        should_respond, reason = self.controller.should_respond(
            message_content=ctx.raw_content,
            channel_id=ctx.channel_id,
            bot_mentioned=ctx.message.guild is not None
            and ctx.message.guild.me in ctx.message.mentions,
            user_id=ctx.user_id,
            recent_messages=[],
        )

        if not should_respond:
            ctx.should_respond = False
            ctx.halt_reason = reason or "no_response_needed"
            logger.debug("pipeline.decision", extra={
                "user": ctx.username,
                "user_id": ctx.user_id,
                "channel_id": ctx.channel_id,
                "decision": False,
                "reason": ctx.halt_reason,
            })
            return ctx

        ctx.should_respond = True
        logger.debug("pipeline.decision", extra={
            "user": ctx.username,
            "user_id": ctx.user_id,
            "channel_id": ctx.channel_id,
            "decision": True,
            "reason": "will_respond",
        })
        return ctx
