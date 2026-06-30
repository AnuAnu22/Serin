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

from serin.config.logger import logger
from serin.state.message_context import MessageContext
from serin.pipeline.act.stages_init import PipelineStage


# Intent → default strategy
_INTENT_STRATEGY = {
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
    """Produces a structured decision object from beliefs + facts + intent."""

    async def _run(self, ctx: MessageContext) -> MessageContext:
        logger.debug("pipeline.response_planner_start", extra={
            "user": ctx.username,
            "intent": ctx.intent,
        })

        # ── 1. Gather inputs ─────────────────────────────────────────────
        beliefs = ctx.beliefs or []
        facts = ctx.facts or []
        user_claim = _detect_user_claim(ctx.raw_content)

        # ── 2. Determine stance ──────────────────────────────────────────
        stance = "neutral"
        confidence = 0.5
        constraints = []
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
                        contradiction_flags.append({
                            "belief": content,
                            "user_says": user_claim,
                            "confidence": conf,
                            "state": state,
                        })

                        if is_negation and not is_agreement:
                            # User is contradicting a strong belief
                            stance = "disagree_firmly" if strategy["base_stance"] in (
                                "disagree_gently", "disagree_firmly"
                            ) else "disagree_gently"
                            constraints.append(
                                f"You are confident that {content}. "
                                f"The user claims otherwise, but the evidence supports you."
                            )
                        elif is_agreement:
                            stance = "agree"
                            constraints.append(
                                f"The user agrees with your belief that {content}."
                            )
                        else:
                            stance = strategy["base_stance"]
                            constraints.append(
                                f"You believe {content}. The user's "
                                f"statement '{user_claim}' is noted."
                            )

                if not constraints:
                    constraints.append(f"You believe {content}.")
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
                    f"by new evidence. Do not assert it."
                )
                forbidden_moves.append(f"asserting that {content}")

            elif state == "UNKNOWN":
                pass  # No constraint from unknown beliefs

        # Strengthen stance based on intent
        if stance == "neutral" and strategy["base_stance"] != "neutral":
            stance = strategy["base_stance"]

        # ── 3. Build response plan ───────────────────────────────────────
        ctx.response_plan = {
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
