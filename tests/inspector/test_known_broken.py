"""Known-broken validation: the checks must catch a real bug class.

Reproduces the dropped-planner-constraints bug (found in this project's
history: constraints recorded in ``ctx.response_plan`` silently vanished before
reaching the LLM). The inspector's check now asserts against the ACTUAL model
payload (``ctx.metadata['inspector_model_payload_system']``), not the
intermediate ``ctx.system_prompt`` field — so a downstream rebuild that
discards the upstream work is caught.

After Fix 3, the production ``get_response_natural`` forwards the
upstream-assembled system prompt (``current_messages`` first ``role == "system"``
message, which carries the planner's response-plan constraints) instead of
rebuilding from scratch. So a healthy run now records a payload WITH the
constraints and the check must PASS. The regression anchor is now
``test_known_broken_records_payload_with_constraints``; the manual-discard test
still proves the check catches a downstream drop.
"""
from __future__ import annotations

import asyncio

from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from tools.pipeline_inspector.checks import (
    MODEL_PAYLOAD_KEY,
    planner_constraints_survive,
)
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


def test_known_broken_records_payload_with_constraints():
    """After Fix 3 the real pipeline assembles constraints into ctx.system_prompt
    AND forwards that exact prompt to the model, so the check must PASS (green).
    Regression anchor: if get_response_natural ever drops current_messages[0]
    again, this flips red."""
    ctx = _materialized_ctx()
    constraints = (ctx.response_plan or {}).get("constraints") or []
    assert constraints, "planner produced no constraints for this scenario"
    # Both the intermediate field and the ACTUAL payload must carry them:
    assert all(c in (ctx.system_prompt or "") for c in constraints)
    payload = (ctx.metadata or {}).get(MODEL_PAYLOAD_KEY) or ""
    assert all(c in payload for c in constraints), (
        f"constraints not in model payload: {constraints}"
    )
    err = planner_constraints_survive(ctx)
    assert err is None, f"check should pass on fixed code, got: {err}"


def test_downstream_rebuild_discarding_constraints_is_caught():
    """A fresh payload dropping recorded constraints must trip the check, even
    when the intermediate ctx.system_prompt still contains them."""
    ctx = _materialized_ctx()
    constraints = (ctx.response_plan or {}).get("constraints") or []
    assert constraints, "planner produced no constraints for this scenario"

    # Simulate the old bug: a downstream builder rewrites the payload from
    # scratch, silently discarding what ResponsePlannerStage recorded upstream.
    ctx.metadata[MODEL_PAYLOAD_KEY] = "You are Serin. Keep it natural."
    err = planner_constraints_survive(ctx)
    assert err is not None
    assert "dropped from model payload" in err
    assert constraints[0] in err
