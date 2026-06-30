from __future__ import annotations

from typing import TYPE_CHECKING

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage

if TYPE_CHECKING:
    from serin.messaging.context import PipelineDeps


class ContextAssemblyStage(PipelineStage):
    async def _run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        ctx.formatted_context = deps.context_builder.format_context_for_llm(ctx.context)

        personality_context = deps.bot_personality.get_personality_context()
        if personality_context:
            ctx.formatted_context += f"\n\n{personality_context}"

        if ctx.preference_context:
            ctx.formatted_context += f"\n\nNote: You think {ctx.preference_context}"

        if ctx.voice_info:
            channel_name = ctx.voice_info.get('channel_name', 'voice channel')
            duration = ctx.voice_info.get('duration_minutes', 0)
            ctx.formatted_context += (
                f"\n\n[Note: {ctx.user_messages[-1]['user_name']} is "
                f"currently in '{channel_name}' ({duration} min)]"
            )

        ctx.resolved_message = ctx.user_messages[-1]['content']
        ctx.tone_modifier = deps.personality.get_tone_modifier()

        self._log_debug(ctx)

    def _log_debug(self, ctx: MessageContext) -> None:
        logger.info("=" * 60)
        logger.info("ENHANCED CONTEXT PREPARED")
        logger.info("=" * 60)
        logger.info(f"Recent messages: {len(ctx.context.get('recent_conversation', []))}")
        logger.info(f"Relevant memories: {len(ctx.context.get('relevant_memories', []))}")
        logger.info(f"Conversation mood: {deps_mood(ctx)}")
        logger.info(f"Tone modifier: {ctx.tone_modifier}")
        logger.info("=" * 60)

        # Full prompt debug
        logger.info("=" * 80)
        logger.info("COMPLETE PROMPT BEING SENT TO LLM")
        logger.info("=" * 80)
        for i, msg in enumerate(ctx.user_messages):
            logger.info(f"  [{i}] {msg['user_name']}: {msg['content'][:100]}...")
        logger.info(f"\nFormatted context length: {len(ctx.formatted_context)} chars")
        logger.info(f"\nFormatted context:\n{ctx.formatted_context}")
        logger.info(f"\nTone modifier: {ctx.tone_modifier}")
        logger.info(f"Message complexity: {ctx.length_analysis.get('complexity', 'unknown')}")
        logger.info(f"Channel ID: {ctx.channel.id}")
        logger.info(f"Channel name: {ctx.channel.name}")
        logger.info("=" * 80)
        logger.info("SENDING TO LLM")
        logger.info("=" * 80)


def deps_mood(ctx: MessageContext) -> str:
    return 'unknown'
