from __future__ import annotations

from typing import TYPE_CHECKING

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage

if TYPE_CHECKING:
    from serin.messaging.context import PipelineDeps


class MessagePreparationStage(PipelineStage):
    async def _run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        batch = [m for m in ctx.batch if not getattr(m.author, "bot", False)]
        if not batch:
            ctx.should_halt = True
            return

        ctx.channel = batch[0].channel

        user_messages = []
        for msg in batch:
            content = deps.mention_translator.clean_for_bot(msg.content, msg)
            if msg.attachments:
                has_image = any(
                    a.content_type and a.content_type.startswith('image/')
                    for a in msg.attachments
                )
                if has_image:
                    content += " [User posted an image]"

            payload = {
                'user_id': str(msg.author.id),
                'user_name': msg.author.display_name,
                'content': content,
                'timestamp': msg.created_at.isoformat()
            }

            if msg.id in deps.pending_visual_contexts:
                payload['image_url'] = deps.pending_visual_contexts[msg.id]
                del deps.pending_visual_contexts[msg.id]

            user_messages.append(payload)

        ctx.user_messages = user_messages

        # Admin instruction check
        last_msg_content = ctx.user_messages[-1]['content']
        last_msg_user = ctx.user_messages[-1]['user_name']
        is_creator = (
            deps.response_controller.creator_id
            and ctx.user_messages[-1]['user_id'] == deps.response_controller.creator_id
        )

        if last_msg_content.startswith('/instruct'):
            if 'rin' in last_msg_user.lower() or is_creator:
                logger.info(f"Admin instruction detected from {last_msg_user}")
                ctx.is_instruction = True
                ctx.user_messages[-1]['content'] = last_msg_content.replace('/instruct', '', 1).strip()
            else:
                logger.warning(f"Unauthorized /instruct attempt from {last_msg_user}")
                ctx.should_halt = True
                return
