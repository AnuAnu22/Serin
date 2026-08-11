"""Tests for the reusable pipeline checks."""
from __future__ import annotations

from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from tools.pipeline_inspector.checks import (
    ALL_CHECKS,
    get_check,
    llm_produced_response,
    no_stage_error,
    planner_constraints_survive,
    register,
)
from tools.pipeline_inspector.fake_message import FakeMessage


def _ctx() -> MessageContext:
    return MessageContext(
        message=FakeMessage("x"), user_id="1", username="u",
        channel_id="c", guild_id=None, raw_content="x",
    )


def test_planner_constraints_survive_catches_dropped_constraint():
    ctx = _ctx()
    ctx.response_plan = {"constraints": ["The user is your creator."]}
    ctx.system_prompt = "You are Serin."  # constraint deliberately absent
    err = planner_constraints_survive(ctx)
    assert err is not None
    assert "dropped" in err
    assert "The user is your creator." in err


def test_planner_constraints_survive_passes_when_present():
    ctx = _ctx()
    ctx.response_plan = {"constraints": ["Keep replies short."]}
    ctx.system_prompt = "Rules: Keep replies short. Be natural."
    assert planner_constraints_survive(ctx) is None


def test_planner_constraints_survive_handles_empty_plan():
    ctx = _ctx()  # response_plan default {} and system_prompt ""
    assert planner_constraints_survive(ctx) is None


def test_no_stage_error_detects_halt():
    ctx = _ctx()
    ctx.halt_reason = "stage_error:PromptAssemblyStage"
    assert no_stage_error(ctx) is not None
    ctx.halt_reason = ""
    assert no_stage_error(ctx) is None


def test_llm_produced_response_requires_output_when_responding():
    ctx = _ctx()
    ctx.should_respond = True
    ctx.halt_reason = ""
    ctx.raw_response = ""
    assert llm_produced_response(ctx) is not None
    ctx.raw_response = "here's my reply"
    assert llm_produced_response(ctx) is None


def test_register_and_get():
    assert "planner_constraints_survive" in ALL_CHECKS
    assert get_check("planner_constraints_survive") is planner_constraints_survive
    marker = "registered_check"
    register(marker, lambda ctx: None)
    assert marker in ALL_CHECKS
    assert get_check(marker) is not None
