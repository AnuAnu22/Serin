"""Pipeline run metrics — SQLite recorder + query + retention (edge-A).

CONNECTIONS.md Phase-5 rec #4: every ``MessagePipeline.process()`` run is
recorded as one ``pipeline_runs`` row so the control panel can chart
duration/halt-rate/stage-latency over time. Today the panel's pipeline view
is RAM-only (``bot_state['pipeline_status']``), wiped on the hot-reloader's
frequent respawns — a restart erases the evidence of the slowdown you were
investigating.

Design constraints honored here:
- Duck-typed ``store`` (anything with ``.conn``) — same contract as
  ``d5_4_dynamics_store``, so callers pass ``memory.conn``-bearing objects
  without importing the store class (depth-DAG / edge-B pattern).
- Recording NEVER breaks the message flow: every function swallows and logs
  storage errors. Metrics are observability; they must not take the bot down.
- Retention prunes by age so a long-lived bot cannot grow the table forever.

# --- Imports ---
"""
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
# Stage timings ride in JSON; 40 stages would already be pathological — cap
# the payload defensively so a runaway stage list cannot bloat rows.
_MAX_STAGES_IN_JSON: int = 64


# --- Helpers ---


def _stages_json(stage_timings: dict[str, float]) -> str:
    """Serialize stage timings defensively (cap count, tolerate bad values)."""
    items: list[tuple[str, float]] = []
    for name, ms in list(stage_timings.items())[:_MAX_STAGES_IN_JSON]:
        try:
            items.append((str(name), float(ms)))
        except (TypeError, ValueError):
            continue
    return json.dumps(dict(items))


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Decode one pipeline_runs row into an API-shaped dict."""
    raw_stages: Any = row["stages_json"]
    try:
        stages: Any = json.loads(raw_stages) if isinstance(raw_stages, str) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        stages = {}
    return {
        "id": int(row["id"]),
        "started_ts": float(row["started_ts"]),
        "duration_ms": round(float(row["duration_ms"]), 2),
        "user_id": row["user_id"],
        "channel_id": row["channel_id"],
        "halted": bool(row["halted"]),
        "halt_reason": row["halt_reason"],
        "responded": bool(row["responded"]),
        "stage_count": int(row["stage_count"]),
        # dict for per-stage latency charts; tolerate legacy/list payloads
        "stages": stages if isinstance(stages, dict) else {},
        "error": row["error"],
    }


# --- Entry ---


def record_pipeline_run(store: Any, run: dict[str, Any]) -> bool:
    """Insert one completed pipeline run. Returns True on success.

    Expected keys: started_ts, duration_ms, user_id, channel_id, halted,
    halt_reason, responded, stage_count, stage_timings (dict), error.
    Missing keys fall back to safe defaults; only started_ts/duration_ms are
    required for a meaningful row.
    """
    try:
        cursor: sqlite3.Cursor = store.conn.cursor()
        cursor.execute(
            """
            INSERT INTO pipeline_runs
                (started_ts, duration_ms, user_id, channel_id,
                 halted, halt_reason, responded, stage_count,
                 stages_json, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                float(run.get("started_ts", time.time())),
                float(run.get("duration_ms", 0.0)),
                run.get("user_id"),
                run.get("channel_id"),
                1 if run.get("halted") else 0,
                str(run.get("halt_reason", "") or ""),
                1 if run.get("responded") else 0,
                int(run.get("stage_count", 0)),
                _stages_json(run.get("stage_timings", {}) or {}),
                str(run.get("error", "") or ""),
            ),
        )
        store.conn.commit()
        return True
    except Exception as e:
        logger.error("Error recording pipeline run metrics: %s", e)
        return False


