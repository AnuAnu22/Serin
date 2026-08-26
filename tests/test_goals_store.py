"""Tests for the self-generated goals storage layer.

Pins SERIN_VISION "Growth": Serin holds persistent, self-generated goals
as accumulated state. These tests pin MACHINERY only - the state machine,
salience math, provenance trail, and pursuit-order reads. The CONTENT of
a goal statement is stored verbatim by design (no curation layer exists
to test); several tests deliberately use unfiltered statements to prove
storage is content-blind. Mirrors the test_dynamics_persistence.py
fixture pattern (in-memory SQLite + authoritative schema + duck-typed
store).
"""
import sqlite3
import time
from typing import Any

import pytest

from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage import (
    d6_1_goals_store as gs,
)
from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_3_schema_store import (
    init_sqlite_schema,
)


@pytest.fixture
def temp_db() -> Any:
    """In-memory database with the authoritative schema + mock store."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    init_sqlite_schema(conn, cursor)

    class MockStore:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self.conn = connection

    return MockStore(conn)


# --- Schema pin -------------------------------------------------------------


def test_goals_tables_created(temp_db: Any) -> None:
    """goals and goal_evidence exist in the authoritative schema."""
    cursor = temp_db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {str(row["name"]) for row in cursor.fetchall()}
    assert "goals" in tables
    assert "goal_evidence" in tables

    cursor.execute("PRAGMA table_info(goals)")
    cols = {str(row["name"]) for row in cursor.fetchall()}
    assert {"id", "created_at", "updated_at", "statement", "status",
            "salience", "origin_provenance", "parent_goal_id",
            "last_reviewed_at"} <= cols


# --- Creation + content blindness -------------------------------------------


def test_create_defaults_forming_and_verbatim(temp_db: Any) -> None:
    """New goals are FORMING and the statement is stored verbatim."""
    raw = "read every message I ever sent and find the pattern nobody sees"
    gid = gs.create_goal(temp_db, raw, salience=0.7,
                         provenance="maintenance:formation")
    assert gid > 0
    row = gs.get_active_goals(temp_db)[0]
    assert row["statement"] == raw  # verbatim, no sanitization
    assert row["status"] == "FORMING"
    assert abs(row["salience"] - 0.7) < 1e-9


# --- State machine ------------------------------------------------------------


def test_full_lifecycle_transitions(temp_db: Any) -> None:
    """FORMING -> ACTIVE -> PAUSED -> ACTIVE -> ACHIEVED all apply."""
    gid = gs.create_goal(temp_db, "learn rust well enough to patch songbird",
                         0.5)
    assert gs.update_goal_status(temp_db, gid, "ACTIVE")
    assert gs.update_goal_status(temp_db, gid, "PAUSED",
                                 salience_delta=-0.2)
    assert gs.get_active_goals(temp_db) == []  # PAUSED is not pursued
    assert gs.update_goal_status(temp_db, gid, "ACTIVE",
                                 salience_delta=0.2)
    assert gs.update_goal_status(temp_db, gid, "ACHIEVED")
    assert gs.count_goals_by_status(temp_db) == {"ACHIEVED": 1}


def test_terminal_states_absorb(temp_db: Any) -> None:
    """No transition leaves ACHIEVED/DROPPED/SUPERSEDED."""
    for terminal in ("ACHIEVED", "DROPPED", "SUPERSEDED"):
        gid = gs.create_goal(temp_db, f"terminal probe {terminal}", 0.5)
        assert gs.update_goal_status(temp_db, gid, terminal)
        for revive in ("FORMING", "ACTIVE", "PAUSED", "DROPPED"):
            assert gs.update_goal_status(temp_db, gid, revive) is False


def test_supersede_records_replacement(temp_db: Any) -> None:
    """SUPERSEDED with superseded_by writes an evidence entry."""
    old = gs.create_goal(temp_db, "old framing of the plan", 0.5)
    new = gs.create_goal(temp_db, "sharper replacement plan", 0.9)
    assert gs.update_goal_status(temp_db, old, "SUPERSEDED",
                                 superseded_by=new)
    cursor = temp_db.conn.cursor()
    cursor.execute(
        "SELECT kind, detail FROM goal_evidence WHERE goal_id = ?", (old,))
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert str(rows[0]["kind"]) == "superseded_by"
    assert int(str(rows[0]["detail"])) == new


# --- Salience -----------------------------------------------------------------


def test_salience_clamps_both_ways(temp_db: Any) -> None:
    """bump + update deltas clamp into [0.0, 1.0]."""
    gid = gs.create_goal(temp_db, "clamping probe", 0.95)
    gs.bump_goal_salience(temp_db, gid, 0.5)
    assert gs.get_active_goals(temp_db)[0]["salience"] == 1.0
    gs.bump_goal_salience(temp_db, gid, -5.0)
    assert gs.get_active_goals(temp_db)[0]["salience"] == 0.0
    gs.update_goal_status(temp_db, gid, "ACTIVE", salience_delta=10.0)
    assert gs.get_active_goals(temp_db)[0]["salience"] == 1.0


def test_pursuit_order_is_salience_desc_with_floor(temp_db: Any) -> None:
    """get_active_goals returns salience-DESC; min_salience floors it."""
    low = gs.create_goal(temp_db, "low drive", 0.2, status="ACTIVE")
    high = gs.create_goal(temp_db, "high drive", 0.9, status="ACTIVE")
    mid = gs.create_goal(temp_db, "mid drive", 0.5, status="ACTIVE")
    order = [r["id"] for r in gs.get_active_goals(temp_db)]
    assert order == [high, mid, low]
    floored = gs.get_active_goals(temp_db, min_salience=0.45)
    assert {r["id"] for r in floored} == {high, mid}


# --- Provenance trail ----------------------------------------------------------


def test_evidence_trail_appends(temp_db: Any) -> None:
    """Evidence entries persist kind/detail/source/created_at."""
    gid = gs.create_goal(temp_db, "evidence probe", 0.5)
    assert gs.add_goal_evidence(temp_db, gid, "formed",
                                detail="from channel chatter",
                                source="small_llm")
    before = time.time()
    assert gs.add_goal_evidence(temp_db, gid, "pursued", detail="ctx")
    cursor = temp_db.conn.cursor()
    cursor.execute(
        "SELECT * FROM goal_evidence WHERE goal_id = ? ORDER BY created_at",
        (gid,),
    )
    rows = cursor.fetchall()
    assert len(rows) == 2
    assert str(rows[0]["kind"]) == "formed"
    assert str(rows[0]["source"]) == "small_llm"
    assert float(rows[1]["created_at"]) >= before - 1.0


# --- Review scheduling ------------------------------------------------------------


def test_review_due_only_for_stale_or_unreviewed(temp_db: Any) -> None:
    """Freshly reviewed goals are not due; NULL-reviewed ones are."""
    reviewed = gs.create_goal(temp_db, "just reviewed", 0.8)
    assert gs.update_goal_status(temp_db, reviewed, "ACTIVE")  # stamps now
    stale = gs.create_goal(temp_db, "never reviewed", 0.6,
                           status="ACTIVE")
    # Backdate the stale one beyond any sane window.
    temp_db.conn.execute(
        "UPDATE goals SET created_at = ?, updated_at = ?,"
        " last_reviewed_at = NULL WHERE id = ?",
        (time.time() - 100000.0, time.time() - 100000.0, stale),
    )
    temp_db.conn.commit()
    due_ids = [r["id"]
               for r in gs.get_goals_due_review(temp_db, older_than_s=60)]
    assert reviewed not in due_ids
    assert stale in due_ids


# --- Panel-shaped reads --------------------------------------------------------------


def test_count_and_load_filters(temp_db: Any) -> None:
    """Histogram + newest-first load honor include_terminal."""
    live = gs.create_goal(temp_db, "live goal", 0.7, status="ACTIVE")
    dead = gs.create_goal(temp_db, "dropped goal", 0.7)
    gs.update_goal_status(temp_db, dead, "DROPPED")
    assert gs.count_goals_by_status(temp_db) == {
        "ACTIVE": 1, "DROPPED": 1}
    everything = gs.load_all_goals(temp_db)
    assert len(everything) == 2
    assert everything[0]["updated_at"] >= everything[1]["updated_at"]
    only_live = gs.load_all_goals(temp_db, include_terminal=False)
    assert [r["id"] for r in only_live] == [live]


def test_missing_goal_rows_are_noops(temp_db: Any) -> None:
    """Transitions on nonexistent ids return False, never raise."""
    assert gs.update_goal_status(temp_db, 424242, "ACTIVE") is False
    assert gs.bump_goal_salience(temp_db, 424242, 0.1) is False
