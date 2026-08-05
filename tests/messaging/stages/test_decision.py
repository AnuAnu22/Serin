"""Tests for ResponseDecisionStage."""
from unittest.mock import MagicMock

import pytest

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_1_decision_temporal import (
    ResponseDecisionStage,
)


@pytest.mark.asyncio
async def test_responds_when_mentioned(base_context):
    controller = MagicMock()
    controller.should_respond.return_value = (True, "mentioned")
    stage = ResponseDecisionStage(controller)
    ctx = await stage.run(base_context)
    assert ctx.should_respond is True
    assert ctx.halt_reason == ""


@pytest.mark.asyncio
async def test_halts_when_rate_limited(base_context):
    controller = MagicMock()
    controller.should_respond.return_value = (False, "rate_limited")
    stage = ResponseDecisionStage(controller)
    ctx = await stage.run(base_context)
    assert ctx.should_respond is False
    assert ctx.halt_reason != ""


@pytest.mark.asyncio
async def test_stage_timing_recorded(base_context):
    controller = MagicMock()
    controller.should_respond.return_value = (True, "mentioned")
    stage = ResponseDecisionStage(controller)
    ctx = await stage.run(base_context)
    assert "ResponseDecisionStage" in ctx.stage_timings
    assert ctx.stage_timings["ResponseDecisionStage"] >= 0
