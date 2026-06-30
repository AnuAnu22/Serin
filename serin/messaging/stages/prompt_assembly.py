"""
PromptAssemblyStage
-------------------
Builds the LLM prompt: system message + typed context sections + conversation history.
Each memory type gets its own section with a per-type cap. Confidence is surfaced
explicitly so the model can weigh evidence against claims. Conflicts between
high-confidence facts and low-confidence claims are flagged.
"""
from __future__ import annotations

from datetime import datetime
from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage
from serin.messaging.response_generator import build_natural_system_prompt


def _time_label(ts_raw: str) -> str:
    """Convert a timestamp string to a human-readable label."""
    if not ts_raw:
        return ""
    try:
        dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        delta = datetime.now() - dt
        if delta.days == 0:
            return "[Today] "
        elif delta.days == 1:
            return "[Yesterday] "
        elif delta.days < 7:
            return f"[{delta.days}d ago] "
        return f"[{ts_raw[:10]}] "
    except (ValueError, TypeError):
        return f"[{ts_raw[:10]}] "


def _confidence_label(conf: float) -> str:
    """Convert a confidence score to a human-readable label."""
    if conf >= 0.9:
        return "[very confident]"
    elif conf >= 0.7:
        return "[confident]"
    elif conf >= 0.4:
        return "[uncertain]"
    return "[low confidence]"


def _format_memories(memories, max_items: int) -> list[str]:
    """Format a list of memories with time labels, limited to max_items."""
    sorted_mems = sorted(
        memories,
        key=lambda m: m.get("timestamp", ""),
        reverse=True,
    )
    return [
        f"- {_time_label(m.get('timestamp', ''))}{m['content']}"
        for m in sorted_mems[:max_items]
    ]


class PromptAssemblyStage(PipelineStage):
    """Assembles the final messages array sent to the LLM."""

    def __init__(self, mention_translator):
        self.mention_translator = mention_translator

    async def _run(self, ctx: MessageContext) -> MessageContext:
        # Build system prompt
        ctx.system_prompt = build_natural_system_prompt()
        if ctx.tone_modifier:
            ctx.system_prompt += f"\n\nCurrent mood: {ctx.tone_modifier}"

        # Build typed context sections
        context_parts = []

        # 0. Facts — highest priority, from FactStore with confidence surfaced
        if ctx.facts:
            fact_lines = []
            # Detect conflict: high-confidence fact vs low-confidence user claim
            high_conf_facts = [
                f for f in ctx.facts
                if f.get("confidence", 0) >= 0.7
                and f.get("source_type") == "derived"
            ]
            low_conf_claims = [
                f for f in ctx.facts
                if f.get("confidence", 0) < 0.4
                and f.get("source_type") == "user_claim"
            ]

            # Surface conflict explicitly if evidence contradicts a claim
            if high_conf_facts and low_conf_claims:
                for hf in high_conf_facts:
                    for lc in low_conf_claims:
                        if any(kw in lc.get("content", "").lower()
                               for kw in ["win", "won", "lost", "wrong"]):
                            fact_lines.append(
                                f"⚠ {hf['content']} "
                                f"{_confidence_label(hf.get('confidence', 0))} "
                                f"but {lc.get('source_username', 'someone')} claims "
                                f"the opposite {_confidence_label(lc.get('confidence', 0))}"
                            )

            for f in ctx.facts[:5]:
                label = _time_label(f.get("timestamp", ""))
                conf = f.get("confidence", 0.5)
                conf_tag = _confidence_label(conf)
                source_tag = f.get("source_type", "")
                if source_tag == "evidence_extracted":
                    tag = " [evidence]"
                elif source_tag == "user_claim":
                    tag = f" [{f.get('source_username', 'someone')} claims]"
                elif source_tag == "bot_assertion":
                    tag = " [known]"
                elif source_tag == "derived":
                    tag = " [derived]"
                else:
                    tag = ""
                fact_lines.append(
                    f"- {label}{f['content']} {conf_tag}{tag}"
                )
            if fact_lines:
                context_parts.append(
                    "Things I know to be true:\n" + "\n".join(fact_lines)
                )

        # 0b. Beliefs — what I think based on weighing facts
        if ctx.beliefs:
            belief_lines = []
            for b in ctx.beliefs[:3]:
                conf = b.get("confidence", 0.5)
                conf_tag = _confidence_label(conf)
                evidence_ct = b.get("evidence_count", 0)
                claim_ct = b.get("claim_count", 0)
                belief_lines.append(
                    f"- {b['content']} {conf_tag} "
                    f"(based on {evidence_ct} evidence pieces, "
                    f"{claim_ct} counter-claims)"
                )
            context_parts.append(
                "What I think:\n" + "\n".join(belief_lines)
            )

        # 1. Evidence — second priority, raw evidence seen
        if ctx.evidence_memories:
            lines = _format_memories(ctx.evidence_memories, max_items=3)
            context_parts.append("Evidence I've seen:\n" + "\n".join(lines))

        # 2. Episodic memories — what happened previously on this topic
        if ctx.episode_memories:
            lines = _format_memories(ctx.episode_memories, max_items=2)
            context_parts.append("What I remember about this:\n" + "\n".join(lines))

        # 3. Utterance memories — what people have said (lowest priority)
        if ctx.utterance_memories:
            lines = _format_memories(ctx.utterance_memories, max_items=2)
            if context_parts:
                context_parts.append("What people have said:\n" + "\n".join(lines))
            else:
                context_parts.append("Things people have said:\n" + "\n".join(lines))

        # 4. Personality context
        if ctx.personality_context:
            context_parts.append(ctx.personality_context)

        # 5. Relationships
        if ctx.relationships:
            rel_lines = []
            for rel in ctx.relationships[:3]:
                other = rel.get("other_username", "someone")
                strength = rel.get("relationship_strength", 0)
                if strength > 0.7:
                    rel_lines.append(f"You talk to {other} often — you're close.")
                elif strength > 0.4:
                    rel_lines.append(f"You know {other} — you've talked a few times.")
            if rel_lines:
                context_parts.append("Relationships: " + " ".join(rel_lines))

        # 6. User profile
        if ctx.user_profile:
            traits = ctx.user_profile.get("personality_traits", [])[:5]
            interests = ctx.user_profile.get("interests", [])[:5]
            if traits or interests:
                profile_parts = []
                if traits:
                    profile_parts.append(f"Traits: {', '.join(traits)}")
                if interests:
                    profile_parts.append(f"Interests: {', '.join(interests)}")
                context_parts.append("User profile: " + "; ".join(profile_parts))

        ctx.context_block = "\n\n".join(context_parts)

        # Build messages array
        messages = []
        messages.append({"role": "system", "content": ctx.system_prompt})

        if ctx.context_block:
            messages.append({"role": "system", "content": ctx.context_block})

        # Add recent conversation
        for msg in ctx.recent_messages:
            role = "user"
            content = f"{msg.get('user_name', 'unknown')}: {msg.get('content', '')}"
            messages.append({"role": role, "content": content})

        # Add current message
        messages.append(
            {"role": "user", "content": f"{ctx.username}: {ctx.raw_content}"}
        )

        ctx.built_messages = messages

        logger.debug("pipeline.prompt_assembled", extra={
            "user": ctx.username,
            "system_prompt_len": len(ctx.system_prompt),
            "context_block_len": len(ctx.context_block),
            "built_messages_count": len(ctx.built_messages),
        })

        return ctx
