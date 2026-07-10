"""Web Server - Control Panel for Serin Bot.

FastAPI-based web interface for complete bot control. This package is the
folder form of the former ``server.py`` (Rule 2: a file over 500 lines becomes
a folder). Shared state, the FastAPI ``app`` and the pydantic models live in
``state`` and are re-exported here; the route handlers live in the ``websocket``,
``status`` and ``controls`` submodules and register themselves on ``app`` when
imported. Existing import paths (``from ...control_panel.server import ...``)
keep working unchanged.
"""

from __future__ import annotations

from typing import Any, cast

from serin.d1_5_ops_tooling.control_panel.panels.panel_control import (
    register_control_routes,
)
from serin.d1_5_ops_tooling.control_panel.panels.panel_voice import (
    register_voice_routes,
)
from serin.d1_5_ops_tooling.control_panel.routes import register_enhanced_routes
from serin.d1_5_ops_tooling.control_panel.server.state import (
    ChannelControl,
    MemoryQuery,
    ModelConfig,
    SettingsUpdate,
    VoiceChannelControl,
    VoiceLoad,
    active_websockets,
    app,
    bot_state,
    get_gpu_vram_usage,
    make_json_safe,
)

from .controls import (
    get_allowed_channels,
    get_model_info,
    start_background_processor,
    stop_background_processor,
)
from .status import (
    get_current_stats,
    get_stats,
    get_status,
    get_system_health,
    homepage,
)
from .websocket import broadcast_event, broadcast_log, websocket_endpoint

__all__ = [
    "make_json_safe",
    "bot_state",
    "active_websockets",
    "ModelConfig",
    "ChannelControl",
    "VoiceChannelControl",
    "VoiceLoad",
    "SettingsUpdate",
    "MemoryQuery",
    "app",
    "get_gpu_vram_usage",
    "websocket_endpoint",
    "broadcast_log",
    "broadcast_event",
    "homepage",
    "get_status",
    "get_stats",
    "get_system_health",
    "get_current_stats",
    "get_model_info",
    "start_background_processor",
    "stop_background_processor",
    "get_allowed_channels",
]

register_enhanced_routes(app, bot_state, broadcast_event)

register_control_routes(cast(Any, app))
register_voice_routes(cast(Any, app))
