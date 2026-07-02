"""Tests for ResponseDecisionStage."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from serin.d1_1_pipeline_flow.act.stages.decision_temporal import ResponseDecisionStage
from serin.d1_3_state_core.message_context import MessageContext


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
