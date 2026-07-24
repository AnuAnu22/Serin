"""
PromptAssemblyStage
-------------------
Builds the LLM prompt: system message + typed context sections + conversation history.
Each memory type gets its own section with a per-type cap. Confidence is surfaced
explicitly so the model can weigh evidence against claims. Conflicts between
high-confidence facts and low-confidence claims are flagged.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator import (
    build_natural_system_prompt,
)
from serin.d1_3_state_core.d2_5_core_logger import logger
from serin.d1_3_state_core.d2_5_message_context import MessageContext


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
        logger.exception("Failed to parse timestamp: %s", ts_raw)
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


def _fuzz_memories(memories: list[dict[str, Any]], limit: int = 8) -> str:
    """Present memories as fuzzy human impressions, not database records.

    - Recent memories (< 24h): recalled clearly
    - Medium memories (1-7 days): recalled with slight vagueness
    - Old memories (> 7 days): recalled as vague impressions
    - Low confidence facts: recalled with uncertainty language
    """
    if not memories:
        return ""

    # Deduplicate by content hash
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for mem in memories:
        content = mem.get("content", "")
        key = content.strip().lower()[:100]
        if key not in seen and key:
            seen.add(key)
            unique.append(mem)
    memories = unique

    now = datetime.now(UTC)
    lines: list[str] = []

    for mem in memories[:limit]:
        content = mem.get("content", "")
        ts = mem.get("timestamp", "")
        confidence = mem.get("confidence", 1.0)
        username = mem.get("username", mem.get("user_id", "someone"))

        try:
            if isinstance(ts, str):
                mem_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            else:
                mem_time = ts
            if mem_time.tzinfo is None:
                mem_time = mem_time.replace(tzinfo=UTC)
            age_hours = (now - mem_time).total_seconds() / 3600
        except Exception:
            logger.debug("Failed to parse memory timestamp: %s", ts)
            age_hours = 999

        if len(content) > 150:
            content = content[:147] + "..."

        if age_hours < 24:
            lines.append(f"- {username} said: \"{content}\"")
        elif age_hours < 168:
            if secrets.randbelow(100) < 30:
                lines.append(f"- {username} mentioned something about: \"{content}\"")
            else:
                lines.append(f"- {username} said (a few days ago): \"{content}\"")
        else:
            if secrets.randbelow(100) < 50:
                words = content.split()
                gist = " ".join(words[:8]) + "..." if len(words) > 8 else content
                lines.append(f"- Something about {username} and: \"{gist}\" (vague memory)")
            else:
                lines.append(f"- {username} talked about (a while ago): \"{content}\"")

        if confidence < 0.5 and secrets.randbelow(100) < 40:
            lines[-1] += " (not sure about this)"

    return "\n".join(lines)


def _relationship_context(memory_system: Any, ctx: MessageContext) -> str:
    """Build a natural description of how Serin feels about this user."""
    if not memory_system or not ctx.user_id:
        return ""
    try:
        bot_user_id = None
        if ctx.message.guild and ctx.message.guild.me:
            bot_user_id = str(ctx.message.guild.me.id)
        else:
            return ""

        rels = memory_system.get_user_relationships(bot_user_id)
        if not rels:
            return ""

        user_rel = None
        for rel in rels:
            if rel.get("other_user_id") == ctx.user_id:
                user_rel = rel
                break

        if not user_rel:
            return ""

        strength = user_rel.get("relationship_strength", 0.0)
        interactions = user_rel.get("interaction_count", 0)

        username_rel = ctx.username

        lines = []

        if strength > 0.7:
            lines.append(f"You really like {username_rel}. They're one of your favorite people to talk to.")
        elif strength > 0.5:
            lines.append(f"You enjoy talking to {username_rel}. You have a good rapport.")
        elif strength > 0.3:
            lines.append(f"You're friendly with {username_rel}.")
        elif strength > 0.1:
            lines.append(f"You're neutral toward {username_rel}.")
        else:
            lines.append(f"You don't really like {username_rel}. You're curt with them.")

        if interactions > 100:
            lines.append(f"You've talked to {username_rel} a LOT ({interactions} conversations). You know them well.")
        elif interactions > 20:
            lines.append(f"You've had {interactions} conversations with {username_rel}.")
        elif interactions > 0:
            lines.append(f"You've only talked to {username_rel} a few times ({interactions}).")

        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Failed to build relationship context: %s", exc)
        return ""


def _belief_evolution_context(memory_system: Any, query: str) -> str:
    """Find beliefs that recently changed and surface them naturally."""
    if not memory_system:
        return ""
    try:
        beliefs = memory_system.get_relevant_beliefs(query=query, limit=5)
        if not beliefs:
            return ""

        evolved = []
        for belief in beliefs:
            state = belief.get("state", "")
            content = belief.get("content", "")
            confidence = belief.get("confidence", 0.5)

            if state == "CONTESTED" and confidence < 0.5:
                evolved.append(
                    f"You used to believe \"{content}\" but now you're not so sure. "
                    f"You might mention this uncertainty naturally."
                )
            elif state == "SUPERSEDED":
                evolved.append(
                    f"You used to think \"{content}\" but your opinion has changed. "
                    f"You can reference how your thinking evolved."
                )
            elif state == "SUPPORTED" and confidence > 0.8:
                evolved.append(
                    f"You strongly believe \"{content}\". "
                    f"This is a core opinion you hold confidently."
                )

        if not evolved:
            return ""
        return "\n".join(evolved[:3])
    except Exception as exc:
        logger.debug("Failed to build belief evolution context: %s", exc)
        return ""


def _facts_context(memory_system: Any, user_id: str) -> str:
    """Build a natural description of known facts about this user from the Bayesian engine."""
    if not memory_system or not user_id:
        return ""
    try:
        engine = getattr(memory_system, "belief_engine", None)
        if engine is None:
            return ""
        facts = engine.get_facts_for_user(user_id, limit=5)
        if not facts:
            return ""
        lines: list[str] = []
        for f in facts:
            label = engine.get_confidence_label(f["belief"], f["variance"])
            state = f.get("state", "PENDING")
            if state == "SUPERSEDED":
                continue
            elif state == "CONTESTED":
                lines.append(f"- {f['claim']} ({label}, but someone disagreed)")
            else:
                lines.append(f"- {f['claim']} ({label})")
        if not lines:
            return ""
        return "Things you know about this person:\n" + "\n".join(lines)
    except Exception:
        return ""


CONTEXT_BUDGET: dict[str, int] = {
    "facts": 200,
    "beliefs": 100,
    "relationship": 80,
    "belief_evolution": 80,
    "missed": 80,
    "memories": 200,
    "personality": 50,
    "user_profile": 100,
    "history": 500,
}
_TOTAL_BUDGET_CHARS: int = sum(v * 4 for v in CONTEXT_BUDGET.values())


def _truncate_to_budget(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."


class PromptAssemblyStage(PipelineStage):
    """Assembles the final messages array sent to the LLM."""

    def __init__(self, mention_translator: Any, memory_system: Any = None) -> None:
        self.mention_translator = mention_translator
        self.memory_system = memory_system

    async def _run(self, ctx: MessageContext) -> MessageContext:
        # Build system prompt
        ctx.system_prompt = build_natural_system_prompt()
        if ctx.tone_modifier:
            ctx.system_prompt += f"\n\nCurrent mood: {ctx.tone_modifier}"

        # ── Binding constraints from Response Planner ────────────────────
        plan = ctx.response_plan or {}
        if plan.get("constraints"):
            constraint_lines = []
            for c in plan["constraints"]:
                constraint_lines.append(f"- {c}")
            ctx.system_prompt += (
                "\n\nResponse constraints (these are important — "
                "don't ignore them):\n" + "\n".join(constraint_lines)
            )

        if plan.get("forbidden_moves"):
            forbid_lines = []
            for f in plan["forbidden_moves"]:
                forbid_lines.append(f"- Don't {f}")
            ctx.system_prompt += (
                "\n\nForbidden:\n" + "\n".join(forbid_lines)
            )

        if plan.get("stance") == "uncertain":
            ctx.system_prompt += (
                "\n\nYou're uncertain about something in this conversation. "
                "It's fine to say you're not sure."
            )
        elif plan.get("stance") == "disagree_gently":
            ctx.system_prompt += (
                "\n\nThe evidence supports a different conclusion than what "
                "was just said. You can disagree, but be natural about it."
            )
        elif plan.get("stance") == "disagree_firmly":
            ctx.system_prompt += (
                "\n\nThe evidence strongly supports a different conclusion. "
                "State what you know confidently, using the evidence you have."
            )
        elif plan.get("stance") == "agree":
            ctx.system_prompt += (
                "\n\nThe evidence agrees with what was just said. "
                "Affirm and add relevant details."
            )

        # Build typed context sections
        context_parts = []

        # 0. Facts — from Bayesian engine with confidence labels
        fact_text = _facts_context(self.memory_system, str(ctx.user_id))
        if fact_text:
            context_parts.append(
                _truncate_to_budget(fact_text, CONTEXT_BUDGET["facts"])
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
                _truncate_to_budget("What I think:\n" + "\n".join(belief_lines), CONTEXT_BUDGET["beliefs"])
            )

        # 1. Relationship context — how Serin feels about this user
        rel_context = _relationship_context(self.memory_system, ctx)
        if rel_context:
            context_parts.append(
                _truncate_to_budget(
                    f"Your feelings about {ctx.username}:\n{rel_context}",
                    CONTEXT_BUDGET["relationship"]
                )
            )

        # 2. Belief evolution — how Serin's opinions have changed
        belief_context = _belief_evolution_context(self.memory_system, ctx.raw_content)
        if belief_context:
            context_parts.append(
                _truncate_to_budget("Your evolving opinions (reference naturally if relevant):\n" + belief_context, CONTEXT_BUDGET["belief_evolution"])
            )

        # 3. Missed messages — things Serin didn't notice earlier
        try:
            from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_1_decision_temporal import (
                clear_missed_messages,
                get_missed_messages,
            )
            missed = get_missed_messages(ctx.channel_id)
            if missed:
                missed_text = "\n".join(
                    f"- {m['username']} asked you something earlier: \"{m['content'][:100]}\" (you missed it)"
                    for m in missed[-3:]
                )
                context_parts.append(
                    _truncate_to_budget(
                        f"Messages you missed earlier (you can bring them up naturally):\n{missed_text}",
                        CONTEXT_BUDGET["missed"]
                    )
                )
                clear_missed_messages(ctx.channel_id)
        except Exception as exc:
            logger.debug("Failed to add missed messages context: %s", exc)

        # 4. Fuzzy memories — human-like imperfect recall
        memory_text = _fuzz_memories(ctx.memories, limit=8)
        if memory_text:
            context_parts.append(
                _truncate_to_budget(
                    f"Things you vaguely remember from past conversations:\n{memory_text}",
                    CONTEXT_BUDGET["memories"]
                )
            )

        # 5. Personality context
        if ctx.personality_context:
            context_parts.append(
                _truncate_to_budget(ctx.personality_context, CONTEXT_BUDGET["personality"])
            )

        # 6. Relationships
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
                context_parts.append(_truncate_to_budget("Relationships: " + " ".join(rel_lines), CONTEXT_BUDGET["relationship"]))

        # 7. User profile
        if ctx.user_profile:
            traits = ctx.user_profile.get("personality_traits", [])[:5]
            interests = ctx.user_profile.get("interests", [])[:5]
            if traits or interests:
                profile_parts = []
                if traits:
                    profile_parts.append(f"Traits: {', '.join(traits)}")
                if interests:
                    profile_parts.append(f"Interests: {', '.join(interests)}")
                context_parts.append(_truncate_to_budget("User profile: " + "; ".join(profile_parts), CONTEXT_BUDGET["user_profile"]))

        ctx.context_block = "\n\n".join(context_parts)

        # Build messages array
        messages = []
        messages.append({"role": "system", "content": ctx.system_prompt})

        if ctx.context_block:
            messages.append({"role": "system", "content": ctx.context_block})

        # ── Filter, deduplicate, and fold conversation history ─────────
        bot_id = ""
        try:
            if ctx.message and ctx.message.guild and ctx.message.guild.me:
                bot_id = str(ctx.message.guild.me.id)
        except Exception:
            pass

        _system_patterns = [
            "voice channel",
            "started a call", "ended a call",
            "pinned a message", "added a reaction",
        ]

        filtered_messages: list[dict[str, Any]] = []
        for msg in ctx.recent_messages:
            content = msg.get("content", "").strip()
            if not content:
                continue
            if any(pat in content.lower() for pat in _system_patterns):
                continue
            if len(content) < 2:
                continue
            filtered_messages.append(msg)

        # Collapse consecutive duplicates from same user
        collapsed: list[dict[str, Any]] = []
        for msg in filtered_messages:
            if collapsed:
                prev = collapsed[-1]
                if (prev.get("user_id") == msg.get("user_id") and
                        prev.get("content", "").strip().lower() == msg.get("content", "").strip().lower()):
                    continue
            collapsed.append(msg)

        collapsed = collapsed[-10:]

        for msg in collapsed:
            msg_user_id = str(msg.get("user_id", ""))
            username = msg.get("username", "unknown")
            content = msg.get("content", "")
            if bot_id and msg_user_id == bot_id:
                messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": "user", "content": f"{username}: {content}"})

        # Add current message (with image if present)
        current_msg: dict[str, Any] = {"role": "user", "content": f"{ctx.username}: {ctx.raw_content}"}

        # Check if this message has an image attachment
        visual_contexts = ctx.metadata.get("pending_visual_contexts", {}) if ctx.metadata else {}
        msg_id = getattr(ctx.message, "id", None) if ctx.message else None
        if msg_id and msg_id in visual_contexts:
            current_msg["image_url"] = visual_contexts[msg_id]
            logger.debug("Added image_url to prompt for message %s", msg_id)

        messages.append(current_msg)

        ctx.built_messages = messages

        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_11_debug_routes import (
                store_prompt_debug,
            )
            full_prompt = "\n\n".join(
                str(message.get("content", "")) for message in ctx.built_messages
            )
            channel = getattr(getattr(ctx, "message", None), "channel", None)
            store_prompt_debug({
                "user": getattr(ctx, "username", ""),
                "channel": getattr(channel, "name", ""),
                "system_prompt": ctx.system_prompt[:2000],
                "memories": memory_text[:1000] if memory_text else "",
                "relationship": rel_context[:500] if rel_context else "",
                "beliefs": belief_context[:500] if belief_context else "",
                "time": "",
                "energy": ctx.tone_modifier[:200] if ctx.tone_modifier else "",
                "user_message": getattr(ctx, "raw_content", "")[:500],
                "full_prompt": full_prompt[:5000],
            })
        except Exception as exc:
            logger.debug("Failed to store prompt debug entry: %s", exc)

        logger.debug("pipeline.prompt_assembled", extra={
            "user": ctx.username,
            "system_prompt_len": len(ctx.system_prompt),
            "context_block_len": len(ctx.context_block),
            "built_messages_count": len(ctx.built_messages),
        })

        return ctx
