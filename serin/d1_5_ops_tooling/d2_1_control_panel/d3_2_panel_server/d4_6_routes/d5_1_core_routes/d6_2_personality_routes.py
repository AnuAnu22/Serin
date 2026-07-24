from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from serin.d1_4_config_base.d2_3_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    MoodUpdate,
    make_json_safe,
)


def register_personality_routes(app: FastAPI, bot_state: dict[str, Any]) -> None:
    @app.get("/api/personality/state")
    async def get_personality_state() -> Any:
        manager = bot_state.get("message_manager")
        if not manager:
            return {"error": "Manager not initialized"}
        try:
            personality = getattr(manager, "personality", None)
            if not personality:
                return {"error": "Personality module not found"}
            state = {
                "energy_level": getattr(personality, "energy_level", 0.5),
                "sass_level": getattr(personality, "sass_level", 0.5),
                "engagement": getattr(personality, "engagement", 0.5),
                "tone_modifier": getattr(personality, "tone_modifier", ""),
                "current_mood": getattr(personality, "current_mood", "neutral"),
            }
            if hasattr(manager, "mood_state"):
                mood = manager.mood_state
                state["mood_state"] = {"tone_modifier": getattr(mood, "get_tone_modifier", lambda: "")(), "current_state": getattr(mood, "current_state", {})}
            return make_json_safe(state)
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/personality/mood")
    async def update_mood(update: MoodUpdate) -> Any:
        manager = bot_state.get("message_manager")
        if not manager:
            return {"success": False, "error": "Manager not initialized"}
        try:
            personality = getattr(manager, "personality", None)
            if not personality:
                return {"success": False, "error": "Personality module not found"}
            changes = []
            if update.energy_level is not None:
                personality.energy_level = update.energy_level
                changes.append(f"energy={update.energy_level}")
            if update.sass_level is not None:
                personality.sass_level = update.sass_level
                changes.append(f"sass={update.sass_level}")
            if update.engagement is not None:
                personality.engagement = update.engagement
                changes.append(f"engagement={update.engagement}")
            if update.tone_modifier is not None:
                personality.tone_modifier = update.tone_modifier
                changes.append(f"tone={update.tone_modifier}")
            logger.info("Personality updated: %s", ", ".join(changes))
            return {"success": True, "changes": changes}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/personality/conversation/{channel_id}")
    async def get_conversation_analysis(channel_id: str) -> Any:
        manager = bot_state.get("message_manager")
        if not manager:
            return {"error": "Manager not initialized"}
        try:
            analyzer = getattr(manager, "conversation_analyzer", None)
            if not analyzer:
                return {"error": "Conversation analyzer not found"}
            current_topic = analyzer.active_topics.get(channel_id)
            history = analyzer.get_topic_history(channel_id, limit=10)
            return make_json_safe({"channel_id": channel_id, "current_topic": current_topic, "topic_history": history})
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/personality/topic-fatigue")
    async def get_topic_fatigue() -> Any:
        manager = bot_state.get("message_manager")
        if not manager:
            return {"error": "Manager not initialized"}
        try:
            fatigue = getattr(manager, "topic_fatigue", None)
            if not fatigue:
                return {"fatigue": {}, "note": "Topic fatigue tracker not found"}
            return make_json_safe({"fatigue": getattr(fatigue, "fatigue_map", {})})
        except Exception as e:
            return {"error": str(e)}

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

    @app.post("/api/context/sever")
    async def sever_context(data: dict[str, str]) -> Any:
        manager = bot_state.get("message_manager")
        if not manager or not hasattr(manager, "response_controller"):
            return {"success": False, "error": "Manager not initialized"}
        channel_id = data.get("channel_id", "")
        rc = manager.response_controller
        if hasattr(rc, "active_conversations") and channel_id in rc.active_conversations:
            del rc.active_conversations[channel_id]
            logger.info("Severed context for %s", channel_id)
            return {"success": True}
        return {"success": False, "error": "Context not found"}


