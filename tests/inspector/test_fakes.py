"""Tests for the in-memory fakes + pipeline assembler."""
from __future__ import annotations

from tools.pipeline_inspector.fakes import (
    CannedLLM,
    FakeAffectEngine,
    FakeMemorySystem,
    build_pipeline,
)
from tools.pipeline_inspector.scenario import Scenario, _Snap

STAGE_NAMES = [
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


def test_build_pipeline_produces_all_ten_real_stages_in_order():
    pipeline = build_pipeline()
    assert [s.__class__.__name__ for s in pipeline.stages] == STAGE_NAMES


def test_build_pipeline_uses_real_classes_not_mocks():
    pipeline = build_pipeline()
    # The whole point: these are the genuine production classes, injected with
    # fakes — a wrong class here means the inspector stops being trustworthy.
    for stage in pipeline.stages:
        assert stage.__class__.__module__.startswith("serin.")


async def test_canned_llm_returns_scripted_response():
    llm = CannedLLM("scripted reply")
    out = await llm(current_messages=[], context="ctx", tone_modifier="warm")
    assert out == "scripted reply"


def test_fake_affect_snapshot_and_sentiments():
    engine = FakeAffectEngine()
    engine.set_snapshot("42", _Snap(valence=0.9, familiarity=0.4))
    snap = engine.snapshot_cached("42")
    assert snap is not None
    assert snap.valence == 0.9
    assert snap.familiarity == 0.4
    assert engine.snapshot_cached("nope") is None


def test_build_pipeline_seeds_affect_from_scenario():
    scenario = Scenario(content="hi again", user_id="7")
    scenario.affect = _Snap(valence=0.6, familiarity=0.8)
    pipeline = build_pipeline(scenario=scenario)
    engine = pipeline.stages[0].affect_engine
    assert engine.snapshot_cached("7").familiarity == 0.8


def test_build_pipeline_seeds_memory_profile_and_belief_engine():
    scenario = Scenario(content="x", user_id="7",
                         user_profile={"name": "Rin"},
                         facts=[{"claim": "likes jazz", "belief": 0.8, "variance": 0.1}])
    pipeline = build_pipeline(scenario=scenario)
    memory = pipeline.stages[1].memory
    assert memory.get_user_profile("7") == {"name": "Rin"}
    facts = memory.belief_engine.get_facts_for_user("7")
    assert facts[0]["claim"] == "likes jazz"


def test_memory_writes_record_kwargs():
    memory = FakeMemorySystem()
    memory.add_memory_enhanced(content="c", user_id="1", memory_type="episode")
    assert memory.writes == [{"content": "c", "user_id": "1", "memory_type": "episode"}]
