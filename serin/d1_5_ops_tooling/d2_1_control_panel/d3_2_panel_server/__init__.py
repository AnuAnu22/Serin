import logging

from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_1_state_access import (
    ChannelControl,
    MemoryQuery,
    MemorySearchAdvanced,
    ModelConfig,
    MoodUpdate,
    SettingsUpdate,
    VoiceChannelControl,
    VoiceLoad,
    active_websockets,
    app,
    bot_state,
    get_gpu_vram_usage,
    get_request_metrics,
    make_json_safe,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_2_server_controls import (
    get_allowed_channels,
    get_full_config,
    get_model_info,
    load_model,
    start_background_processor,
    stop_background_processor,
    update_allowed_channels,
    update_full_config,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import (
    get_performance_metrics,
    get_pipeline_status,
    get_stats,
    get_status,
    get_system_health,
    homepage,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_5_server_websocket import (
    broadcast_event,
    broadcast_log,
    websocket_endpoint,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_6_memory_routes import (
    register_memory_routes,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_personality_routes import (
    register_personality_routes,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_8_ops_routes import (
    register_ops_routes,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_9_missing_routes import (
    register_missing_routes,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_10_test_routes import (
    register_test_routes,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_11_debug_routes import (
    register_debug_routes,
)

_logger = logging.getLogger("control_panel")

try:
    register_memory_routes(app, bot_state)
    _logger.info("Registered: memory routes")
except Exception as e:
    _logger.error("FAILED to register memory routes: %s", e)

try:
    register_personality_routes(app, bot_state)
    _logger.info("Registered: personality routes")
except Exception as e:
    _logger.error("FAILED to register personality routes: %s", e)

try:
    register_ops_routes(app, bot_state)
    _logger.info("Registered: ops routes")
except Exception as e:
    _logger.error("FAILED to register ops routes: %s", e)

try:
    register_missing_routes(app, bot_state)
    _logger.info("Registered: missing routes")
except Exception as e:
    _logger.error("FAILED to register missing routes: %s", e)

try:
    register_test_routes(app, bot_state)
    _logger.info("Registered: test routes")
except Exception as e:
    _logger.error("FAILED to register test routes: %s", e)

try:
    register_debug_routes(app, bot_state)
    _logger.info("Registered: debug routes")
except Exception as e:
    _logger.error("FAILED to register debug routes: %s", e)

# d4_4_server_status.py is imported for its module-level side effects
try:
    exec(
        "from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import d4_4_server_status"
    )
    _logger.info("d4_4_server_status imported OK")
except Exception as e:
    _logger.debug("d4_4_server_status not importable: %s", e)

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
    "MemorySearchAdvanced",
    "MoodUpdate",
    "app",
    "get_gpu_vram_usage",
    "get_request_metrics",
    "websocket_endpoint",
    "broadcast_log",
    "broadcast_event",
    "homepage",
    "get_status",
    "get_stats",
    "get_system_health",
    "get_performance_metrics",
    "get_pipeline_status",
    "get_model_info",
    "load_model",
    "start_background_processor",
    "stop_background_processor",
    "get_allowed_channels",
    "update_allowed_channels",
    "get_full_config",
    "update_full_config",
]
