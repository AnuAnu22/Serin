"""Recent messages cache — SQLite-backed message history.
Extracted from store.py.
"""
import json
from datetime import datetime
from typing import List, Dict, Optional
from serin.config.logger import logger


def store_recent_message(
    self,
    user_id: str,
    username: str,
    channel_id: str,
    content: str,
    message_id: str,
    timestamp: Optional[datetime] = None
    ) -> None:
    """Store recent message in SQLite"""
    cursor = store.conn.cursor()
    try:
        ts = timestamp or datetime.now()
        
        cursor.execute("""
            INSERT INTO recent_messages (message_id, user_id, username, channel_id, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO NOTHING
        """, (message_id, user_id, username, channel_id, content, ts))
        
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
        
        store.conn.commit()
    except Exception as e:
        logger.error(f" Error storing recent message: {e}")

def get_latest_message(store, channel_id: str) -> Optional[Dict]:
        """Get most recent message from a channel"""
        cursor = store.conn.cursor()
        cursor.execute("""
            SELECT message_id, user_id, username, content, timestamp
            FROM recent_messages
            WHERE channel_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (channel_id,))
        
        result = cursor.fetchone()
        return dict(result) if result else None

def get_recent_conversation_from_sqlite(store, channel_id: str, limit: int = 20) -> List[Dict]:
        """Get recent conversation from SQLite (short-term buffer)."""
        cursor = store.conn.cursor()
        try:
            cursor.execute("""
                SELECT user_id, username, content, timestamp
                FROM recent_messages
                WHERE channel_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (channel_id, limit))
            rows = cursor.fetchall()
            messages = []
            for row in reversed(rows):
                messages.append({
                    'user_id': row['user_id'],
                    'username': row['username'],
                    'content': row['content'],
                    'timestamp': row['timestamp'],
                })
            return messages
        except Exception as e:
            logger.error(f" Error reading recent messages: {e}")
            return []

def get_message_count(store, channel_id: str) -> int:
        """Get total message count for a channel"""
        cursor = store.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM recent_messages
            WHERE channel_id = ?
        """, (channel_id,))
        
        return cursor.fetchone()['count']

def get_message_at_position(store, channel_id: str, position: int) -> Optional[Dict]:
        """Get message at specific position (0 = oldest)"""
        cursor = store.conn.cursor()
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
    """Get messages around a timestamp (\u00b1radius)"""
    def safe_datetime_convert(ts):
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except:
                return datetime.now()
        return ts
    
    ts = safe_datetime_convert(timestamp)
    cursor = store.conn.cursor()
    
    cursor.execute("""
        SELECT message_id, user_id, username, content, timestamp
        FROM recent_messages
        WHERE channel_id = ? AND timestamp < ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (channel_id, ts, radius))
    
    before = [dict(row) for row in cursor.fetchall()]
    before.reverse()
    
    cursor.execute("""
        SELECT message_id, user_id, username, content, timestamp
        FROM recent_messages
        WHERE channel_id = ? AND timestamp > ?
        ORDER BY timestamp ASC
        LIMIT ?
    """, (channel_id, ts, radius))
    
    after = [dict(row) for row in cursor.fetchall()]
    
    return before + after

def get_message_by_id(store, message_id: str) -> Optional[Dict]:
        """Get a specific message by its ID"""
        cursor = store.conn.cursor()
        cursor.execute("""
            SELECT message_id, user_id, username, content, timestamp
            FROM recent_messages
            WHERE message_id = ?
        """, (message_id,))
        
        result = cursor.fetchone()
        return dict(result) if result else None

    
def cleanup_old_memories(store, days_old: int = 90, min_importance: float = 0.3) -> None:
        """Remove old, unimportant memories"""
        try:
            cutoff = (datetime.now() - timedelta(days=days_old)).isoformat()
            
            if store.qdrant_client:
                old_memories = store.qdrant_client.scroll(
                    collection_name="memories",
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(key="timestamp_ts", range=models.Range(lt=datetime.fromisoformat(cutoff).timestamp())),
                            models.FieldCondition(key="importance", range=models.Range(lt=min_importance))
                        ]
                    ),
                    limit=1000
                )
                
                if old_memories[0]:
                    memory_ids = [m.id for m in old_memories[0]]
                    
                    store.qdrant_client.delete(
                        collection_name="memories",
                        points_selector=models.Filter(
                            must=[models.HasIdCondition(has_id=memory_ids)]
                        )
                    )
                    
                    if store.bm25_index:
                        store.bm25_index.delete_documents(memory_ids)
                    
                    logger.info(f" Cleaned up {len(memory_ids)} old memories")
                    return len(memory_ids)
            
            return 0
        except Exception as e:
            logger.error(f" Error cleaning memories: {e}")
            return 0
    
