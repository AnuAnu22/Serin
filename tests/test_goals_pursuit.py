"""C3 tests: goals pursuit reaches the live pipeline.

Pins the wiring that makes self-generated goals ACTUALLY cause behavior
(SERIN_VISION "Growth" - accumulated state driving present action, not a
per-boot simulation):

- ResponseDecisionStage._goal_salience_bonus: a deterministic, bounded lift
  (0.10 x salience per goal) derived from accumulated goal state - no RNG.
- ResponseDecisionStage._run: presence of active goals records them in
  ctx.metadata["active_goals"]; an absent engine leaves it unset.
- ResponsePlannerStage._run: the top active goal appears verbatim as a binding
  constraint and in ctx.response_plan["active_goals"] (machinery only - the
  statement is quoted, never rewritten; it slots ahead of per-message belief
  constraints but still respects the 3-slot cap).

A fake goals_engine returns a fixed pursuit_snapshot list so the tests never
touch the DB or the LLM.
"""
from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_1_decision_temporal import (
    ResponseDecisionStage,
)
from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_4_response_planner import (
    ResponsePlannerStage,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)


class FakeGoals:
    """Returns a fixed pursuit snapshot, or none."""

    def __init__(self, goals: list[dict[str, Any]] | None) -> None:
        self._goals = goals

    def pursuit_snapshot(self, limit: int = 3) -> list[dict[str, Any]]:
        if self._goals is None:
            return []
        return self._goals[:limit]


def _ctx(raw: str = "hey serin what's up") -> MessageContext:
    msg = type("M", (), {})()
    msg.author = type("A", (), {"id": 12345, "display_name": "TestUser"})()
    msg.channel = type("C", (), {"id": 67890})()
    msg.guild = type("G", (), {"id": 11111, "me": object()})()
    msg.mentions = []
    msg.content = raw
    return MessageContext(
        message=msg,
        user_id="12345",
        username="TestUser",
        channel_id="67890",
        guild_id="11111",
        raw_content=raw,
    )


def test_goal_bonus_is_deterministic_and_weighted() -> None:
    """0.10 x salience per goal; two goals sum without RNG."""
    stage = ResponseDecisionStage(
        goals_engine=FakeGoals([
            {"statement": "A", "salience": 1.0},
            {"statement": "B", "salience": 0.5},
        ]))
    assert abs(stage._goal_salience_bonus(
        stage.goals_engine.pursuit_snapshot()) - 0.15) < 1e-9


def test_goal_bonus_zero_without_engine() -> None:
    """No engine => zero lift (the path never calls pursuit_snapshot)."""
    stage = ResponseDecisionStage(goals_engine=None)
    assert stage._goal_salience_bonus([]) == 0.0
    assert stage.goals_engine is None


def test_decision_records_active_goals_metadata() -> None:
    """Active goals are surfaced on ctx.metadata; absent engine leaves it unset."""
    import asyncio

    ctx = _ctx()
    stage = ResponseDecisionStage(goals_engine=FakeGoals(
        [{"statement": "map every panel endpoint", "salience": 1.0}]))
    asyncio.run(stage._run(ctx))
    assert ctx.metadata.get("active_goals") == ["map every panel endpoint"]

    ctx2 = _ctx()
    none_stage = ResponseDecisionStage(goals_engine=FakeGoals(None))
    asyncio.run(none_stage._run(ctx2))
    assert ctx2.metadata.get("active_goals") is None


def test_planner_injects_verbatim_goal_constraint() -> None:
    """Top active goal is quoted verbatim into constraints AND the plan key."""
    import asyncio

    ctx = _ctx()
    ctx.beliefs = [
        {"state": "SUPPORTED", "confidence": 0.9, "content": "the sky is blue"}]
    stage = ResponsePlannerStage(goals_engine=FakeGoals(
        [{"statement": "read the control panel source end to end", "salience": 0.8}]))
    asyncio.run(stage._run(ctx))

    plan = ctx.response_plan
    assert plan["active_goals"] == ["read the control panel source end to end"]
    joined = " ".join(plan["constraints"])
    assert "read the control panel source end to end" in joined
    # Machinery only: quoted verbatim, not paraphrased or silently dropped.
    assert "self-goal" in joined.lower()


def test_planner_goal_survives_constraint_cap() -> None:
    """With 3+ pre-existing belief constraints, the goal still slots in front."""
    import asyncio

    ctx = _ctx()
    ctx.beliefs = [
        {"state": "SUPPORTED", "confidence": 0.9, "content": f"belief {i}"}
        for i in range(4)
    ]
    stage = ResponsePlannerStage(goals_engine=FakeGoals(
        [{"statement": "finish the songbird migration", "salience": 0.9}]))
    asyncio.run(stage._run(ctx))

    constraints = ctx.response_plan["constraints"]
    assert len(constraints) <= 3  # cap preserved
    assert constraints[0].startswith("Standing self-goal")
    assert "finish the songbird migration" in constraints[0]


def test_planner_no_engine_is_noop() -> None:
    """No goals_engine means no active_goals key pollution."""
    import asyncio

    ctx = _ctx()
    stage = ResponsePlannerStage(personality=None)
    asyncio.run(stage._run(ctx))
    assert ctx.response_plan.get("active_goals") == []
