"""
MemoryRetrievalStage
--------------------
Fetches relevant memories, user profile, and recent messages from the
memory system (Qdrant hybrid search). Populates ctx.memories,
ctx.recent_messages, and ctx.user_profile.
"""
from __future__ import annotations

from serin.config.logger import logger
from serin.state.message_context import MessageContext
from serin.pipeline.act.stages_init import PipelineStage


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
                mood_state={"tone_modifier": ctx.tone_modifier},
            )
        else:
            context_data = {}

        # Extract memories by type
        facts = context_data.get("facts", [])
        beliefs = context_data.get("beliefs", [])
        evidence_memories = context_data.get("evidence_memories", [])
        episode_memories = context_data.get("episode_memories", [])
        utterance_memories = context_data.get("utterance_memories", [])

        # Apply garbage filter to facts and all memory types
        def _clean_garbage(memories):
            clean = []
            for mem in memories:
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
                clean.append(mem)
            return clean

        ctx.facts = _clean_garbage(facts)
        ctx.beliefs = _clean_garbage(beliefs)
        ctx.evidence_memories = _clean_garbage(evidence_memories)
        ctx.episode_memories = _clean_garbage(episode_memories)
        ctx.utterance_memories = _clean_garbage(utterance_memories)

        # Deprioritize summaries when evidence exists for the same topic.
        # If evidence memories share keywords with episode memories, the
        # summary is redundant — raw evidence is always preferred.
        if ctx.evidence_memories and ctx.episode_memories:
            evidence_keywords = set()
            for ev in ctx.evidence_memories:
                for w in ev.get("content", "").lower().split():
                    if len(w) > 4:
                        evidence_keywords.add(w)
            filtered_episodes = []
            for ep in ctx.episode_memories:
                ep_words = set(w for w in ep.get("content", "").lower().split() if len(w) > 4)
                # Require at least 2 overlapping content words to consider
                # a summary redundant — single-word matches are coincidental
                overlap = evidence_keywords & ep_words
                if len(overlap) >= 2:
                    logger.debug(
                        "pipeline.summary_deprioritized",
                        extra={
                            "summary": ep.get("content", "")[:40],
                            "overlap_keywords": list(overlap)[:5],
                        }
                    )
                    continue
                filtered_episodes.append(ep)
            ctx.episode_memories = filtered_episodes

        # Flatten all memories for backwards compatibility
        ctx.memories = (ctx.evidence_memories + ctx.episode_memories + ctx.utterance_memories)

        ctx.recent_messages = context_data.get("recent_conversation", [])
        ctx.relationships = context_data.get("relationships", [])

        logger.info("pipeline.memory_retrieval_complete", extra={
            "user": ctx.username,
            "facts_found": len(ctx.facts),
            "beliefs_found": len(ctx.beliefs),
            "evidence_found": len(ctx.evidence_memories),
            "episodes_found": len(ctx.episode_memories),
            "utterances_found": len(ctx.utterance_memories),
            "recent_messages": len(ctx.recent_messages),
            "relationships_found": len(ctx.relationships),
        })

        return ctx
