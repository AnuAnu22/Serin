from __future__ import annotations

from typing import TYPE_CHECKING

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage

if TYPE_CHECKING:
    from serin.messaging.context import PipelineDeps


class MemoryRetrievalStage(PipelineStage):
    GARBAGE_PATTERNS = [
        "We are given", "We must write", "CRITICAL RULES", "CRITICAL:",
        "one sentence", "Summary:", "Task:", "INSTRUCTIONS",
        "### FINAL", "[the ", "template", "example",
        "Output Format", "JSON", "search_needed", "query:",
        "username followed by", "third person"
    ]

    async def _run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        logger.debug("Building enhanced context...")

        ctx.context = deps.context_builder.build_context(
            user_messages=ctx.user_messages,
            channel_id=str(ctx.channel.id)
        )

        # Filter polluted memories
        clean_memories = []
        for mem in ctx.context.get('relevant_memories', []):
            content = mem.get('content', '')
            is_garbage = any(
                pattern.lower() in content.lower()
                for pattern in self.GARBAGE_PATTERNS
            )
            if is_garbage:
                logger.warning(f"Filtered polluted memory: {content[:50]}...")
                continue
            clean_memories.append(mem)
        ctx.context['relevant_memories'] = clean_memories

        deps.stats['context_improvements'] += 1
        logger.info("Using ConversationContextBuilder for context")
        self._log_context(ctx)

    def _log_context(self, ctx: MessageContext) -> None:
        logger.info(f"Recent messages: {len(ctx.context.get('recent_conversation', []))}")
        logger.info(f"Relevant memories: {len(ctx.context.get('relevant_memories', []))}")
        logger.info(f"User profiles: {len(ctx.context.get('profiles', {}))}")
        logger.info(f"Relationships: {len(ctx.context.get('relationships', []))}")
