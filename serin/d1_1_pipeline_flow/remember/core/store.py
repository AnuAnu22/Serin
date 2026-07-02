"""
Qdrant Memory Store — I/O layer for Qdrant vector DB + SQLite structured data.

This file owns the connection to external storage (Qdrant, SQLite) and exposes
it via QdrantMemorySystem. Pure domain logic (fact extraction, belief state
machines) lives in sibling modules evidence.py and beliefs.py.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sqlite3
import time as time_mod
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

from serin.d1_1_pipeline_flow.remember.core.schema_store import (
    init_sqlite_schema as _run_init_sqlite_schema,
)
from serin.d1_1_pipeline_flow.remember.core.storage.search_store import (
    _build_qdrant_filter as _build_qdrant_filter_fn,
)
from serin.d1_1_pipeline_flow.remember.core.storage.search_store import (
    search_hybrid as _run_search_hybrid,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    cleanup_old_memories as _run_cleanup_old_memories,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    get_latest_message as _run_get_latest_message,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    get_message_at_position as _run_get_message_at_position,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    get_message_by_id as _run_get_message_by_id,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    get_message_count as _run_get_message_count,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    get_messages_around_timestamp as _run_get_messages_around_timestamp,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    get_recent_conversation_from_sqlite as _run_get_recent_conversation_from_sqlite,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    get_user_profile as _run_get_user_profile,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    get_user_relationships as _run_get_user_relationships,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    log_activity as _run_log_activity,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    store_recent_message as _run_store_recent_message,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    update_relationship as _run_update_relationship,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    update_user_activity as _run_update_user_activity,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    update_user_traits as _run_update_user_traits,
)
from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
    upsert_user as _run_upsert_user,
)
from serin.d1_1_pipeline_flow.remember.core.storage.write_store import (
    add_memory_enhanced as _run_add_memory_enhanced,
)
from serin.d1_3_state_core.bm25_index import SQLiteBM25Index
from serin.d1_3_state_core.logger import logger
from serin.d1_3_state_core.memory.belief_store import BeliefStore
from serin.d1_3_state_core.memory.evidence_store import FactStore

# Qdrant imports
try:
    from qdrant_client.http.models import Distance, VectorParams
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("Qdrant not available - falling back to mock implementation")

# Embedding service
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    logger.warning("Sentence transformers not available")

# BM25 implementation
BM25_AVAILABLE = importlib.util.find_spec("rank_bm25") is not None
if not BM25_AVAILABLE:
    logger.warning("Rank BM25 not available")


class QdrantMemorySystem:
    # Keep _build_qdrant_filter accessible on the instance for search_store.py
    _build_qdrant_filter = _build_qdrant_filter_fn

    def __init__(self, data_dir: str = "./bot_data", qdrant_host: str = "localhost", qdrant_port: int = 6333) -> None:
        """Initialize Qdrant-based memory system with hybrid search capabilities"""
        logger.info(" Initializing Qdrant Memory System")

        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        # Initialize Qdrant client with retry + Docker auto-start
        if QDRANT_AVAILABLE:
            self.qdrant_client = self._connect_with_retry(qdrant_host, qdrant_port)
        else:
            self.qdrant_client = None

        # Initialize embedding service
        self.embedding_model: SentenceTransformer | None
        self.embedding_dim = 384  # MiniLM dimension
        if EMBEDDING_AVAILABLE:
            try:
                self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info(" Embedding model loaded (all-MiniLM-L6-v2)")
            except Exception as e:
                logger.error(f" Failed to load embedding model: {e}")
                self.embedding_model = None
        else:
            self.embedding_model = None

        # Initialize BM25 index
        self.bm25_index: SQLiteBM25Index | None
        if BM25_AVAILABLE:
            try:
                self.bm25_index = SQLiteBM25Index(os.path.join(data_dir, "memory_fts.db"))
                logger.info(" BM25 index initialized")
            except Exception as e:
                logger.error(f" Failed to initialize BM25: {e}")
                self.bm25_index = None
        else:
            self.bm25_index = None

        # Initialize SQLite for structured data
        self.db_path = os.path.join(data_dir, "bot_data.db")
        self.conn: sqlite3.Connection
        self._init_sqlite_robust()

        # Domain-logic stores (delegated to evidence.py / beliefs.py)
        self.fact_store = FactStore(self.conn)
        self.belief_store = BeliefStore(self.conn)

        # Setup collection if needed
        if self.qdrant_client:
            self._setup_collection()

        # Background job queue (simplified implementation)
        self.background_jobs: list[Any] = []

        logger.info(" Qdrant Memory System ready")

    @staticmethod
    def _connect_with_retry(host: str, port: int, max_attempts: int = 3) -> Any | None:
        from serin.d1_1_pipeline_flow.remember.core.connection_store import (
            connect_with_retry as _run,
        )
        return _run(host, port, max_attempts)

    @staticmethod
    def _find_qdrant_container() -> str | None:
        from serin.d1_1_pipeline_flow.remember.core.connection_store import (
            find_qdrant_container as _run,
        )
        return _run()

    @staticmethod
    def _ensure_qdrant_docker(host: str, port: int) -> Any | None:
        from serin.d1_1_pipeline_flow.remember.core.connection_store import (
            ensure_qdrant_docker as _run,
        )
        return _run(host, port)

    def _init_sqlite_robust(self) -> None:
        """Initialize SQLite with corruption handling"""
        try:
            self._connect_and_init_schema()
        except sqlite3.DatabaseError as e:
            logger.error(f" SQLite corruption detected: {e}")
            self._handle_corruption()
            # Try again with fresh DB
            self._connect_and_init_schema()

    def _connect_and_init_schema(self) -> None:
        """Connect to DB and initialize schema"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self.conn.row_factory = sqlite3.Row

        # Test connection with a simple query
        try:
            self.conn.execute("SELECT 1")
        except sqlite3.DatabaseError:
            self.conn.close()
            raise

        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_sqlite_schema()

    def _handle_corruption(self) -> None:
        """Handle corrupted database by backing up and deleting"""
        if os.path.exists(self.db_path):
            timestamp = int(time_mod.time())
            backup_path = f"{self.db_path}.corrupt.{timestamp}"
            logger.warning(f" Moving corrupt database to {backup_path}")
            try:
                if self.conn:
                    try:
                        self.conn.close()
                    except Exception:
                        logger.exception("Failed to close corrupt SQLite connection in store.py")
                shutil.move(self.db_path, backup_path)
                # Also move WAL/SHM files if they exist
                for ext in ['-wal', '-shm']:
                    if os.path.exists(self.db_path + ext):
                        shutil.move(self.db_path + ext, backup_path + ext)
            except Exception as e:
                logger.error(f" Error moving corrupt DB: {e}")

    def _init_sqlite_schema(self) -> None:
        cursor: sqlite3.Cursor = self.conn.cursor()
        _run_init_sqlite_schema(self.conn, cursor)
        self.conn.commit()

    def _setup_collection(self) -> None:
        """Setup Qdrant collection with optimized configuration"""
        logger.debug("Entering _setup_collection")
        if not self.qdrant_client:
            logger.debug("No qdrant_client")
            return

        try:
            try:
                self.qdrant_client.get_collection("memories")
                logger.info(" Existing memories collection found")
                logger.debug("Collection already exists")
                return
            except Exception as e:
                logger.debug("Collection does not exist (%s), creating...", e)
                pass

            logger.debug("Calling create_collection with defaults...")
            self.qdrant_client.create_collection(
                collection_name="memories",
                vectors_config=VectorParams(
                    size=self.embedding_dim,
                    distance=Distance.COSINE,
                    on_disk=True
                )
            )

            logger.debug("Recording metadata...")
            cursor: sqlite3.Cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO qdrant_collections
                (collection_name, vector_size, distance_metric, status)
                VALUES (?, ?, ?, ?)
            """, ("memories", self.embedding_dim, "cosine", "active"))
            self.conn.commit()

            logger.info(" Qdrant collection 'memories' created with optimized settings")
            logger.debug("Collection created successfully")

        except Exception as e:
            logger.error(f" Failed to setup Qdrant collection: {e}")
            import traceback
            traceback.print_exc()


    # ========================================================================
    # Stats & Maintenance
    # ========================================================================

    def get_stats(self) -> dict[str, Any]:
        """Get memory system statistics"""
        cursor: sqlite3.Cursor = self.conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM relationships WHERE relationship_strength > 0.5")
            strong_relationships = cursor.fetchone()['count']

            memory_count = 0
            if self.qdrant_client:
                try:
                    memory_count = self.qdrant_client.count("memories").count
                except Exception:
                    logger.exception("Failed to count memories in Qdrant (store.py)")

            return {
                'total_users': total_users,
                'total_memories': memory_count,
                'strong_relationships': strong_relationships
            }
        except Exception as e:
            logger.error(f" Error getting stats: {e}")
            return {}

    # ========================================================================
    # Recent Messages Cache
    # ========================================================================


    def __del__(self) -> None:
        """Cleanup"""
        if hasattr(self, 'conn'):
            self.conn.close()

    # ── Delegation to split-out modules ────────────────────────────────────

    def search_hybrid(self, query: str, user_id: str | None = None, n_results: int = 5, **filters: Any) -> list[dict[str, Any]]:
        return _run_search_hybrid(self, query, user_id, n_results, **filters)

    def add_memory_enhanced(self, content: str, user_id: str, **kwargs: Any) -> str | None:
        return _run_add_memory_enhanced(self, content, user_id, **kwargs)

    # ── Legacy API wrappers ────────────────────────────────────────────────

    def add_memory(self, content: str, user_id: str, username: str, channel_id: str, **kwargs: Any) -> str | None:
        return self.add_memory_enhanced(content, user_id, source_message_id=kwargs.get('source_message_id'), username=username, channel_id=channel_id)

    def search_memories(self, query: str, user_id: str | None = None, channel_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        return self.search_hybrid(query, user_id, n_results=limit)

    def get_recent_conversation(self, channel_id: str = "", user_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        return _run_get_recent_conversation_from_sqlite(self, channel_id, limit)

    def get_relevant_facts(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.fact_store.get_relevant_facts(query=query, limit=limit)

    def get_relevant_beliefs(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        return self.belief_store.get_relevant_beliefs(query=query, limit=limit)

    # ── SQLite store wrappers ──────────────────────────────────────────────

    def cleanup_old_memories(self, days_old: int = 90, min_importance: float = 0.3) -> int:
        return _run_cleanup_old_memories(self, days_old, min_importance)

    def get_latest_message(self, channel_id: str) -> dict[str, Any] | None:
        return _run_get_latest_message(self, channel_id)

    def get_message_at_position(self, channel_id: str, position: int) -> dict[str, Any] | None:
        return _run_get_message_at_position(self, channel_id, position)

    def get_message_by_id(self, message_id: str) -> dict[str, Any] | None:
        return _run_get_message_by_id(self, message_id)

    def get_message_count(self, channel_id: str) -> int:
        return _run_get_message_count(self, channel_id)

    def get_messages_around_timestamp(self, channel_id: str, timestamp: str, radius: int = 2) -> list[dict[str, Any]]:
        return _run_get_messages_around_timestamp(self, channel_id, timestamp, radius)

    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        return _run_get_user_profile(self, user_id)

    def get_user_relationships(self, user_id: str, min_strength: float = 0.1) -> list[dict[str, Any]]:
        return _run_get_user_relationships(self, user_id, min_strength)

    def log_activity(self, user_id: str, channel_id: str, message_length: int, sentiment: float) -> None:
        _run_log_activity(self, user_id, channel_id, message_length, sentiment)

    def store_recent_message(self, user_id: str, username: str, channel_id: str, content: str, message_id: str, timestamp: datetime | None = None) -> None:
        _run_store_recent_message(self, user_id, username, channel_id, content, message_id, timestamp)

    def update_relationship(self, user_a_id: str, user_b_id: str, interaction_type: str = 'message') -> None:
        _run_update_relationship(self, user_a_id, user_b_id, interaction_type)

    def update_user_activity(self, user_id: str, message_length: int) -> None:
        _run_update_user_activity(self, user_id, message_length)

    def update_user_traits(self, user_id: str, traits: list[str] | None = None, interests: list[str] | None = None) -> None:
        _run_update_user_traits(self, user_id, traits, interests)

    def upsert_user(self, user_id: str, username: str, display_name: str | None = None) -> None:
        _run_upsert_user(self, user_id, username, display_name)
