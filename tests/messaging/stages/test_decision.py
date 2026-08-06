"""Tests for ResponseDecisionStage — the live Boltzmann decision path."""
from typing import Any
from unittest.mock import MagicMock

import pytest


def _make_stage(dynamics: Any = None, **kwargs: Any) -> Any:
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_1_decision_temporal import (
        ResponseDecisionStage,
    )
    return ResponseDecisionStage(dynamics=dynamics, **kwargs)


def _mock_dynamics(action: str = "reply") -> MagicMock:
    dyn = MagicMock()
    dyn.decide_action.return_value = action
    dyn.sample_reaction_delay.return_value = 0.0
    dyn.channels = {"67890": {"momentum": 0.0}}
    return dyn


@pytest.mark.asyncio
async def test_bot_name_in_message_is_hard_override(base_context: Any) -> None:
    """'serin' in the message bypasses the physics engine entirely."""
    dyn = _mock_dynamics(action="ignore")  # engine would say ignore...
    stage = _make_stage(dynamics=dyn)
    ctx = await stage.run(base_context)  # raw_content: "hey serin what's up"
    assert ctx.should_respond is True
    assert ctx.halt_reason == ""
    dyn.decide_action.assert_not_called()


@pytest.mark.asyncio
async def test_dynamics_reply_action(base_context: Any) -> None:
    base_context.raw_content = "what a wild game last night"
    dyn = _mock_dynamics(action="reply")
    stage = _make_stage(dynamics=dyn)
    ctx = await stage.run(base_context)
    assert ctx.should_respond is True
    assert ctx.halt_reason == ""
    dyn.decide_action.assert_called_once()


@pytest.mark.asyncio
async def test_dynamics_ignore_action(base_context: Any) -> None:
    base_context.raw_content = "what a wild game last night"
    dyn = _mock_dynamics(action="ignore")
    stage = _make_stage(dynamics=dyn)
    ctx = await stage.run(base_context)
    assert ctx.should_respond is False
    assert ctx.halt_reason == "boltzmann_ignore"


@pytest.mark.asyncio
async def test_dynamics_react_action(base_context: Any) -> None:
    base_context.raw_content = "what a wild game last night"
    dyn = _mock_dynamics(action="react")
    stage = _make_stage(dynamics=dyn)
    ctx = await stage.run(base_context)
    assert ctx.should_respond is False
    assert ctx.halt_reason == "react_only"


@pytest.mark.asyncio
async def test_no_dynamics_defaults_to_reply(base_context: Any) -> None:
    base_context.raw_content = "what a wild game last night"
    stage = _make_stage(dynamics=None)
    ctx = await stage.run(base_context)
    assert ctx.should_respond is True


@pytest.mark.asyncio
async def test_observe_message_feeds_engine(base_context: Any) -> None:
    """Every message updates the physics state, even hard overrides."""
    dyn = _mock_dynamics(action="reply")
    stage = _make_stage(dynamics=dyn)
    await stage.run(base_context)
    dyn.observe_message.assert_called_once()
    dyn.allocate_attention.assert_called_once()


@pytest.mark.asyncio
async def test_stage_timing_recorded(base_context: Any) -> None:
    stage = _make_stage(dynamics=_mock_dynamics())
    ctx = await stage.run(base_context)
    assert "ResponseDecisionStage" in ctx.stage_timings
    assert ctx.stage_timings["ResponseDecisionStage"] >= 0
