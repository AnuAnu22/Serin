"""Contract: planner response-plan constraints reach the FINAL model payload.

Fix 2/Fix 3 proved that constraints recorded by ``ResponsePlannerStage`` must
survive into ``ctx.system_prompt`` AND into the actual payload forwarded to
``chat_completion`` — not just an intermediate field a downstream rebuild may
discard. This is the permanent regression guard for that.

We seed a CONTESTED belief so the planner emits a constraint, then assert the
constraint text is present in ``ctx.metadata[MODEL_PAYLOAD_KEY]`` — the system
prompt the LLM stage ACTUALLY forwarded (via the same ``resolve_system_prompt``
the real generator uses). Planner constraints are written into ``ctx.system_prompt``,
which is the FIRST system message, so ``resolve_system_prompt`` forwards them
verbatim — this is exactly the Fix-3 blind spot the inspector's
``planner_constraints_survive`` check guards.
"""
from __future__ import annotations

from tools.pipeline_inspector.checks import planner_constraints_survive
from tools.pipeline_inspector.scenario import Scenario, _Snap

# A CONTESTED belief triggers: "The evidence is mixed on <content>. You are uncertain."
CONTESTED_CONTENT = "the server is moving to a new host"
CONSTRAINT_TEXT = f"The evidence is mixed on {CONTESTED_CONTENT}"


async def test_planner_constraint_reaches_final_model_payload(
    run_contract,
) -> None:
    scenario = Scenario(
        content="so are we actually moving servers or what",
        user_id="555",
        username="Quinn",
        affect=_Snap(valence=0.2, familiarity=0.3),
        beliefs=[
            {
                "content": CONTESTED_CONTENT,
                "state": "CONTESTED",
                "confidence": 0.5,
                "evidence_count": 1,
                "claim_count": 1,
            }
        ],
    )
    result = await run_contract(scenario)  # default: force_reply=True

    assert result.ctx.halt_reason == "", (
        f"message unexpectedly halted: {result.ctx.halt_reason!r}"
    )

    # The planner must have produced the constraint from the CONTESTED belief.
    plan = result.ctx.response_plan or {}
    constraints = plan.get("constraints") or []
    assert any(CONSTRAINT_TEXT in c for c in constraints), (
        f"ResponsePlannerStage did not emit the expected constraint. "
        f"Got constraints={constraints!r}"
    )

    # Checkpoint (Fix 3 point): the constraint must be in the FINAL payload the
    # LLM stage forwarded (the captured system prompt), not merely an
    # intermediate field.
    assert result.model_payload is not None, (
        "no model payload captured — LLM stage did not record what it sent"
    )
    assert CONSTRAINT_TEXT in result.model_payload, (
        "planner constraint present in ctx.response_plan but DROPPED from the "
        f"final payload sent to the model. Constraint={CONSTRAINT_TEXT!r}"
    )

    # The reusable inspector check must also pass (single source of truth).
    assert planner_constraints_survive(result.ctx) is None, (
        "planner_constraints_survive check failed"
    )

    # Intermediate ctx.system_prompt should ALSO contain it (regression signal).
    assert CONSTRAINT_TEXT in result.ctx.system_prompt, (
        "planner constraint missing from ctx.system_prompt (assembler regression)"
    )
