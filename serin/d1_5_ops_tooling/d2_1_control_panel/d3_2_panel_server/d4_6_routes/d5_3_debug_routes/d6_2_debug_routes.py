from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI

from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    get_gpu_vram_usage,
    make_json_safe,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_2_server_state import (
    _get_current_stats,
    get_system_health,
)

_logger = logging.getLogger("control_panel")
_prompt_history: list[dict[str, Any]] = []
_alert_rules: list[dict[str, Any]] = []
_alert_history: list[dict[str, Any]] = []
_MAX_PROMPTS = 50


def store_prompt_debug(entry: dict[str, Any]) -> None:
    """Store a bounded prompt debugger entry."""
    _prompt_history.append(
        {
            "timestamp": time.time(),
            "user": entry.get("user", ""),
            "channel": entry.get("channel", ""),
            "system_prompt": entry.get("system_prompt", ""),
            "memories_injected": entry.get("memories", ""),
            "relationship_context": entry.get("relationship", ""),
            "belief_context": entry.get("beliefs", ""),
            "time_context": entry.get("time", ""),
            "energy_instruction": entry.get("energy", ""),
            "user_message": entry.get("user_message", ""),
            "full_prompt": entry.get("full_prompt", ""),
            "response": "",
            "model": entry.get("model", ""),
            "elapsed_ms": 0,
        }
    )
    if len(_prompt_history) > _MAX_PROMPTS:
        _prompt_history.pop(0)


def update_last_prompt_debug(response: str, elapsed_ms: float) -> None:
    """Attach the LLM result to the most recently assembled prompt."""
    if _prompt_history:
        _prompt_history[-1]["response"] = response[:2000]
        _prompt_history[-1]["elapsed_ms"] = elapsed_ms


def _conn(bot_state: dict[str, Any]) -> Any | None:
    memory = bot_state.get("memory_system")
    return getattr(memory, "conn", None) if memory else None


