"""
ResponsePlannerStage
--------------------
Reads beliefs, facts, and intent — then produces a compact decision object
(stance, constraints, contradiction flags) that the prompt assembler uses
to write binding constraints into the system prompt.

Beliefs are no longer advisory text. They are active state that constrains
what the model can plausibly say. The LLM still has room to sound natural,
but it cannot ignore high-confidence beliefs or direct evidence.
"""
from __future__ import annotations

from typing import Any, cast

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from serin.d1_4_config_base.d2_3_core_logger import logger

# Intent → default strategy
_INTENT_STRATEGY: dict[str, dict[str, str | float]] = {
    "seek_validation": {"base_stance": "agree", "strength_bonus": 0.2},
    "seek_explanation": {"base_stance": "neutral", "strength_bonus": 0.0},
    "seek_argument": {"base_stance": "disagree_gently", "strength_bonus": 0.1},
    "seek_joke": {"base_stance": "neutral", "strength_bonus": 0.0},
    "social": {"base_stance": "neutral", "strength_bonus": 0.0},
    "question": {"base_stance": "neutral", "strength_bonus": 0.0},
    "command": {"base_stance": "neutral", "strength_bonus": 0.0},
    "statement": {"base_stance": "neutral", "strength_bonus": 0.0},
}


def _detect_user_claim(raw_content: str) -> str:
    """Extract the core claim from the user's current message."""
    lower = raw_content.lower()
    # Win/loss claim
    for kw in ["i won", "i have won", "i beat", "i win"]:
        if kw in lower:
            return "user claims they won"
    for kw in ["i lost", "i didn't", "i don't"]:
        if kw in lower:
            return "user claims they did not win"
    # Contradiction claim
    for kw in ["you're wrong", "you are wrong", "that's wrong", "no you", "no it"]:
        if kw in lower:
            return "user disagrees with you"
    # Agreement
    for kw in ["you're right", "you are right", "that's right", "yes"]:
        if kw in lower:
            return "user agrees with you"
    return ""


