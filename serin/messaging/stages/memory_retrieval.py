"""
MemoryRetrievalStage
--------------------
Fetches relevant memories, user profile, and recent messages from the
memory system (Qdrant hybrid search). Populates ctx.memories,
ctx.recent_messages, and ctx.user_profile.
"""
from __future__ import annotations

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage


class MemoryRetrievalStage(PipelineStage):
    """Searches Qdrant for semantic + keyword matches and builds context."""

    GARBAGE_PATTERNS = [
        "We are given",
        "We must write",
        "CRITICAL RULES",
        "CRITICAL:",
        "one sentence",
        "Summary:",
        "Task:",
        "INSTRUCTIONS",
        "### FINAL",
        "[the ",
        "template",
        "example",
        "Output Format",
        "JSON",
        "search_needed",
        "query:",
        "username followed by",
        "third person",
    ]

    def __init__(self, memory_system, retrieval):
        self.memory = memory_system
        self.retrieval = retrieval

    async def _run(self, ctx: MessageContext) -> MessageContext:
        logger.debug("pipeline.memory_retrieval_start", extra={
            "user": ctx.username,
            "channel_id": ctx.channel_id,
        })

        # Fetch user profile
        ctx.user_profile = self.memory.get_user_profile(ctx.user_id) or {}

        # Build context from conversation context builder
        if hasattr(self.retrieval, "build_context"):
            user_messages_for_ctx = [{"user_id": ctx.user_id, "user_name": ctx.username, "content": ctx.raw_content}]
            context_data = self.retrieval.build_context(
                user_messages=user_messages_for_ctx,
                channel_id=ctx.channel_id,
            )
        else:
            context_data = {}

        # Extract memories
        raw_memories = context_data.get("relevant_memories", [])
        clean_memories = []
        for mem in raw_memories:
            content = mem.get("content", "")
            is_garbage = any(
                pattern.lower() in content.lower()
                for pattern in self.GARBAGE_PATTERNS
            )
            if is_garbage:
                logger.warning("pipeline.memory_filtered_garbage", extra={
                    "content_preview": content[:50],
                })
                continue
            clean_memories.append(mem)

        ctx.memories = clean_memories
        ctx.recent_messages = context_data.get("recent_conversation", [])

        logger.info("pipeline.memory_retrieval_complete", extra={
            "user": ctx.username,
            "memories_found": len(ctx.memories),
            "recent_messages": len(ctx.recent_messages),
        })

        return ctx
