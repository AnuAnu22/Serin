"""User profile and memory-stat accessors (perception layer)."""

from __future__ import annotations

from typing import Any

from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_4_core_manager import (
    EnhancedMessageManagerV3,
)


def get_user_profile(self: Any, user_id: str) -> dict[str, Any] | None:
    """Get user profile"""
    result: dict[str, Any] | None = self.memory.get_user_profile(user_id)
    return result


def get_memory_stats(self: Any) -> dict[str, Any]:
    """Get memory statistics"""
    stats: dict[str, Any] = self.memory.get_stats()
    stats["manager_stats"] = self.stats
    stats["enhanced_context"] = {
        "improvements_used": self.stats["context_improvements"],
        "current_source": "enhanced",
    }
    if hasattr(self.memory, "qdrant_client"):
        stats["memory_system"] = "Qdrant"
        stats["memory_features"] = {
            "hybrid_search": True,
            "bm25_available": hasattr(self.memory, "bm25_index"),
            "embedding_available": hasattr(self.memory, "embedding_model"),
        }
    return stats


# Alias for backward compatibility with discord_bot.py
MessageManagerV3 = EnhancedMessageManagerV3