class ResponsePlannerStage(PipelineStage):
    """Produces a structured decision object from beliefs + facts + intent.

    Optionally consults the bot's own opinions (BotPersonality) so Serin is
    genuinely biased per SERIN_VISION.md: when the user states a stance on a
    topic the bot holds a confident opinion about, the planner sets a real
    disagree/agree stance and a binding constraint (not a random roll).
    """

    def __init__(self, personality: Any = None,
                 goals_engine: Any | None = None) -> None:
        self.personality = personality
        self.goals_engine = goals_engine

    async def _run(self, ctx: MessageContext) -> MessageContext:
        logger.debug("pipeline.response_planner_start", extra={
            "user": ctx.username,
            "intent": ctx.intent,
        })

        # ── 1. Gather inputs ─────────────────────────────────────────────
        beliefs = ctx.beliefs or []
        user_claim = _detect_user_claim(ctx.raw_content)

        # ── 2. Determine stance ──────────────────────────────────────────
        stance = "neutral"
        confidence = 0.5
        constraints: list[str] = []
        contradiction_flags = []
        forbidden_moves = []
        allowed_tones = ["natural", "conversational"]

        strategy = _INTENT_STRATEGY.get(ctx.intent, _INTENT_STRATEGY["statement"])

        # Scan beliefs for relevant high-confidence items
        for belief in beliefs:
            state = belief.get("state", "UNKNOWN")
            conf = belief.get("confidence", 0.0)
            content = belief.get("content", "")

            if state == "SUPPORTED" and conf >= 0.7:
                # Strong belief — should constrain the response
                confidence = max(confidence, conf)

                if user_claim:
                    # Check if user claim contradicts this belief
                    claim_lower = user_claim.lower()
                    belief_lower = content.lower()

                    # Simple contradiction detection via keyword overlap
                    negation_words = ["not", "didn't", "doesn't", "isn't", "wasn't", "never", "no"]
                    is_negation = any(w in claim_lower for w in negation_words)
                    is_agreement = any(w in claim_lower for w in ["agree", "right", "yes", "correct"])

                    if belief_lower and claim_lower:
                        if is_negation and not is_agreement:
                            # User is contradicting a strong belief — the ONLY
                            # case that is a genuine contradiction (M3: an
                            # agreement used to be flagged as one).
                            contradiction_flags.append({
                                "belie": content,
                                "user_says": user_claim,
                                "confidence": conf,
                                "state": state,
                            })
                            base_stance_val = cast(str, strategy["base_stance"])
                            stance = "disagree_firmly" if base_stance_val in (
                                "disagree_gently", "disagree_firmly"
                            ) else "disagree_gently"
                            constraints.append(
                                f"You are confident that {content}. "
                                "The user claims otherwise, but the evidence supports you."
                            )
                        elif is_agreement:
                            stance = "agree"
                            constraints.append(
                                f"The user agrees with your belief that {content}."
                            )
                        else:
                            stance = cast(str, strategy["base_stance"])
                            constraints.append(
                                f"You believe {content}. The user's "
                                f"statement '{user_claim}' is noted."
                            )
                else:
                    # No user claim on this belief — flag defaults so the
                    # "not constraints" branch below never touches an
                    # unbound name.
                    is_agreement = False
                    is_negation = False

                if not constraints:
                    # A strong belief still constrains the reply...
                    constraints.append(f"You believe {content}.")
                    # ...but M4: it must NOT stamp stance="agree" on its own —
                    # agreement is caused by the user actually agreeing, never
                    # by the absence of a claim. Without one, the stance stays
                    # whatever the intent strategy already chose.
                    if is_agreement:
                        stance = "agree"

            elif state == "CONTESTED":
                constraints.append(
                    f"The evidence is mixed on {content}. You are uncertain."
                )
                stance = "uncertain"
                allowed_tones.append("tentative")

            elif state == "SUPERSEDED":
                constraints.append(
                    f"Your prior belief about {content} has been superseded "
                    "by new evidence. Do not assert it."
                )
                forbidden_moves.append(f"asserting that {content}")

            elif state == "UNKNOWN":
                pass  # No constraint from unknown beliefs

        # Strengthen stance based on intent
        base_stance = cast(str, strategy["base_stance"])
        if stance == "neutral" and base_stance != "neutral":
            stance = base_stance

        # ── 2b. Consult the bot's own opinions (genuine bias) ─────────────
        # If the user states a stance on a topic the bot holds a confident
        # opinion about, let that persistent state drive the stance — not the
        # intent alone. This is the "Serin is not neutral" behavior.
        if self.personality is not None and hasattr(self.personality, "detect_topic_stance"):
            detected: tuple[str, str] | None = self.personality.detect_topic_stance(ctx.raw_content)
            # Guard against mocks/non-tuple returns so we only handle real
            # (topic, stance) detections.
            if detected is not None and isinstance(detected, tuple) and len(detected) == 2:
                topic, user_stance = detected
                opinion: dict[str, Any] | None = self.personality.get_opinion(topic)
                if opinion is not None:
                    opinion_text: str = str(opinion.get("opinion_text", ""))
                    should_disagree: bool = self.personality.can_disagree(topic, user_stance)
                    if should_disagree:
                        stance = "disagree_gently"
                        constraints.append(
                            f"You have a real opinion on {topic.replace('_', ' ')}: "
                            f"{opinion_text} The user feels differently — you can push back."
                        )
                    elif user_stance == str(opinion.get("stance")):
                        stance = "agree"
                        constraints.append(
                            f"You're on the same page as the user about "
                            f"{topic.replace('_', ' ')}: {opinion_text}"
                        )
                    else:
                        # No direct conflict (e.g. one side neutral) — don't force a stance.
                        pass

        # ── 2b. Self-generated goals (SERIN_VISION Growth) ───────────────
        active_goals_local = []
        if self.goals_engine is not None:
            try:
                active_goals_local = self.goals_engine.pursuit_snapshot(limit=3)
            except Exception as exc:
                logger.debug("goals pursuit snapshot skipped: %s", exc)
        if active_goals_local:
            ctx.metadata["active_goals"] = [str(g.get("statement", "")) for g in active_goals_local]
            top_goal = active_goals_local[0]
            goal_constraint = (
                f"Standing self-goal (salience {float(top_goal.get('salience', 0.0)):.2f}): "
                f"{top_goal.get('statement', '')}. Let it color your engagement when naturally "
                "relevant — do not force the topic."
            )
            constraints = [goal_constraint] + constraints

        # ── 3. Build response plan ───────────────────────────────────────
        ctx.response_plan = {
            "active_goals": ctx.metadata.get("active_goals", []),
            "stance": stance,
            "confidence": round(confidence, 2),
            "constraints": constraints[:3],  # Cap at 3 for prompt space
            "contradictions": contradiction_flags[:2],
            "allowed_tones": allowed_tones[:3],
            "forbidden_moves": forbidden_moves[:2],
        }

        logger.info("pipeline.response_planner_complete", extra={
            "user": ctx.username,
            "stance": stance,
            "confidence": confidence,
            "constraints": len(constraints),
            "contradictions": len(contradiction_flags),
            "intent": ctx.intent,
        })

        return ctx
