"""Tests for T9 — decision stage consumes affect (salience bump + bias floats)."""
from typing import Any
from unittest.mock import MagicMock

import pytest

from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
    AffectSnapshot,
)


def _make_stage(dynamics: Any = None, affect_engine: Any = None, **kw: Any) -> Any:
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_1_decision_temporal import (
        ResponseDecisionStage,
    )
    return ResponseDecisionStage(dynamics=dynamics, affect_engine=affect_engine, **kw)


def _mock_dynamics(action: str = "reply") -> MagicMock:
    dyn = MagicMock()
    dyn.decide_action.return_value = action
    dyn.sample_reaction_delay.return_value = 0.0
    dyn.channels = {"67890": {"momentum": 0.0}}
    return dyn


def _mock_affect_engine(valence: float = 0.0, familiarity: float = 0.0,
                        impression: str | None = None) -> MagicMock:
    ae = MagicMock()
    ae.snapshot_cached.return_value = AffectSnapshot(
        valence=valence, familiarity=familiarity, impression=impression
    )
    return ae


@pytest.mark.asyncio
async def test_familiarity_bumps_salience(base_context: Any) -> None:
    """A familiar user should have their salience raised by 0.1 * familiarity."""
    base_context.raw_content = "quick test"
    dyn = _mock_dynamics(action="reply")
    ae = _mock_affect_engine(familiarity=0.8)

    stage = _make_stage(dynamics=dyn, affect_engine=ae)
    await stage.run(base_context)

    call_kwargs = dyn.decide_action.call_args
    salience_passed = call_kwargs[1]["salience"] if call_kwargs[1] else call_kwargs[0][1]
    base_salience = 0.3  # no '?' or 'serin' in content
    expected_salience = min(1.0, base_salience + 0.1 * 0.8)
    assert abs(salience_passed - expected_salience) < 0.01


@pytest.mark.asyncio
async def test_affect_bias_floats_forwarded(base_context: Any) -> None:
    """valence and familiarity from snapshot must be passed to decide_action."""
    base_context.raw_content = "quick test"
    dyn = _mock_dynamics(action="reply")
    ae = _mock_affect_engine(valence=0.7, familiarity=0.6)

    stage = _make_stage(dynamics=dyn, affect_engine=ae)
    await stage.run(base_context)

    dyn.decide_action.assert_called_once()
    kwargs = dyn.decide_action.call_args[1]
    assert kwargs.get("user_valence") == pytest.approx(0.7, abs=0.01)
    assert kwargs.get("user_familiarity") == pytest.approx(0.6, abs=0.01)


@pytest.mark.asyncio
async def test_no_affect_engine_uses_neutral_defaults(base_context: Any) -> None:
    """Without an affect_engine the stage must still work, passing 0/0 to decide_action."""
    base_context.raw_content = "quick test"
    dyn = _mock_dynamics(action="reply")

    stage = _make_stage(dynamics=dyn, affect_engine=None)
    ctx = await stage.run(base_context)

    assert ctx.should_respond is True
    dyn.decide_action.assert_called_once()
    kwargs = dyn.decide_action.call_args[1]
    assert kwargs.get("user_valence", 0.0) == pytest.approx(0.0)
    assert kwargs.get("user_familiarity", 0.0) == pytest.approx(0.0)
