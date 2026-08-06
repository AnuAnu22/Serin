"""Tests for T7 — affect engine wired through pipeline and sentiment hook."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_memory_system() -> MagicMock:
    ms = MagicMock()
    ms.get_user_profile.return_value = {}
    ms.get_user_relationships.return_value = []
    ms.get_relevant_beliefs.return_value = []
    ms.get_recent_conversation.return_value = []
    ms.search_hybrid.return_value = []
    return ms


@pytest.mark.asyncio
async def test_memory_write_stage_calls_record_sentiment(base_context: Any) -> None:
    """MemoryWriteStage must call affect_engine.record_sentiment on each message."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_3_memory_write import (
        MemoryWriteStage,
    )

    affect_engine = MagicMock()
    affect_engine.record_sentiment = AsyncMock()

    stage = MemoryWriteStage(
        memory_system=_mock_memory_system(),
        affect_engine=affect_engine,
    )
    await stage.run(base_context)

    affect_engine.record_sentiment.assert_awaited_once()
    call_args = affect_engine.record_sentiment.call_args
    assert call_args[0][0] == base_context.user_id
    sentiment = call_args[0][1]
    assert -1.0 <= sentiment <= 1.0


@pytest.mark.asyncio
async def test_memory_write_stage_no_affect_engine_safe(base_context: Any) -> None:
    """MemoryWriteStage with no affect_engine must not raise."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_3_memory_write import (
        MemoryWriteStage,
    )

    stage = MemoryWriteStage(memory_system=_mock_memory_system())
    ctx = await stage.run(base_context)
    assert ctx is not None


def test_affect_engine_constructed_in_manager() -> None:
    """EnhancedMessageManagerV3 source must construct a UserAffectEngine."""
    import ast
    import pathlib

    src = pathlib.Path(
        "serin/d1_1_pipeline_flow/d2_2_flow_ingest/d3_2_ingest_core/d4_4_core_manager.py"
    ).read_text()
    tree = ast.parse(src)
    assignments = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Attribute) and t.attr == "affect_engine"
            for t in node.targets
        )
    ]
    assert assignments, (
        "affect_engine must be assigned in EnhancedMessageManagerV3.__init__"
    )
