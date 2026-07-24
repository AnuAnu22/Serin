from __future__ import annotations

import logging
import os
from typing import Any

from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_1_state_access import (
    make_json_safe,
)

_logger = logging.getLogger("control_panel")


def register_missing_routes(app: Any, bot_state: dict[str, Any]) -> None:
    existing_paths = {r.path for r in app.routes}

    # ── Mood ──
    if "/api/mood/current" not in existing_paths:

        @app.get("/api/mood/current")
        async def get_current_mood() -> Any:
            try:
                manager = bot_state.get("message_manager")
                if not manager:
                    return {"current_mood": "neutral", "energy_level": 0.5, "sass_level": 0.5, "engagement": 0.5, "tone_modifier": ""}
                personality = getattr(manager, "personality", manager)
                tone_modifier = ""
                if hasattr(personality, "get_tone_modifier"):
                    try:
                        tone_modifier = personality.get_tone_modifier()
                    except Exception:
                        pass
                result = {
                    "current_mood": getattr(personality, "current_mood", "neutral"),
                    "energy_level": getattr(personality, "energy_level", 0.5),
                    "sass_level": getattr(personality, "sass_level", 0.5),
                    "engagement": getattr(personality, "engagement", 0.5),
                    "tone_modifier": tone_modifier,
                }
                ps = getattr(manager, "personality_state", None) or getattr(personality, "personality_state", None)
                if ps and hasattr(ps, "to_dict"):
                    result["personality_state"] = ps.to_dict()
                elif ps and hasattr(ps, "get_history"):
                    result["mood_history_count"] = len(ps.get_history(5))
                return make_json_safe(result)
            except Exception as e:
                _logger.error("Error in /api/mood/current: %s", e)
                return {"error": str(e)}

    if "/api/mood/set" not in existing_paths:

        @app.post("/api/mood/set")
        async def set_mood(data: dict[str, Any]) -> Any:
            try:
                mood = data.get("mood", "neutral")
                manager = bot_state.get("message_manager")
                if not manager:
                    return {"success": False, "error": "Manager not initialized"}
                ps = getattr(manager, "personality_state", None) or getattr(getattr(manager, "personality", None), "personality_state", None)
                if ps and hasattr(ps, "set_mood_preset"):
                    ps.set_mood_preset(mood)
                else:
                    personality = getattr(manager, "personality", None) or manager
                    presets = {
                        "high_energy": {"energy_level": 0.9, "sass_level": 0.6, "engagement": 0.9},
                        "neutral": {"energy_level": 0.5, "sass_level": 0.5, "engagement": 0.5},
                        "sass": {"energy_level": 0.6, "sass_level": 0.9, "engagement": 0.7},
                        "cheerful": {"energy_level": 0.8, "sass_level": 0.4, "engagement": 0.8},
                        "calm": {"energy_level": 0.3, "sass_level": 0.3, "engagement": 0.5},
                        "sarcastic": {"energy_level": 0.5, "sass_level": 0.9, "engagement": 0.6},
                        "energetic": {"energy_level": 0.9, "sass_level": 0.5, "engagement": 0.9},
                    }
                    p = presets.get(mood, presets["neutral"])
                    for k, v in p.items():
                        setattr(personality, k, v)
                return {"success": True, "mood": mood}
            except Exception as e:
                _logger.error("Error in /api/mood/set: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/mood/history" not in existing_paths:

        @app.get("/api/mood/history")
        async def get_mood_history(limit: int = 50) -> Any:
            try:
                manager = bot_state.get("message_manager")
                if not manager:
                    return {"history": []}
                ps = getattr(manager, "personality_state", None) or getattr(getattr(manager, "personality", None), "personality_state", None)
                if ps and hasattr(ps, "get_history"):
                    return {"history": make_json_safe(ps.get_history(limit))}
                return {"history": []}
            except Exception as e:
                _logger.error("Error in /api/mood/history: %s", e)
                return {"error": str(e), "history": []}

    # ── Voice ──
    if "/api/voice/join" not in existing_paths:

        @app.post("/api/voice/join")
        async def join_voice(data: dict[str, Any]) -> dict:
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
        async def leave_voice(data: dict[str, Any]) -> dict:
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
                return {
                    "connected": getattr(listener, "is_connected", lambda: False)(),
                    "guild_id": getattr(listener, "guild_id", None),
                    "channel_id": getattr(listener, "channel_id", None),
                    "is_in_voice": getattr(listener, "is_in_voice", lambda: False)(),
                }
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
                        channels.append({
                            "guild_id": str(guild.id),
                            "guild_name": guild.name,
                            "channel_id": str(vc.id),
                            "channel_name": vc.name,
                            "member_count": len(vc.members),
                        })
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

    # ── TTS ──
    if "/api/tts/voice/test" not in existing_paths:

        @app.post("/api/tts/voice/test")
        async def test_tts_voice() -> Any:
            try:
                tts = bot_state.get("tts_engine")
                if tts and hasattr(tts, "synthesize"):
                    tts.synthesize("Hello, this is a test of my voice.")
                return {"success": True}
            except Exception as e:
                _logger.error("Error in /api/tts/voice/test: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/tts/voice/load" not in existing_paths:

        @app.post("/api/tts/voice/load")
        async def load_tts_voice(data: dict[str, Any]) -> Any:
            try:
                filename = data.get("filename", "")
                tts = bot_state.get("tts_engine")
                if tts and hasattr(tts, "set_voice_reference"):
                    tts.set_voice_reference(filename)
                return {"success": True}
            except Exception as e:
                _logger.error("Error in /api/tts/voice/load: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/tts/voice/clear" not in existing_paths:

        @app.post("/api/tts/voice/clear")
        async def clear_tts_voice() -> Any:
            try:
                tts = bot_state.get("tts_engine")
                if tts and hasattr(tts, "clear_voice_reference"):
                    tts.clear_voice_reference()
                return {"success": True}
            except Exception as e:
                _logger.error("Error in /api/tts/voice/clear: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/tts/test" not in existing_paths:

        @app.post("/api/tts/test")
        async def test_tts() -> Any:
            try:
                tts = bot_state.get("tts_engine")
                if tts and hasattr(tts, "synthesize"):
                    tts.synthesize("Testing TTS output.")
                return {"success": True}
            except Exception as e:
                _logger.error("Error in /api/tts/test: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/tts/voices" not in existing_paths:

        @app.get("/api/tts/voices")
        async def get_tts_voices() -> Any:
            try:
                tts = bot_state.get("tts_engine")
                voices = []
                if tts and hasattr(tts, "get_available_speakers"):
                    voices = tts.get_available_speakers()
                if not voices:
                    try:
                        import edge_tts
                        voices = [{"name": v["Name"], "short": v["ShortName"]} for v in await edge_tts.list_voices()]
                    except Exception:
                        pass
                return {"voices": make_json_safe(voices)}
            except Exception as e:
                _logger.error("Error in /api/tts/voices: %s", e)
                return {"error": str(e), "voices": []}

    if "/api/tts/current" not in existing_paths:

        @app.get("/api/tts/current")
        async def get_current_tts() -> Any:
            try:
                tts = bot_state.get("tts_engine")
                if not tts:
                    return {"model": None, "device": None, "active_profile": None, "voice_reference": None, "total_generations": 0}
                return {
                    "model": getattr(tts, "model_name", getattr(tts, "model", None)),
                    "device": getattr(tts, "device", getattr(tts, "device_id", None)),
                    "active_profile": getattr(tts, "active_profile", getattr(tts, "profile_name", None)),
                    "voice_reference": getattr(tts, "voice_reference", getattr(tts, "reference", None)),
                    "total_generations": getattr(tts, "total_generations", getattr(tts, "generation_count", 0)),
                }
            except Exception as e:
                _logger.error("Error in /api/tts/current: %s", e)
                return {"error": str(e)}

    if "/api/tts/settings/update" not in existing_paths:

        @app.post("/api/tts/settings/update")
        async def update_tts_settings(data: dict[str, Any]) -> Any:
            try:
                tts = bot_state.get("tts_engine")
                if not tts:
                    return {"success": False, "error": "TTS engine not initialized"}
                for key in ("device", "model", "speed", "temperature"):
                    if key in data:
                        setattr(tts, key, data[key])
                return {"success": True}
            except Exception as e:
                _logger.error("Error in /api/tts/settings/update: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/tts/status" not in existing_paths:

        @app.get("/api/tts/status")
        async def get_tts_status() -> Any:
            try:
                tts = bot_state.get("tts_engine")
                if not tts:
                    return {"status": "disabled", "model": None, "voice_reference": None}
                return {
                    "status": "ok",
                    "model": getattr(tts, "model_name", getattr(tts, "model", None)),
                    "voice_reference": getattr(tts, "voice_reference", getattr(tts, "reference", None)),
                    "active_profile": getattr(tts, "active_profile", getattr(tts, "profile_name", None)),
                    "device": getattr(tts, "device", getattr(tts, "device_id", None)),
                    "loaded": getattr(tts, "loaded", getattr(tts, "is_loaded", True)),
                }
            except Exception as e:
                _logger.error("Error in /api/tts/status: %s", e)
                return {"error": str(e)}

    # ── Audio ──
    if "/api/audio/settings" not in existing_paths:

        @app.get("/api/audio/settings")
        async def get_audio_settings() -> Any:
            try:
                listener = bot_state.get("voice_listener")
                if not listener:
                    return {"vad_threshold": 0.5, "silence_threshold": 0.5, "transcription_enabled": True}
                ap = getattr(listener, "audio_processor", None) or listener
                return {
                    "vad_threshold": getattr(ap, "vad_threshold", 0.5),
                    "silence_threshold": getattr(ap, "silence_threshold", 0.5),
                    "transcription_enabled": getattr(ap, "transcription_enabled", True),
                }
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

    # ── Voice Behavior ──
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

    # ── Voice Profiles ──
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
                except Exception:
                    pass
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
                    create_voice_profile(
                        name=name,
                        speed=data.get("speed", 1.0),
                        temperature=data.get("temperature", 0.7),
                        description=data.get("description", ""),
                    )
                except Exception:
                    pass
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
                except Exception:
                    pass
                return {"success": True}
            except Exception as e:
                _logger.error("Error in voice-profiles delete: %s", e)
                return {"success": False, "error": str(e)}

    # ── Enhanced / Test Connection ──
    if "/api/enhanced/test-connection" not in existing_paths:

        @app.post("/api/enhanced/test-connection")
        async def test_qdrant_connection(data: dict[str, Any]) -> dict:
            host = data.get("qdrant_host", "localhost")
            port = int(data.get("qdrant_port", 6333))
            try:
                from qdrant_client import QdrantClient
                client = QdrantClient(host=host, port=port, timeout=5)
                collections = client.get_collections().collections
                client.close()
                return {
                    "success": True,
                    "message": f"Connected to Qdrant at {host}:{port}",
                    "collections": [c.name for c in collections],
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Connection failed: {str(e)}",
                }

    # ── Background Maintenance ──
    if "/api/background/maintenance" not in existing_paths:

        @app.post("/api/background/maintenance")
        async def run_background_maintenance() -> Any:
            try:
                bg = bot_state.get("background_processor")
                if bg and hasattr(bg, "run_maintenance"):
                    await bg.run_maintenance()
                return {"success": True}
            except Exception as e:
                _logger.error("Error in background maintenance: %s", e)
                return {"success": False, "error": str(e)}

    # ── Crawler Start/Stop ──
    if "/api/crawler/start" not in existing_paths:

        @app.post("/api/crawler/start")
        async def start_crawler() -> Any:
            try:
                crawler = bot_state.get("message_crawler")
                if crawler and hasattr(crawler, "start"):
                    await crawler.start()
                return {"success": True}
            except Exception as e:
                _logger.error("Error starting crawler: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/crawler/stop" not in existing_paths:

        @app.post("/api/crawler/stop")
        async def stop_crawler() -> Any:
            try:
                crawler = bot_state.get("message_crawler")
                if crawler and hasattr(crawler, "stop"):
                    await crawler.stop()
                return {"success": True}
            except Exception as e:
                _logger.error("Error stopping crawler: %s", e)
                return {"success": False, "error": str(e)}

    if "/api/crawler/force-backfill" not in existing_paths:

        @app.post("/api/crawler/force-backfill")
        async def force_backfill(data: dict[str, Any]) -> dict:
            """Force a full re-backfill of messages."""
            crawler = bot_state.get("message_crawler")
            if not crawler:
                return {"success": False, "error": "Crawler not initialized"}
            channel_ids = data.get("channel_ids")
            limit = data.get("limit", 20000)
            try:
                results = await crawler.force_backfill(
                    channel_ids=channel_ids,
                    limit=limit,
                )
                total = sum(v for v in results.values() if isinstance(v, int))
                return {
                    "success": True,
                    "total_backfilled": total,
                    "channels": results,
                }
            except Exception as e:
                _logger.error("Force backfill failed: %s", e)
                return {"success": False, "error": str(e)}

    # ── Memory: Rebuild BM25 ──
    if "/api/memory/rebuild-bm25" not in existing_paths:

        @app.post("/api/memory/rebuild-bm25")
        async def rebuild_bm25_index() -> Any:
            try:
                mem = bot_state.get("memory_system")
                if mem and hasattr(mem, "bm25_index") and hasattr(mem.bm25_index, "rebuild"):
                    mem.bm25_index.rebuild()
                return {"success": True}
            except Exception as e:
                _logger.error("Error rebuilding BM25: %s", e)
                return {"success": False, "error": str(e)}

    _logger.info("Registered: missing routes (%d registered)", len(app.routes) - len(existing_paths))
