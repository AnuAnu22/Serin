"""Tests for creator override and instant-reply delay bypass."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_1_runners_dispatch.d5_2_dispatch_send import (
    SendStage,
)
from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_1_decision_temporal import (
    ResponseDecisionStage,
)


def _mock_dynamics(action: str = "ignore") -> MagicMock:
    dyn = MagicMock()
    dyn.decide_action.return_value = action
    dyn.sample_delay.return_value = 5.0
    dyn.sample_reaction_delay.return_value = 0.0
    dyn.channels = {"67890": {"momentum": 0.0}}
    return dyn


@pytest.mark.asyncio
async def test_creator_forces_reply_and_instant_flag(base_context: Any) -> None:
    """A creator message bypasses the physics engine and flags instant reply."""
    base_context.raw_content = "quick test message"  # no bot name
    dyn = _mock_dynamics(action="ignore")  # engine would ignore...
    stage = ResponseDecisionStage(dynamics=dyn, creator_ids=frozenset({"12345"}))
    ctx = await stage.run(base_context)  # base_context.user_id == "12345"
    assert ctx.should_respond is True
    assert ctx.halt_reason == ""
    assert ctx.metadata.get("instant_reply") is True
    dyn.decide_action.assert_not_called()
    dyn.observe_message.assert_called_once()  # physics state stays coherent


@pytest.mark.asyncio
async def test_non_creator_goes_through_engine(base_context: Any) -> None:
    base_context.raw_content = "quick test message"
    dyn = _mock_dynamics(action="reply")
    stage = ResponseDecisionStage(dynamics=dyn, creator_ids=frozenset({"99999"}))
    ctx = await stage.run(base_context)
    dyn.decide_action.assert_called_once()
    assert ctx.metadata.get("instant_reply") is not True


@pytest.mark.asyncio
async def test_mention_override_is_not_instant(base_context: Any) -> None:
    """@mention forces a reply but keeps the natural typing delay."""
    dyn = _mock_dynamics(action="ignore")
    stage = ResponseDecisionStage(dynamics=dyn, creator_ids=frozenset({"99999"}))
    ctx = await stage.run(base_context)  # raw_content contains 'serin'
    assert ctx.should_respond is True
    assert ctx.metadata.get("instant_reply") is not True


@pytest.mark.asyncio
async def test_send_stage_skips_delay_on_instant_reply(base_context: Any) -> None:
    dyn = _mock_dynamics()
    base_context.final_response = "here!"
    base_context.metadata["instant_reply"] = True
    stage = SendStage(dynamics=dyn)
    await stage.run(base_context)
    dyn.sample_delay.assert_not_called()
    base_context.message.channel.send.assert_awaited_once_with("here!")


@pytest.mark.asyncio
async def test_send_stage_uses_dynamics_delay_normally(base_context: Any) -> None:
    dyn = _mock_dynamics()
    dyn.sample_delay.return_value = 0.0  # keep the test fast
    base_context.final_response = "here!"
    stage = SendStage(dynamics=dyn)
    await stage.run(base_context)
    dyn.sample_delay.assert_called_once_with("67890")


@pytest.mark.asyncio
async def test_build_wires_creator_ids_from_config() -> None:
    """MessagePipeline.build defaults creator_ids to config.CREATOR_IDS."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
        MessagePipeline,
    )
    from serin.d1_4_config_base.d2_1_base_config import config

    pipeline = MessagePipeline.build(
        memory_system=MagicMock(),
        retrieval=MagicMock(),
        personality=MagicMock(),
        temporal_context=MagicMock(),
        response_generator=AsyncMock(),
        thinking_filter=MagicMock(),
        mention_translator=MagicMock(),
    )
    decision_stage = pipeline.stages[0]
    assert decision_stage.creator_ids == config.CREATOR_IDS
