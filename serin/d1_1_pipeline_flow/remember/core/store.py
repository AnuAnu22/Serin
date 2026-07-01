"""
Qdrant Memory Store — I/O layer for Qdrant vector DB + SQLite structured data.

This file owns the connection to external storage (Qdrant, SQLite) and exposes
it via QdrantMemorySystem. Pure domain logic (fact extraction, belief state
machines) lives in sibling modules evidence.py and beliefs.py.
"""
import importlib
import os
import shutil
import sqlite3
import time as time_mod
from typing import Any

from serin.d1_1_pipeline_flow.remember.core.bm25_index import SQLiteBM25Index
from serin.d1_1_pipeline_flow.remember.knowledge.belief.beliefs import BeliefStore
from serin.d1_1_pipeline_flow.remember.knowledge.belief.evidence import FactStore
from serin.d1_3_state_core.logger import logger

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
        if EMBEDDING_AVAILABLE:
            try:
                self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                self.embedding_dim = 384  # MiniLM dimension
                logger.info(" Embedding model loaded (all-MiniLM-L6-v2)")
            except Exception as e:
                logger.error(f" Failed to load embedding model: {e}")
                self.embedding_model = None
                self.embedding_dim = 384
        else:
            self.embedding_model = None
            self.embedding_dim = 384

        # Initialize BM25 index
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
        self._init_sqlite_robust()

        # Domain-logic stores (delegated to evidence.py / beliefs.py)
        self.fact_store = FactStore(self.conn)
        self.belief_store = BeliefStore(self.conn)

        # Setup collection if needed
        if self.qdrant_client:
            self._setup_collection()

        # Background job queue (simplified implementation)
        self.background_jobs = []

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

    def _init_sqlite_robust(self):
        """Initialize SQLite with corruption handling"""
        try:
            self._connect_and_init_schema()
        except sqlite3.DatabaseError as e:
            logger.error(f" SQLite corruption detected: {e}")
            self._handle_corruption()
            # Try again with fresh DB
            self._connect_and_init_schema()

    def _connect_and_init_schema(self):
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

    def _handle_corruption(self):
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

    def _init_sqlite_schema(self):
        from serin.d1_1_pipeline_flow.remember.core.schema_store import (
            init_sqlite_schema as _run,
        )
        cursor = self.conn.cursor()
        _run(self.conn, cursor)
        self.conn.commit()

    def _setup_collection(self):
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
            cursor = self.conn.cursor()
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

    def get_stats(self) -> dict:
        """Get memory system statistics"""
        cursor = self.conn.cursor()

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


    def __del__(self):
        """Cleanup"""
        if hasattr(self, 'conn'):
            self.conn.close()

    # ── Delegation to split-out modules ────────────────────────────────────
    from serin.d1_1_pipeline_flow.remember.core.storage.search_store import (
        _build_qdrant_filter,
        _condense_results,
        _merge_candidates,
        _rerank_results_simple,
    )
    from serin.d1_1_pipeline_flow.remember.core.storage.search_store import (
        search_hybrid as _search_hybrid,
    )
    from serin.d1_1_pipeline_flow.remember.core.storage.sqlite_store import (
        cleanup_old_memories,
        get_latest_message,
        get_message_at_position,
        get_message_by_id,
        get_message_count,
        get_messages_around_timestamp,
        get_recent_conversation_from_sqlite,
        get_user_profile,
        get_user_relationships,
        log_activity,
        store_recent_message,
        update_relationship,
        update_user_activity,
        update_user_traits,
        upsert_user,
    )
    from serin.d1_1_pipeline_flow.remember.core.storage.write_store import (
        _build_payload,
        _chunk_content,
        _get_existing_memory_id,
        _is_duplicate,
        _queue_background_jobs,
        generate_memory_id,
    )
    from serin.d1_1_pipeline_flow.remember.core.storage.write_store import (
        add_memory_enhanced as _add_memory_enhanced,
    )

    def search_hybrid(self, query, user_id=None, n_results=5, **filters):
        return self._search_hybrid(query, user_id, n_results, **filters)

    def add_memory_enhanced(self, content, user_id, **kwargs):
        return self._add_memory_enhanced(content, user_id, **kwargs)

    # ── Legacy API wrappers ────────────────────────────────────────────────
    def add_memory(self, content, user_id, username, channel_id, **kwargs):
        return self.add_memory_enhanced(content, user_id, source_message_id=kwargs.get('source_message_id'), username=username, channel_id=channel_id)

    def search_memories(self, query, user_id=None, channel_id=None, limit=10):
        return self.search_hybrid(query, user_id, n_results=limit)

    def get_recent_conversation(self, channel_id=None, user_id=None, limit=20):
        return self.get_recent_conversation_from_sqlite(channel_id, limit)

