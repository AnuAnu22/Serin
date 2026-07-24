from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from serin.d1_4_config_base.d2_3_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    bot_state,
    make_json_safe,
)


def register_voice_memory_routes(app: FastAPI) -> None:

    @app.get("/api/voice/memory")
    async def get_voice_memory() -> Any:
        mem = bot_state.get("memory_system")
        if not mem:
            return {"memories": []}
        try:
            cursor = mem.conn.cursor()
            cursor.execute(
                "SELECT * FROM recent_messages "
                "ORDER BY timestamp DESC LIMIT 50"
            )
            rows = [dict(row) for row in cursor.fetchall()]
            return {"memories": make_json_safe(rows)}
        except Exception as e:
            logger.debug("recent_messages query failed: %s", e)
            return {"error": str(e), "memories": []}

    @app.get("/api/voice/memory/stats")
    async def get_voice_memory_stats() -> Any:
        mem = bot_state.get("memory_system")
        if not mem:
            return {"total": 0}
        try:
            cursor = mem.conn.cursor()
            cursor.execute("SELECT COUNT(*) as c FROM recent_messages")
            total = cursor.fetchone()["c"]
            cursor.execute(
                "SELECT COUNT(DISTINCT user_id) as c FROM recent_messages"
            )
            users = cursor.fetchone()["c"]
            return {"total_messages": total, "unique_users": users}
        except Exception as e:
            logger.debug("recent_messages stats query failed: %s", e)
            return {"error": str(e)}
