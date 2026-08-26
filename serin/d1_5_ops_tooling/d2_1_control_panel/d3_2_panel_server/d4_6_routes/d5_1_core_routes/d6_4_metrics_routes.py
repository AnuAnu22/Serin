"""Pipeline metrics routes — run-history + retention for the control panel.

Backed by the ``pipeline_runs`` SQLite table (edge-A writes from
``MessagePipeline.process``, recorder in ``d5_5_pipeline_metrics``).
The store is read out of ``bot_state['memory_system']`` (duck-typed:
anything with ``.conn``) so the panel never constructs storage itself.

# --- Imports ---
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, HTTPException

from serin.d1_4_config_base.d2_1_base_config import config
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    bot_state,
)

# --- Types ---
# (none)

# --- Constants ---
_MAX_HOURS: int = 24 * 30          # one month of history per query, max
_MAX_LIMIT: int = 1000
_PRUNE_CONFIRM: str = "yes"


# --- Helpers ---


def _metrics_store() -> Any | None:
    """Resolve the duck-typed store for pipeline_runs, or None."""
    memory = bot_state.get("memory_system")
    if memory is not None and hasattr(memory, "conn"):
        return memory
    return None


# --- Entry ---


def register_metrics_routes(app: FastAPI, bot_state: dict[str, Any]) -> None:

    @app.get("/api/metrics/pipeline")
    async def get_pipeline_metrics(hours: int = 24, limit: int = 200) -> Any:
        """Run history over the last ``hours`` hours, newest first.

        Returns runs plus a window summary (avg/p50/p95/max duration,
        halt rate, slowest stage) and the retention config echo.
        """
        hours = max(1, min(int(hours), _MAX_HOURS))
        limit = max(1, min(int(limit), _MAX_LIMIT))
        store = _metrics_store()
        if store is None:
            return {
                "enabled": bool(config.PIPELINE_METRICS_ENABLED),
                "runs": [],
                "summary": None,
                "reason": "no sqlite-backed memory_system registered",
            }
        # Local import keeps the panel decoupled from storage at module load.
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_5_pipeline_metrics import (
            load_recent_pipeline_runs,
            prune_pipeline_runs,
            summarize_pipeline_runs,
        )

        deleted = prune_pipeline_runs(
            store,
            max_age_s=float(config.PIPELINE_METRICS_RETENTION_DAYS) * 86400.0,
        )
        window_s = float(hours * 3600)
        summary = summarize_pipeline_runs(store, window_s=window_s)
        runs = load_recent_pipeline_runs(
            store, limit=limit, since_ts=time.time() - window_s
        )
        return {
            "enabled": bool(config.PIPELINE_METRICS_ENABLED),
            "retention_days": int(config.PIPELINE_METRICS_RETENTION_DAYS),
            "pruned": deleted,
            "summary": summary,
            "count": len(runs),
            "runs": runs,
        }

    @app.post("/api/metrics/prune")
    async def prune_pipeline_metrics(confirm: str = "") -> Any:
        """Delete ALL pipeline_runs rows. Requires ?confirm=yes (destructive)."""
        if confirm != _PRUNE_CONFIRM:
            raise HTTPException(
                status_code=400,
                detail="confirm=yes required to delete pipeline metrics",
            )
        store = _metrics_store()
        if store is None:
            return {"success": False, "error": "no sqlite-backed memory_system registered"}
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_5_pipeline_metrics import (
            delete_all_pipeline_runs,
        )

        deleted = delete_all_pipeline_runs(store)
        return {"success": True, "deleted": deleted}

# --- Core ---
# (routes above)

# --- Errors ---
# (HTTPException only for missing prune confirmation)
