from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_6_routes.d5_2_voice_routes.d6_2_missing_routes_voice import (
    _register_voice_routes,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    make_json_safe,
)

_logger = logging.getLogger("control_panel")


def _register_mood_routes(app: FastAPI, bot_state: dict[str, Any], existing_paths: set[str]) -> None:
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
                    except Exception as e:
                        _logger.debug("get_tone_modifier failed: %s", e)
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
                personality = getattr(manager, "personality", None)
                ps = personality if (personality is not None and hasattr(personality, "set_mood_preset")) else getattr(manager, "personality_state", None)
                if ps is None and personality is not None:
                    ps = getattr(personality, "personality_state", None)
                if ps is not None and hasattr(ps, "set_mood_preset"):
                    if ps.set_mood_preset(mood) is False:
                        return {"success": False, "error": f"Unknown mood preset: {mood}"}
                    return {"success": True, "mood": mood}
                personality = getattr(manager, "personality", None) or manager
                presets = {"high_energy": {"energy_level": 0.9, "sass_level": 0.6, "engagement": 0.9}, "neutral": {"energy_level": 0.5, "sass_level": 0.5, "engagement": 0.5}, "sass": {"energy_level": 0.6, "sass_level": 0.9, "engagement": 0.7}, "cheerful": {"energy_level": 0.8, "sass_level": 0.4, "engagement": 0.8}, "calm": {"energy_level": 0.3, "sass_level": 0.3, "engagement": 0.5}, "sarcastic": {"energy_level": 0.5, "sass_level": 0.9, "engagement": 0.6}, "energetic": {"energy_level": 0.9, "sass_level": 0.5, "engagement": 0.9}}
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


# Voice routes are imported from d4_9_missing_routes_voice.py

def _register_tts_routes(app: FastAPI, bot_state: dict[str, Any], existing_paths: set[str]) -> None:
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
                    except Exception as e:
                        _logger.debug("edge_tts fallback failed: %s", e)
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
                return {"model": getattr(tts, "model_name", getattr(tts, "model", None)), "device": getattr(tts, "device", getattr(tts, "device_id", None)), "active_profile": getattr(tts, "active_profile", getattr(tts, "profile_name", None)), "voice_reference": getattr(tts, "voice_reference", getattr(tts, "reference", None)), "total_generations": getattr(tts, "total_generations", getattr(tts, "generation_count", 0))}
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
                return {"status": "ok", "model": getattr(tts, "model_name", getattr(tts, "model", None)), "voice_reference": getattr(tts, "voice_reference", getattr(tts, "reference", None)), "active_profile": getattr(tts, "active_profile", getattr(tts, "profile_name", None)), "device": getattr(tts, "device", getattr(tts, "device_id", None)), "loaded": getattr(tts, "loaded", getattr(tts, "is_loaded", True))}
            except Exception as e:
                _logger.error("Error in /api/tts/status: %s", e)
                return {"error": str(e)}


def _register_maintenance_routes(app: FastAPI, bot_state: dict[str, Any], existing_paths: set[str]) -> None:
    if "/api/enhanced/test-connection" not in existing_paths:
        @app.post("/api/enhanced/test-connection")
        async def test_qdrant_connection(data: dict[str, Any]) -> dict[str, Any]:
            host = data.get("qdrant_host", "localhost")
            port = int(data.get("qdrant_port", 6333))
            try:
                from qdrant_client import QdrantClient
                qclient = QdrantClient(host=host, port=port, timeout=5)
                collections = qclient.get_collections().collections
                qclient.close()
                return {"success": True, "message": f"Connected to Qdrant at {host}:{port}", "collections": [c.name for c in collections]}
            except Exception as e:
                return {"success": False, "message": f"Connection failed: {str(e)}"}

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
        async def force_backfill(data: dict[str, Any]) -> dict[str, Any]:
            crawler = bot_state.get("message_crawler")
            if not crawler:
                return {"success": False, "error": "Crawler not initialized"}
            channel_ids = data.get("channel_ids")
            limit = data.get("limit", 20000)
            try:
                results = await crawler.force_backfill(channel_ids=channel_ids, limit=limit)
                total = sum(v for v in results.values() if isinstance(v, int))
                return {"success": True, "total_backfilled": total, "channels": results}
            except Exception as e:
                _logger.error("Force backfill failed: %s", e)
                return {"success": False, "error": str(e)}

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


def register_missing_routes(app: FastAPI, bot_state: dict[str, Any]) -> None:
    existing_paths = {r.path for r in app.routes if hasattr(r, "path")}
    _register_mood_routes(app, bot_state, existing_paths)
    _register_voice_routes(app, bot_state, existing_paths)
    _register_tts_routes(app, bot_state, existing_paths)
    _register_maintenance_routes(app, bot_state, existing_paths)
    _logger.info("Registered: missing routes (%d registered)", len(app.routes) - len(existing_paths))
