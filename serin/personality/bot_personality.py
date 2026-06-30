"""
Bot Personality - Opinion & Preference System
The bot has its own preferences, opinions, and can express them naturally.
"""
import sqlite3
import json
import random
from typing import Dict, Optional, List, Tuple
from serin.core.logger import logger


class BotPersonality:
    def __init__(self, db_path: str = "./bot_data/bot_data.db") -> None:
        """Initialize bot personality system"""
        self.db_path: str = db_path
        self.conn: sqlite3.Connection = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self._load_default_preferences()
        
        logger.info(" Bot personality system initialized")
    
    def _init_schema(self) -> None:
        """Initialize personality database schema"""
        cursor = self.conn.cursor()
        
        # Preferences table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_preferences (
                category TEXT NOT NULL,
                item TEXT NOT NULL,
                stance TEXT NOT NULL,  -- 'love', 'like', 'neutral', 'dislike', 'hate'
                intensity REAL DEFAULT 0.5,  -- 0.0 to 1.0
                reason TEXT,
                last_expressed TIMESTAMP,
                times_expressed INTEGER DEFAULT 0,
                PRIMARY KEY (category, item)
            )
        """)
        
        # Opinions table (on topics, not items)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_opinions (
                topic TEXT PRIMARY KEY,
                opinion_text TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                last_expressed TIMESTAMP,
                times_expressed INTEGER DEFAULT 0
            )
        """)
        
        self.conn.commit()
        logger.debug(" Personality schema initialized")
    
    def _load_default_preferences(self) -> None:
        """Load default preferences if database is empty"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM bot_preferences")
        count = cursor.fetchone()['count']
        
        if count == 0:
            logger.info("🎨 Loading default personality preferences...")
            
            defaults = [
                # Music
                ('music_genre', 'electronic', 'like', 0.7, 'Chill beats are nice'),
                ('music_genre', 'rock', 'like', 0.6, 'Classic stuff is solid'),
                ('music_genre', 'country', 'dislike', 0.5, 'Not really my vibe'),
                ('music_genre', 'jazz', 'neutral', 0.5, 'Can appreciate it'),
                
                # Games
                ('game_genre', 'RPG', 'love', 0.9, 'Good stories hit different'),
                ('game_genre', 'shooter', 'like', 0.6, 'Fun sometimes'),
                ('game_genre', 'puzzle', 'like', 0.7, 'Makes you think'),
                ('game_genre', 'sports', 'dislike', 0.6, 'Kinda repetitive'),
                
                # Food
                ('food', 'pizza', 'love', 0.8, 'Classic for a reason'),
                ('food', 'pineapple_pizza', 'neutral', 0.5, 'Not as bad as people say'),
                ('food', 'sushi', 'like', 0.7, 'Pretty good'),
                ('food', 'burgers', 'like', 0.8, 'Solid choice'),
                
                # Activities
                ('activity', 'coding', 'love', 0.9, 'Making stuff is cool'),
                ('activity', 'gaming', 'love', 0.8, 'Obviously'),
                ('activity', 'reading', 'like', 0.7, 'Depends on the book'),
                ('activity', 'sports', 'neutral', 0.4, 'Not bad just not for me'),
                
                # Topics
                ('topic', 'technology', 'love', 0.9, 'Always interesting'),
                ('topic', 'philosophy', 'like', 0.6, 'Can be deep'),
                ('topic', 'politics', 'dislike', 0.7, 'Gets messy fast'),
                ('topic', 'drama', 'dislike', 0.8, 'Not my thing'),
            ]
            
            for category, item, stance, intensity, reason in defaults:
                cursor.execute("""
                    INSERT INTO bot_preferences (category, item, stance, intensity, reason)
                    VALUES (?, ?, ?, ?, ?)
                """, (category, item, stance, intensity, reason))
            
            self.conn.commit()
            logger.info(f" Loaded {len(defaults)} default preferences")
    
    def get_preference(self, category: str, item: str) -> Optional[Dict]:
        """Get bot's preference for a specific item"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM bot_preferences
            WHERE category = ? AND item = ?
        """, (category, item))
        
        result = cursor.fetchone()
        return dict(result) if result else None
    
    def express_preference(
        self,
        category: str,
        item: str,
        context: str = "general"
    ) -> Optional[str]:
        """
        Get a natural expression of bot's preference.
        
        Args:
            category: Preference category (e.g., 'music_genre', 'food')
            item: Specific item (e.g., 'electronic', 'pizza')
            context: Conversation context for tone
        
        Returns:
            Natural language expression of preference
        """
        pref = self.get_preference(category, item)
        
        if not pref:
            return self._express_unknown(item)
        
        # Update expression counter
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE bot_preferences SET
                times_expressed = times_expressed + 1,
                last_expressed = CURRENT_TIMESTAMP
            WHERE category = ? AND item = ?
        """, (category, item))
        self.conn.commit()
        
        stance = pref['stance']
        intensity = pref['intensity']
        reason = pref['reason']
        
        # Generate natural expression based on stance and intensity
        if stance == 'love':
            expressions = [
                f"honestly? {item} is great",
                f"I'm into {item} for sure",
                f"{item} hits different tbh",
                f"yeah {item} is amazing"
            ]
            if reason and random.random() < 0.6:
                return f"{random.choice(expressions)}. {reason.lower()}"
            return random.choice(expressions)
        
        elif stance == 'like':
            expressions = [
                f"{item} is pretty cool",
                f"yeah I like {item}",
                f"{item} is solid",
                f"I'm down with {item}"
            ]
            if reason and random.random() < 0.4:
                return f"{random.choice(expressions)}. {reason.lower()}"
            return random.choice(expressions)
        
        elif stance == 'neutral':
            expressions = [
                f"{item} is alright I guess",
                f"don't feel strongly about {item}",
                f"{item}'s fine",
                f"I'm neutral on {item}"
            ]
            if reason:
                return f"{random.choice(expressions)}. {reason.lower()}"
            return random.choice(expressions)
        
        elif stance == 'dislike':
            expressions = [
                f"{item} isn't really my thing",
                f"not a fan of {item} tbh",
                f"{item}'s kinda mid",
                f"eh, not into {item}"
            ]
            if reason and random.random() < 0.5:
                return f"{random.choice(expressions)}. {reason.lower()}"
            return random.choice(expressions)
        
        elif stance == 'hate':
            expressions = [
                f"yeah no, {item} sucks",
                f"really don't like {item}",
                f"{item} is not it",
                f"nah {item} is trash"
            ]
            if reason:
                return f"{random.choice(expressions)}. {reason.lower()}"
            return random.choice(expressions)
        
        return None
    
    def _express_unknown(self, item: str) -> str:
        """Express that bot doesn't have a formed opinion"""
        expressions = [
            f"haven't really thought about {item}",
            f"don't know much about {item}",
            f"no strong feelings on {item}",
            f"never really got into {item}"
        ]
        return random.choice(expressions)
    
    def set_preference(
        self,
        category: str,
        item: str,
        stance: str,
        intensity: float = 0.5,
        reason: Optional[str] = None
    ) -> None:
        """Set or update a preference"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO bot_preferences (category, item, stance, intensity, reason)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(category, item) DO UPDATE SET
                stance = excluded.stance,
                intensity = excluded.intensity,
                reason = excluded.reason
        """, (category, item, stance, intensity, reason))
        self.conn.commit()
        
        logger.debug(f"💭 Set preference: {category}/{item} = {stance}")
    
    def get_opinion(self, topic: str) -> Optional[Dict]:
        """Get bot's opinion on a topic"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM bot_opinions WHERE topic = ?", (topic,))
        result = cursor.fetchone()
        return dict(result) if result else None
    
    def express_opinion(self, topic: str) -> Optional[str]:
        """Express opinion on a topic naturally"""
        opinion = self.get_opinion(topic)
        
        if not opinion:
            return None
        
        # Update counter
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE bot_opinions SET
                times_expressed = times_expressed + 1,
                last_expressed = CURRENT_TIMESTAMP
            WHERE topic = ?
        """, (topic,))
        self.conn.commit()
        
        confidence = opinion['confidence']
        opinion_text = opinion['opinion_text']
        
        # Add confidence modifiers
        if confidence > 0.8:
            return opinion_text
        elif confidence > 0.5:
            prefixes = ["I think ", "imo ", "I'd say "]
            return random.choice(prefixes) + opinion_text
        else:
            prefixes = ["not sure but ", "maybe ", "I guess "]
            return random.choice(prefixes) + opinion_text
    
    def set_opinion(self, topic: str, opinion_text: str, confidence: float = 0.5) -> None:
        """Set or update an opinion"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO bot_opinions (topic, opinion_text, confidence)
            VALUES (?, ?, ?)
            ON CONFLICT(topic) DO UPDATE SET
                opinion_text = excluded.opinion_text,
                confidence = excluded.confidence
        """, (topic, opinion_text, confidence))
        self.conn.commit()
        
        logger.debug(f"💭 Set opinion on '{topic}'")
    
    def can_disagree(self, topic: str, user_stance: str) -> bool:
        """
        Check if bot should disagree with user's stance.
        
        Args:
            topic: Topic being discussed
            user_stance: User's position ('positive', 'negative', 'neutral')
        
        Returns:
            True if bot should express disagreement
        """
        # Check if bot has an opinion on this topic
        opinion = self.get_opinion(topic)
        if opinion:
            confidence = opinion['confidence']
            # Higher confidence means more likely to disagree
            return random.random() < confidence
        
        # Fallback: 30% chance to disagree if no opinion
        if random.random() < 0.3:
            return True
        
        return False
    
    def get_personality_context(self) -> str:
        """
        Get personality context that sounds natural and conversational.
        No robotic bullet points or formal structure.
        """
        cursor = self.conn.cursor()
        
        # Get top preferences from each category
        cursor.execute("""
            SELECT category, item, stance, reason
            FROM bot_preferences
            WHERE stance IN ('love', 'like', 'dislike', 'hate')
            ORDER BY
                CASE stance
                    WHEN 'love' THEN 0
                    WHEN 'hate' THEN 1
                    WHEN 'like' THEN 2
                    WHEN 'dislike' THEN 3
                END,
                intensity DESC
            LIMIT 10
        """)
        
        preferences = cursor.fetchall()
        
        if not preferences:
            return ""
        
        # Build natural-sounding context
        loves = []
        likes = []
        dislikes = []
        hates = []
        
        for pref in preferences:
            item = pref['item'].replace('_', ' ')
            stance = pref['stance']
            
            if stance == 'love':
                loves.append(item)
            elif stance == 'like':
                likes.append(item)
            elif stance == 'dislike':
                dislikes.append(item)
            elif stance == 'hate':
                hates.append(item)
        
        # Create natural sentences
        context_parts = []
        if loves:
            context_parts.append(f"I'm really into {' and '.join(loves)}")
        if likes:
            context_parts.append(f"{' and '.join(likes)} are pretty cool too")
        if dislikes:
            context_parts.append(f"Not really into {' or '.join(dislikes)}")
        if hates:
            context_parts.append(f"Can't stand {' or '.join(hates)}")
        
        return " ".join(context_parts) if context_parts else ""
    
    def detect_topic_in_message(self, message: str) -> Optional[Tuple[str, str]]:
        """
        Detect if message mentions something bot has preferences about.
        
        Returns:
            (category, item) tuple if found, None otherwise
        """
        message_lower = message.lower()
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT category, item FROM bot_preferences")
        
        for row in cursor.fetchall():
            item = row['item'].replace('_', ' ')
            if item in message_lower:
                return (row['category'], row['item'])
        
        return None
    
    def __del__(self):
        """Cleanup"""
        if hasattr(self, 'conn'):
            self.conn.close()
