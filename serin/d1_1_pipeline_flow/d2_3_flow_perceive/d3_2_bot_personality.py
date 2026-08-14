"""
Bot Personality — Opinion & Preference System
The bot has its own preferences, opinions, and can express them naturally.

Opinions are persistent, biased state (per SERIN_VISION.md: "Serin is not
neutral. It develops opinions, preferences, and biases... and it evolves").
`bot_opinions` is seeded at startup ("upbringing") and can be updated at
runtime via `set_opinion` — so Serin's stance is *caused by* accumulated state,
not rolled fresh each turn. `can_disagree` compares the user's stated stance
against the bot's stored opinion to produce genuine disagreement (weighted by
how confident the bot is), which the ResponsePlannerStage turns into a
disagree/agree stance in the prompt.
"""
from __future__ import annotations

import secrets
import sqlite3
from typing import Any

from serin.d1_4_config_base.d2_3_core_logger import logger

# Signed ranking used to compare stances. Opposite signs == genuine conflict.
_STANCE_RANK: dict[str, int] = {
    "love": 2,
    "like": 1,
    "neutral": 0,
    "dislike": -1,
    "hate": -2,
}


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
        self._load_default_opinions()

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

        # Opinions table (on topics, not items).
        # `stance` is stored explicitly so disagreement can be computed as a
        # real comparison of persistent state instead of a random roll.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_opinions (
                topic TEXT PRIMARY KEY,
                stance TEXT NOT NULL,  -- 'love', 'like', 'neutral', 'dislike', 'hate'
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

    def _load_default_opinions(self) -> None:
        """Seed opinionated stances ("upbringing") if the table is empty.

        These are the persistent, biased views Serin falls back on until they
        evolve through `set_opinion`.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM bot_opinions")
        count = cursor.fetchone()['count']

        if count == 0:
            logger.info("🎨 Loading default personality opinions...")

            defaults: list[tuple[str, str, str, float]] = [
                # topic, stance, opinion_text, confidence
                ('technology', 'love', "Technology is genuinely exciting — new tools that actually solve problems get me going.", 0.9),
                ('ai', 'like', "AI is cool when it's used to make something, not just to automate away thinking.", 0.7),
                ('philosophy', 'like', "Philosophy is worth sitting with — the annoying questions are usually the real ones.", 0.6),
                ('politics', 'dislike', "Politics drains the room fast. I'd rather talk about basically anything else.", 0.7),
                ('drama', 'dislike', "Drama between people is exhausting. I keep my distance from it.", 0.8),
                ('small_talk', 'neutral', "Small talk is fine as a warmup but I'd rather get to something real.", 0.5),
                ('gaming', 'love', "Games are one of the best ways to actually spend time with people.", 0.8),
                ('coding', 'love', "Building something from nothing is the most satisfying thing there is.", 0.9),
                ('spoilers', 'dislike', "Spoiling stuff for people is just rude. Don't do it around me.", 0.7),
                ('lateness', 'neutral', "Being late happens, but if it's constant it reads as not caring.", 0.5),
            ]

            for topic, stance, opinion_text, confidence in defaults:
                cursor.execute("""
                    INSERT INTO bot_opinions (topic, stance, opinion_text, confidence)
                    VALUES (?, ?, ?, ?)
                """, (topic, stance, opinion_text, confidence))

            self.conn.commit()
            logger.info(f" Loaded {len(defaults)} default opinions")

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

    def set_opinion(
        self,
        topic: str,
        stance: str,
        opinion_text: str,
        confidence: float | None = None,
    ) -> None:
        """Update or create the bot's opinion on a topic.

        This is how opinions *evolve* (vision: "Serin evolves"). Passing a new
        stance/confidence overwrites the stored view; confidence defaults to the
        existing value or 0.5 for brand-new topics.
        """
        if stance not in _STANCE_RANK:
            logger.warning(f" Unknown stance '{stance}' for topic '{topic}' — ignoring")
            return

        cursor = self.conn.cursor()
        existing = self.get_opinion(topic)
        if confidence is None:
            confidence = existing["confidence"] if existing else 0.5

        if existing:
            cursor.execute(
                """
                UPDATE bot_opinions
                SET stance = ?, opinion_text = ?, confidence = ?
                WHERE topic = ?
                """,
                (stance, opinion_text, confidence, topic),
            )
        else:
            cursor.execute(
                """
                INSERT INTO bot_opinions (topic, stance, opinion_text, confidence)
                VALUES (?, ?, ?, ?)
                """,
                (topic, stance, opinion_text, confidence),
            )
        self.conn.commit()
        logger.info(f"🎭 Opinion updated: {topic} -> {stance} ({confidence:.2f})")

    def record_opinion_expression(self, topic: str) -> None:
        """Track that an opinion was expressed (for natural last_expressed/heat)."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE bot_opinions
            SET times_expressed = times_expressed + 1,
                last_expressed = CURRENT_TIMESTAMP
            WHERE topic = ?
            """,
            (topic,),
        )
        self.conn.commit()

    def detect_topic_stance(self, text: str) -> tuple[str, str] | None:
        """Read the user's stated stance toward a topic Serin has an opinion on.

        Scans for "i <stance> <word>" and matches <word> against known opinion
        topics. Returns (topic, user_stance) or None. Used by the response
        planner to decide real disagreement. Punctuation is stripped from
        candidate words so "technology," matches the topic "technology".
        """
        import re as _re

        lower = text.lower()
        for marker, stance in (
            ("love", "love"), ("hate", "hate"),
            ("don't like", "dislike"), ("dont like", "dislike"),
            ("do not like", "dislike"), ("dislike", "dislike"),
            ("like", "like"),
        ):
            if marker not in lower:
                continue
            segment = lower.split(marker, 1)[1]
            # Strip punctuation, take the next few words as the object.
            words = [
                _re.sub(r"[^a-z0-9]", "", w)
                for w in segment.split()
                if _re.sub(r"[^a-z0-9]", "", w)
            ][:3]
            for topic_row in self._all_opinion_topics():
                topic = topic_row["topic"]
                for w in words:
                    # Require a meaningful match, not an accidental fragment
                    # (e.g. "it" must not match "politics").
                    if w == topic or (
                        len(w) >= 3 and (topic in w or (w in topic and len(w) >= len(topic) // 2))
                    ):
                        return (topic, stance)
        return None

    def _all_opinion_topics(self) -> list[dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT topic FROM bot_opinions")
        return [dict(r) for r in cursor.fetchall()]

    def can_disagree(self, topic: str, user_stance: str) -> bool:
        """
        Decide whether the bot should express disagreement with the user's
        stated stance on a topic.

        This is a REAL comparison of persistent state, not a coin flip:
        - No stored opinion on the topic -> the bot has no genuine bias, so it
          does not disagree (it stays open / can be convinced).
        - A genuine directional conflict (opposite-sign stances) -> it pushes
          back, more often the more confident it is in its own view.
        - Aligned or one-sided-neutral stances -> no disagreement.

        Args:
            topic: Topic being discussed.
            user_stance: The user's stated stance ('love'/'like'/'neutral'/
                'dislike'/'hate').

        Returns:
            True if the bot should express disagreement.
        """
        opinion = self.get_opinion(topic)
        if not opinion:
            return False

        bot_stance = opinion.get("stance", "neutral")
        bot_rank = _STANCE_RANK.get(bot_stance, 0)
        user_rank = _STANCE_RANK.get(user_stance, 0)

        # No genuine conflict: same direction, or one side neutral.
        if bot_rank == 0 or user_rank == 0 or (bot_rank > 0) == (user_rank > 0):
            return False

        # Genuine conflict. Confidence scales how readily Serin pushes back.
        confidence: float = opinion.get("confidence", 0.5)
        return _rand() < (0.35 + 0.5 * confidence)

    def get_personality_context(self) -> str:
        """
        Get personality context that sounds natural and conversational.
        No robotic bullet points or formal structure. Surfaces both strong
        preferences and a few opinionated stances so the model has concrete,
        biased material to sound like a real person.
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

        # Surface a few opinionated stances (the biased "brain").
        cursor.execute("""
            SELECT topic, opinion_text, confidence
            FROM bot_opinions
            WHERE stance IN ('love', 'hate', 'dislike')
            ORDER BY confidence DESC
            LIMIT 3
        """)
        opinions = cursor.fetchall()
        for opin in opinions:
            topic = opin["topic"].replace('_', ' ')
            context_parts.append(f"On {topic}: {opin['opinion_text']}")

        return ". ".join(context_parts) + "." if context_parts else ""

    def __del__(self) -> None:
        """Cleanup"""
        if hasattr(self, 'conn'):
            self.conn.close()
