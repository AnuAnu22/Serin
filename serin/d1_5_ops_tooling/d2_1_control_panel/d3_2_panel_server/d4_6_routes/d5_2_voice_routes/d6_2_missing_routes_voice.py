"""
Missing Voice Routes
--------------------
Voice, audio, and voice-profile API routes for the control panel.
Extracted from d4_9_missing_routes.py to keep files under 500 lines.
"""
# --- Imports ---
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI

from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    make_json_safe,
)

_logger = logging.getLogger("control_panel")

# --- Types ---
# (none)

# --- Constants ---
# (none)

# --- Entry ---


def _register_voice_routes(app: FastAPI, bot_state: dict[str, Any], existing_paths: set[str]) -> None:
    """Register voice, audio, and voice-profile API routes."""
    if "/api/voice/join" not in existing_paths:
        @app.post("/api/voice/join")
        async def join_voice(data: dict[str, Any]) -> dict[str, Any]:
            guild_id = data.get("guild_id", "")
            channel_id = data.get("channel_id", "")
            if not guild_id or not channel_id:
                return {"success": False, "error": "guild_id and channel_id required"}
            listener = bot_state.get("voice_listener")
            if not listener:
                return {"success": False, "error": "Voice listener not initialized"}
            try:
                result = await listener.join_channel(int(guild_id), int(channel_id))
                return {"success": bool(result)}
            except Exception as e:
                _logger.error("Voice join failed: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/voice/leave" not in existing_paths:
        @app.post("/api/voice/leave")
        async def leave_voice(data: dict[str, Any]) -> dict[str, Any]:
            guild_id = data.get("guild_id", "")
            if not guild_id:
                return {"success": False, "error": "guild_id required"}
            listener = bot_state.get("voice_listener")
            if not listener:
                return {"success": False, "error": "Voice listener not initialized"}
            try:
                result = await listener.leave_channel(int(guild_id))
                return {"success": bool(result)}
            except Exception as e:
                _logger.error("Voice leave failed: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/voice/status" not in existing_paths:
        @app.get("/api/voice/status")
        async def get_voice_status() -> Any:
            try:
                listener = bot_state.get("voice_listener")
                if not listener:
                    return {"connected": False, "is_in_voice": False}
                if hasattr(listener, "get_status"):
                    return make_json_safe(listener.get_status())
                return {"connected": getattr(listener, "is_connected", lambda: False)(), "guild_id": getattr(listener, "guild_id", None), "channel_id": getattr(listener, "channel_id", None), "is_in_voice": getattr(listener, "is_in_voice", lambda: False)()}
            except Exception as e:
                _logger.error("Error in /api/voice/status: %s", e)
                return {"error": str(e)}

    if "/api/voice/files" not in existing_paths:
        @app.get("/api/voice/files")
        async def get_voice_files() -> Any:
            try:
                voices_dir = "tts/voices"
                if not os.path.isdir(voices_dir):
                    return {"voices": []}
                files = [f for f in os.listdir(voices_dir) if os.path.isfile(os.path.join(voices_dir, f))]
                return {"voices": files}
            except Exception as e:
                _logger.error("Error in /api/voice/files: %s", e)
                return {"error": str(e), "voices": []}

    if "/api/voice/load" not in existing_paths:
        @app.post("/api/voice/load")
        async def load_voice_file(data: dict[str, Any]) -> Any:
            try:
                filename = data.get("filename", "")
                if not filename:
                    return {"success": False, "error": "filename required"}
                vm = bot_state.get("voice_manager") or bot_state.get("tts_engine")
                if not vm:
                    return {"success": False, "error": "Voice manager not initialized"}
                if hasattr(vm, "load_voice"):
                    tts = bot_state.get("tts_engine")
                    vm.load_voice(tts, filename)
                elif hasattr(vm, "set_voice_reference"):
                    vm.set_voice_reference(filename)
                return {"success": True}
            except Exception as e:
                _logger.error("Error in /api/voice/load: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/voice/clear" not in existing_paths:
        @app.post("/api/voice/clear")
        async def clear_voice() -> Any:
            try:
                vm = bot_state.get("voice_manager") or bot_state.get("tts_engine")
                if vm and hasattr(vm, "clear_voice_reference"):
                    vm.clear_voice_reference()
                return {"success": True}
            except Exception as e:
                _logger.error("Error in /api/voice/clear: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/voice/channels" not in existing_paths:
        @app.get("/api/voice/channels")
        async def get_voice_channels() -> Any:
            try:
                client = bot_state.get("discord_client")
                if not client or not client.guilds:
                    return {"channels": []}
                channels = []
                for guild in client.guilds:
                    for vc in guild.voice_channels:
                        channels.append({"guild_id": str(guild.id), "guild_name": guild.name, "channel_id": str(vc.id), "channel_name": vc.name, "member_count": len(vc.members)})
                return {"channels": channels}
            except Exception as e:
                _logger.error("Error in /api/voice/channels: %s", e)
                return {"error": str(e), "channels": []}

    if "/api/voice/leave-all" not in existing_paths:
        @app.post("/api/voice/leave-all")
        async def leave_all_voice_channels() -> Any:
            try:
                listener = bot_state.get("voice_listener")
                if listener and hasattr(listener, "leave_all_channels"):
                    await listener.leave_all_channels()
                return {"success": True}
            except Exception as e:
                _logger.error("Error in /api/voice/leave-all: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/audio/settings" not in existing_paths:
        @app.get("/api/audio/settings")
        async def get_audio_settings() -> Any:
            try:
                listener = bot_state.get("voice_listener")
                if not listener:
                    return {"vad_threshold": 0.5, "silence_threshold": 0.5, "transcription_enabled": True}
                ap = getattr(listener, "audio_processor", None) or listener
                return {"vad_threshold": getattr(ap, "vad_threshold", 0.5), "silence_threshold": getattr(ap, "silence_threshold", 0.5), "transcription_enabled": getattr(ap, "transcription_enabled", True)}
            except Exception as e:
                _logger.error("Error in /api/audio/settings: %s", e)
                return {"error": str(e)}

    if "/api/audio/settings/update" not in existing_paths:
        @app.post("/api/audio/settings/update")
        async def update_audio_settings(data: dict[str, Any]) -> Any:
            try:
                listener = bot_state.get("voice_listener")
                if not listener:
                    return {"success": False, "error": "Voice listener not initialized"}
                ap = getattr(listener, "audio_processor", None) or listener
                for key in ("vad_threshold", "silence_threshold", "transcription_enabled"):
                    if key in data:
                        setattr(ap, key, data[key])
                return {"success": True}
            except Exception as e:
                _logger.error("Error in /api/audio/settings/update: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/audio/speakers" not in existing_paths:
        @app.get("/api/audio/speakers")
        async def get_audio_speakers() -> Any:
            try:
                listener = bot_state.get("voice_listener")
                if not listener or not hasattr(listener, "get_active_speakers"):
                    return {"speakers": []}
                return {"speakers": make_json_safe(listener.get_active_speakers())}
            except Exception as e:
                _logger.error("Error in /api/audio/speakers: %s", e)
                return {"error": str(e), "speakers": []}

    if "/api/audio/stats" not in existing_paths:
        @app.get("/api/audio/stats")
        async def get_audio_stats() -> Any:
            try:
                listener = bot_state.get("voice_listener")
                if listener and hasattr(listener, "get_stats"):
                    return make_json_safe(listener.get_stats())
                return {}
            except Exception as e:
                _logger.error("Error in /api/audio/stats: %s", e)
                return {"error": str(e)}

    if "/api/voice/behavior/settings" not in existing_paths:
        @app.get("/api/voice/behavior/settings")
        async def get_voice_behavior_settings() -> Any:
            try:
                vbm = bot_state.get("voice_behavior_manager")
                if vbm and hasattr(vbm, "get_settings"):
                    return make_json_safe(vbm.get_settings())
                return {"join_aggressiveness": 50, "leave_after_silence": 30, "max_session_duration": 60}
            except Exception as e:
                _logger.error("Error in /api/voice/behavior/settings: %s", e)
                return {"error": str(e)}

    if "/api/voice/behavior/settings" not in existing_paths:
        @app.post("/api/voice/behavior/settings")
        async def update_voice_behavior_settings(data: dict[str, Any]) -> Any:
            try:
                vbm = bot_state.get("voice_behavior_manager")
                if not vbm:
                    return {"success": False, "error": "Voice behavior manager not initialized"}
                if hasattr(vbm, "update_settings"):
                    vbm.update_settings(data)
                else:
                    for key in ("join_aggressiveness", "leave_after_silence", "max_session_duration"):
                        if key in data:
                            setattr(vbm, key, data[key])
                return {"success": True}
            except Exception as e:
                _logger.error("Error in voice behavior settings update: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/voice/behavior/stats" not in existing_paths:
        @app.get("/api/voice/behavior/stats")
        async def get_voice_behavior_stats() -> Any:
            try:
                vbm = bot_state.get("voice_behavior_manager")
                if vbm and hasattr(vbm, "get_stats"):
                    return make_json_safe(vbm.get_stats())
                return {"auto_joins": 0, "auto_leaves": 0, "rejected_joins": 0}
            except Exception as e:
                _logger.error("Error in /api/voice/behavior/stats: %s", e)
                return {"error": str(e)}

    if "/api/voice-profiles/list" not in existing_paths:
        @app.get("/api/voice-profiles/list")
        async def list_voice_profiles() -> Any:
            try:
                try:
                    from serin.d1_3_state_core.voice.voice_profiles import (
                        get_voice_profiles,
                    )
                    profiles = get_voice_profiles()
                except Exception:
                    profiles = []
                return {"profiles": make_json_safe(profiles)}
            except Exception as e:
                _logger.error("Error in /api/voice-profiles/list: %s", e)
                return {"error": str(e), "profiles": []}

    if "/api/voice-profiles/set-active" not in existing_paths:
        @app.post("/api/voice-profiles/set-active")
        async def set_active_voice_profile(data: dict[str, Any]) -> Any:
            try:
                name = data.get("name", data.get("profile_name", ""))
                if not name:
                    return {"success": False, "error": "Profile name required"}
                try:
                    from serin.d1_3_state_core.voice.voice_profiles import (
                        set_active_profile,
                    )
                    set_active_profile(name)
                except Exception as e:
                    _logger.error("Error setting active voice profile %s: %s", name, e)
                    return {"success": False, "error": str(e)}
                return {"success": True}
            except Exception as e:
                _logger.error("Error in voice-profiles set-active: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/voice-profiles/create" not in existing_paths:
        @app.post("/api/voice-profiles/create")
        async def create_voice_profile(data: dict[str, Any]) -> Any:
            try:
                name = data.get("name", "")
                if not name:
                    return {"success": False, "error": "Name required"}
                try:
                    from serin.d1_3_state_core.voice.voice_profiles import (
                        create_voice_profile,
                    )
                    create_voice_profile(name=name, speed=data.get("speed", 1.0), temperature=data.get("temperature", 0.7), description=data.get("description", ""))
                except Exception as e:
                    _logger.error("Error creating voice profile %s: %s", name, e)
                    return {"success": False, "error": str(e)}
                return {"success": True}
            except Exception as e:
                _logger.error("Error in voice-profiles create: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/voice-profiles/delete" not in existing_paths:
        @app.post("/api/voice-profiles/delete")
        async def delete_voice_profile(data: dict[str, Any]) -> Any:
            try:
                name = data.get("name", "")
                if not name:
                    return {"success": False, "error": "Name required"}
                try:
                    from serin.d1_3_state_core.voice.voice_profiles import (
                        delete_voice_profile,
                    )
                    delete_voice_profile(name)
                except Exception as e:
                    _logger.error("Error deleting voice profile %s: %s", name, e)
                    return {"success": False, "error": str(e)}
                return {"success": True}
            except Exception as e:
                _logger.error("Error in voice-profiles delete: %s", e)
                return {"success": False, "error": str(e)}

# --- Core ---
# (none)

# --- Helpers ---
# (none)

# --- Errors ---
# (none)
