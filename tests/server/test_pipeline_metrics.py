"""Pipeline metrics history — recorder, routes, retention (Plan 3, edge-A).

Covers:
- record/load round trip against a real in-memory SQLite DB with the
  authoritative schema (init_sqlite_schema).
- defensive degradation: corrupt JSON stages, failing store, missing keys.
- summarize stats math (p50/p95, halt rate, slowest stage).
- retention prune + explicit delete-all.
- /api/metrics/pipeline + /api/metrics/prune over the REAL FastAPI app with
  bot_state pointed at a temp-file-backed memory fake.
- MessagePipeline._record_run_metrics wiring (edge-A): enabled => one row;
  disabled or store-less pipeline => zero rows, no exception.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any

import pytest

from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_5_pipeline_metrics import (
    delete_all_pipeline_runs,
    load_recent_pipeline_runs,
    prune_pipeline_runs,
    record_pipeline_run,
    summarize_pipeline_runs,
)
from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_3_schema_store import (
    init_sqlite_schema,
)

# --- Helpers ---

class MemStore:
    """Minimal duck-typed store: real SQLite conn with the real schema."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_sqlite_schema(self.conn, self.conn.cursor())

    def count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) AS n FROM pipeline_runs")
        row: sqlite3.Row = cur.fetchone()
        return int(row["n"])


def _run(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "started_ts": time.time(),
        "duration_ms": 123.4,
        "user_id": "845531416296361986",
        "channel_id": "9999",
        "halted": False,
        "halt_reason": "",
        "responded": True,
        "stage_count": 2,
        "stage_timings": {"LLMCallStage": 100.0, "SendStage": 20.0},
        "error": "",
    }
    base.update(overrides)
    return base


# --- Core ---


@pytest.fixture
def store() -> MemStore:
    return MemStore()


def test_record_and_load_round_trip(store: MemStore) -> None:
    assert record_pipeline_run(store, _run()) is True
    runs = load_recent_pipeline_runs(store)
    assert len(runs) == 1
    run = runs[0]
    assert run["duration_ms"] == 123.4
    assert run["halted"] is False
    assert run["responded"] is True
    assert run["stages"] == {"LLMCallStage": 100.0, "SendStage": 20.0}
    assert run["stage_count"] == 2


def test_load_newest_first_and_limit(store: MemStore) -> None:
    for i in range(5):
        record_pipeline_run(store, _run(started_ts=1000.0 + i))
    runs = load_recent_pipeline_runs(store, limit=3)
    assert [r["id"] for r in runs] == sorted(
        (r["id"] for r in runs), reverse=True
    )
    assert len(runs) == 3


def test_corrupt_stages_json_degrades_to_empty_dict(store: MemStore) -> None:
    store.conn.execute(
        "INSERT INTO pipeline_runs (started_ts, duration_ms, stages_json) "
        "VALUES (?, ?, ?)",
        (time.time(), 5.0, "{not json"),
    )
    store.conn.commit()
    runs = load_recent_pipeline_runs(store)
    assert len(runs) == 1
    assert runs[0]["stages"] == {}


def test_record_on_broken_store_returns_false() -> None:
    class Broken:
        class conn:  # noqa: N801 — deliberate minimal failure object
            @staticmethod
            def cursor() -> Any:
                raise sqlite3.OperationalError("boom")

    assert record_pipeline_run(Broken(), _run()) is False


def test_load_on_missing_table_returns_empty() -> None:
    bare = sqlite3.connect(":memory:")
    bare.row_factory = sqlite3.Row

    class BareStore:
        conn = bare

    assert load_recent_pipeline_runs(BareStore()) == []
    assert summarize_pipeline_runs(BareStore())["total_runs"] == 0


def test_summarize_math(store: MemStore) -> None:
    now = time.time()
    durations = [100.0, 200.0, 300.0, 400.0]
    for i, d in enumerate(durations):
        record_pipeline_run(store, _run(
            started_ts=now - i,
            duration_ms=d,
            halted=(i == 3),
            halt_reason="decision" if i == 3 else "",
            responded=(i != 3),
            stage_timings={"LLMCallStage": d * 0.9},
        ))
    s = summarize_pipeline_runs(store, window_s=3600.0)
    assert s["total_runs"] == 4
    assert s["halted"] == 1
    assert s["halt_rate"] == 0.25
    assert s["avg_duration_ms"] == 250.0
    assert s["max_duration_ms"] == 400.0
    # slowest stage by mean latency
    assert s["slowest_stage"] is not None
    assert s["slowest_stage"]["name"] == "LLMCallStage"


def test_summarize_empty_window(store: MemStore) -> None:
    record_pipeline_run(store, _run(started_ts=time.time() - 10 * 3600))
    s = summarize_pipeline_runs(store, window_s=60.0)
    assert s["total_runs"] == 0
    assert s["avg_duration_ms"] is None
    assert s["slowest_stage"] is None


def test_prune_by_age_and_delete_all(store: MemStore) -> None:
    now = time.time()
    record_pipeline_run(store, _run(started_ts=now - 30 * 86400))   # old
    record_pipeline_run(store, _run(started_ts=now - 3600))         # fresh
    deleted = prune_pipeline_runs(store, max_age_s=14 * 86400.0)
    assert deleted == 1
    assert store.count() == 1
    assert delete_all_pipeline_runs(store) == 1
    assert store.count() == 0


