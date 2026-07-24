from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from serin.d1_4_config_base.d2_3_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_1_state_access import (
    MemoryQuery as _MemoryQuery,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_1_state_access import (
    MemorySearchAdvanced as _MemorySearchAdvanced,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_1_state_access import (
    make_json_safe,
)


class FactSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    category: str | None = Field(default=None, pattern=r"^(observation|board_state|game_result|reference|personality|preference)$")
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=20, ge=1, le=50)
    active_only: bool = True


class BeliefSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    state: str | None = Field(default=None, pattern=r"^(PENDING|SUPPORTED|CONTESTED|SUPERSEDED|UNKNOWN)$")
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=20, ge=1, le=50)


def register_memory_routes(app: FastAPI, bot_state: dict[str, Any]) -> None:
    def _get_memory() -> Any:
        return bot_state.get("memory_system")

    @app.post("/api/memory/search/advanced")
    async def search_memories_advanced(request: _MemorySearchAdvanced) -> Any:
        mem = _get_memory()
        if not mem:
            return {"error": "Memory system not initialized", "results": []}
        try:
            start = time.perf_counter()
            filters: dict[str, Any] = {}
            if request.channel_id:
                filters["channel_id"] = request.channel_id
            if hasattr(mem, "search_hybrid"):
                raw_results = mem.search_hybrid(request.query, request.user_id, request.limit, **filters)
            else:
                raw_results = mem.search_memories(query=request.query, user_id=request.user_id, limit=request.limit)

            enriched: list[dict[str, Any]] = []
            now = time.time()
            for i, result in enumerate(raw_results):
                entry: dict[str, Any] = {
                    "rank": i + 1,
                    "content": result.get("content", result.get("text", "")),
                    "memory_type": result.get("memory_type", "unknown"),
                    "user_id": result.get("person_id", result.get("user_id", "")),
                    "timestamp": result.get("timestamp", ""),
                    "importance": result.get("importance", 0.5),
                    "channel_id": result.get("channel_id", ""),
                }
                if request.include_vector_scores:
                    entry["vector_score"] = result.get("score", result.get("vector_score", 0.0))
                if request.include_bm25_scores:
                    entry["bm25_score"] = result.get("bm25_score", 0.0)
                if request.include_rrf_scores:
                    entry["rrf_score"] = result.get("rrf_score", result.get("score", 0.0))
                if request.include_temporal_scores:
                    ts = result.get("timestamp", "")
                    if ts:
                        try:
                            mem_time = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if isinstance(ts, str) else float(ts)
                            days_old = (now - mem_time) / 86400
                            entry["temporal_score"] = round(max(0.0, 1.0 - (days_old / request.time_decay_days)), 4)
                            entry["days_old"] = round(days_old, 1)
                        except (ValueError, TypeError):
                            entry["temporal_score"] = 0.0
                    else:
                        entry["temporal_score"] = 0.0
                vec = entry.get("vector_score", 0.0)
                temp = entry.get("temporal_score", 0.0)
                imp = entry.get("importance", 0.5)
                entry["final_score"] = round(0.6 * vec + 0.3 * temp + 0.1 * imp, 4)

                if "all" not in request.memory_types and entry["memory_type"] not in request.memory_types:
                    continue
                if entry["importance"] < request.min_importance:
                    continue
                enriched.append(entry)

            sort_key = request.sort_by
            enriched.sort(key=lambda x: x.get(f"{sort_key}_score", x.get("final_score", 0)), reverse=True)
            elapsed = time.perf_counter() - start
            return {
                "query": request.query,
                "results_count": len(enriched),
                "results": make_json_safe(enriched),
                "scoring": {"weights": {"similarity": 0.6, "recency": 0.3, "importance": 0.1}, "time_decay_days": request.time_decay_days, "sort_by": request.sort_by},
                "search_time_ms": round(elapsed * 1000, 2),
            }
        except Exception as e:
            logger.error("Error in advanced memory search: %s", e)
            return {"error": str(e), "results": []}

    @app.post("/api/memory/search")
    async def search_memories_simple(query: _MemoryQuery) -> Any:
        mem = _get_memory()
        if not mem:
            return {"memories": [], "error": "Memory not initialized"}
        try:
            results = mem.search_memories(query=query.query, user_id=query.user_id, limit=query.limit)
            return {"memories": make_json_safe(results), "count": len(results)}
        except Exception as e:
            return {"error": str(e), "memories": []}

    @app.post("/api/memory/facts/search")
    async def search_facts(req: FactSearchRequest) -> Any:
        mem = _get_memory()
        if not mem:
            return {"facts": [], "error": "Memory not initialized"}
        try:
            raw = mem.get_relevant_facts(req.query, req.limit) if hasattr(mem, "get_relevant_facts") else []
            filtered = []
            for f in raw:
                if req.category and f.get("category") != req.category:
                    continue
                if f.get("confidence", 1.0) < req.min_confidence:
                    continue
                if req.active_only and not f.get("is_active", True):
                    continue
                filtered.append(f)
            return {"facts": make_json_safe(filtered), "count": len(filtered), "categories": list(set(f.get("category", "") for f in filtered if f.get("category")))}
        except Exception as e:
            return {"error": str(e), "facts": []}

    @app.get("/api/memory/facts/stats")
    async def get_fact_stats() -> Any:
        mem = _get_memory()
        if not mem:
            return {"total_active_facts": 0, "by_category": {}, "by_source": {}}
        try:
            cursor = mem.conn.cursor()
            cursor.execute("SELECT category, COUNT(*) as cnt, AVG(belief) as avg_conf, MIN(belief) as min_conf, MAX(belief) as max_conf FROM facts WHERE is_active = 1 GROUP BY category")
            by_category = {r["category"]: {"count": r["cnt"], "avg_confidence": round(r["avg_conf"], 3) if r["avg_conf"] else 0, "min_confidence": r["min_conf"] or 0, "max_confidence": r["max_conf"] or 0} for r in cursor.fetchall()}
            cursor.execute("SELECT source_type, COUNT(*) as cnt, AVG(belief) as avg_conf FROM facts WHERE is_active = 1 GROUP BY source_type")
            by_source = {r["source_type"]: {"count": r["cnt"], "avg_confidence": round(r["avg_conf"], 3) if r["avg_conf"] else 0} for r in cursor.fetchall()}
            cursor.execute("SELECT COUNT(*) as c FROM facts WHERE is_active = 1")
            total = cursor.fetchone()["c"]
            return {"total_active_facts": total, "by_category": by_category, "by_source": by_source}
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/memory/beliefs/search")
    async def search_beliefs(req: BeliefSearchRequest) -> Any:
        mem = _get_memory()
        if not mem:
            return {"beliefs": [], "error": "Memory not initialized"}
        try:
            raw = mem.get_relevant_beliefs(req.query, req.limit) if hasattr(mem, "get_relevant_beliefs") else []
            filtered = []
            for b in raw:
                if req.state and b.get("state") != req.state:
                    continue
                if b.get("confidence", 0.0) < req.min_confidence:
                    continue
                filtered.append(b)
            return {
                "beliefs": make_json_safe(filtered),
                "count": len(filtered),
                "state_machine": "PENDING → SUPPORTED/CONTESTED → SUPERSEDED",
                "confidence_formula": "Bayesian update from supporting and contradicting facts",
            }
        except Exception as e:
            return {"error": str(e), "beliefs": []}

    @app.get("/api/memory/beliefs/stats")
    async def get_belief_stats() -> Any:
        mem = _get_memory()
        if not mem:
            return {"total_active_beliefs": 0, "by_state": {}}
        try:
            cursor = mem.conn.cursor()
            cursor.execute("SELECT state, COUNT(*) as cnt, AVG(confidence) as avg_conf FROM beliefs WHERE is_active = 1 GROUP BY state")
            by_state = {r["state"]: {"count": r["cnt"], "avg_confidence": round(r["avg_conf"], 3) if r["avg_conf"] else 0} for r in cursor.fetchall()}
            cursor.execute("SELECT COUNT(*) as c FROM beliefs WHERE is_active = 1")
            total = cursor.fetchone()["c"]
            return {"total_active_beliefs": total, "by_state": by_state}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/memory/distribution")
    async def get_memory_distribution() -> Any:
        mem = _get_memory()
        if not mem:
            return {"error": "Memory not initialized"}
        try:
            result: dict[str, Any] = {"types": {}}
            if hasattr(mem, "qdrant_client") and mem.qdrant_client:
                total = mem.qdrant_client.count("memories").count
                result["total_vectors"] = total
                type_counts: dict[str, int] = {}
                offset = None
                while True:
                    records, offset = mem.qdrant_client.scroll("memories", limit=100, offset=offset, with_payload=["memory_type"], with_vectors=False)
                    for rec in records:
                        mt = rec.payload.get("memory_type", "unknown") if rec.payload else "unknown"
                        type_counts[mt] = type_counts.get(mt, 0) + 1
                    if offset is None:
                        break
                result["types"] = type_counts
            else:
                result["total_vectors"] = 0

            cursor = mem.conn.cursor()
            cursor.execute("SELECT COUNT(*) as c FROM users")
            result["total_users"] = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) as c FROM facts WHERE is_active = 1")
            result["active_facts"] = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) as c FROM beliefs WHERE is_active = 1")
            result["active_beliefs"] = cursor.fetchone()["c"]
            try:
                cursor.execute("SELECT COUNT(*) as c FROM recent_messages")
                result["conversation_messages"] = cursor.fetchone()["c"]
            except Exception as e:
                logger.debug("recent_messages table query failed: %s", e)
                result["conversation_messages"] = 0
            return make_json_safe(result)
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/memory/add")
    async def add_memory_manual(data: dict[str, Any]) -> Any:
        mem = _get_memory()
        if not mem:
            return {"success": False, "error": "Memory not initialized"}
        try:
            content = data.get("content", "")
            if not content or len(content) > 10000:
                return {"success": False, "error": "Content required (max 10000 chars)"}
            memory_id = mem.add_memory_enhanced(content=content, user_id=data.get("user_id", "manual"), username=data.get("username", "panel_user"), channel_id=data.get("channel_id"), importance=min(max(float(data.get("importance", 0.5)), 0.0), 1.0), memory_type=data.get("memory_type", "manual"))
            return {"success": True, "memory_id": memory_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/memory/cleanup")
    async def cleanup_memories(data: dict[str, Any]) -> Any:
        mem = _get_memory()
        if not mem:
            return {"success": False, "error": "Memory not initialized"}
        try:
            days_old = int(data.get("days_old", 90))
            min_importance = float(data.get("min_importance", 0.3))
            cleaned = mem.cleanup_old_memories(days_old, min_importance)
            return {"success": True, "cleaned_count": cleaned}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/memory/users")
    async def get_all_users() -> Any:
        mem = _get_memory()
        if not mem:
            return {"users": []}
        try:
            cursor = mem.conn.cursor()
            cursor.execute("SELECT user_id, username, total_messages, first_seen, last_seen FROM users ORDER BY total_messages DESC LIMIT 100")
            users = [dict(r) for r in cursor.fetchall()]
            return {"users": make_json_safe(users)}
        except Exception as e:
            return {"error": str(e), "users": []}

    @app.get("/api/memory/user/{user_id}")
    async def get_user_profile(user_id: str) -> Any:
        mem = _get_memory()
        if not mem:
            return {"error": "Memory not initialized"}
        try:
            profile = mem.get_user_profile(user_id)
            if not profile:
                return {"error": "User not found"}
            relationships = mem.get_user_relationships(user_id)
            profile["relationships"] = relationships
            return make_json_safe(profile)
        except Exception as e:
            return {"error": str(e)}