def _rows(cursor: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def register_debug_routes(app: FastAPI, bot_state: dict[str, Any]) -> None:
    """Register control-panel diagnostics, timeline, alerts, and report routes."""

    @app.get("/api/debug/prompts")
    async def get_prompt_history(limit: int = 20) -> Any:
        try:
            return make_json_safe(
                {"prompts": _prompt_history[-max(1, min(limit, _MAX_PROMPTS)) :]}
            )
        except Exception as exc:
            _logger.error("Prompt history failed: %s", exc)
            return {"error": str(exc), "prompts": []}

    @app.get("/api/debug/prompts/{index}")
    async def get_prompt_detail(index: int) -> Any:
        try:
            if 0 <= index < len(_prompt_history):
                return make_json_safe(_prompt_history[index])
            return {"error": "Not found"}
        except Exception as exc:
            _logger.error("Prompt detail failed: %s", exc)
            return {"error": str(exc)}

    @app.get("/api/debug/conversation/{user_id}")
    async def get_conversation(
        user_id: str, channel_id: str = "", limit: int = 100
    ) -> Any:
        conn = _conn(bot_state)
        if not conn:
            return {"messages": []}
        try:
            cursor = conn.cursor()
            query = "SELECT message_id, user_id, username, channel_id, content, timestamp FROM recent_messages WHERE user_id = ?"
            params: list[Any] = [user_id]
            if channel_id:
                query += " AND channel_id = ?"
                params.append(channel_id)
            cursor.execute(
                query + " ORDER BY timestamp DESC LIMIT ?",
                (*params, max(1, min(limit, 500))),
            )
            messages = _rows(cursor)
            messages.reverse()
            return make_json_safe({"messages": messages, "count": len(messages)})
        except Exception as exc:
            _logger.error("Conversation lookup failed: %s", exc)
            return {"error": str(exc), "messages": []}

    @app.get("/api/debug/personality-history")
    async def get_personality_history(hours: int = 24) -> Any:
        conn = _conn(bot_state)
        if not conn:
            return {"history": []}
        try:
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS personality_history (id INTEGER PRIMARY KEY AUTOINCREMENT, energy REAL, sass REAL, engagement REAL, recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            cursor.execute(
                "SELECT energy, sass, engagement, recorded_at FROM personality_history WHERE recorded_at > datetime('now', ? || ' hours') ORDER BY recorded_at",
                (str(-max(1, min(hours, 8760))),),
            )
            return make_json_safe({"history": _rows(cursor)})
        except Exception as exc:
            _logger.error("Personality history failed: %s", exc)
            return {"error": str(exc), "history": []}

    @app.get("/api/debug/relationships")
    async def get_all_relationships() -> Any:
        memory = bot_state.get("memory_system")
        conn = _conn(bot_state)
        if not memory or not conn:
            return {"relationships": []}
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, username, total_messages, last_seen FROM users ORDER BY total_messages DESC LIMIT 50"
            )
            result: list[dict[str, Any]] = []
            for user in _rows(cursor):
                # Read from user_affect table instead of deprecated relationships
                try:
                    cursor.execute(
                        "SELECT valence, familiarity_count, impression_text FROM user_affect WHERE user_id = ?",
                        (user["user_id"],)
                    )
                    affect_row = cursor.fetchone()
                    if affect_row:
                        affect_dict = dict(affect_row)
                        # Compute familiarity from count using the same formula as AffectEngine
                        import math
                        count = affect_dict.get("familiarity_count", 0)
                        familiarity = 0.0 if count <= 0 else 1.0 - math.exp(-count / 50.0)

                        result.append(
                            {
                                **user,
                                "valence": affect_dict.get("valence", 0.0),
                                "familiarity": familiarity,
                                "familiarity_count": count,
                                "impression": affect_dict.get("impression_text", ""),
                            }
                        )
                    else:
                        # User has no affect data yet
                        result.append(
                            {
                                **user,
                                "valence": 0.0,
                                "familiarity": 0.0,
                                "familiarity_count": 0,
                                "impression": "",
                            }
                        )
                except Exception as e:
                    _logger.debug("Failed to get affect for user %s: %s", user.get("user_id", "?"), e)
                    result.append(
                        {
                            **user,
                            "valence": 0.0,
                            "familiarity": 0.0,
                            "familiarity_count": 0,
                            "impression": "",
                        }
                    )
            return make_json_safe({"relationships": result})
        except Exception as exc:
            _logger.error("Relationships failed: %s", exc)
            return {"error": str(exc), "relationships": []}

    @app.get("/api/memory/timeline")
    async def get_memory_timeline(
        before: str = "", limit: int = 50, user_id: str = "", channel_id: str = ""
    ) -> Any:
        conn = _conn(bot_state)
        if not conn:
            return {"messages": [], "has_more": False}
        try:
            clauses: list[str] = []
            params: list[Any] = []
            for clause, value in (
                ("timestamp < ?", before),
                ("user_id = ?", user_id),
                ("channel_id = ?", channel_id),
            ):
                if value:
                    clauses.append(clause)
                    params.append(value)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            capped = max(1, min(limit, 200))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT message_id, user_id, username, channel_id, content, timestamp FROM recent_messages"  # nosec B608
                + where
                + " ORDER BY timestamp DESC LIMIT ?",
                (*params, capped + 1),
            )
            rows = _rows(cursor)
            return make_json_safe(
                {"messages": rows[:capped], "has_more": len(rows) > capped}
            )
        except Exception as exc:
            _logger.error("Timeline failed: %s", exc)
            return {"error": str(exc), "messages": [], "has_more": False}

    @app.get("/api/alerts/rules")
    async def get_alert_rules() -> Any:
        return make_json_safe({"rules": _alert_rules})

    @app.post("/api/alerts/rules")
    async def add_alert_rule(data: dict[str, Any]) -> Any:
        try:
            rule = {
                "id": (max((r["id"] for r in _alert_rules), default=0) + 1),
                "metric": data.get("metric", ""),
                "operator": data.get("operator", ">"),
                "threshold": float(data.get("threshold", 0)),
                "webhook_url": data.get("webhook_url", ""),
                "enabled": True,
            }
            _alert_rules.append(rule)
            return make_json_safe({"success": True, "rule": rule})
        except Exception as exc:
            _logger.error("Add alert rule failed: %s", exc)
            return {"success": False, "error": str(exc)}

    @app.delete("/api/alerts/rules/{rule_id}")
    async def delete_alert_rule(rule_id: int) -> Any:
        _alert_rules[:] = [rule for rule in _alert_rules if rule["id"] != rule_id]
        return {"success": True}

    @app.get("/api/alerts/history")
    async def get_alert_history() -> Any:
        return make_json_safe({"history": _alert_history[-50:]})

    @app.post("/api/alerts/check")
    async def check_alerts() -> Any:
        try:
            stats = _get_current_stats()
            health = await get_system_health()
            triggered: list[dict[str, Any]] = []
            for rule in _alert_rules:
                values = {
                    "error_count": stats.get("manager", {}).get("errors", 0),
                    "queue_size": stats.get("background", {}).get("queue_size", 0),
                    "gpu_vram": await get_gpu_vram_usage(),
                    "qdrant_status": 0
                    if health.get("components", {}).get("memory", {}).get("status")
                    == "ok"
                    else 1,
                }
                value = values.get(rule["metric"], 0)
                threshold = rule["threshold"]
                op = rule["operator"]
                if {
                    ">": value > threshold,
                    "<": value < threshold,
                    ">=": value >= threshold,
                    "==": value == threshold,
                }.get(op, False):
                    alert = {
                        "rule_id": rule["id"],
                        "metric": rule["metric"],
                        "value": value,
                        "threshold": threshold,
                        "time": time.time(),
                    }
                    _alert_history.append(alert)
                    triggered.append(alert)
            return make_json_safe(
                {"triggered": triggered, "checked": len(_alert_rules)}
            )
        except Exception as exc:
            _logger.error("Alert check failed: %s", exc)
            return {"error": str(exc), "triggered": []}

    @app.get("/api/dynamics/state")
    async def get_dynamics_state() -> Any:
        manager = bot_state.get("message_manager")
        if not manager:
            return {"error": "Manager not initialized"}
        engine = getattr(manager, "dynamics_engine", None)
        if not engine:
            return {"error": "Dynamics engine not initialized"}
        return make_json_safe(engine.get_state_for_panel())

    @app.get("/api/debug/report")
    async def generate_health_report() -> Any:
        """Generate a full state report with memory, personality, and config sections."""
        report: dict[str, Any] = {"generated_at": time.time(), "sections": {}}
        try:
            report["sections"]["health"] = await get_system_health()
        except Exception as exc:
            _logger.error("Report health section failed: %s", exc)
            report["sections"]["health"] = {"error": str(exc)}
        try:
            report["sections"]["stats"] = _get_current_stats()
        except Exception as exc:
            _logger.error("Report stats section failed: %s", exc)
            report["sections"]["stats"] = {"error": str(exc)}
        start = bot_state.get("start_time")
        report["sections"]["uptime"] = {
            "seconds": round(time.time() - start, 1)
            if isinstance(start, (int, float))
            else 0
        }
        memory = bot_state.get("memory_system")
        conn = _conn(bot_state)
        if memory and conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as c FROM recent_messages")
                total_msgs = cursor.fetchone()["c"]
                cursor.execute("SELECT COUNT(*) as c FROM facts WHERE is_active=1")
                active_facts = cursor.fetchone()["c"]
                cursor.execute("SELECT COUNT(*) as c FROM beliefs WHERE is_active=1")
                active_beliefs = cursor.fetchone()["c"]
                cursor.execute("SELECT COUNT(*) as c FROM users")
                total_users = cursor.fetchone()["c"]
                report["sections"]["memory"] = {
                    "total_messages": total_msgs,
                    "active_facts": active_facts,
                    "active_beliefs": active_beliefs,
                    "total_users": total_users,
                }
            except Exception as exc:
                _logger.error("Report memory section failed: %s", exc)
                report["sections"]["memory"] = {"error": str(exc)}
        manager = bot_state.get("message_manager")
        if manager:
            try:
                p = getattr(manager, "personality", None) or getattr(
                    manager, "personality_state", None
                )
                if p:
                    report["sections"]["personality"] = {
                        "energy": getattr(p, "energy_level", 0.5),
                        "sass": getattr(p, "sass_level", 0.5),
                        "engagement": getattr(p, "engagement", 0.5),
                        "mood": getattr(p, "current_mood", "neutral"),
                    }
            except Exception as exc:
                _logger.error("Report personality section failed: %s", exc)
        try:
            from serin.d1_4_config_base.config import config

            report["sections"]["config"] = {
                "model": getattr(config, "LLM_MODEL", ""),
                "voice_enabled": getattr(config, "ENABLE_VOICE", False),
                "tts_enabled": getattr(config, "ENABLE_TTS", False),
                "debug": getattr(config, "DEBUG_MODE", False),
                "log_level": getattr(config, "LOG_LEVEL", "INFO"),
            }
        except Exception as exc:
            _logger.error("Report config section failed: %s", exc)
        return make_json_safe(report)
