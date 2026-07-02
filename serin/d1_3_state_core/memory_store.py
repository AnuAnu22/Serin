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
from typing import Any

from serin.d1_3_state_core.bm25_index import SQLiteBM25Index
from serin.d1_3_state_core.logger import logger
from serin.d1_3_state_core.memory.belief_store import BeliefStore
from serin.d1_3_state_core.memory.evidence_store import FactStore

# Qdrant imports
try:
    from qdrant_client import QdrantClient
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

        # Initialize Qdrant client with retry
        self.qdrant_client: QdrantClient | None = None
        if QDRANT_AVAILABLE:
            for attempt in range(3):
                try:
                    self.qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port, timeout=5)
                    # Test connection
                    self.qdrant_client.get_collections()
                    logger.info(f" Qdrant client connected to {qdrant_host}:{qdrant_port}")
                    break
                except Exception as e:
                    if attempt < 2:
                        logger.warning(f" Qdrant connection failed (attempt {attempt+1}/3): {e}. Retrying...")
                        time_mod.sleep(2)
                    else:
                        logger.error(f" Failed to connect to Qdrant after 3 attempts: {e}")
                        self.qdrant_client = None
        else:
            self.qdrant_client = None

        # Initialize embedding service
        self.embedding_model: SentenceTransformer | None = None
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
        self.bm25_index: SQLiteBM25Index | None = None
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
        self.background_jobs: list[Any] = []

        logger.info(" Qdrant Memory System ready")

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
                        logger.exception("Failed to close corrupt SQLite connection")
                shutil.move(self.db_path, backup_path)
                # Also move WAL/SHM files if they exist
                for ext in ['-wal', '-shm']:
                    if os.path.exists(self.db_path + ext):
                        shutil.move(self.db_path + ext, backup_path + ext)
            except Exception as e:
                logger.error(f" Error moving corrupt DB: {e}")

    def _init_sqlite_schema(self) -> None:
        """Initialize SQLite tables for structured data"""
        cursor = self.conn.cursor()

        # User profiles
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                display_name TEXT,
                total_messages INTEGER DEFAULT 0,
                avg_message_length REAL DEFAULT 0,
                personality_traits TEXT,
                interests TEXT,
                communication_style TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Relationships
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_a_id TEXT NOT NULL,
                user_b_id TEXT NOT NULL,
                interaction_count INTEGER DEFAULT 0,
                direct_mentions INTEGER DEFAULT 0,
                relationship_strength REAL DEFAULT 0.0,
                last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_a_id, user_b_id)
            )
        """)

        # Activity logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                channel_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_length INTEGER,
                sentiment_score REAL,
                hour_of_day INTEGER,
                day_of_week INTEGER
            )
        """)

        # BM25 Search Index (SQLite FTS)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                id,
                text,
                person_id,
                channel_id,
                memory_type,
                content=memories,
                content_rowid=id
            )
        """)

        # Background Job Queue
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS background_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                memory_id TEXT,
                payload TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                priority INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0
            )
        """)

        # Qdrant Collection Metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS qdrant_collections (
                collection_name TEXT PRIMARY KEY,
                vector_size INTEGER NOT NULL,
                distance_metric TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)

        # Memory Statistics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                total_memories INTEGER DEFAULT 0,
                total_embeddings INTEGER DEFAULT 0,
                avg_embedding_size REAL DEFAULT 0,
                search_count INTEGER DEFAULT 0,
                ingestion_count INTEGER DEFAULT 0,
                UNIQUE(date)
            )
        """)

        # Recent messages cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_recent_channel_time
            ON recent_messages(channel_id, timestamp DESC)
        """)

        # Fact Store
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'observation',
                confidence REAL DEFAULT 0.5,
                source_message_id TEXT,
                source_user_id TEXT,
                source_username TEXT DEFAULT '',
                source_type TEXT DEFAULT 'user_claim',
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                superseded_by TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_facts_category
            ON facts(category, is_active)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_facts_active
            ON facts(is_active, confidence DESC)
        """)

        # Belief Store
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS beliefs (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'inference',
                state TEXT NOT NULL DEFAULT 'PENDING',
                confidence REAL DEFAULT 0.5,
                supporting_fact_ids TEXT DEFAULT '[]',
                contradicting_fact_ids TEXT DEFAULT '[]',
                evidence_count INTEGER DEFAULT 1,
                claim_count INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_contradicted_at TEXT DEFAULT '',
                contradiction_resolved_at TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_beliefs_confidence
            ON beliefs(confidence DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_beliefs_state
            ON beliefs(state, is_active)
        """)

        # Migration: add state column if table exists without it
        try:
            cursor.execute("ALTER TABLE beliefs ADD COLUMN state TEXT NOT NULL DEFAULT 'PENDING'")
        except Exception:
            logger.exception("Migration: ALTER TABLE beliefs.state failed (column may already exist)")
        try:
            cursor.execute("ALTER TABLE beliefs ADD COLUMN last_contradicted_at TEXT DEFAULT ''")
        except Exception:
            logger.exception("Migration: ALTER TABLE beliefs.last_contradicted_at failed (column may already exist)")
        try:
            cursor.execute("ALTER TABLE beliefs ADD COLUMN contradiction_resolved_at TEXT DEFAULT ''")
        except Exception:
            logger.exception("Migration: ALTER TABLE beliefs.contradiction_resolved_at failed (column may already exist)")

        self.conn.commit()
        logger.debug(" SQLite schema initialized")

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

    def get_stats(self) -> dict[str, Any]:
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
                    logger.exception("Failed to count memories in Qdrant")

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


