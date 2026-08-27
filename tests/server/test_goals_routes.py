"""Goals panel route - GET /api/goals shape + degradation (C5).

Mirrors tests/server/test_pipeline_metrics.py: drives the REAL route against a
temp-file-backed store so the panel and the maintenance loop agree on the world.

# --- Imports ---
"""
from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access as state_mod
from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage import (
    d6_1_goals_store as gs,
)
from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_3_schema_store import (
    init_sqlite_schema,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_4_goals_engine import (
    GoalsEngine,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_6_routes.d5_1_core_routes.d6_5_goal_routes import (
    register_goal_routes,
)

# --- Store ---


class FileStore:
    def __init__(self, tmp_path: Any) -> None:
        self.conn = sqlite3.connect(
            str(tmp_path / 'goals_test.db'), check_same_thread=False
        )
        self.conn.row_factory = sqlite3.Row
        init_sqlite_schema(self.conn, self.conn.cursor())


@pytest.fixture
def file_store(tmp_path: Any) -> FileStore:
    return FileStore(tmp_path)


@pytest.fixture
def api_client(file_store: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    app = FastAPI()
    register_goal_routes(app, state_mod.bot_state)
    monkeypatch.setitem(state_mod.bot_state, 'memory_system', file_store)
    monkeypatch.setitem(state_mod.bot_state, 'goals_engine', None)
    return TestClient(app)


# --- Route shape ---


def test_get_goals_returns_rows_and_counts(api_client: Any, file_store: Any) -> None:
    gs.create_goal(file_store, 'map the panel endpoints', 0.6, status='ACTIVE')
    gs.create_goal(file_store, 'write a parser', 0.4, status='FORMING')
    gs.create_goal(file_store, 'old finished goal', 0.2, status='ACHIEVED')
    resp = api_client.get('/api/goals?limit=50&include_terminal=true')
    assert resp.status_code == 200
    body = resp.json()
    assert body['counts'] == {'ACTIVE': 1, 'FORMING': 1, 'ACHIEVED': 1}
    assert len(body['goals']) == 3
    # Terminal rows included; stats None because engine not wired here.
    assert body['stats'] is None
    assert body['review_interval_s'] is None


def test_get_goals_excludes_terminal(api_client: Any, file_store: Any) -> None:
    gs.create_goal(file_store, 'live goal', 0.6, status='ACTIVE')
    gs.create_goal(file_store, 'done goal', 0.2, status='ACHIEVED')
    resp = api_client.get('/api/goals?include_terminal=false')
    assert resp.status_code == 200
    body = resp.json()
    # counts is a full status histogram; only the returned rows are filtered.
    assert body['counts'].get('ACHIEVED') == 1
    assert [g['status'] for g in body['goals']] == ['ACTIVE']


def test_get_goals_uses_engine_stats(api_client: Any, file_store: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    gs.create_goal(file_store, 'engine-backed goal', 0.7, status='ACTIVE')
    engine = GoalsEngine(file_store)
    monkeypatch.setitem(state_mod.bot_state, 'goals_engine', engine)
    resp = api_client.get('/api/goals')
    assert resp.status_code == 200
    body = resp.json()
    assert body['stats']['counts'] == {'ACTIVE': 1}
    assert body['review_interval_s'] > 0


def test_get_goals_without_store_degrades(api_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(state_mod.bot_state, 'memory_system', object())
    resp = api_client.get('/api/goals')
    assert resp.status_code == 200
    body = resp.json()
    assert body['goals'] == []
    assert body['counts'] == {}
    assert "no sqlite" in body["reason"]
