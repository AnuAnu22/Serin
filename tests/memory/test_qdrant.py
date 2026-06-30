"""
Tests for QdrantMemorySystem logic (mocking external services).
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.mark.asyncio
async def test_add_memory_skips_on_embedding_failure():
    """If embedding fails, memory write should return None, not write garbage."""
    with patch("serin.pipeline.remember.store.SentenceTransformer") as mock_st:
        mock_st.return_value.encode.side_effect = RuntimeError("Model not loaded")

        from serin.pipeline.remember.store import QdrantMemorySystem

        ms = QdrantMemorySystem.__new__(QdrantMemorySystem)
        ms.data_dir = "/tmp/test_serin_mem"
        ms.embedding_model = mock_st.return_value
        ms.embedding_dim = 384
        ms.qdrant_client = MagicMock()
        ms.bm25_index = MagicMock()
        ms.conn = MagicMock()
        ms.db_path = ":memory:"
        ms.background_jobs = []

        # Bypass dedup check — embedding failure is what we're testing
        with patch.object(ms, "_is_duplicate", return_value=False):
            result = ms.add_memory_enhanced(
                user_id="test_user",
                content="This is a test memory that should fail embedding",
            )
        assert result is None, "Should return None when embedding fails"


@pytest.mark.asyncio
async def test_add_memory_skips_on_empty_content():
    """Empty content should skip write and return None."""
    from serin.pipeline.remember.store import QdrantMemorySystem

    ms = QdrantMemorySystem.__new__(QdrantMemorySystem)
    ms.data_dir = "/tmp/test_serin_mem"
    ms.embedding_model = MagicMock()
    ms.embedding_dim = 384
    ms.qdrant_client = MagicMock()
    ms.bm25_index = MagicMock()
    ms.conn = MagicMock()
    ms.db_path = ":memory:"
    ms.background_jobs = []

    with patch.object(ms, "_is_duplicate", return_value=False):
        result = ms.add_memory_enhanced(
            user_id="test_user",
            content="",
        )
    assert result is None


def test_search_hybrid_handles_missing_embedding_model():
    """search_hybrid should degrade gracefully when embedding model is unavailable."""
    from serin.pipeline.remember.store import QdrantMemorySystem

    ms = QdrantMemorySystem.__new__(QdrantMemorySystem)
    ms.data_dir = "/tmp/test_serin_mem"
    ms.embedding_model = None
    ms.embedding_dim = 384
    ms.qdrant_client = MagicMock()
    ms.bm25_index = MagicMock()
    ms.bm25_index.search.return_value = []
    ms.conn = MagicMock()
    ms.db_path = ":memory:"
    ms.background_jobs = []

    results = ms.search_hybrid(query="test query", user_id="test_user", n_results=5)
    assert isinstance(results, list)
