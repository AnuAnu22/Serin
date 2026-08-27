"""SQLite persistence for self-generated goals (``goals`` + ``goal_evidence``).

Extracted into its own package because ``d4_1_core_storage`` already holds
five non-init modules (THE_LAW Rule 1: max 5 files per directory) - this is
the first module of ``d5_6_goal_storage``. Follows the
``d5_4_dynamics_store`` duck-typed contract exactly: every function takes a
``store`` that is anything with ``.conn``, so d1_3/d1_5 callers never import
d1_1 store classes (edge-B pattern, CONNECTIONS.md).

Machinery only. The content of `statement` is stored verbatim; nothing in
this module curates, sanitizes, or templates goal text.
"""
# --- Imports ---
from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

logger = logging.getLogger("serin")

# --- Types ---
# (none)

# --- Constants ---
_TERMINAL_STATUSES: tuple[str, ...] = ("ACHIEVED", "DROPPED", "SUPERSEDED")
_LIVE_STATUSES_SQL: str = "('FORMING', 'ACTIVE', 'PAUSED')"

# --- Helpers ---
# (none)

# --- Entry ---


def create_goal(store: Any, statement: str, salience: float,
                provenance: str = "", parent_goal_id: int | None = None,
                status: str = "FORMING", user_id: str = "global") -> int:
    """Insert one new goal row; returns its id (-1 on storage failure).

    `statement` is persisted verbatim. `status` defaults to FORMING;
    callers that already know better may create directly ACTIVE.
    """
    now = time.time()
    cursor: sqlite3.Cursor = store.conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO goals (created_at, updated_at, statement, status,
                               salience, origin_provenance, parent_goal_id, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now, now, statement, status, float(salience), provenance,
             parent_goal_id, user_id),
        )
        store.conn.commit()
        last_id = cursor.lastrowid
        return int(last_id) if last_id is not None else -1
    except Exception as e:
        logger.error("Error creating goal row: %s", e)
        return -1


def add_goal_evidence(store: Any, goal_id: int, kind: str, detail: str = "",
                      source: str = "") -> bool:
    """Append one provenance entry to `goal_evidence`. Never raises."""
    try:
        cursor: sqlite3.Cursor = store.conn.cursor()
        cursor.execute(
            "INSERT INTO goal_evidence "
            "(goal_id, kind, detail, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (int(goal_id), kind, detail, source, time.time()),
        )
        store.conn.commit()
        return True
    except Exception as e:
        logger.error("Error adding goal evidence for %s: %s", goal_id, e)
        return False


def update_goal_status(store: Any, goal_id: int, new_status: str,
                       salience_delta: float = 0.0,
                       superseded_by: int | None = None) -> bool:
    """Apply one state-machine transition to a goal row.

    Terminal statuses (ACHIEVED/DROPPED/SUPERSEDED) are absorbing: no
    further transition leaves them. SUPERSEDED records the replacement goal
    via a `goal_evidence` entry. Returns True when a transition happened.
    """
    cursor: sqlite3.Cursor = store.conn.cursor()
    try:
        cursor.execute("SELECT status FROM goals WHERE id = ?", (int(goal_id),))
        row: sqlite3.Row | None = cursor.fetchone()
        if row is None:
            return False
        if str(row["status"]) in _TERMINAL_STATUSES:
            return False
        stamp = time.time()
        if superseded_by is not None:
            cursor.execute(
                "UPDATE goals SET status = 'SUPERSEDED', updated_at = ?, "
                "last_reviewed_at = ? WHERE id = ?",
                (stamp, stamp, int(goal_id)),
            )
            store.conn.commit()
            add_goal_evidence(
                store, goal_id, "superseded_by", detail=str(superseded_by))
            return True
        cursor.execute(
            "UPDATE goals SET status = ?, updated_at = ?, last_reviewed_at = ?,"
            " salience = MAX(0.0, MIN(1.0, salience + ?)) WHERE id = ?",
            (new_status, stamp, stamp, float(salience_delta), int(goal_id)),
        )
        store.conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error("Error transitioning goal %s: %s", goal_id, e)
        return False


