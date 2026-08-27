"""Self-generated goals routes - control-panel view of Growth state.

Reads the goals + goal_evidence tables (edge-A writes from GoalsEngine).
The store is resolved from bot_state['memory_system'] (duck-typed: anything
with .conn) so the panel never constructs storage. The GoalsEngine (when
present in bot_state) supplies the same stats() the maintenance loop uses,
otherwise the rows are read directly from the store.

# --- Imports ---
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from serin.d1_3_state_core.d2_5_state_conversation.d3_4_goals_engine import (
    REVIEW_INTERVAL_S,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    bot_state,
)

# --- Types ---
# (none)

# --- Constants ---
_MAX_LIMIT: int = 200


# --- Helpers ---


def _goals_store() -> Any | None:
    """Resolve the duck-typed store for goals, or None."""
    memory = bot_state.get("memory_system")
    if memory is not None and hasattr(memory, "conn"):
        return memory
    return None


def _goals_engine() -> Any | None:
    """Resolve the live GoalsEngine from bot_state, or None."""
    return bot_state.get("goals_engine")


# --- Entry ---


def register_goal_routes(app: FastAPI, bot_state: dict[str, Any]) -> None:

    @app.get("/api/goals")
    async def get_goals(limit: int = 50, include_terminal: bool = True) -> Any:
        """All goals newest-first, plus a status histogram and live stats.

        `limit` caps the returned rows; `include_terminal` toggles
        ACHIEVED/DROPPED/SUPERSEDED rows. Mirrors the maintenance
        review surface so the panel and the bot agree on the world.
        """
        limit = max(1, min(int(limit), _MAX_LIMIT))
        store = _goals_store()
        if store is None:
            return {
                "goals": [],
                "counts": {},
                "stats": None,
                "reason": "no sqlite-backed memory_system registered",
            }
        engine = _goals_engine()
        if engine is not None:
            stats = engine.stats()
        else:
            stats = None
        # Local import keeps the panel decoupled from storage at module load.
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage.d6_1_goals_store import (
            count_goals_by_status,
            load_all_goals,
        )

        rows = load_all_goals(store, limit=limit, include_terminal=bool(include_terminal))
        counts = count_goals_by_status(store)
        return {
            "goals": rows,
            "counts": counts,
            "stats": stats,
            "review_interval_s": (REVIEW_INTERVAL_S if engine is not None else None),
        }


# --- Core ---
# (routes above)

# --- Errors ---
# (none)
