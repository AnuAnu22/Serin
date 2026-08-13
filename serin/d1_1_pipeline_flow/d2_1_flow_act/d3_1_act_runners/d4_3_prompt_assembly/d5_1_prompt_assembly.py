"""
PromptAssemblyStage
-------------------
Builds the LLM prompt: system message + typed context sections + conversation history.
Each memory type gets its own section with a per-type cap. Confidence is surfaced
explicitly so the model can weigh evidence against claims. Conflicts between
high-confidence facts and low-confidence claims are flagged.
"""
# --- Imports ---
from __future__ import annotations

from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_3_prompt_assembly.d5_2_prompt_helpers import (
    CONTEXT_BUDGET,
    _affect_context,
    _belief_evolution_context,
    _confidence_label,
    _facts_context,
    _fuzz_memories,
    _truncate_to_budget,
)
from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator import (
    build_natural_system_prompt,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from serin.d1_4_config_base.d2_3_core_logger import logger

# --- Types ---
# (none)

# --- Constants ---
# (none)

# --- Entry ---


class PromptAssemblyStage(PipelineStage):
    """Assembles the final messages array sent to the LLM."""

    def __init__(self, mention_translator: Any, memory_system: Any = None,
                 affect_engine: Any = None) -> None:
        self.mention_translator = mention_translator
        self.memory_system = memory_system
        self.affect_engine = affect_engine

# --- Core ---
    async def _run(self, ctx: MessageContext) -> MessageContext:
        ctx.system_prompt = build_natural_system_prompt()
        if ctx.tone_modifier:
            ctx.system_prompt += f"\n\nCurrent mood: {ctx.tone_modifier}"

        self._add_response_plan_constraints(ctx)

        context_parts: list[str] = []
        self._build_facts_context(ctx, context_parts)
        self._build_beliefs_context(ctx, context_parts)
        self._build_relationship_context(ctx, context_parts)
        self._build_belief_evolution_context(ctx, context_parts)
        self._build_missed_messages_context(ctx, context_parts)
        self._build_memory_context(ctx, context_parts)
        self._build_personality_context(ctx, context_parts)
        self._build_user_profile_context(ctx, context_parts)

        ctx.context_block = "\n\n".join(context_parts)
        ctx.built_messages = self._build_messages(ctx)

        memory_text = _fuzz_memories(ctx.memories, limit=8)
        snap = self.affect_engine.snapshot_cached(ctx.user_id) if self.affect_engine else None
        rel_context = _affect_context(snap, ctx.username) if snap is not None else ""
        belief_context = _belief_evolution_context(self.memory_system, ctx.raw_content)
        self._store_prompt_debug(ctx, memory_text or "", rel_context or "", belief_context or "")

        return ctx

    def _add_response_plan_constraints(self, ctx: MessageContext) -> None:
        plan = ctx.response_plan or {}
        if plan.get("constraints"):
            constraint_lines = [f"- {c}" for c in plan["constraints"]]
            ctx.system_prompt += (
                "\n\nResponse constraints (these are important — "
                "don't ignore them):\n" + "\n".join(constraint_lines)
            )
        if plan.get("forbidden_moves"):
            forbid_lines = [f"- Don't {f}" for f in plan["forbidden_moves"]]
            ctx.system_prompt += "\n\nForbidden:\n" + "\n".join(forbid_lines)
        stance = plan.get("stance")
        if stance == "uncertain":
            ctx.system_prompt += "\n\nYou're uncertain about something in this conversation. It's fine to say you're not sure."
        elif stance == "disagree_gently":
            ctx.system_prompt += "\n\nThe evidence supports a different conclusion than what was just said. You can disagree, but be natural about it."
        elif stance == "disagree_firmly":
            ctx.system_prompt += "\n\nThe evidence strongly supports a different conclusion. State what you know confidently, using the evidence you have."
        elif stance == "agree":
            ctx.system_prompt += "\n\nThe evidence agrees with what was just said. Affirm and add relevant details."

    def _build_facts_context(self, ctx: MessageContext, context_parts: list[str]) -> None:
        fact_text = _facts_context(self.memory_system, str(ctx.user_id))
        if fact_text:
            context_parts.append(_truncate_to_budget(fact_text, CONTEXT_BUDGET["facts"]))

    def _build_beliefs_context(self, ctx: MessageContext, context_parts: list[str]) -> None:
        if not ctx.beliefs:
            return
        belief_lines = []
        for b in ctx.beliefs[:3]:
            conf = b.get("confidence", 0.5)
            conf_tag = _confidence_label(conf)
            evidence_ct = b.get("evidence_count", 0)
            claim_ct = b.get("claim_count", 0)
            belief_lines.append(
                f"- {b['content']} {conf_tag} "
                f"(based on {evidence_ct} evidence pieces, {claim_ct} counter-claims)"
            )
        context_parts.append(
            _truncate_to_budget("What I think:\n" + "\n".join(belief_lines), CONTEXT_BUDGET["beliefs"])
        )

    def _build_relationship_context(self, ctx: MessageContext, context_parts: list[str]) -> None:
        snap = self.affect_engine.snapshot_cached(ctx.user_id) if self.affect_engine else None
        rel_context = _affect_context(snap, ctx.username) if snap is not None else ""
        if rel_context:
            context_parts.append(
                _truncate_to_budget(
                    f"Your feelings about {ctx.username}:\n{rel_context}",
                    CONTEXT_BUDGET["relationship"]
                )
            )

    def _build_belief_evolution_context(self, ctx: MessageContext, context_parts: list[str]) -> None:
        belief_context = _belief_evolution_context(self.memory_system, ctx.raw_content)
        if belief_context:
            context_parts.append(
                _truncate_to_budget(
                    "Your evolving opinions (reference naturally if relevant):\n" + belief_context,
                    CONTEXT_BUDGET["belief_evolution"]
                )
            )

    def _build_missed_messages_context(self, ctx: MessageContext, context_parts: list[str]) -> None:
        try:
            from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_1_decision_temporal import (
                clear_missed_messages,
                get_missed_messages,
            )
            missed = get_missed_messages(ctx.channel_id)
            if not missed:
                return
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

    def _build_memory_context(self, ctx: MessageContext, context_parts: list[str]) -> None:
        memory_text = _fuzz_memories(ctx.memories, limit=8)
        if memory_text:
            context_parts.append(
                _truncate_to_budget(
                    f"Things you vaguely remember from past conversations:\n{memory_text}",
                    CONTEXT_BUDGET["memories"]
                )
            )

    def _build_personality_context(self, ctx: MessageContext, context_parts: list[str]) -> None:
        if ctx.personality_context:
            context_parts.append(
                _truncate_to_budget(ctx.personality_context, CONTEXT_BUDGET["personality"])
            )

    def _build_user_profile_context(self, ctx: MessageContext, context_parts: list[str]) -> None:
        if not ctx.user_profile:
            return
        traits = ctx.user_profile.get("personality_traits", [])[:5]
        interests = ctx.user_profile.get("interests", [])[:5]
        if not traits and not interests:
            return
        profile_parts = []
        if traits:
            profile_parts.append(f"Traits: {', '.join(traits)}")
        if interests:
            profile_parts.append(f"Interests: {', '.join(interests)}")
        context_parts.append(
            _truncate_to_budget("User profile: " + "; ".join(profile_parts), CONTEXT_BUDGET["user_profile"])
        )

    def _build_messages(self, ctx: MessageContext) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        messages.append({"role": "system", "content": ctx.system_prompt})
        if ctx.context_block:
            messages.append({"role": "system", "content": ctx.context_block})

        bot_id = ""
        try:
            if ctx.message and ctx.message.guild and ctx.message.guild.me:
                bot_id = str(ctx.message.guild.me.id)
        except Exception as e:
            logger.debug("Failed to get bot_id for dedup: %s", e)

        filtered_messages = self._filter_history_messages(ctx.recent_messages)
        collapsed = self._collapse_duplicates(filtered_messages)
        collapsed = collapsed[-10:]

        # Map raw DB dicts to standard chat format
        for msg in collapsed:
            author_id = msg.get("author_id", msg.get("user_id", ""))
            role = "assistant" if str(author_id) == bot_id else "user"
            content = msg.get("content", "")
            if not content:
                continue
            messages.append({"role": role, "content": content})

        logger.debug(
            "Built %d messages: %d history (latest: %s)",
            len(messages), len(collapsed),
            collapsed[-1].get("content", "")[:50] if collapsed else "NONE",
        )
        return messages

# --- Helpers ---
    def _filter_history_messages(self, recent_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # NOTE (Cause 2 fix): previously this dropped any message whose
        # ``role == "assistant"`` and ``author_id == bot_id``. That guard was
        # both ineffective on real data (production recent_messages rows carry
        # only ``user_id``/``username``/``content``/``timestamp`` — never
        # ``role`` or ``author_id``) and wrong in intent: it would hide the
        # bot's own prior turns from the model, so Serin appeared to forget
        # what it had just said. We now keep the bot's turns as ordinary
        # conversational context (they are mapped to the ``assistant`` role by
        # the caller when the author id matches bot_id). The only filtering
        # retained is dropping empty content.
        filtered = []
        for msg in recent_messages:
            content = msg.get("content", "")
            if not content:
                continue
            filtered.append(msg)
        return filtered

    def _collapse_duplicates(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not messages:
            return []
        collapsed = [messages[0]]
        for msg in messages[1:]:
            if msg.get("content") != collapsed[-1].get("content"):
                collapsed.append(msg)
        return collapsed

    def _store_prompt_debug(self, ctx: MessageContext, memory_text: str, rel_context: str, belief_context: str) -> None:
        logger.debug(
            "Prompt debug: channel=%s user=%s memory_len=%d rel_len=%d belief_len=%d",
            ctx.channel_id, ctx.user_id,
            len(memory_text), len(rel_context), len(belief_context),
        )
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_6_routes.d5_3_debug_routes.d6_2_debug_routes import (
                store_prompt_debug,
            )
            store_prompt_debug({
                "user": str(ctx.user_id) if ctx.user_id else "",
                "channel": str(ctx.channel_id) if ctx.channel_id else "",
                "system_prompt": (ctx.system_prompt[:2000] if ctx.system_prompt else ""),
                "memories": memory_text[:1000] if memory_text else "",
                "relationship": rel_context[:500] if rel_context else "",
                "beliefs": belief_context[:500] if belief_context else "",
                "user_message": (ctx.raw_content[:500] if ctx.raw_content else ""),
                "full_prompt": (str(ctx.built_messages)[:3000] if ctx.built_messages else ""),
            })
        except Exception as e:
            logger.debug("Failed to store prompt debug: %s", e)

# --- Errors ---
# (none)