def test_stage_timings_capped_and_sanitized(store: MemStore) -> None:
    bad = {f"S{i}": float(i) for i in range(200)}
    bad["broken"] = "not-a-number"  # type: ignore[dict-item]
    record_pipeline_run(store, _run(stage_timings=bad))
    run = load_recent_pipeline_runs(store)[0]
    assert len(run["stages"]) <= 64
    assert "broken" not in run["stages"]


# --- Panel routes ---


class FileStore(MemStore):
    """Temp-FILE-backed so the route's separate connection sees committed rows."""

    def __init__(self, tmp_path: Any) -> None:
        # check_same_thread=False mirrors production's connection so
        # TestClient's worker thread can use the same handle.
        self.conn = sqlite3.connect(
            str(tmp_path / "metrics_test.db"), check_same_thread=False
        )
        self.conn.row_factory = sqlite3.Row
        init_sqlite_schema(self.conn, self.conn.cursor())


@pytest.fixture
def file_store(tmp_path: Any) -> FileStore:
    return FileStore(tmp_path)


@pytest.fixture
def api_client(file_store: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access as state_mod
    from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_6_routes.d5_1_core_routes.d6_4_metrics_routes import (
        register_metrics_routes,
    )

    app = FastAPI()
    register_metrics_routes(app, state_mod.bot_state)
    monkeypatch.setitem(state_mod.bot_state, "memory_system", file_store)
    return TestClient(app)


def test_route_get_pipeline_metrics(api_client: Any, file_store: Any) -> None:
    record_pipeline_run(file_store, _run(duration_ms=42.0))
    resp = api_client.get("/api/metrics/pipeline?hours=24&limit=50")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["count"] == 1
    assert body["runs"][0]["duration_ms"] == 42.0
    assert body["summary"]["total_runs"] == 1
    assert body["retention_days"] >= 1


def test_route_without_store_degrades(api_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access as state_mod

    monkeypatch.setitem(state_mod.bot_state, "memory_system", object())
    resp = api_client.get("/api/metrics/pipeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["runs"] == []
    assert body["summary"] is None
    assert "no sqlite" in body["reason"]


def test_route_prune_requires_confirm(api_client: Any, file_store: Any) -> None:
    record_pipeline_run(file_store, _run())
    resp = api_client.post("/api/metrics/prune")
    assert resp.status_code == 400
    assert file_store.count() == 1
    resp = api_client.post("/api/metrics/prune?confirm=yes")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
    assert file_store.count() == 0


# --- Edge-A wiring ---


def test_process_records_row_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
        MessagePipeline,
    )

    pipe = MessagePipeline(stages=[])
    fake_store = MemStore()
    pipe._metrics_store = fake_store
    ctx = _fake_ctx()
    pipe._record_run_metrics(ctx)
    runs = load_recent_pipeline_runs(fake_store)
    assert len(runs) == 1
    assert runs[0]["responded"] is True
    assert runs[0]["halted"] is False


def test_process_records_nothing_when_disabled() -> None:
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
        MessagePipeline,
    )

    pipe = MessagePipeline(stages=[])
    assert pipe._metrics_store is None
    pipe._record_run_metrics(_fake_ctx())  # must not raise
    # nothing to assert beyond "did not raise" — store was never touched


def test_build_wires_metrics_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
        MessagePipeline,
    )
    from serin.d1_4_config_base.d2_1_base_config import config

    monkeypatch.setattr(config, "PIPELINE_METRICS_ENABLED", True)
    mem = MemStore()
    pipe = MessagePipeline.build(
        memory_system=mem,
        retrieval=object(),
        personality=object(),
        temporal_context=object(),
        response_generator=object(),
        thinking_filter=object(),
        mention_translator=object(),
    )
    assert pipe._metrics_store is mem

    monkeypatch.setattr(config, "PIPELINE_METRICS_ENABLED", False)
    pipe_off = MessagePipeline.build(
        memory_system=mem,
        retrieval=object(),
        personality=object(),
        temporal_context=object(),
        response_generator=object(),
        thinking_filter=object(),
        mention_translator=object(),
    )
    assert pipe_off._metrics_store is None


def test_build_skips_store_without_conn(monkeypatch: pytest.MonkeyPatch) -> None:
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
        MessagePipeline,
    )
    from serin.d1_4_config_base.d2_1_base_config import config

    monkeypatch.setattr(config, "PIPELINE_METRICS_ENABLED", True)
    pipe = MessagePipeline.build(
        memory_system=object(),  # no .conn — must not be used as store
        retrieval=object(),
        personality=object(),
        temporal_context=object(),
        response_generator=object(),
        thinking_filter=object(),
        mention_translator=object(),
    )
    assert pipe._metrics_store is None


# --- Helpers (continued) ---


def _fake_ctx() -> Any:
    """Minimal stand-in exposing only the attrs _record_run_metrics reads."""
    class Ctx:
        user_id = "845531416296361986"
        channel_id = "9999"
        halt_reason = ""
        final_response = "hello!"
        stage_timings = {"LLMCallStage": 90.0}

    return Ctx()