def load_recent_pipeline_runs(
    store: Any,
    limit: int = 200,
    since_ts: float | None = None,
) -> list[dict[str, Any]]:
    """Return up to ``limit`` runs, newest first, optionally since a timestamp.

    A failing read returns [] — the panel renders "no data" rather than 500.
    """
    try:
        cursor: sqlite3.Cursor = store.conn.cursor()
        if since_ts is not None:
            cursor.execute(
                """
                SELECT * FROM pipeline_runs WHERE started_ts >= ?
                ORDER BY started_ts DESC LIMIT ?
                """,
                (float(since_ts), int(limit)),
            )
        else:
            cursor.execute(
                "SELECT * FROM pipeline_runs ORDER BY started_ts DESC LIMIT ?",
                (int(limit),),
            )
        rows: list[sqlite3.Row] = cursor.fetchall()
    except Exception as e:
        logger.error("Error loading pipeline run metrics: %s", e)
        return []
    decoded: list[dict[str, Any]] = []
    for row in rows:
        try:
            decoded.append(_row_to_dict(row))
        except (KeyError, TypeError, ValueError):
            logger.debug("Skipping malformed pipeline_runs row: %r", tuple(row))
    return decoded


def summarize_pipeline_runs(
    store: Any,
    window_s: float = 3600.0,
) -> dict[str, Any]:
    """Aggregate stats over the last ``window_s`` seconds for the panel header."""
    since = time.time() - float(window_s)
    runs = load_recent_pipeline_runs(store, limit=10_000, since_ts=since)
    total = len(runs)
    halted = sum(1 for r in runs if r["halted"])
    durations = sorted(r["duration_ms"] for r in runs)
    summary: dict[str, Any] = {
        "window_s": float(window_s),
        "total_runs": total,
        "halted": halted,
        "halt_rate": round(halted / total, 4) if total else 0.0,
        "responded": sum(1 for r in runs if r["responded"]),
        "avg_duration_ms": None,
        "p50_duration_ms": None,
        "p95_duration_ms": None,
        "max_duration_ms": None,
        "slowest_stage": None,
    }
    if durations:
        mid = len(durations) // 2
        p95_idx = min(len(durations) - 1, int(len(durations) * 0.95))
        summary["avg_duration_ms"] = round(sum(durations) / len(durations), 2)
        summary["p50_duration_ms"] = round(durations[mid], 2)
        summary["p95_duration_ms"] = round(durations[p95_idx], 2)
        summary["max_duration_ms"] = round(durations[-1], 2)
    # Slowest stage across the window (mean per stage name).
    stage_totals: dict[str, float] = {}
    stage_counts: dict[str, int] = {}
    for r in runs:
        for name, ms in r["stages"].items():
            stage_totals[name] = stage_totals.get(name, 0.0) + float(ms)
            stage_counts[name] = stage_counts.get(name, 0) + 1
    if stage_totals:
        means = {
            name: total / stage_counts[name] for name, total in stage_totals.items()
        }
        slowest = max(means.items(), key=lambda kv: kv[1])
        summary["slowest_stage"] = {
            "name": slowest[0],
            "avg_ms": round(slowest[1], 2),
        }
    return summary


def prune_pipeline_runs(store: Any, max_age_s: float = 7 * 86400.0) -> int:
    """Delete runs older than ``max_age_s`` (default 7 days). Returns deleted count.

    Called opportunistically from the metrics route (cheap DELETE with the
    started_ts index); also safe to call from any maintenance sweep.
    """
    try:
        cursor: sqlite3.Cursor = store.conn.cursor()
        cutoff = time.time() - float(max_age_s)
        cursor.execute("DELETE FROM pipeline_runs WHERE started_ts < ?", (cutoff,))
        deleted: int = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        store.conn.commit()
        return deleted
    except Exception as e:
        logger.error("Error pruning pipeline run metrics: %s", e)
        return 0


def delete_all_pipeline_runs(store: Any) -> int:
    """Wipe every pipeline_runs row (panel's explicit confirm-gated prune)."""
    try:
        cursor: sqlite3.Cursor = store.conn.cursor()
        cursor.execute("DELETE FROM pipeline_runs")
        deleted: int = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        store.conn.commit()
        return deleted
    except Exception as e:
        logger.error("Error deleting all pipeline run metrics: %s", e)
        return 0


# --- Core ---
# (entry functions above)

# --- Errors ---
# (none — all failures log and degrade to empty/False/0)
