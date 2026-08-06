"""Tests for user_affect table and store methods."""
import sqlite3
import time
from typing import Any

import pytest


@pytest.fixture
def temp_db() -> Any:
    """Create a temporary in-memory database for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Initialize schema including user_affect
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_3_schema_store import (
        init_sqlite_schema,
    )
    init_sqlite_schema(conn, cursor)

    # Create a mock store object
    class MockStore:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self.conn = connection

    return MockStore(conn)


def test_user_affect_table_created(temp_db: Any) -> None:
    """Verify user_affect table exists with correct columns."""
    cursor = temp_db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_affect'")
    assert cursor.fetchone() is not None

    cursor.execute("PRAGMA table_info(user_affect)")
    columns = {row[1] for row in cursor.fetchall()}
    expected = {"user_id", "valence", "valence_updated", "familiarity_count",
                "impression_text", "impression_updated", "since_impression"}
    assert expected.issubset(columns)


def test_upsert_user_affect_creates_new(temp_db: Any) -> None:
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
        upsert_user_affect,
    )

    now = time.time()
    upsert_user_affect(temp_db, "user123", valence=0.3, valence_updated=now, familiarity_count=5)

    cursor = temp_db.conn.cursor()
    cursor.execute("SELECT * FROM user_affect WHERE user_id = ?", ("user123",))
    row = cursor.fetchone()
    assert row is not None
    assert row["user_id"] == "user123"
    assert abs(row["valence"] - 0.3) < 0.001
    assert row["familiarity_count"] == 5


def test_upsert_user_affect_updates_existing(temp_db: Any) -> None:
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
        upsert_user_affect,
    )

    now = time.time()
    upsert_user_affect(temp_db, "user123", valence=0.3, valence_updated=now, familiarity_count=5)
    upsert_user_affect(temp_db, "user123", valence=0.5, valence_updated=now + 10, familiarity_count=6,
                      impression_text="friendly", impression_updated=now + 10, since_impression=0)

    cursor = temp_db.conn.cursor()
    cursor.execute("SELECT * FROM user_affect WHERE user_id = ?", ("user123",))
    row = cursor.fetchone()
    assert abs(row["valence"] - 0.5) < 0.001
    assert row["familiarity_count"] == 6
    assert row["impression_text"] == "friendly"
    assert row["since_impression"] == 0


def test_get_user_affect_returns_none_for_missing(temp_db: Any) -> None:
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
        get_user_affect,
    )

    result = get_user_affect(temp_db, "nonexistent")
    assert result is None


def test_get_user_affect_returns_dict(temp_db: Any) -> None:
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
        get_user_affect,
        upsert_user_affect,
    )

    now = time.time()
    upsert_user_affect(temp_db, "user123", valence=0.3, valence_updated=now, familiarity_count=5)
    result = get_user_affect(temp_db, "user123")

    assert result is not None
    assert result["user_id"] == "user123"
    assert abs(result["valence"] - 0.3) < 0.001
    assert result["familiarity_count"] == 5


def test_get_users_due_impression_filters_correctly(temp_db: Any) -> None:
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
        get_users_due_impression,
        upsert_user_affect,
    )

    now = time.time()
    # User eligible: since_impression >= 25, familiarity >= 10
    upsert_user_affect(temp_db, "eligible1", valence=0.0, valence_updated=now,
                      familiarity_count=10, since_impression=25)
    upsert_user_affect(temp_db, "eligible2", valence=0.0, valence_updated=now,
                      familiarity_count=50, since_impression=30)
    # User ineligible: too few since_impression
    upsert_user_affect(temp_db, "ineligible1", valence=0.0, valence_updated=now,
                      familiarity_count=10, since_impression=20)
    # User ineligible: too few messages
    upsert_user_affect(temp_db, "ineligible2", valence=0.0, valence_updated=now,
                      familiarity_count=5, since_impression=30)

    results = get_users_due_impression(temp_db, limit=10)
    user_ids = {r["user_id"] for r in results}
    assert user_ids == {"eligible1", "eligible2"}


def test_get_users_due_impression_respects_limit(temp_db: Any) -> None:
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
        get_users_due_impression,
        upsert_user_affect,
    )

    now = time.time()
    for i in range(5):
        upsert_user_affect(temp_db, f"user{i}", valence=0.0, valence_updated=now,
                          familiarity_count=10, since_impression=25)

    results = get_users_due_impression(temp_db, limit=3)
    assert len(results) == 3
