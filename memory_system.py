"""
Unified Memory System - ChromaDB + SQLite
Everything the bot experiences goes into one searchable memory.
No separate "facts" vs "events" - just memories with context.
"""
import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from thinking_filter import filter_for_memory
import chromadb
from chromadb.utils import embedding_functions
from logger_config import logger
from debug_logger import log_memory


class UnifiedMemorySystem:
    def __init__(self, data_dir: str = "./bot_data"):
        """Initialize ChromaDB for semantic memory + SQLite for structured data"""
        logger.info("🚀 Initializing Unified Memory System")
        
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        # ChromaDB for semantic search (new API)
        chroma_path = os.path.join(data_dir, "chroma_data")
        logger.debug(f"📂 ChromaDB path: {chroma_path}")
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        logger.info("✅ ChromaDB client initialized")
        
        # Use sentence transformers embedding (local)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        # Create/get collections
        try:
            self.memories = self.chroma_client.get_collection(
                name="memories",
                embedding_function=self.embedding_fn
            )
            logger.info("✅ Loaded existing memories collection")
        except Exception:
            self.memories = self.chroma_client.create_collection(
                name="memories",
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("✅ Created new memories collection")
        
        # SQLite for structured data (users, relationships, stats)
        self.db_path = os.path.join(data_dir, "bot_data.db")
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
        self.conn.execute("PRAGMA synchronous=NORMAL")  # Balanced durability/performance
        self._init_sqlite_schema()
        
        # Add memory pressure monitoring
        self._last_memory_check = datetime.now()
        self._memory_warnings = []
        
        logger.info("✅ Memory system ready")
    
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
                personality_traits TEXT,  -- JSON array
                interests TEXT,  -- JSON array
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
                last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                relationship_strength REAL DEFAULT 0,
                UNIQUE(user_a_id, user_b_id)
            )
        """)
        
        # Activity patterns
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
        
        self.conn.commit()
        logger.debug("✅ SQLite schema initialized")
        
        # Memory pressure monitoring
        self._last_memory_check = datetime.now()
        self._memory_warnings = []
    
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
                personality_traits TEXT,  -- JSON array
                interests TEXT,  -- JSON array
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
                last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                relationship_strength REAL DEFAULT 0,
                UNIQUE(user_a_id, user_b_id)
            )
        """)
        
        # Activity patterns
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
        
        # NEW TABLE: Recent messages cache
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
        
        # Create index for fast retrieval
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_recent_channel_time 
            ON recent_messages(channel_id, timestamp DESC)
        """)
        
        self.conn.commit()
        logger.debug("✅ SQLite schema initialized")
        
        # Memory pressure monitoring
        self._last_memory_check = datetime.now()
        self._memory_warnings = []
        
    def check_memory_pressure(self) -> Dict:
        """Check for memory pressure and potential data loss indicators"""
        try:
            current_time = datetime.now()
            time_since_check = (current_time - self._last_memory_check).total_seconds()
            
            # Check every 60 seconds
            if time_since_check < 60:
                return {'status': 'ok', 'message': 'Recent check performed'}
            
            self._last_memory_check = current_time
            
            # Check recent messages table size
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM recent_messages")
            total_messages = cursor.fetchone()[0]
            
            # Check table sizes
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            tables = cursor.fetchall()
            
            table_sizes = {}
            for table in tables:
                table_name = table[0]
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    table_sizes[table_name] = count
                except Exception as e:
                    table_sizes[table_name] = f"Error: {e}"
            
            # ChromaDB memory count
            try:
                chroma_count = self.memories.count()
            except Exception as e:
                chroma_count = f"Error: {e}"
            
            # Check for rapid growth (potential memory pressure)
            warnings = []
            if hasattr(self, '_last_message_count'):
                message_growth = total_messages - self._last_message_count
                if message_growth > 1000:  # More than 1000 new messages since last check
                    warnings.append(f"Rapid message growth: +{message_growth} messages")
            
            self._last_message_count = total_messages
            
            # Memory pressure assessment
            pressure_level = "normal"
            if total_messages > 50000:
                pressure_level = "high"
                warnings.append("High message volume: >50k messages")
            elif total_messages > 25000:
                pressure_level = "moderate"
                warnings.append("Moderate message volume: >25k messages")
            
            return {
                'status': 'ok',
                'timestamp': current_time.isoformat(),
                'total_messages': total_messages,
                'table_sizes': table_sizes,
                'chroma_memories': chroma_count,
                'pressure_level': pressure_level,
                'warnings': warnings,
                'time_since_check_seconds': time_since_check
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }    

    # ========================================================================
    # MEMORY OPERATIONS (ChromaDB)
    # ========================================================================
    
    def add_memory(
        self,
        content: str,
        user_id: str,
        username: str,
        channel_id: str,
        participants: List[str],
        emotional_tone: str = "neutral",
        importance: float = 0.5,
        message_id: str = None
    ) -> str:
        """
        Add a memory to the system. Everything goes here.
        No distinction between facts/events - just memories with context.
        """
        content = filter_for_memory(content)
        try:
            memory_id = f"mem_{user_id}_{int(datetime.now().timestamp() * 1000)}"
            
            metadata = {
                "user_id": user_id,
                "username": username,
                "channel_id": channel_id,
                "participants": json.dumps(participants),
                "emotional_tone": emotional_tone,
                "importance": importance,
                "timestamp": datetime.now().isoformat(),
                "message_id": message_id or ""
            }
            
            self.memories.add(
                documents=[content],
                metadatas=[metadata],
                ids=[memory_id]
            )
            
            logger.debug(f"💾 Stored memory: {content[:50]}...")
            log_memory(content, metadata)
            return memory_id
            
        except Exception as e:
            logger.error(f"❌ Error adding memory: {e}")
            return ""
    
    def search_memories(
        self,
        query: str,
        user_id: str = None,
        channel_id: str = None,
        n_results: int = 5,
        time_decay_days: int = 60
    ) -> List[Dict]:
        """
        Search memories using semantic similarity.
        Returns memories with metadata, sorted by relevance + recency.
        """
        try:
            where_filter = {}
            
            # Build filters
            if user_id:
                where_filter["user_id"] = user_id
            if channel_id:
                where_filter["channel_id"] = channel_id
            
            # Query ChromaDB
            results = self.memories.query(
                query_texts=[query],
                n_results=n_results * 2,  # Get more, then filter by time
                where=where_filter if where_filter else None
            )
            
            if not results or not results['documents'][0]:
                logger.debug("🔍 No memories found")
                return []
            
            # Process results
            memories = []
            now = datetime.now()
            
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i] if 'distances' in results else 0
                
                # Calculate time decay - handle both string and datetime timestamps
                def safe_datetime_convert(ts):
                    """Safely convert timestamp to datetime, handling both string and datetime inputs"""
                    if isinstance(ts, str):
                        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    return ts
                
                timestamp = safe_datetime_convert(metadata['timestamp'])
                age_days = (now - timestamp).days
                
                if age_days > time_decay_days:
                    continue
                
                # Recency boost (newer = higher score)
                recency_score = max(0, 1 - (age_days / time_decay_days))
                
                # Combine similarity + recency + importance
                relevance = (1 - distance) * 0.6 + recency_score * 0.3 + metadata['importance'] * 0.1
                
                memories.append({
                    'content': doc,
                    'username': metadata['username'],
                    'timestamp': metadata['timestamp'],
                    'emotional_tone': metadata['emotional_tone'],
                    'relevance': relevance,
                    'age_days': age_days,
                    'channel_id': metadata['channel_id'],
                    'participants': json.loads(metadata['participants'])
                })
            
            # Sort by relevance
            memories.sort(key=lambda x: x['relevance'], reverse=True)
            
            logger.info(f"🔍 Found {len(memories)} relevant memories")
            return memories[:n_results]
            
        except Exception as e:
            logger.error(f"❌ Error searching memories: {e}")
            return []
    
    def get_recent_conversation(
        self,
        channel_id: str = None,
        user_id: str = None,
        limit: int = 20
    ) -> List[Dict]:
        """Get recent conversation context (last N messages)"""
        try:
            # Get all memories, sort by timestamp
            results = self.memories.get(
                where={"channel_id": channel_id} if channel_id else None,
                limit=limit * 2
            )
            
            if not results or not results['documents']:
                return []
            
            memories = []
            for i, doc in enumerate(results['documents']):
                metadata = results['metadatas'][i]
                memories.append({
                    'content': doc,
                    'username': metadata['username'],
                    'timestamp': metadata['timestamp'],
                    'user_id': metadata['user_id']
                })
            
            # Sort by timestamp (most recent last)
            memories.sort(key=lambda x: x['timestamp'])
            
            return memories[-limit:]
            
        except Exception as e:
            logger.error(f"❌ Error getting recent conversation: {e}")
            return []
    
    # ========================================================================
    # USER MANAGEMENT (SQLite)
    # ========================================================================
    
    def upsert_user(self, user_id: str, username: str, display_name: str = None):
        """Create or update user profile"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (user_id, username, display_name, last_seen)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    display_name = excluded.display_name,
                    last_seen = CURRENT_TIMESTAMP
            """, (user_id, username, display_name or username))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Error upserting user: {e}")
    
    def update_user_activity(self, user_id: str, message_length: int):
        """Update user activity metrics"""
        cursor = self.conn.cursor()
        try:
            # Get current stats
            cursor.execute("SELECT total_messages, avg_message_length FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            if result:
                total_msgs = result['total_messages']
                avg_len = result['avg_message_length']
                
                new_total = total_msgs + 1
                new_avg = ((avg_len * total_msgs) + message_length) / new_total
                
                cursor.execute("""
                    UPDATE users SET
                        total_messages = ?,
                        avg_message_length = ?,
                        last_seen = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (new_total, new_avg, user_id))
                self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Error updating user activity: {e}")
    
    def update_user_traits(self, user_id: str, traits: List[str] = None, interests: List[str] = None):
        """Update user personality traits and interests"""
        cursor = self.conn.cursor()
        try:
            # Get existing
            cursor.execute("SELECT personality_traits, interests FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            if result:
                existing_traits = set(json.loads(result['personality_traits'] or '[]'))
                existing_interests = set(json.loads(result['interests'] or '[]'))
                
                if traits:
                    existing_traits.update(traits)
                if interests:
                    existing_interests.update(interests)
                
                cursor.execute("""
                    UPDATE users SET
                        personality_traits = ?,
                        interests = ?
                    WHERE user_id = ?
                """, (
                    json.dumps(list(existing_traits)),
                    json.dumps(list(existing_interests)),
                    user_id
                ))
                self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Error updating traits: {e}")
    
    def get_user_profile(self, user_id: str) -> Optional[Dict]:
        """Get user profile"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result:
            profile = dict(result)
            profile['personality_traits'] = json.loads(profile['personality_traits'] or '[]')
            profile['interests'] = json.loads(profile['interests'] or '[]')
            return profile
        return None
    
    # ========================================================================
    # RELATIONSHIP MANAGEMENT (SQLite)
    # ========================================================================
    
    def update_relationship(self, user_a_id: str, user_b_id: str, interaction_type: str = 'message'):
        """Update relationship between two users"""
        # Ensure ordering
        if user_a_id > user_b_id:
            user_a_id, user_b_id = user_b_id, user_a_id
        
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO relationships (user_a_id, user_b_id, interaction_count, last_interaction)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(user_a_id, user_b_id) DO UPDATE SET
                    interaction_count = interaction_count + 1,
                    last_interaction = CURRENT_TIMESTAMP
            """, (user_a_id, user_b_id))
            
            if interaction_type == 'mention':
                cursor.execute("""
                    UPDATE relationships SET direct_mentions = direct_mentions + 1
                    WHERE user_a_id = ? AND user_b_id = ?
                """, (user_a_id, user_b_id))
            
            # Calculate relationship strength
            cursor.execute("""
                UPDATE relationships SET
                    relationship_strength = MIN(1.0, 
                        (interaction_count * 1.0 / 100.0) * 0.7 +
                        (direct_mentions * 1.0 / 20.0) * 0.3
                    )
                WHERE user_a_id = ? AND user_b_id = ?
            """, (user_a_id, user_b_id))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Error updating relationship: {e}")
    
    def get_user_relationships(self, user_id: str, min_strength: float = 0.1) -> List[Dict]:
        """Get all relationships for a user"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT r.*, 
                   CASE WHEN r.user_a_id = ? THEN ub.username ELSE ua.username END as other_username,
                   CASE WHEN r.user_a_id = ? THEN r.user_b_id ELSE r.user_a_id END as other_user_id
            FROM relationships r
            LEFT JOIN users ua ON r.user_a_id = ua.user_id
            LEFT JOIN users ub ON r.user_b_id = ub.user_id
            WHERE (r.user_a_id = ? OR r.user_b_id = ?)
              AND r.relationship_strength >= ?
            ORDER BY r.relationship_strength DESC
        """, (user_id, user_id, user_id, user_id, min_strength))
        
        return [dict(row) for row in cursor.fetchall()]
    
    # ========================================================================
    # ACTIVITY TRACKING
    # ========================================================================
    
    def log_activity(self, user_id: str, channel_id: str, message_length: int, sentiment: float):
        """Log user activity for pattern analysis"""
        cursor = self.conn.cursor()
        try:
            now = datetime.now()
            cursor.execute("""
                INSERT INTO activity_log 
                (user_id, channel_id, message_length, sentiment_score, hour_of_day, day_of_week)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, channel_id, message_length, sentiment, now.hour, now.weekday()))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Error logging activity: {e}")
    
    # ========================================================================
    # STATS & MAINTENANCE
    # ========================================================================
    
    def get_stats(self) -> Dict:
        """Get memory system statistics"""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM relationships WHERE relationship_strength > 0.5")
            strong_relationships = cursor.fetchone()['count']
            
            memory_count = self.memories.count()
            
            return {
                'total_users': total_users,
                'total_memories': memory_count,
                'strong_relationships': strong_relationships
            }
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {}
    
    def cleanup_old_memories(self, days_old: int = 90, min_importance: float = 0.3):
        """Remove old, unimportant memories"""
        try:
            cutoff = (datetime.now() - timedelta(days=days_old)).isoformat()
            
            # Get all memories
            all_memories = self.memories.get()
            
            if not all_memories or not all_memories['ids']:
                return 0
            
            # Find memories to delete
            to_delete = []
            for i, metadata in enumerate(all_memories['metadatas']):
                if metadata['timestamp'] < cutoff and metadata['importance'] < min_importance:
                    to_delete.append(all_memories['ids'][i])
            
            if to_delete:
                self.memories.delete(ids=to_delete)
                logger.info(f"🗑️ Cleaned up {len(to_delete)} old memories")
                return len(to_delete)
            
            return 0
        except Exception as e:
            logger.error(f"❌ Error cleaning memories: {e}")
            return 0
    
    def __del__(self):
        """Cleanup"""
        if hasattr(self, 'conn'):
            self.conn.close()

    def store_recent_message(
        self,
        user_id: str,
        username: str,
        channel_id: str,
        content: str,
        message_id: str,
        timestamp: datetime = None
    ):
        """Store recent message in SQLite (NOT ChromaDB)"""
        cursor = self.conn.cursor()
        try:
            ts = timestamp or datetime.now()
            
            cursor.execute("""
                INSERT INTO recent_messages (message_id, user_id, username, channel_id, content, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO NOTHING
            """, (message_id, user_id, username, channel_id, content, ts))
            
            # Keep only last 20,000 messages per channel
            cursor.execute("""
                DELETE FROM recent_messages
                WHERE channel_id = ?
                AND id NOT IN (
                    SELECT id FROM recent_messages
                    WHERE channel_id = ?
                    ORDER BY timestamp DESC
                    LIMIT 20000
                )
            """, (channel_id, channel_id))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Error storing recent message: {e}")

    def get_latest_message(self, channel_id: str) -> Optional[Dict]:
        """Get most recent message from a channel"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT message_id, user_id, username, content, timestamp
            FROM recent_messages
            WHERE channel_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (channel_id,))
        
        result = cursor.fetchone()
        return dict(result) if result else None

    def get_message_count(self, channel_id: str) -> int:
        """Get total message count for a channel"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM recent_messages
            WHERE channel_id = ?
        """, (channel_id,))
        
        return cursor.fetchone()['count']

    def get_message_at_position(self, channel_id: str, position: int) -> Optional[Dict]:
        """Get message at specific position (0 = oldest)"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT message_id, user_id, username, content, timestamp
            FROM recent_messages
            WHERE channel_id = ?
            ORDER BY timestamp ASC
            LIMIT 1 OFFSET ?
        """, (channel_id, position))
        
        result = cursor.fetchone()
        return dict(result) if result else None

    def get_messages_around_timestamp(
        self,
        channel_id: str,
        timestamp,
        radius: int = 2
    ) -> List[Dict]:
        """Get messages around a timestamp (±radius)"""
        # Handle both datetime objects and ISO format strings
        def safe_datetime_convert(ts):
            """Safely convert timestamp to datetime, handling both string and datetime inputs"""
            if isinstance(ts, str):
                return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            return ts
        
        ts = safe_datetime_convert(timestamp)
        cursor = self.conn.cursor()
        
        # Get messages before
        cursor.execute("""
            SELECT message_id, user_id, username, content, timestamp
            FROM recent_messages
            WHERE channel_id = ? AND timestamp < ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (channel_id, ts, radius))
        
        before = [dict(row) for row in cursor.fetchall()]
        before.reverse()
        
        # Get messages after
        cursor.execute("""
            SELECT message_id, user_id, username, content, timestamp
            FROM recent_messages
            WHERE channel_id = ? AND timestamp > ?
            ORDER BY timestamp ASC
            LIMIT ?
        """, (channel_id, ts, radius))
        
        after = [dict(row) for row in cursor.fetchall()]
        
        return before + after

    def get_message_by_id(self, message_id: str) -> Optional[Dict]:
        """Get a specific message by its ID"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT message_id, user_id, username, content, timestamp
            FROM recent_messages
            WHERE message_id = ?
        """, (message_id,))
        
        result = cursor.fetchone()
        return dict(result) if result else None
