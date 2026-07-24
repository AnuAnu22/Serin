from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    VoiceLoad,
    bot_state,
    make_json_safe,
)


def register_voice_tts_routes(app: FastAPI) -> None:

    @app.get("/api/tts/status")
    async def get_tts_status() -> Any:
        tts = bot_state.get("tts_engine")
        if not tts:
            return {"status": "disabled"}
        return make_json_safe({
            "status": "active",
            "device": getattr(tts, "device", "cpu"),
            "model": getattr(tts, "model_name", "unknown"),
            "active_profile": getattr(tts, "active_profile", "default"),
            "total_generations": getattr(tts, "total_generations", 0),
        })

    @app.post("/api/tts/test")
    async def test_tts() -> Any:
        tts = bot_state.get("tts_engine")
        if not tts:
            return {"success": False, "error": "TTS not initialized"}
        try:
            if hasattr(tts, "synthesize") and callable(tts.synthesize):
                await tts.synthesize("Hello, I am Serin. This is a test.")
                return {"success": True}
            return {"success": False, "error": "No synthesize method"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/tts/voices")
    async def list_tts_voices() -> Any:
        try:
            manager = bot_state.get("voice_manager")
            if manager and hasattr(manager, "list_voices"):
                return {"voices": manager.list_voices()}
            import edge_tts
            edge_voices = await edge_tts.list_voices()
            return {"voices": [
                {"name": v["Name"], "id": v["ShortName"]} for v in edge_voices[:50]
            ]}
        except Exception as e:
            return {"error": str(e), "voices": []}

    @app.post("/api/voice/load")
    async def load_voice(data: VoiceLoad) -> Any:
        voice_manager = bot_state.get("voice_manager")
        if not voice_manager:
            return {"success": False, "error": "Voice manager not initialized"}
        try:
            success = await voice_manager.load_voice(data.filename)
            return {"success": success}
        except Exception as e:
            return {"success": False, "error": str(e)}
