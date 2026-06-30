from __future__ import annotations

from typing import TYPE_CHECKING

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage

if TYPE_CHECKING:
    from serin.messaging.context import PipelineDeps


class ResponseDecisionStage(PipelineStage):
    async def _run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        should_respond, reason = deps.response_controller.should_respond(
            message_content=ctx.user_messages[-1]['content'],
            channel_id=str(ctx.channel.id),
            bot_mentioned=ctx.bot_mentioned or ctx.is_instruction,
            user_id=ctx.primary_user_id,
            recent_messages=ctx.context.get('recent_conversation', [])
        )

        if not should_respond and not ctx.is_instruction:
            logger.info(f"Skipping response (reason: {reason})")
            ctx.should_halt = True
            return

        logger.info(f"Responding (reason: {reason})")
