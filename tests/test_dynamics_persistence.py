"""Tests for ConversationDynamicsEngine persistence (channel_dynamics table).

Pins the SERIN_VISION "Growth" requirement: conversational physics state
(momentum, phase, timing) must survive restarts as accumulated state, not
reset to zero. Mirrors the user_affect test fixture pattern (in-memory SQLite
+ authoritative schema + duck-typed store).
"""
import sqlite3
import time
from typing import Any

import pytest

from serin.d1_3_state_core.d2_5_state_conversation.d3_1_dynamics_engine import (
    FLUSH_INTERVAL_S,
    ConversationDynamicsEngine,
)


@pytest.fixture
def temp_db() -> Any:
    """In-memory database with the authoritative schema + mock store."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_3_schema_store import (
        init_sqlite_schema,
    )
    init_sqlite_schema(conn, cursor)

    class MockStore:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self.conn = connection

    return MockStore(conn)


def _observed_engine(channel_id: str = "chan1") -> ConversationDynamicsEngine:
    """Engine with one channel observed twice (real accumulated state)."""
    engine = ConversationDynamicsEngine()
    now = time.time()
    engine.observe_message(channel_id, "hello serin how are you", "userA",
                           timestamp=now - 30)
    engine.observe_message(channel_id, "pretty good thanks friend", "userB",
                           timestamp=now - 10)
    return engine


# ── Schema pin ────────────────────────────────────────────────────────────────

def test_channel_dynamics_table_created(temp_db: Any) -> None:
    """channel_dynamics table exists with the expected columns."""
    cursor = temp_db.conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='channel_dynamics'"
    )
    assert cursor.fetchone() is not None

    cursor.execute("PRAGMA table_info(channel_dynamics)")
    columns = {row[1] for row in cursor.fetchall()}
    expected = {
        "channel_id", "momentum", "phase", "frequency", "temperature",
        "last_active", "total_words", "message_times_json", "word_counts_json",
        "participants_json", "last_action", "last_action_time", "updated_at",
    }
    assert expected == columns


# ── Roundtrip through the real store functions ───────────────────────────────

def test_flush_then_restore_roundtrip(temp_db: Any) -> None:
    """State flushed to SQLite restores into a fresh engine bit-for-bit."""
    source = _observed_engine()
    assert source.flush_to_store(temp_db, force=True) == 1

    fresh = ConversationDynamicsEngine()
    snapshots = ConversationDynamicsEngine.load_persisted_snapshots(temp_db)
    assert len(snapshots) == 1
    assert fresh.restore_from_snapshots(snapshots) == 1

    src_ch = source.channels["chan1"]
    dst_ch = fresh.channels["chan1"]
    assert dst_ch["momentum"] == pytest.approx(src_ch["momentum"])
    assert dst_ch["phase"] == pytest.approx(src_ch["phase"])
    assert dst_ch["frequency"] == pytest.approx(src_ch["frequency"])
    assert dst_ch["total_words"] == src_ch["total_words"]
    assert dst_ch["word_counts"] == dict(src_ch["word_counts"])
    assert dst_ch["participants"] == src_ch["participants"]


def test_upsert_updates_same_channel(temp_db: Any) -> None:
    """Second flush for the same channel updates the row (no duplicates)."""
    engine = _observed_engine()
    engine.flush_to_store(temp_db, force=True)
    engine.observe_message("chan1", "one more message here", "userC")
    engine.flush_to_store(temp_db, force=True)

    cursor = temp_db.conn.cursor()
    cursor.execute("SELECT COUNT(*) AS c FROM channel_dynamics")
    assert cursor.fetchone()["c"] == 1

    rows = ConversationDynamicsEngine.load_persisted_snapshots(temp_db)
    assert rows[0]["momentum"] >= engine.channels["chan1"]["momentum"] - 0.001


def test_snapshot_skips_never_observed_channels() -> None:
    """Defaultdict entries never touched by observe_message are not exported."""
    engine = ConversationDynamicsEngine()
    engine.channels["ghost"]  # touch without observing
    assert engine.snapshot_persist_state() == []


def test_restore_ignores_malformed_snapshots(caplog: Any) -> None:
    """Corrupt rows degrade to skip — a bad snapshot must never break boot."""
    engine = ConversationDynamicsEngine()
    restored = engine.restore_from_snapshots([
        {"channel_id": "good", "momentum": 0.5, "phase": 1.0, "frequency": 0.1,
         "temperature": 2.0, "last_active": time.time(), "total_words": 4,
         "message_times": [time.time()], "word_counts": {"hello": 1},
         "participants": ["u1"], "last_action": "reply", "last_action_time": 1.0},
        {"channel_id": "bad", "momentum": "not-a-number"},
        {"nonsense": True},
    ])
    assert restored == 1
    assert "bad" not in engine.channels or engine.channels["bad"]["momentum"] == 0.0


# ── Causality doctrine: persistence must not change decisions ────────────────

def test_restored_state_produces_identical_energies() -> None:
    """decide_action energies depend only on channel state — identical after
    restore (state-caused behavior, per causality_not_performance)."""
    source = _observed_engine("chanX")

    fresh = ConversationDynamicsEngine()
    fresh.restore_from_snapshots(source.snapshot_persist_state())

    # Boltzmann probability ratios derive from energies; compare the energy
    # inputs the engine reads from channel state rather than sampling RNG.
    s_ch = source.channels["chanX"]
    f_ch = fresh.channels["chanX"]
    assert f_ch["momentum"] == pytest.approx(s_ch["momentum"])
    assert f_ch["temperature"] == pytest.approx(s_ch["temperature"])
    assert f_ch["phase"] == pytest.approx(s_ch["phase"])


def test_flush_throttled_by_default(temp_db: Any) -> None:
    """Non-forced flushes inside FLUSH_INTERVAL_S are no-ops."""
    engine = _observed_engine()
    assert engine.flush_to_store(temp_db) == 1          # first flush lands
    engine.observe_message("chan1", "burst message here", "userD")
    assert engine.flush_to_store(temp_db) == 0          # throttled
    assert engine.flush_to_store(temp_db, force=True) == 1  # force bypasses
    assert FLUSH_INTERVAL_S > 0
