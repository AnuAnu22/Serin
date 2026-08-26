"""SQLite schema initialization — all table DDL.
Extracted from store.py.
"""
import sqlite3

from serin.d1_4_config_base.d2_3_core_logger import logger


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

    # Fact Store — Bayesian belief dynamics schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id TEXT NOT NULL,
            subject_name TEXT,
            claim TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'observation',
            belief REAL DEFAULT 0.5,
            variance REAL DEFAULT 0.25,
            log_odds REAL DEFAULT 0.0,
            first_observed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_confirmed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_challenged TIMESTAMP,
            observation_count INTEGER DEFAULT 1,
            corroboration_count INTEGER DEFAULT 0,
            contradiction_count INTEGER DEFAULT 0,
            primary_source TEXT,
            source_type TEXT DEFAULT 'user_claim',
            state TEXT DEFAULT 'PENDING',
            is_active INTEGER DEFAULT 1,
            claim_hash TEXT UNIQUE
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_facts_subject
        ON facts(subject_id, is_active)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_facts_state
        ON facts(state, is_active)
    """)

    # Fact Observations Log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_id INTEGER,
            observer_id TEXT,
            observation_type TEXT,
            source_type TEXT,
            weight REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
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

    # Per-user affect state — sentiment-driven valence with decay
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_affect (
            user_id TEXT PRIMARY KEY,
            valence REAL NOT NULL DEFAULT 0.0,
            valence_updated REAL NOT NULL,
            familiarity_count INTEGER NOT NULL DEFAULT 0,
            impression_text TEXT,
            impression_updated REAL,
            since_impression INTEGER NOT NULL DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_affect_due_impression
        ON user_affect(since_impression, familiarity_count)
        WHERE since_impression >= 25 AND familiarity_count >= 10
    """)

    # Per-user mood state — relationship-scoped energy/sass/engagement for
    # emotional persistence (CODING_GUIDELINES §4). Deliberately separate
    # from user_affect (sentiment valence) and personality_state (the global
    # default mood) so each table owns exactly one concern: this table holds
    # one mood vector per relationship, keyed by the relationship's user.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_mood_state (
            user_id TEXT PRIMARY KEY,
            energy_level REAL NOT NULL DEFAULT 0.5,
            sass_level REAL NOT NULL DEFAULT 0.5,
            engagement REAL NOT NULL DEFAULT 0.5,
            updated_at REAL NOT NULL
        )
    """)

    # Per-channel dynamics snapshot — Kuramoto/momentum/Hawkes physics state
    # for ConversationDynamicsEngine so conversational rhythm survives restarts
    # (SERIN_VISION "Growth": accumulated state, not a fresh simulation per
    # boot; hot_reloader respawns the bot on every .py change). One row per
    # channel; word_counts/message_times/participants ride in JSON payloads.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel_dynamics (
            channel_id TEXT PRIMARY KEY,
            momentum REAL NOT NULL DEFAULT 0.0,
            phase REAL NOT NULL DEFAULT 0.0,
            frequency REAL NOT NULL DEFAULT 0.0,
            temperature REAL NOT NULL DEFAULT 1.0,
            last_active REAL NOT NULL DEFAULT 0.0,
            total_words INTEGER NOT NULL DEFAULT 0,
            message_times_json TEXT NOT NULL DEFAULT '[]',
            word_counts_json TEXT NOT NULL DEFAULT '{}',
            participants_json TEXT NOT NULL DEFAULT '[]',
            last_action TEXT NOT NULL DEFAULT 'none',
            last_action_time REAL NOT NULL DEFAULT 0.0,
            updated_at REAL NOT NULL
        )
    """)

    # Pipeline run metrics — one row per completed MessagePipeline.process()
    # (edge-A in CONNECTIONS.md). Written by the d5_5_pipeline_metrics
    # recorder via the duck-typed store contract; read by the control panel's
    # /api/metrics/pipeline route. Kept here (authoritative schema) so boot
    # creates it even if the first runs happen before any panel request.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_ts REAL NOT NULL,
            duration_ms REAL NOT NULL,
            user_id TEXT,
            channel_id TEXT,
            halted INTEGER NOT NULL DEFAULT 0,
            halt_reason TEXT NOT NULL DEFAULT '',
            responded INTEGER NOT NULL DEFAULT 0,
            stage_count INTEGER NOT NULL DEFAULT 0,
            stages_json TEXT NOT NULL DEFAULT '[]',
            error TEXT NOT NULL DEFAULT ''
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started "
        "ON pipeline_runs(started_ts)"
    )

    # Self-generated goals — Serin's own persistent cognitive state
    # (SERIN_VISION "Growth"). The engine only owns MACHINERY here: rows are
    # formed/revised/pursued/dropped through the state machine below; the
    # CONTENT of a goal statement is whatever the forming LLM produced and is
    # never curated, filtered, or templated by this code (causality, not
    # performance: pursuit weight comes from salience, never a die roll).
    # One row per goal; goal_evidence is the append-only provenance trail.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            statement TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'FORMING'
                CHECK (status IN ('FORMING','ACTIVE','PAUSED','ACHIEVED',
                                  'DROPPED','SUPERSEDED')),
            salience REAL NOT NULL DEFAULT 0.5,
            origin_provenance TEXT NOT NULL DEFAULT '',
            parent_goal_id INTEGER,
            last_reviewed_at REAL
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_goals_active_salience "
        "ON goals(status, salience DESC)"
    )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goal_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_goal_evidence_goal "
        "ON goal_evidence(goal_id, created_at)"
    )

    # Migration: add state column if table exists without it
    import sqlite3
    for col, dtype in [
        ("state", "TEXT NOT NULL DEFAULT 'PENDING'"),
        ("last_contradicted_at", "TEXT DEFAULT ''"),
        ("contradiction_resolved_at", "TEXT DEFAULT ''"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE beliefs ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError:
            logger.info("Migration: column %s already exists, skipping", col)
        except Exception:
            logger.exception("Migration: ALTER TABLE beliefs.%s failed", col)

    logger.debug(" SQLite schema initialized")
