from __future__ import annotations

from typing import Any

from fastapi.responses import FileResponse, HTMLResponse

from serin.d1_4_config_base.d2_3_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_1_state_access import (
    app,
    bot_state,
    get_request_metrics,
    make_json_safe,
)


@app.get("/", response_class=HTMLResponse)
async def homepage() -> Any:
    return FileResponse("control_panel/static/index.html")


@app.get("/api/status")
async def get_status() -> Any:
    client = bot_state.get("discord_client")
    if not client:
        return {"online": False, "user": None, "guilds": [], "latency": 0}
    guilds = []
    if client.guilds:
        for guild in client.guilds:
            guilds.append({
                "id": str(guild.id),
                "name": guild.name,
                "member_count": guild.member_count,
                "text_channels": len(guild.text_channels),
                "voice_channels": len(guild.voice_channels),
            })
    return {
        "online": client.is_ready(),
        "user": {
            "id": str(client.user.id),
            "name": client.user.name,
            "discriminator": client.user.discriminator,
        } if client.user else None,
        "guilds": guilds,
        "latency": round(client.latency * 1000, 2),
    }


@app.get("/api/stats")
async def get_stats() -> Any:
    return _get_current_stats()


@app.get("/api/health")
async def get_system_health() -> Any:
    health: dict[str, Any] = {"status": "healthy", "components": {}}

    client = bot_state.get("discord_client")
    health["components"]["discord"] = {
        "status": "ok" if client and client.is_ready() else "error",
        "latency": round(client.latency * 1000, 2) if client else 0,
    }

    mem = bot_state.get("memory_system")
    health["components"]["memory"] = {
        "status": "ok" if mem else "error",
        "type": "Qdrant" if mem and hasattr(mem, "qdrant_client") else "Unknown",
        "qdrant_connected": bool(mem and getattr(mem, "qdrant_client", None)),
        "bm25_available": bool(mem and getattr(mem, "bm25_index", None)),
        "embedding_available": bool(mem and getattr(mem, "embedding_model", None)),
    }

    listener = bot_state.get("voice_listener")
    health["components"]["voice_input"] = {
        "status": "ok" if listener else "disabled",
        "connected": listener.is_connected() if listener and hasattr(listener, "is_connected") else False,
    }

    tts = bot_state.get("tts_engine")
    health["components"]["tts"] = {
        "status": "ok" if tts else "disabled",
        "model": getattr(tts, "model_name", None) if tts else None,
    }

    bg = bot_state.get("background_processor")
    health["components"]["background"] = {
        "status": "ok" if bg and getattr(bg, "is_running", False) else "stopped",
        "queue_size": len(getattr(bg, "processing_queue", []) or []) if bg else 0,
    }

    crawler = bot_state.get("message_crawler")
    health["components"]["crawler"] = {"status": "ok" if crawler else "disabled"}

    statuses = [c["status"] for c in health["components"].values()]
    if "error" in statuses:
        health["status"] = "degraded"
    if all(s == "error" for s in statuses):
        health["status"] = "critical"

    return health


@app.get("/api/performance")
async def get_performance_metrics() -> Any:
    return {"endpoints": get_request_metrics()}


@app.get("/api/pipeline/status")
async def get_pipeline_status() -> Any:
    manager = bot_state.get("message_manager")
    if not manager:
        return {"status": "offline", "stages": []}
    return make_json_safe({
        "status": "online",
        "stages": [
            {"id": 1, "name": "ResponseDecision", "description": "Should bot respond?"},
            {"id": 2, "name": "MemoryRetrieval", "description": "Qdrant + BM25 hybrid search"},
            {"id": 3, "name": "ResponsePlanner", "description": "Belief/claim analysis"},
            {"id": 4, "name": "Temporal", "description": "Date/time resolution"},
            {"id": 5, "name": "Personality", "description": "Tone/mood modifier"},
            {"id": 6, "name": "PromptAssembly", "description": "System prompt + context"},
            {"id": 7, "name": "LLMCall", "description": "Model inference"},
            {"id": 8, "name": "ResponseCleaning", "description": "Filter + truncate"},
            {"id": 9, "name": "Send", "description": "Discord delivery"},
            {"id": 10, "name": "MemoryWrite", "description": "Store response"},
        ],
        "last_run": getattr(manager, "_last_pipeline_time", None),
        "total_processed": getattr(manager, "stats", {}).get("messages_processed", 0),
    })


def _get_current_stats() -> Any:
    stats: dict[str, Any] = {}
    components = [
        ("message_manager", "manager", "stats"),
        ("background_processor", "background", "get_stats"),
        ("passive_monitor", "passive", "get_stats"),
        ("message_crawler", "crawler", "get_stats"),
        ("memory_system", "memory", "get_stats"),
        ("voice_listener", "voice", "get_stats"),
    ]
    for state_key, stat_key, method in components:
        try:
            obj = bot_state.get(state_key)
            if obj:
                if method == "stats":
                    stats[stat_key] = obj.stats.copy() if hasattr(obj, "stats") else {}
                elif callable(getattr(obj, method, None)):
                    stats[stat_key] = getattr(obj, method)()
                else:
                    stats[stat_key] = {}
            else:
                stats[stat_key] = {}
        except Exception as e:
            logger.error("Error getting %s stats: %s", stat_key, e)
            stats[stat_key] = {"error": str(e)}
    stats["bot"] = bot_state.get("bot_stats", {})
    return make_json_safe(stats)
