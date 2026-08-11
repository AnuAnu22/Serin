from __future__ import annotations

from typing import Any

from serin.d1_4_config_base.d2_1_base_config import config
from serin.d1_4_config_base.d2_3_core_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    ChannelControl,
    ModelConfig,
    app,
    bot_state,
    make_json_safe,
)

ALLOWED_CONFIG_KEYS = {
    "DEBUG_MODE", "TRACE_MESSAGES", "MAINTENANCE_INTERVAL_HOURS",
    "ENABLE_VOICE", "ENABLE_TTS", "LLM_BASE_URL", "LLM_MODEL",
}

# Sensitive keys that redirect model traffic / credentials require an explicit
# `confirm: True` flag rather than applying on a bare, unconfirmed POST.
SENSITIVE_CONFIG_KEYS = {"LLM_BASE_URL", "LLM_MODEL"}


@app.get("/api/model")
async def get_model_info() -> Any:
    try:
        from serin.d1_3_state_core.d2_3_model_system.d3_3_system_factory import (
            get_model_connector,
        )
        connector = get_model_connector()
        if getattr(connector, "client", None) is None:
            connector.load_model()
        return make_json_safe(connector.get_model_info())
    except Exception as e:
        logger.error("Error getting model info: %s", e)
        return {"error": str(e)}


@app.post("/api/model/load")
async def load_model(cfg: ModelConfig) -> Any:
    try:
        from serin.d1_3_state_core.d2_3_model_system.d3_3_system_factory import (
            get_model_connector,
        )
        connector = get_model_connector(cfg.model_name)
        connector.load_model()
        if cfg.make_active:
            logger.info("Model switched to: %s", cfg.model_name)
        return {"success": True, "model": cfg.model_name}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/background/start")
async def start_background_processor() -> Any:
    try:
        bg = bot_state.get("background_processor")
        if bg:
            await bg.start()
            return {"success": True}
        return {"success": False, "error": "Background processor not initialized"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/background/stop")
async def stop_background_processor() -> Any:
    try:
        bg = bot_state.get("background_processor")
        if bg:
            await bg.stop()
            return {"success": True}
        return {"success": False, "error": "Background processor not initialized"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/channels/allowed")
async def get_allowed_channels() -> Any:
    try:
        return {"channels": [str(cid) for cid in config.ALLOWED_CHANNEL_IDS]}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/channels/allowed")
async def update_allowed_channels(control: ChannelControl) -> Any:
    try:
        channel_id = int(control.channel_id)
        if control.action == "add":
            config.ALLOWED_CHANNEL_IDS.add(channel_id)
        elif control.action == "remove":
            config.ALLOWED_CHANNEL_IDS.discard(channel_id)
        logger.info("Channel %s: %d", control.action, channel_id)
        return {"success": True, "channels": [str(c) for c in config.ALLOWED_CHANNEL_IDS]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/config")
async def get_full_config() -> Any:
    try:
        return make_json_safe(config.to_dict())
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/config")
async def update_full_config(data: dict[str, Any]) -> Any:
    try:
        confirm = bool(data.get("confirm", False))
        filtered = {k: v for k, v in data.items() if k in ALLOWED_CONFIG_KEYS}
        if not filtered:
            return {"success": False, "error": "No valid config keys provided"}
        blocked_keys = [k for k in filtered if k in SENSITIVE_CONFIG_KEYS and not confirm]
        if blocked_keys:
            return {"success": False, "blocked_keys": blocked_keys}
        config.update_from_dict(filtered)
        return {"success": True, "updated_keys": list(filtered.keys())}
    except Exception as e:
        return {"success": False, "error": str(e)}
