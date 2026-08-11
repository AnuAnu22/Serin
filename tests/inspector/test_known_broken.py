"""Known-broken validation: the checks must catch a real bug class.

Reproduces the dropped-planner-constraints bug (found in this project's
history: constraints recorded in ``ctx.response_plan`` silently vanished from
the assembled ``system_prompt`` before reaching the LLM) WITHOUT modifying any
real stage. The real PromptAssemblyStage faithfully re-adds constraints, so the
test uses the inspector's mutate-and-continue hook to simulate the offending
*downstream* rebuild that discarded the upstream work — the exact defect the
inspector exists to surface.
"""
from __future__ import annotations

import asyncio

from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from tools.pipeline_inspector.checks import planner_constraints_survive
from tools.pipeline_inspector.inspector import PipelineInspector
from tools.pipeline_inspector.scenario import Scenario


def _run(coro):
    return asyncio.run(coro)


def _materialized_ctx() -> MessageContext:
    """Run the real pipeline end-to-end for a scenario the planner constrains."""
    scenario = Scenario(
        content="that was a brutal loss. are we regrouping?",
        beliefs=[{
            "content": "Sam handles losses well and bounces back fast",
            "state": "SUPPORTED",
            "confidence": 0.9,
        }],
    )
    inspector = PipelineInspector.from_scenario(
        scenario,
        force_reply=True,
        response="yeah, we learn from it and move on",
    )
    return _run(inspector.run_until(scenario.build_context()))


def test_healthy_run_passes_check():
    """A clean run keeps constraints in system_prompt; the check must pass."""
    ctx = _materialized_ctx()
    assert ctx.halt_reason == ""
    assert planner_constraints_survive(ctx) is None


def test_downstream_rebuild_discarding_constraints_is_caught():
    """A fresh system_prompt dropping recorded constraints must trip the check."""
    ctx = _materialized_ctx()
    constraints = (ctx.response_plan or {}).get("constraints") or []
    assert constraints, "planner produced no constraints for this scenario"

    # Simulate the old bug: a downstream builder rewrites system_prompt from
    # scratch, silently discarding what ResponsePlannerStage recorded upstream.
    ctx.system_prompt = "You are Serin. Keep it natural."  # constraints absent
    err = planner_constraints_survive(ctx)
    assert err is not None
    assert "dropped" in err
    assert constraints[0] in err
