"""Tests for MemoryRetrievalStage."""
from unittest.mock import MagicMock

import pytest

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_2_memory_retrieval import (
    MemoryRetrievalStage,
)


@pytest.mark.asyncio
async def test_populates_memories(base_context):
    memory_system = MagicMock()
    memory_system.get_user_profile.return_value = {}
    retrieval = MagicMock()
    retrieval.build_context.return_value = {
        "facts": [],
        "beliefs": [],
        "evidence_memories": [
            {"content": "Evidence memory", "score": 0.9},
        ],
        "episode_memories": [
            {"content": "Episode memory", "score": 0.8},
        ],
        "utterance_memories": [],
        "recent_conversation": [],
        "relationships": [],
        "profiles": {},
    }
    stage = MemoryRetrievalStage(memory_system, retrieval)
    ctx = await stage.run(base_context)
    assert len(ctx.memories) == 2
    assert ctx.memories[0]["content"] == "Evidence memory"


@pytest.mark.asyncio
async def test_handles_empty_results(base_context):
    memory_system = MagicMock()
    memory_system.get_user_profile.return_value = {}
    retrieval = MagicMock()
    retrieval.build_context.return_value = {
        "facts": [],
        "beliefs": [],
        "evidence_memories": [],
        "episode_memories": [],
        "utterance_memories": [],
        "recent_conversation": [],
        "relationships": [],
        "profiles": {},
    }
    stage = MemoryRetrievalStage(memory_system, retrieval)
    ctx = await stage.run(base_context)
    assert ctx.memories == []


@pytest.mark.asyncio
async def test_stage_timing_recorded(base_context):
    memory_system = MagicMock()
    memory_system.get_user_profile.return_value = {}
    retrieval = MagicMock()
    retrieval.build_context.return_value = {
        "facts": [],
        "beliefs": [],
        "evidence_memories": [],
        "episode_memories": [],
        "utterance_memories": [],
        "recent_conversation": [],
        "relationships": [],
        "profiles": {},
    }
    stage = MemoryRetrievalStage(memory_system, retrieval)
    ctx = await stage.run(base_context)
    assert "MemoryRetrievalStage" in ctx.stage_timings
