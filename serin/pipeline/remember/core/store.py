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
import subprocess
import time as time_mod
from typing import Any

from serin.config.config import config
from serin.logger import logger
from serin.pipeline.remember.core.bm25_index import SQLiteBM25Index
from serin.pipeline.remember.knowledge.beliefs import BeliefStore
from serin.pipeline.remember.knowledge.evidence import FactStore

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
        """Try connecting to Qdrant, then fall back to Docker auto-start if configured."""
        for attempt in range(max_attempts):
            try:
                client = QdrantClient(host=host, port=port, timeout=5.0)
                client.get_collections()
                logger.info(f" Qdrant client connected to {host}:{port}")
                return client
            except Exception as e:
                if attempt < max_attempts - 1:
                    logger.warning(f" Qdrant connection failed (attempt {attempt+1}/{max_attempts}): {e}. Retrying...")
                    time_mod.sleep(2)
                else:
                    logger.error(f" Failed to connect to Qdrant after {max_attempts} attempts: {e}")

        if config.QDRANT_USE_DOCKER or host in ("localhost", "127.0.0.1"):
            logger.info(" Attempting Qdrant Docker auto-start...")
            return QdrantMemorySystem._ensure_qdrant_docker(host, port)
        return None

    @staticmethod
    def _find_qdrant_container() -> str | None:
        """Find any existing Qdrant container (by configured name or image)."""
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={config.QDRANT_DOCKER_CONTAINER_NAME}", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=10,
            )
            if config.QDRANT_DOCKER_CONTAINER_NAME in result.stdout:
                return config.QDRANT_DOCKER_CONTAINER_NAME
        except Exception:
            pass

        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"ancestor={config.QDRANT_DOCKER_IMAGE}", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=10,
            )
            names = result.stdout.strip().splitlines()
            if names:
                return names[0]
        except Exception:
            pass

        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Image}}"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) == 2 and "qdrant" in parts[1].lower():
                    return parts[0]
        except Exception:
            pass

        return None

    @staticmethod
    def _ensure_qdrant_docker(host: str, port: int) -> Any | None:
        """Auto-start Qdrant via Docker if container exists or can be created."""
        container_name = QdrantMemorySystem._find_qdrant_container()
        image = config.QDRANT_DOCKER_IMAGE

        try:
            if container_name:
                logger.info(f" Starting Qdrant container '{container_name}'...")
                subprocess.run(["docker", "start", container_name], check=True, capture_output=True, timeout=30)
            else:
                logger.info(f" Creating Qdrant container '{config.QDRANT_DOCKER_CONTAINER_NAME}'...")
                subprocess.run(
                    [
                        "docker", "run", "-d",
                        "--name", config.QDRANT_DOCKER_CONTAINER_NAME,
                        "--restart", "unless-stopped",
                        "-p", f"{port}:6333",
                        "-p", "6334:6334",
                        "-v", f"{config.QDRANT_DOCKER_CONTAINER_NAME}_data:/qdrant/storage",
                        image,
                    ],
                    check=True, capture_output=True, timeout=120,
                )
                container_name = config.QDRANT_DOCKER_CONTAINER_NAME

            logger.info(" Waiting for Qdrant to accept connections...")
            for _ in range(30):
                time_mod.sleep(1)
                try:
                    client = QdrantClient(host=host, port=port, timeout=5.0)
                    client.get_collections()
                    logger.success(f" Qdrant Docker container ready on {host}:{port}")
                    return client
                except Exception:
                    pass
            logger.error(" Qdrant container started but not accepting connections after 30s")
        except FileNotFoundError:
            logger.warning(" Docker not found — cannot auto-start Qdrant")
        except subprocess.TimeoutExpired:
            logger.warning(" Docker command timed out")
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode().strip() if e.stderr else str(e)
            logger.error(f" Docker command failed (exit {e.returncode}): {stderr}")
        except Exception as e:
            logger.error(f" Docker auto-start failed: {e}")

        return None

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
                        pass
                shutil.move(self.db_path, backup_path)
                # Also move WAL/SHM files if they exist
                for ext in ['-wal', '-shm']:
                    if os.path.exists(self.db_path + ext):
                        shutil.move(self.db_path + ext, backup_path + ext)
            except Exception as e:
                logger.error(f" Error moving corrupt DB: {e}")

    def _init_sqlite_schema(self):
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
            pass
        try:
            cursor.execute("ALTER TABLE beliefs ADD COLUMN last_contradicted_at TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE beliefs ADD COLUMN contradiction_resolved_at TEXT DEFAULT ''")
        except Exception:
            pass

        self.conn.commit()
        logger.debug(" SQLite schema initialized")

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
                    pass

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
    from serin.pipeline.remember.core.search_store import (
        _build_qdrant_filter,
        _condense_results,
        _merge_candidates,
        _rerank_results_simple,
    )
    from serin.pipeline.remember.core.search_store import (
        search_hybrid as _search_hybrid,
    )
    from serin.pipeline.remember.core.sqlite_store import (
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
    from serin.pipeline.remember.core.write_store import (
        _build_payload,
        _chunk_content,
        _get_existing_memory_id,
        _is_duplicate,
        _queue_background_jobs,
        generate_memory_id,
    )
    from serin.pipeline.remember.core.write_store import (
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

