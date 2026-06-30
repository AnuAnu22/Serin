from __future__ import annotations

from typing import TYPE_CHECKING

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage

if TYPE_CHECKING:
    from serin.messaging.context import PipelineDeps


class GenerationStage(PipelineStage):
    async def _run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        deps.current_state['abort_flag'] = False

        from serin.messaging.response_generator import get_response_natural

        response = await get_response_natural(
            current_messages=ctx.user_messages,
            context=ctx.formatted_context,
            resolved_last_message=ctx.resolved_message,
            tone_modifier=ctx.tone_modifier,
            personality_state=deps.personality.__dict__,
            message_complexity=ctx.length_analysis.get('complexity', 'medium'),
            is_instruction=ctx.is_instruction,
        )

        if deps.current_state.get('abort_flag'):
            logger.warning("Response generation aborted by user!")
            deps.current_state['status'] = 'IDLE'
            deps.current_state['current_prompt'] = None
            ctx.should_halt = True
            return

        if not response or not response.strip():
            logger.warning("Empty response generated, not sending")
            ctx.should_halt = True
            return

        if len(response) > 2000:
            response = response[:1997] + "..."

        response = deps.mention_translator.restore_for_discord(response, ctx.channel.guild)

        deps.current_state['status'] = 'SENDING'

        await deps.response_controller.send_with_typing(
            ctx.channel,
            response,
            simulate_typing=True,
            message_complexity=ctx.length_analysis.get('complexity', 'medium'),
            has_question='?' in ctx.user_messages[-1]['content']
        )

        deps.response_controller.mark_response(str(ctx.channel.id))

        deps.stats['responses_generated'] += 1
        logger.info(f"Response sent: '{response[:60]}...'")

        ctx.response = response
