from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from fastapi import FastAPI

from serin.d1_4_config_base.d2_3_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_1_state_access import (
    make_json_safe,
)

_background_tasks: set[asyncio.Task[Any]] = set()


def register_ops_routes(app: FastAPI, bot_state: dict[str, Any]) -> None:
    @app.post("/api/crawler/trigger-sync")
    async def trigger_manual_sync() -> Any:
        crawler = bot_state.get("message_crawler")
        if not crawler:
            return {"success": False, "error": "Crawler not initialized"}
        try:
            task = asyncio.create_task(_run_manual_sync(crawler))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
            return {"success": True, "message": "Sync started"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/crawler/status")
    async def get_crawler_status() -> Any:
        crawler = bot_state.get("message_crawler")
        if not crawler:
            return {"status": "disabled"}
        try:
            return make_json_safe(crawler.get_stats())
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/background/queue")
    async def get_background_queue() -> Any:
        bg = bot_state.get("background_processor")
        if not bg:
            return {"size": 0, "is_running": False}
        return {"size": len(getattr(bg, "processing_queue", []) or []), "is_running": getattr(bg, "is_running", False)}

    @app.post("/api/background/clear-queue")
    async def clear_background_queue() -> Any:
        bg = bot_state.get("background_processor")
        if not bg:
            return {"success": False, "error": "Not initialized"}
        try:
            q = getattr(bg, "processing_queue", None)
            cleared = 0
            if q and isinstance(q, list):
                cleared = len(q)
                q.clear()
            elif q and hasattr(q, "qsize"):
                cleared = q.qsize()
                while not q.empty():
                    try:
                        q.get_nowait()
                    except Exception:
                        break
            return {"success": True, "cleared": cleared}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/logs/recent")
    async def get_recent_logs() -> Any:
        try:
            log_paths = ["serin/logs/serin_ai.log", "bot.log"]
            for log_file in log_paths:
                if os.path.exists(log_file):
                    with open(log_file) as f:
                        lines = f.readlines()[-100:]
                    return {"logs": [ln.rstrip() for ln in lines], "source": log_file}
            return {"logs": [], "source": None}
        except Exception as e:
            return {"error": str(e), "logs": []}

    @app.get("/api/db/health")
    async def get_db_health() -> Any:
        mem = bot_state.get("memory_system")
        if not mem:
            return {"status": "unavailable"}
        try:
            cursor = mem.conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            integrity = cursor.fetchone()[0]
            cursor.execute("PRAGMA page_count")
            pages = cursor.fetchone()[0]
            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]
            cursor.execute("PRAGMA freelist_count")
            freelist = cursor.fetchone()[0]
            db_size_mb = round((pages * page_size) / (1024 * 1024), 2)
            free_mb = round((freelist * page_size) / (1024 * 1024), 2)
            return {"integrity": integrity, "size_mb": db_size_mb, "free_space_mb": free_mb, "journal_mode": "WAL", "path": getattr(mem, "db_path", "unknown")}
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/bot/restart")
    async def restart_bot() -> Any:
        try:
            from serin.d1_5_ops_tooling.d2_3_hot_reloader import SIGNAL_FILE
            open(SIGNAL_FILE, "w").close()
            logger.warning("Restart signal sent to hot-reloader")
            return {"success": True, "message": "Restart signal sent"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/bot/uptime")
    async def get_uptime() -> Any:
        start_time = bot_state.get("start_time")
        if not start_time:
            return {"uptime_seconds": 0}
        return {"uptime_seconds": round(time.time() - start_time, 1)}

async def _run_manual_sync(crawler: Any) -> None:
    try:
        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_1_state_access import (
            bot_state as _bs,
        )
        client = _bs.get("discord_client")
        if not client:
            return
        synced_count = 0
        for guild in client.guilds:
            for channel in guild.text_channels:
                try:
                    synced = await crawler._quick_sync_channel(channel)
                    synced_count += synced
                except Exception as e:
                    logger.debug("Channel sync failed for %s: %s", channel.name, e)
        logger.info("Manual sync complete: %d messages", synced_count)
    except Exception as e:
        logger.error("Error in manual sync: %s", e)
