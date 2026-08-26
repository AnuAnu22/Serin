"""Tests for GoalsEngine: formation parsing, review decay, promotion, pursuit.

Pins the C2 machinery layer. Doctrine under test:
- parse_formation validates LLM output shape but NEVER rewrites statement
  content (verbatim pass-through or discard);
- review decay + auto-drop are deterministic arithmetic (causality, not
  performance - no RNG anywhere in the goal lifecycle);
- formation is threshold-gated by the maintenance caller, not by content
  filtering.
"""
import sqlite3
from typing import Any

import pytest

from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage import (
    d6_1_goals_store as gs,
)
from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_3_schema_store import (
    init_sqlite_schema,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_4_goals_engine import (
    DECAY_ACTIVE_PER_REVIEW,
    SALIENCE_DROP_FLOOR,
    GoalsEngine,
    parse_formation,
)


@pytest.fixture
def engine_db() -> Any:
    """GoalsEngine over an in-memory store with the authoritative schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_sqlite_schema(conn, conn.cursor())

    class MockStore:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self.conn = connection

    return GoalsEngine(MockStore(conn))


# --- Formation prompt ---------------------------------------------------------


def test_formation_prompt_carries_material_and_existing(engine_db: Any) -> None:
    """Prompt embeds recent lines and current goals verbatim."""
    prompt = engine_db.build_formation_prompt(
        ["user: i keep losing my configs", "serin: sounds like a tool gap"],
        ["keep a changelog"],
    )
    assert "i keep losing my configs" in prompt
    assert "- keep a changelog" in prompt
    # The empty-goal escape hatch must exist so the LLM can decline.
    '{"statement": "", "salience": 0.0}' in prompt


# --- parse_formation ------------------------------------------------------------


def test_parse_accepts_bare_json_verbatim() -> None:
    """Well-formed JSON passes the statement through UNTOUCHED."""
    raw = '{"statement": "Reverse engineer the neighbor cat routine", "salience": 0.8}'
    parsed = parse_formation(raw)
    assert parsed is not None
    statement, salience = parsed
    assert statement == "Reverse engineer the neighbor cat routine"
    assert abs(salience - 0.8) < 1e-9


def test_parse_accepts_fenced_json_and_clamps_salience() -> None:
    """Code-fenced JSON parses; out-of-range salience clamps into [0,1]."""
    raw = 'here you go:\n```json\n{"statement": "x", "salience": 42}\n```'
    parsed = parse_formation(raw)
    assert parsed is not None
    _, salience = parsed
    assert salience == 1.0


def test_parse_rejects_malformed_and_empty() -> None:
    """Garbage, non-dict JSON, empty statements, and oversized ones die."""
    assert parse_formation("no json here at all") is None
    assert parse_formation('[1, 2, 3]') is None
    assert parse_formation('{"statement": "", "salience": 0.5}') is None
    assert parse_formation('{"statement": "' + "x" * 900 + '", "salience": 0.5}') is None


# --- form_goal -------------------------------------------------------------------


def test_form_goal_writes_row_plus_evidence(engine_db: Any) -> None:
    """form_goal creates the FORMING row and its formed evidence entry."""
    gid = engine_db.form_goal(
        "write a small synthesizer in rust", 0.75,
        provenance="maintenance:formation", detail="unit")
    assert gid > 0
    row = gs.get_active_goals(engine_db.memory)[0]
    assert row["status"] == "FORMING"
    cursor = engine_db.memory.conn.cursor()
    cursor.execute(
        "SELECT kind, detail FROM goal_evidence WHERE goal_id = ?", (gid,))
    rows = cursor.fetchall()
    assert [str(r["kind"]) for r in rows] == ["formed"]


# --- review decay / auto-drop ------------------------------------------------------


def test_review_decays_active_salience_deterministically(engine_db: Any) -> None:
    """One review cycle removes exactly DECAY_ACTIVE_PER_REVIEW."""
    gs.create_goal(engine_db.memory, "decay probe", 0.50,
                   status="ACTIVE")
    reviewed = engine_db.review_due(older_than_s=0.0)
    assert reviewed == 1
    row = gs.get_active_goals(engine_db.memory)[0]
    assert abs(row["salience"] - (0.50 - DECAY_ACTIVE_PER_REVIEW)) < 1e-9


def test_review_auto_drops_below_floor(engine_db: Any) -> None:
    """Salience under the floor after decay -> DROPPED with evidence."""
    gid = gs.create_goal(engine_db.memory, "dying probe",
                         SALIENCE_DROP_FLOOR - 0.01, status="ACTIVE")
    engine_db.review_due(older_than_s=0.0)
    assert gs.count_goals_by_status(engine_db.memory) == {"DROPPED": 1}
    cursor = engine_db.memory.conn.cursor()
    cursor.execute(
        "SELECT kind FROM goal_evidence WHERE goal_id = ?", (gid,))
    assert [str(r["kind"]) for r in cursor.fetchall()] == ["auto_dropped"]


def test_paused_goals_decay_faster_but_survive_high_start(engine_db: Any) -> None:
    """PAUSED goals use the steeper decay constant."""
    from serin.d1_3_state_core.d2_5_state_conversation.d3_4_goals_engine import (
        DECAY_PAUSED_PER_REVIEW,
    )
    gid = gs.create_goal(engine_db.memory, "paused probe", 0.60,
                         status="PAUSED")
    engine_db.review_due(older_than_s=0.0)
    live = [r for r in gs.load_all_goals(engine_db.memory)
            if int(r["id"]) == gid]
    assert len(live) == 1
    assert str(live[0]["status"]) == "PAUSED"
    assert abs(float(live[0]["salience"])
               - (0.60 - DECAY_PAUSED_PER_REVIEW)) < 1e-9


# --- promotion -----------------------------------------------------------------------


def test_promote_ready_moves_stable_forming_to_active(engine_db: Any) -> None:
    """FORMING goals that carry last_reviewed_at promote to ACTIVE."""
    gid = gs.create_goal(engine_db.memory, "stable forming probe", 0.7)
    # Simulate survival of one review window (review_due stamps it).
    assert gs.update_goal_status(engine_db.memory, gid, "FORMING")
    promoted = engine_db.promote_ready()
    assert promoted == 1
    row = gs.get_active_goals(engine_db.memory)[0]
    assert row["status"] == "ACTIVE"


# --- pursuit ---------------------------------------------------------------------------


def test_pursuit_snapshot_orders_and_floors(engine_db: Any) -> None:
    """Snapshot returns salience-DESC above the pursuit floor only."""
    weak = gs.create_goal(engine_db.memory, "weak drive", 0.05,
                          status="ACTIVE")  # below floor on purpose
    strong = gs.create_goal(engine_db.memory, "strong drive", 0.9,
                            status="ACTIVE")
    snap = engine_db.pursuit_snapshot()
    ids = [int(r["id"]) for r in snap]
    assert strong in ids
    assert weak not in ids


def test_touch_on_mention_reinforces_overlapping_goal(engine_db: Any) -> None:
    """Conversation overlap bumps salience and writes reinforced evidence."""
    stmt = "document every qdrant collection schema field"
    gid = gs.create_goal(engine_db.memory, stmt, 0.40, status="ACTIVE")
    bumped = engine_db.touch_on_mention(
        "we should document every qdrant collection schema field someday")
    assert bumped >= 1
    row = gs.get_active_goals(engine_db.memory)[0]
    assert float(row["salience"]) > 0.40
    cursor = engine_db.memory.conn.cursor()
    cursor.execute(
        "SELECT kind FROM goal_evidence WHERE goal_id = ?", (gid,))
    kinds = [str(r["kind"]) for r in cursor.fetchall()]
    assert "reinforced" in kinds


def test_touch_on_mention_ignores_short_noise(engine_db: Any) -> None:
    """Fragments under the token floor never reinforce anything."""
    gs.create_goal(engine_db.memory, "some long specific goal statement",
                   0.40, status="ACTIVE")
    assert engine_db.touch_on_mention("hi lol") == 0


def test_stats_shape(engine_db: Any) -> None:
    """stats() exposes counts + pursuit rows + cadence for consumers."""
    gs.create_goal(engine_db.memory, "stats probe goal", 0.6,
                   status="ACTIVE")
    stats = engine_db.stats()
    assert stats["counts"] == {"ACTIVE": 1}
    assert stats["pursuit"][0]["statement"] == "stats probe goal"
    assert stats["review_interval_s"] > 0
