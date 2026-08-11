"""Tests for the user_mood_state table created by the schema initializer."""
import sqlite3

from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_3_schema_store import (
    init_sqlite_schema,
)


def _fresh_db():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    init_sqlite_schema(conn, cursor)
    return conn, cursor


def test_user_mood_state_table_created() -> None:
    """init_sqlite_schema must create the per-relationship mood table."""
    conn, cursor = _fresh_db()
    try:
        cursor.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type='table' AND name='user_mood_state'"
        )
        assert cursor.fetchone() is not None
    finally:
        conn.close()


def test_user_mood_state_columns() -> None:
    """The table carries the mood triple plus timestamps."""
    conn, cursor = _fresh_db()
    try:
        cols = {row[1] for row in cursor.execute("PRAGMA table_info(user_mood_state)")}
        assert {
            "user_id", "energy_level", "sass_level", "engagement", "updated_at",
        } <= cols
    finally:
        conn.close()