def bump_goal_salience(store: Any, goal_id: int, delta: float) -> bool:
    """Nudge salience by `delta`, clamped to [0.0, 1.0]. Never raises."""
    try:
        cursor: sqlite3.Cursor = store.conn.cursor()
        cursor.execute(
            "UPDATE goals SET salience = MAX(0.0, MIN(1.0, salience + ?)),"
            " updated_at = ? WHERE id = ?",
            (float(delta), time.time(), int(goal_id)),
        )
        store.conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error("Error bumping goal %s salience: %s", goal_id, e)
        return False


def get_active_goals(store: Any, min_salience: float = 0.0,
                     limit: int = 20, user_id: str | None = None) -> list[dict[str, Any]]:
    """Return live goals ordered by salience DESC (the pursuit order).

    FORMING rows ride along: they were formed but not yet reviewed into
    ACTIVE; excluding them would hide just-formed goals until the next
    maintenance pass reviews them.
    """
    cursor: sqlite3.Cursor = store.conn.cursor()
    try:
        if user_id is None:
            cursor.execute(
                "SELECT * FROM goals WHERE status IN ('FORMING', 'ACTIVE')"
                " AND salience >= ? ORDER BY salience DESC LIMIT ?",
                (float(min_salience), int(limit)),
            )
        else:
            cursor.execute(
                "SELECT * FROM goals WHERE status IN ('FORMING', 'ACTIVE')"
                " AND salience >= ? AND user_id = ? ORDER BY salience DESC LIMIT ?",
                (float(min_salience), user_id, int(limit)),
            )
        rows: list[sqlite3.Row] = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error("Error loading active goals: %s", e)
        return []


def get_goals_due_review(store: Any, older_than_s: float,
                         limit: int = 10) -> list[dict[str, Any]]:
    """Return live goals whose `last_reviewed_at` is NULL or stale."""
    cutoff = time.time() - float(older_than_s)
    cursor: sqlite3.Cursor = store.conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM goals WHERE status IN " + _LIVE_STATUSES_SQL +
            " AND (last_reviewed_at IS NULL OR last_reviewed_at < ?)"
            " ORDER BY COALESCE(last_reviewed_at, 0) ASC LIMIT ?",
            (cutoff, int(limit)),
        )
        rows: list[sqlite3.Row] = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error("Error loading goals due review: %s", e)
        return []


def count_goals_by_status(store: Any) -> dict[str, int]:
    """Status histogram for the panel route / tests."""
    cursor: sqlite3.Cursor = store.conn.cursor()
    counts: dict[str, int] = {}
    try:
        cursor.execute(
            "SELECT status, COUNT(*) AS n FROM goals GROUP BY status")
        for row in cursor.fetchall():
            counts[str(row["status"])] = int(row["n"])
        return counts
    except Exception as e:
        logger.error("Error counting goals: %s", e)
        return {}


def load_all_goals(store: Any, limit: int = 200,
                   include_terminal: bool = True,
                   user_id: str | None = None) -> list[dict[str, Any]]:
    """Goals newest-first for the panel view; terminal ones optional."""
    query = "SELECT * FROM goals"
    params: list[Any] = []
    if not include_terminal:
        query += " WHERE status IN " + _LIVE_STATUSES_SQL
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
    elif user_id is not None:
        query += " WHERE user_id = ?"
        params.append(user_id)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(int(limit))
    cursor: sqlite3.Cursor = store.conn.cursor()
    try:
        cursor.execute(query, tuple(params))
        rows: list[sqlite3.Row] = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error("Error loading goals: %s", e)
        return []

# --- Helpers ---
# (none)

# --- Errors ---
# (none)
