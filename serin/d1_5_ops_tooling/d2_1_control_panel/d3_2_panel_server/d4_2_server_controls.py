"""Model, background-processor, and channel-control routes for the control panel."""

from __future__ import annotations

from typing import Any

from serin.d1_3_state_core.d2_5_core_logger import logger
from serin.d1_4_config_base.d2_1_base_config import config
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import (
    app,
    bot_state,
)


@app.get("/api/model")
async def get_model_info() -> Any:
    """Return active vLLM model info"""
    try:
        from serin.d1_3_state_core.d2_3_model_system.d3_3_system_factory import (
            get_model_connector,
        )
        connector = get_model_connector()
        # Lazy load to ensure info is available
        if getattr(connector, 'client', None) is None:
            connector.load_model()
        return connector.get_model_info()
    except Exception as e:
        logger.error(f" Error getting model info: {e}")
        return {'error': str(e)}


@app.post("/api/background/start")
async def start_background_processor() -> Any:
    """Start background processor"""
    try:
        bg = bot_state['background_processor']
        if bg:
            await bg.start()
            return {'success': True}
        return {'success': False, 'error': 'Background processor not initialized'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.post("/api/background/stop")
async def stop_background_processor() -> Any:
    """Stop background processor"""
    try:
        bg = bot_state['background_processor']
        if bg:
            await bg.stop()
            return {'success': True}
        return {'success': False, 'error': 'Background processor not initialized'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.get("/api/channels/allowed")
async def get_allowed_channels() -> Any:
    """Get list of allowed channels"""
    try:
        return {
            'channels': [str(cid) for cid in config.ALLOWED_CHANNEL_IDS]
        }
    except Exception as e:
        return {'error': str(e)}
