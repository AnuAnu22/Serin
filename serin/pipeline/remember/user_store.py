"""User management methods — profiles, traits, relationships.
Extracted from store.py.
"""
import json
from typing import List, Dict, Optional
from serin.config.logger import logger


def upsert_user(store, user_id: str, username: str, display_name: str = None) -> None:
        """Create or update user profile"""
        cursor = store.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (user_id, username, display_name, last_seen)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    display_name = excluded.display_name,
                    last_seen = CURRENT_TIMESTAMP
            """, (user_id, username, display_name or username))
            store.conn.commit()
        except Exception as e:
            logger.error(f" Error upserting user: {e}")
    
def update_user_activity(store, user_id: str, message_length: int) -> None:
        """Update user activity metrics"""
        cursor = store.conn.cursor()
        try:
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
                store.conn.commit()
        except Exception as e:
            logger.error(f" Error updating user activity: {e}")
    
def get_user_profile(store, user_id: str) -> Optional[Dict]:
        """Get user profile"""
        cursor = store.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result:
            profile = dict(result)
            profile['personality_traits'] = json.loads(profile['personality_traits'] or '[]')
            profile['interests'] = json.loads(profile['interests'] or '[]')
            return profile
        return None
    
def update_user_traits(store, user_id: str, traits: Optional[List[str]] = None, interests: Optional[List[str]] = None) -> None:
        """Update user personality traits and interests"""
        cursor = store.conn.cursor()
        try:
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
                store.conn.commit()
        except Exception as e:
            logger.error(f" Error updating traits: {e}")
    
def log_activity(store, user_id: str, channel_id: str, message_length: int, sentiment: float) -> None:
        """Log user activity for pattern analysis"""
        cursor = store.conn.cursor()
        try:
            now = datetime.now()
            cursor.execute("""
                INSERT INTO activity_log 
                (user_id, channel_id, message_length, sentiment_score, hour_of_day, day_of_week)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, channel_id, message_length, sentiment, now.hour, now.weekday()))
            store.conn.commit()
        except Exception as e:
            logger.error(f" Error logging activity: {e}")
    
def update_relationship(store, user_a_id: str, user_b_id: str, interaction_type: str = 'message') -> None:
        """Update relationship between two users"""
        if user_a_id > user_b_id:
            user_a_id, user_b_id = user_b_id, user_a_id
        
        cursor = store.conn.cursor()
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
            
            cursor.execute("""
                UPDATE relationships SET
                    relationship_strength = MIN(1.0, 
                        (interaction_count * 1.0 / 100.0) * 0.7 +
                        (direct_mentions * 1.0 / 20.0) * 0.3
                    )
                WHERE user_a_id = ? AND user_b_id = ?
            """, (user_a_id, user_b_id))
            
            store.conn.commit()
        except Exception as e:
            logger.error(f" Error updating relationship: {e}")
    
def get_user_relationships(store, user_id: str, min_strength: float = 0.1) -> List[Dict]:
        """Get all relationships for a user"""
        cursor = store.conn.cursor()
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
    # Stats & Maintenance
    # ========================================================================
    
