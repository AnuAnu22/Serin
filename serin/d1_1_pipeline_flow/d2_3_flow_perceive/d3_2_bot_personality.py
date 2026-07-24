"""
Bot Personality - Opinion & Preference System
The bot has its own preferences, opinions, and can express them naturally.
"""
from __future__ import annotations

import secrets
import sqlite3
from typing import Any

from serin.d1_4_config_base.d2_3_logger import logger


def _rand() -> float:
    return secrets.randbelow(10_000_000) / 10_000_000


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

    def get_preference(self, category: str, item: str) -> dict[str, Any] | None:
        """Get bot's preference for a specific item"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM bot_preferences
            WHERE category = ? AND item = ?
        """, (category, item))

        result = cursor.fetchone()
        return dict(result) if result else None

    def _express_unknown(self, item: str) -> str:
        """Express that bot doesn't have a formed opinion"""
        expressions = [
            f"haven't really thought about {item}",
            f"don't know much about {item}",
            f"no strong feelings on {item}",
            f"never really got into {item}"
        ]
        return secrets.choice(expressions)

    def get_opinion(self, topic: str) -> dict[str, Any] | None:
        """Get bot's opinion on a topic"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM bot_opinions WHERE topic = ?", (topic,))
        result = cursor.fetchone()
        return dict(result) if result else None

    def can_disagree(self, topic: str) -> bool:
        """
        Check if bot should disagree with user's stance.

        Args:
            topic: Topic being discussed

        Returns:
            True if bot should express disagreement
        """
        # Check if bot has an opinion on this topic
        opinion = self.get_opinion(topic)
        if opinion:
            confidence: float = opinion['confidence']
            # Higher confidence means more likely to disagree
            return _rand() < confidence

        # Fallback: 30% chance to disagree if no opinion
        if _rand() < 0.3:
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
        loves: list[str] = []
        likes: list[str] = []
        dislikes: list[str] = []
        hates: list[str] = []

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

        # Cap each category at 7 total for loves/likes, 3 for dislikes/hates
        loves = loves[:7]
        likes = likes[:7]
        dislikes = dislikes[:3]
        hates = hates[:3]

        def _join_items(items: list[str]) -> str:
            if len(items) == 1:
                return items[0]
            if len(items) == 2:
                return f"{items[0]} and {items[1]}"
            return f"{', '.join(items[:-1])}, and {items[-1]}"

        # Create natural sentences
        context_parts: list[str] = []
        if loves:
            context_parts.append(f"I'm really into {_join_items(loves)}")
        if likes:
            likes_text = _join_items(likes)
            context_parts.append(f"{likes_text[0].upper() + likes_text[1:]} are pretty cool too")
        if dislikes:
            context_parts.append(f"Not really into {_join_items(dislikes)}")
        if hates:
            context_parts.append(f"Can't stand {_join_items(hates)}")

        return ". ".join(context_parts) + "." if context_parts else ""

    def __del__(self) -> None:
        """Cleanup"""
        if hasattr(self, 'conn'):
            self.conn.close()
