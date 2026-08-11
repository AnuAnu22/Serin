"""Tests for the production-cipher context dump.

Per the project's process rule, dumps always serialize the ACTUAL final state
after a real pipeline run (fully materialized scenario) through production's
own ``make_json_safe`` encoder — never a hand-built, pre-run context rendered
through a decorative formatter.
"""
from __future__ import annotations

import asyncio
import json

from tools.pipeline_inspector.dump import dump_context, dump_snapshot
from tools.pipeline_inspector.inspector import PipelineInspector
from tools.pipeline_inspector.scenario import Scenario, _Snap

STAGE_NAMES = [
    "ResponseDecisionStage", "MemoryRetrievalStage", "ResponsePlannerStage",
    "TemporalStage", "PersonalityStage", "PromptAssemblyStage", "LLMCallStage",
    "ResponseCleaningStage", "SendStage", "MemoryWriteStage",
]


def _run(coro):
    return asyncio.run(coro)


def _materialized_scenario() -> Scenario:
    # Fully populated: seeded affect, facts, beliefs, recent messages, profile.
    return Scenario(
        content="hey serin, I finally pulled a decent sourdough crumb",
        username="Sam",
        affect=_Snap(valence=0.7, familiarity=0.8),
        facts=[{"claim": "Sam bakes sourdough bread", "belief": 0.9, "variance": 0.05}],
        beliefs=[{"content": "Sam enjoys food talk", "confidence": 0.7,
                  "evidence_count": 2, "claim_count": 0}],
        recent_messages=[
            {"user_id": "1234", "content": "trying again on the starter"},
            {"user_id": "1234", "content": "crumb came out great"},
        ],
        user_profile={"name": "Sam", "notes": "avid home baker"},
    )


def test_dump_of_final_run_state_is_production_json():
    scenario = _materialized_scenario()
    ctx = _run(PipelineInspector.from_scenario(
        scenario, response="oh nice, let's see that crumb").run_until(scenario.build_context()))

    out = dump_context(ctx)
    data = json.loads(out)  # must be valid production JSON

    assert data["final_response"] == "oh nice, let's see that crumb"
    assert data["halt_reason"] == ""
    assert data["raw_content"] == "hey serin, I finally pulled a decent sourdough crumb"
    assert set(data["stage_timings"]) == set(STAGE_NAMES)  # all 10 stages really ran
    assert "<discord.Message" not in out
    # Fully materialized inputs survive a real run and show up in final state.
    assert data["facts"][0]["claim"] == "Sam bakes sourdough bread"


def test_dump_omits_message_by_default():
    scenario = _materialized_scenario()
    ctx = _run(PipelineInspector.from_scenario(scenario).run_until(scenario.build_context()))
    out = dump_context(ctx)
    assert '"message"' not in out


def test_dump_snapshot_renders_recorded_boundary():
    scenario = _materialized_scenario()
    inspector = PipelineInspector.from_scenario(scenario)
    _run(inspector.run_until(scenario.build_context()))
    snap = inspector.snapshots[-1]  # final boundary snapshot
    data = json.loads(dump_snapshot(snap))
    assert data["final_response"]
    assert set(data["stage_timings"]) == set(STAGE_NAMES)


def test_dump_is_json_safe_via_production_encoder():
    # snapshot_ctx may carry heterogeneous values (datetimes, sets, tensors) —
    # make_json_safe must coerce them, exactly as production does.
    scenario = _materialized_scenario()
    ctx = _run(PipelineInspector.from_scenario(scenario).run_until(scenario.build_context()))
    ctx.metadata["extra_set"] = {1, 2, 3}
    out = dump_context(ctx)
    assert '"extra_set"' in out  # frozenset co-erced to a list, not dropped
