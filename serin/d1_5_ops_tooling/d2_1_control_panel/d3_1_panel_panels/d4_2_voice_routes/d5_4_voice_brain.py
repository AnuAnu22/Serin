from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from serin.d1_4_config_base.d2_1_base_config import config
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    SettingsUpdate,
    bot_state,
    make_json_safe,
)

ALLOWED_CONFIG_KEYS = {
    "DEBUG_MODE", "TRACE_MESSAGES", "MAINTENANCE_INTERVAL_HOURS",
    "ENABLE_VOICE", "ENABLE_TTS", "LLM_BASE_URL", "LLM_MODEL",
}


def register_voice_brain_routes(app: FastAPI) -> None:

    @app.get("/api/brain/state")
    async def get_brain_state() -> Any:
        manager = bot_state.get("message_manager")
        if not manager:
            return {"status": "OFFLINE"}
        return make_json_safe(getattr(manager, "current_state", {"status": "ONLINE"}))

    @app.post("/api/brain/abort")
    async def abort_generation() -> Any:
        manager = bot_state.get("message_manager")
        if not manager:
            return {"success": False, "error": "Manager not initialized"}
        try:
            if hasattr(manager, "abort_current_generation"):
                manager.abort_current_generation()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/emergency-stop")
    async def emergency_stop() -> Any:
        return await abort_generation()

    @app.get("/api/system_prompt")
    async def get_system_prompt() -> Any:
        manager = bot_state.get("message_manager")
        if not manager:
            return {"prompt": ""}
        return {"prompt": getattr(manager, "system_prompt", "")}

    @app.post("/api/system_prompt")
    async def update_system_prompt(data: dict[str, str]) -> Any:
        manager = bot_state.get("message_manager")
        if not manager:
            return {"success": False, "error": "Manager not initialized"}
        new_prompt = data.get("prompt")
        if new_prompt and len(new_prompt) <= 50000:
            manager.system_prompt = new_prompt
            return {"success": True}
        return {"success": False, "error": "No prompt provided or too long"}

    @app.get("/api/settings")
    async def get_settings() -> Any:
        try:
            return make_json_safe(config.to_dict())
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/settings")
    async def update_settings(update: SettingsUpdate) -> Any:
        try:
            if update.setting_key not in ALLOWED_CONFIG_KEYS:
                return {"success": False, "error": f"Key not allowed: {update.setting_key}"}
            config.update_from_dict({update.setting_key: update.setting_value})
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

