"""Tests for MessagePipeline.build() and full pipeline orchestration."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from serin.messaging.pipeline import MessagePipeline
from serin.messaging.context import MessageContext
from serin.messaging.stages.llm_call import LLMCallStage
from serin.messaging.stages.decision import ResponseDecisionStage


def _mock_controller():
    """Return a response_controller mock that always allows responding."""
    ctrl = MagicMock()
    ctrl.should_respond.return_value = (True, "mentioned")
    return ctrl


def _mock_memory_system():
    ms = MagicMock()
    ms.get_user_profile.return_value = {}
    return ms


def _mock_retrieval():
    r = MagicMock()
    r.build_context.return_value = {
        "facts": [],
        "beliefs": [],
        "evidence_memories": [],
        "episode_memories": [],
        "utterance_memories": [],
        "recent_conversation": [],
        "relationships": [],
        "profiles": {},
    }
    return r


def _mock_personality():
    p = MagicMock()
    p.get_tone_modifier.return_value = "friendly"
    p.get_personality_context.return_value = "You are a helpful assistant."
    return p


def _mock_response_generator():
    """Generator must be an async callable — LLMCallStage does `await self.generator(...)`."""
    return AsyncMock(return_value="Hello, how can I help you?")


def _mock_thinking_filter():
    """ResponseCleaningStage calls filter() on the thinking_filter."""
    tf = MagicMock()
    tf.filter.return_value = "Hello, how can I help you?"
    return tf


def test_build_returns_pipeline():
    """Pipeline.build() should create a fully-wired MessagePipeline."""
    pipeline = MessagePipeline.build(
        response_controller=_mock_controller(),
        memory_system=_mock_memory_system(),
        retrieval=_mock_retrieval(),
        personality=_mock_personality(),
        temporal_context=MagicMock(),
        response_generator=_mock_response_generator(),
        thinking_filter=_mock_thinking_filter(),
        mention_translator=MagicMock(),
    )
    assert isinstance(pipeline, MessagePipeline)
    assert len(pipeline.stages) == 10


def test_build_stages_in_order():
    """Stages should be in the expected order."""
    pipeline = MessagePipeline.build(
        response_controller=_mock_controller(),
        memory_system=_mock_memory_system(),
        retrieval=_mock_retrieval(),
        personality=_mock_personality(),
        temporal_context=MagicMock(),
        response_generator=_mock_response_generator(),
        thinking_filter=_mock_thinking_filter(),
        mention_translator=MagicMock(),
    )
    stage_names = [type(s).__name__ for s in pipeline.stages]
    expected = [
        "ResponseDecisionStage",
        "MemoryRetrievalStage",
        "ResponsePlannerStage",
        "TemporalStage",
        "PersonalityStage",
        "PromptAssemblyStage",
        "LLMCallStage",
        "ResponseCleaningStage",
        "SendStage",
        "MemoryWriteStage",
    ]
    assert stage_names == expected, f"Got {stage_names}"


@pytest.mark.asyncio
async def test_process_runs_all_stages(base_context):
    """Full pipeline process should run all 10 stages and return a complete context."""
    pipeline = MessagePipeline.build(
        response_controller=_mock_controller(),
        memory_system=_mock_memory_system(),
        retrieval=_mock_retrieval(),
        personality=_mock_personality(),
        temporal_context=MagicMock(),
        response_generator=_mock_response_generator(),
        thinking_filter=_mock_thinking_filter(),
        mention_translator=MagicMock(),
    )
    ctx = await pipeline.process(base_context)
    assert isinstance(ctx, MessageContext)
    assert ctx.should_respond is not None
    assert len(ctx.stage_timings) == 10
