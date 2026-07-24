from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import FastAPI

from serin.d1_3_state_core.d2_5_core_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_1_state_access import (
    bot_state,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_5_server_websocket import (
    broadcast_event,
)

_background_tasks: set[asyncio.Task] = set()


def register_voice_ops_routes(app: FastAPI) -> None:

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

    @app.post("/api/bot/restart")
    async def restart_bot() -> Any:
        try:
            from serin.d1_5_ops_tooling.d2_3_hot_reloader import SIGNAL_FILE
            open(SIGNAL_FILE, "w").close()
            logger.warning("Restart signal sent to hot-reloader")
            return {"success": True, "message": "Restart signal sent"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/audio/settings")
    async def get_audio_settings() -> Any:
        listener = bot_state.get("voice_listener")
        if not listener:
            return {"vad_threshold": 150, "silence_frames": 150, "transcription_enabled": True}
        ap = getattr(listener, "audio_processor", None)
        return {
            "vad_threshold": getattr(ap, "VAD_THRESHOLD", 150) if ap else 150,
            "silence_threshold": getattr(ap, "silence_threshold", 3.0) if ap else 3.0,
            "transcription_enabled": getattr(listener, "transcription_enabled", True),
        }

    @app.post("/api/audio/settings")
    async def update_audio_settings(data: dict[str, Any]) -> Any:
        listener = bot_state.get("voice_listener")
        if not listener:
            return {"success": False, "error": "Voice listener not initialized"}
        try:
            ap = getattr(listener, "audio_processor", None)
            if "vad_threshold" in data and ap:
                ap.VAD_THRESHOLD = int(data["vad_threshold"])
            if "silence_threshold" in data and ap:
                ap.silence_threshold = float(data["silence_threshold"])
            if "transcription_enabled" in data:
                listener.transcription_enabled = bool(data["transcription_enabled"])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/audio/speakers")
    async def get_active_speakers() -> Any:
        listener = bot_state.get("voice_listener")
        if not listener:
            return {"speakers": []}
        ap = getattr(listener, "audio_processor", None)
        if ap and hasattr(ap, "currently_speaking"):
            return {"speakers": list(ap.currently_speaking)}
        return {"speakers": []}


async def _run_manual_sync(crawler: Any) -> None:
    try:
        client = bot_state.get("discord_client")
        if not client:
            return
        synced_count = 0
        for guild in client.guilds:
            for channel in guild.text_channels:
                try:
                    synced = await crawler._quick_sync_channel(channel)
                    synced_count += synced
                except Exception:
                    pass
        logger.info("Manual sync complete: %d messages", synced_count)
        await broadcast_event("sync_complete", {"count": synced_count})
    except Exception as e:
        logger.error("Error in manual sync: %s", e)
