from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from serin.d1_1_pipeline_flow.ingest.core.perception.profile import (
    get_memory_stats,
    get_user_profile,
)


class TestGetUserProfile:
    def test_returns_profile_when_found(self) -> None:
        obj = MagicMock()
        obj.memory.get_user_profile.return_value = {"username": "TestUser", "traits": ["funny"]}

        result = get_user_profile(obj, "user123")

        obj.memory.get_user_profile.assert_called_once_with("user123")
        assert result == {"username": "TestUser", "traits": ["funny"]}

    def test_returns_none_when_not_found(self) -> None:
        obj = MagicMock()
        obj.memory.get_user_profile.return_value = None

        result = get_user_profile(obj, "unknown")

        assert result is None

    def test_forwards_exception_from_memory(self) -> None:
        obj = MagicMock()
        obj.memory.get_user_profile.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            get_user_profile(obj, "user123")


class TestGetMemoryStats:
    def test_returns_stats_with_manager_stats(self) -> None:
        obj = MagicMock()
        obj.memory.get_stats.return_value = {"total_memories": 100}
        obj.stats = {"context_improvements": 5}

        result = get_memory_stats(obj)

        assert result["total_memories"] == 100
        assert result["manager_stats"] == {"context_improvements": 5}
        assert result["enhanced_context"]["improvements_used"] == 5
        assert result["enhanced_context"]["current_source"] == "enhanced"

    def test_includes_qdrant_when_available(self) -> None:
        obj = MagicMock()
        obj.memory.get_stats.return_value = {}
        obj.memory.qdrant_client = MagicMock()
        obj.memory.bm25_index = MagicMock()
        obj.memory.embedding_model = MagicMock()
        obj.stats = {"context_improvements": 3}

        result = get_memory_stats(obj)

        assert result["memory_system"] == "Qdrant"
        assert result["memory_features"]["hybrid_search"] is True
        assert result["memory_features"]["bm25_available"] is True
        assert result["memory_features"]["embedding_available"] is True

    def test_bm25_not_available(self) -> None:
        obj = MagicMock()
        obj.memory.get_stats.return_value = {}
        obj.memory.qdrant_client = MagicMock()
        del obj.memory.bm25_index
        obj.memory.embedding_model = MagicMock()
        obj.stats = {"context_improvements": 0}

        result = get_memory_stats(obj)

        assert result["memory_features"]["bm25_available"] is False
        assert result["memory_features"]["embedding_available"] is True

    def test_embedding_not_available(self) -> None:
        obj = MagicMock()
        obj.memory.get_stats.return_value = {}
        obj.memory.qdrant_client = MagicMock()
        obj.memory.bm25_index = MagicMock()
        del obj.memory.embedding_model
        obj.stats = {"context_improvements": 0}

        result = get_memory_stats(obj)

        assert result["memory_features"]["embedding_available"] is False

    def test_no_qdrant_client(self) -> None:
        obj = MagicMock()
        obj.memory.get_stats.return_value = {}
        del obj.memory.qdrant_client
        obj.stats = {"context_improvements": 0}

        result = get_memory_stats(obj)

        assert "memory_system" not in result
        assert "memory_features" not in result
