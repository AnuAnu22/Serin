"""Tests for MemoryRetrievalStage."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from serin.pipeline.act.stages.memory_retrieval import MemoryRetrievalStage
from serin.state.message_context import MessageContext


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
