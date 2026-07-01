"""SQLite schema initialization — all table DDL.
Extracted from store.py.
"""
import sqlite3

from serin.logger import logger


def init_sqlite_schema(conn: sqlite3.Connection, cursor: sqlite3.Cursor) -> None:
    """Initialize SQLite tables for structured data"""

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

    logger.debug(" SQLite schema initialized")
