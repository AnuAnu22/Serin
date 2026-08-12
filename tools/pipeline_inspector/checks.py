"""Reusable assertion checks that run against a MessageContext.

Each check inspects a (post-run) context and returns ``None`` if it passes, or
a short error string naming the first failure. The flagship check,
``planner_constraints_survive``, is the automated version of the
dropped-planner-constraints bug. It asserts every constraint
ResponsePlannerStage recorded appears in the system prompt that was ACTUALLY
sent to the model (captured from the LLM-call payload), not merely in the
intermediate ``ctx.system_prompt`` field — a downstream rebuild that discards
that field is exactly the bug this check exists to catch.
"""
from __future__ import annotations

from collections.abc import Callable

from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)

# A check inspects a context and returns None (pass) or an error string.
Check = Callable[[MessageContext], str | None]

# Metadata key: the inspector copies the generator's recorded system prompt
# (what was actually forwarded toward chat_completion) here after the LLM stage.
MODEL_PAYLOAD_KEY = "inspector_model_payload_system"


def planner_constraints_survive(ctx: MessageContext) -> str | None:
    """Every response_plan constraint must survive into the model payload.

    Reads ``ctx.metadata[MODEL_PAYLOAD_KEY]`` — the system prompt the pipeline
    actually forwarded to the LLM — not ``ctx.system_prompt``, which a
    downstream step may silently discard. Fails closed: if a response was
    decided but no payload was captured, report it rather than return a false
    green.
    """
    plan = ctx.response_plan or {}
    constraints = plan.get("constraints") or []
    payload = (ctx.metadata or {}).get(MODEL_PAYLOAD_KEY)

    if payload is None:
        # No LLM call happened (pipeline halted before the LLM stage) so nothing
        # was sent and nothing could have been dropped.
        if ctx.halt_reason or not ctx.should_respond:
            return None
        return (
            "planner constraints unverifiable: no model payload was captured "
            "(LLM stage did not record what it sent)"
        )

    for constraint in constraints:
        if constraint not in payload:
            return f"planner constraint dropped from model payload: {constraint!r}"
    return None


def no_stage_error(ctx: MessageContext) -> str | None:
    """The pipeline must not have halted on an uncaught stage exception."""
    if (ctx.halt_reason or "").startswith("stage_error:"):
        return f"pipeline halted on stage error: {ctx.halt_reason}"
    return None


def llm_produced_response(ctx: MessageContext) -> str | None:
    """A decided response must actually produce LLM output."""
    if ctx.should_respond and not ctx.halt_reason and not (ctx.raw_response or ctx.final_response):
        return "pipeline decided to respond but produced no LLM output"
    return None


ALL_CHECKS: dict[str, Check] = {
    "planner_constraints_survive": planner_constraints_survive,
    "no_stage_error": no_stage_error,
    "llm_produced_response": llm_produced_response,
}


def register(name: str, fn: Check) -> None:
    """Add or replace a check by name."""
    ALL_CHECKS[name] = fn


def get_check(name: str) -> Check | None:
    return ALL_CHECKS.get(name)


__all__ = [
    "Check",
    "planner_constraints_survive",
    "no_stage_error",
    "llm_produced_response",
    "ALL_CHECKS",
    "register",
    "get_check",
]
