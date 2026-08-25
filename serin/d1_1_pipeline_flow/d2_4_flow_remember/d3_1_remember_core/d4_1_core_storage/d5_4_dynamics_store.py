"""SQLite persistence for ConversationDynamicsEngine channel snapshots.

Extracted into its own module because ``d5_2_sqlite_store.py`` sits near the
500-line ceiling (THE_LAW Rule 2). Follows the ``user_affect`` precedent:
functions take a duck-typed ``store`` (anything with ``.conn``), so the
d1_3 engine can call them via a function-scoped import without importing the
d1_1 store classes (depth-DAG / edge-B pattern, see CONNECTIONS.md).
"""
# --- Imports ---
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

logger = logging.getLogger("serin")

# --- Types ---
# (none)

# --- Constants ---
_MAX_JSON_PARTICIPANTS: int = 200

# --- Helpers ---

def decode_participants(payload: str) -> set[str]:
    """Decode a participants JSON array into a string set (defensive).

    Isolated helper so the untyped ``json.loads`` result is consumed behind
    one annotated boundary; malformed payloads degrade to an empty set.
    """
    try:
        # list(...) wraps the untyped result as list[Any] — the one shape
        # both mypy strict and pyright strict accept iteration over.
        items: list[Any] = list(json.loads(payload))
    except (json.JSONDecodeError, TypeError, ValueError):
        return set()
    decoded: set[str] = set()
    for raw_item in items:
        if isinstance(raw_item, str):
            decoded.add(raw_item)
    return decoded

# --- Entry ---


def upsert_channel_dynamics(store: Any, snapshot: dict[str, Any]) -> None:
    """Insert or update one channel's dynamics row from an engine snapshot.

    ``snapshot`` keys mirror the engine's in-memory channel dict plus
    ``channel_id``. JSON-typed fields are serialized here so the engine
    never touches storage details.
    """
    cursor: sqlite3.Cursor = store.conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO channel_dynamics
                (channel_id, momentum, phase, frequency, temperature,
                 last_active, total_words, message_times_json,
                 word_counts_json, participants_json, last_action,
                 last_action_time, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                momentum          = excluded.momentum,
                phase             = excluded.phase,
                frequency         = excluded.frequency,
                temperature       = excluded.temperature,
                last_active       = excluded.last_active,
                total_words       = excluded.total_words,
                message_times_json = excluded.message_times_json,
                word_counts_json  = excluded.word_counts_json,
                participants_json = excluded.participants_json,
                last_action       = excluded.last_action,
                last_action_time  = excluded.last_action_time,
                updated_at        = excluded.updated_at
            """,
            (
                str(snapshot["channel_id"]),
                float(snapshot["momentum"]),
                float(snapshot["phase"]),
                float(snapshot["frequency"]),
                float(snapshot["temperature"]),
                float(snapshot["last_active"]),
                int(snapshot["total_words"]),
                json.dumps(list(snapshot.get("message_times", []))[-50:]),
                json.dumps(dict(snapshot.get("word_counts", {}))),
                json.dumps(
                    sorted(str(p) for p in snapshot.get("participants", []))
                    [:_MAX_JSON_PARTICIPANTS]
                ),
                str(snapshot.get("last_action", "none")),
                float(snapshot.get("last_action_time", 0.0)),
                float(snapshot["last_active"]) or time.time(),
            ),
        )
        store.conn.commit()
    except Exception as e:
        logger.error("Error upserting channel_dynamics for %s: %s",
                     snapshot.get("channel_id"), e)


def load_channel_dynamics(store: Any) -> list[dict[str, Any]]:
    """Return all persisted channel snapshots (deserialized, engine-shaped).

    Rows decode back into the engine's per-channel dict shape; JSON fields
    that fail to parse degrade to their empty default rather than raising —
    a corrupt row must never block boot.
    """
    cursor: sqlite3.Cursor = store.conn.cursor()
    try:
        cursor.execute("SELECT * FROM channel_dynamics")
        rows: list[sqlite3.Row] = cursor.fetchall()
    except Exception as e:
        logger.error("Error loading channel_dynamics: %s", e)
        return []

    snapshots: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        try:
            message_times = [float(t) for t in json.loads(
                str(record.get("message_times_json") or "[]"))]
        except (json.JSONDecodeError, TypeError, ValueError):
            message_times = []
        try:
            word_counts = {str(k): int(v) for k, v in dict(
                json.loads(str(record.get("word_counts_json") or "{}"))).items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            word_counts = {}
        try:
            participants: set[str] = decode_participants(
                str(record.get("participants_json") or "[]"))
        except (json.JSONDecodeError, TypeError, ValueError):
            participants = set()

        snapshots.append({
            "channel_id": str(record["channel_id"]),
            "momentum": float(record["momentum"]),
            "phase": float(record["phase"]),
            "frequency": float(record["frequency"]),
            "temperature": float(record["temperature"]),
            "last_active": float(record["last_active"]),
            "total_words": int(record["total_words"]),
            "message_times": message_times,
            "word_counts": word_counts,
            "participants": participants,
            "last_action": str(record.get("last_action") or "none"),
            "last_action_time": float(record.get("last_action_time") or 0.0),
        })
    return snapshots


def delete_stale_channel_dynamics(store: Any, before_ts: float) -> int:
    """Drop rows untouched since ``before_ts`` (housekeeping for dead channels).

    Returns the number of rows removed.
    """
    cursor: sqlite3.Cursor = store.conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM channel_dynamics WHERE updated_at < ?", (before_ts,)
        )
        store.conn.commit()
        return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
    except Exception as e:
        logger.error("Error deleting stale channel_dynamics: %s", e)
        return 0

# --- Helpers ---
# (none)

# --- Errors ---
# (none)
