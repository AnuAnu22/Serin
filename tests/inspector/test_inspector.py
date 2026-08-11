"""Tests for the PipelineInspector driver (control-flow mirror of process())."""
from __future__ import annotations

import asyncio

from tools.pipeline_inspector.fakes import FakeMemorySystem, build_pipeline
from tools.pipeline_inspector.inspector import PipelineInspector, snapshot_ctx
from tools.pipeline_inspector.scenario import Scenario

STAGE_COUNT = 10


def _run(coro):  # pytest-asyncio helper for sync tests
    return asyncio.run(coro)


def test_full_run_matches_process_control_flow():
    scenario = Scenario(content="serin, did you catch the game last night?", username="Sam")
    pipeline = build_pipeline(scenario=scenario, force_reply=True)
    inspector = PipelineInspector(pipeline)

    ctx_inspected = _run(inspector.run_until(scenario.build_context()))
    ctx_reference = _run(pipeline.process(scenario.build_context()))

    assert ctx_inspected.final_response == ctx_reference.final_response
    assert ctx_inspected.halt_reason == ctx_reference.halt_reason
    assert set(ctx_inspected.stage_timings) == set(ctx_reference.stage_timings)
    assert len([e for e in inspector.events if e["status"] == "done"]) == STAGE_COUNT


def test_step_then_resume_reaches_completion():
    scenario = Scenario(content="serin hey", username="Sam")
    inspector = PipelineInspector.from_scenario(scenario)
    ctx = scenario.build_context()

    # Run just the first stage (ResponseDecisionStage).
    ctx = _run(inspector.run_until(ctx, stop_after=0))
    assert ctx.should_respond is True          # force_reply -> creator override
    assert [e["status"] for e in inspector.events] == ["done"]
    assert inspector._pos == 1

    # Resume to completion.
    ctx = _run(inspector.run_until(ctx))
    assert ctx.final_response
    assert [e["status"] for e in inspector.events] == ["done"] * STAGE_COUNT


def test_halt_runs_memory_write_tail():
    class BoomMemory(FakeMemorySystem):
        def get_user_profile(self, user_id: str) -> dict:
            raise RuntimeError("boom")

    scenario = Scenario(content="serin hey", username="Sam")
    inspector = PipelineInspector.from_scenario(scenario, memory_system=BoomMemory())
    ctx = _run(inspector.run_until(scenario.build_context()))

    # Replicates process(): halt at the erroring stage, then MemoryWriteStage tail.
    assert ctx.halt_reason == "stage_error:MemoryRetrievalStage"
    statuses = [e["status"] for e in inspector.events]
    assert statuses[0] == "done"
    assert statuses[1] == "error"
    assert "tail" in statuses
    assert statuses[-1] == "tail"


def test_force_reply_is_deterministic():
    scenario = Scenario(content="does anyone know where the server moved", username="Sam")
    r1 = _run(PipelineInspector.from_scenario(scenario).run_until(scenario.build_context()))
    r2 = _run(PipelineInspector.from_scenario(scenario).run_until(scenario.build_context()))
    assert r1.final_response == r2.final_response == "lol yeah that tracks honestly"
    assert r1.halt_reason == r2.halt_reason == ""


def test_snapshot_ctx_summarizes_message_and_deep_copies():
    scenario = Scenario(content="serin hello", username="Rin")
    ctx = scenario.build_context()
    snap = snapshot_ctx(ctx)
    assert snap["message"]["author_id"] == 5
    assert snap["raw_content"] == "serin hello"
    # Mutating the snapshot must not touch the live ctx.
    snap["raw_content"] = "changed"
    assert ctx.raw_content == "serin hello"


def test_run_until_requires_real_pipeline_not_mock():
    pipeline = build_pipeline(scenario=Scenario(content="serin hi"), force_reply=True)
    inspector = PipelineInspector(pipeline)
    for stage in inspector.stages:
        assert stage.__class__.__module__.startswith("serin.")
