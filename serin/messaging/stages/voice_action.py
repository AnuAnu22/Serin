from __future__ import annotations

from typing import TYPE_CHECKING

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage

if TYPE_CHECKING:
    from serin.messaging.context import PipelineDeps


class VoiceActionStage(PipelineStage):
    async def _run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        if not deps.voice_action_decider or not deps.voice_action_callback:
            return
        if deps.current_state.get('abort_flag'):
            return

        try:
            voice_decision = await deps.voice_action_decider.decide(
                user_message=ctx.user_messages[-1]['content'],
                context=ctx.formatted_context,
                personality_state=deps.personality.__dict__,
            )
            if voice_decision and voice_decision['action'] in ('join', 'leave'):
                result = await deps.voice_action_callback(
                    voice_decision,
                    ctx.primary_user_id,
                    ctx.channel.guild.id,
                )
                if result.get('executed'):
                    ctx.formatted_context += (
                        f"\n\n[System: Serin {voice_decision['action']}ed the voice channel "
                        f"because: {voice_decision.get('reason', 'unknown')}]"
                    )
                elif result.get('message') == 'user_not_in_vc':
                    ctx.formatted_context += (
                        "\n\n[System: Serin tried to join the user's voice channel "
                        "but the user is not currently in one. Serin should respond naturally.]"
                    )
        except Exception as e:
            logger.error(f"Voice action error: {e}")
            ctx.formatted_context += (
                "\n\n[System: Serin could not decide on a voice action due to an error."
                " No action was taken. Do not assume Serin joined or left any voice channel.]"
            )
