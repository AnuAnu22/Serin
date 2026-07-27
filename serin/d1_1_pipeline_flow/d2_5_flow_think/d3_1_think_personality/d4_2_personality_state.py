"""PersonalityState — tone modifier from conversation mood."""
from collections import deque
from datetime import datetime
from typing import Any, TypedDict

from serin.d1_4_config_base.d2_3_core_logger import logger

# Bound the history so this can never grow unbounded in a long-running
# process. 500 samples at one update per processed message is comfortably
# multiple days of history for a chat bot, while staying tiny in memory.
_MOOD_HISTORY_MAXLEN = 500


class MoodSample(TypedDict):
    timestamp: str
    energy_level: float
    sass_level: float
    engagement: float


class PersonalityState:
    """Tracks bot's personality state"""

    def __init__(self) -> None:
        self.energy_level: float = 0.5
        self.sass_level: float = 0.5
        self.engagement: float = 0.5
        self.last_update: datetime = datetime.now()
        # Bounded rolling history for the control panel's mood chart.
        # Deliberately a plain deque, not shared across threads/tasks —
        # PersonalityState is only ever mutated from the single-threaded
        # asyncio event loop that runs the pipeline, so no lock is needed
        # here. If that assumption ever changes (e.g. a panel endpoint
        # starts writing to it directly), add an asyncio.Lock at that point.
        self._history: deque[MoodSample] = deque(maxlen=_MOOD_HISTORY_MAXLEN)
        self._record_sample()

    def _record_sample(self) -> None:
        self._history.append({
            'timestamp': self.last_update.isoformat(),
            'energy_level': round(self.energy_level, 3),
            'sass_level': round(self.sass_level, 3),
            'engagement': round(self.engagement, 3),
        })

    def save_to_db(self, conn: Any) -> None:
        """Persist personality state to SQLite."""
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS personality_state (
                    key TEXT PRIMARY KEY,
                    value REAL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS personality_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    energy REAL, sass REAL, engagement REAL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                INSERT INTO personality_history (energy, sass, engagement)
                VALUES (?, ?, ?)
            """, (self.energy_level, self.sass_level, self.engagement))
            state = self.to_dict()
            for key, value in state.items():
                if isinstance(value, (int, float)):
                    cursor.execute("""
                        INSERT INTO personality_state (key, value, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET
                            value = excluded.value,
                            updated_at = CURRENT_TIMESTAMP
                    """, (key, float(value)))
            conn.commit()
        except Exception as e:
            logger.debug("Failed to save personality state: %s", e)

    def load_from_db(self, conn: Any) -> None:
        """Load personality state from SQLite."""
        try:
            self._conn = conn
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS personality_state (
                    key TEXT PRIMARY KEY,
                    value REAL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("SELECT key, value FROM personality_state")
            rows = cursor.fetchall()
            if not rows:
                return
            for row in rows:
                key, value = row[0], row[1]
                if hasattr(self, key):
                    setattr(self, key, value)
            logger.info("Loaded personality state from DB: %d keys", len(rows))
        except Exception as e:
            logger.debug("Failed to load personality state: %s", e)

    def get_history(self, limit: int = 100) -> list[MoodSample]:
        """Return the most recent mood samples, oldest first."""
        return list(self._history)[-limit:]

    def to_dict(self) -> dict[str, float | str]:
        """Snapshot for the control panel's live mood widget."""
        return {
            'energy_level': round(self.energy_level, 3),
            'sass_level': round(self.sass_level, 3),
            'engagement': round(self.engagement, 3),
            'last_update': self.last_update.isoformat(),
            'tone_modifier': self.get_tone_modifier(),
        }

    def update_from_conversation(
        self,
        conversation_mood: str,
        user_traits: list[str],
        time_of_day: int
    ) -> None:
        """Update personality state"""
        # Energy varies by time of day
        if 0 <= time_of_day < 6:
            self.energy_level = max(0.2, self.energy_level - 0.1)
        elif 6 <= time_of_day < 12:
            self.energy_level = min(0.8, self.energy_level + 0.1)
        elif 12 <= time_of_day < 18:
            self.energy_level = 0.7
        else:
            self.energy_level = 0.6

        # Match conversation mood
        if conversation_mood == 'energetic':
            self.energy_level = min(1.0, self.energy_level + 0.2)
            self.engagement = min(1.0, self.engagement + 0.1)
        elif conversation_mood == 'chill':
            self.energy_level = max(0.7, self.energy_level - 0.1)
            self.engagement = max(0.8, self.engagement - 0.1)

        # Adapt sass level
        if 'humorous' in user_traits:
            self.sass_level = min(0.8, self.sass_level + 0.1)
        if 'polite' in user_traits:
            self.sass_level = max(0.3, self.sass_level - 0.1)

        # Natural decay towards baseline
        hours_since_update = (datetime.now() - self.last_update).total_seconds() / 3600
        if hours_since_update > 1:
            self.energy_level += (0.5 - self.energy_level) * 0.1
            self.sass_level += (0.5 - self.sass_level) * 0.1
            self.engagement += (0.5 - self.engagement) * 0.1

        self.last_update = datetime.now()
        self._record_sample()

        # Periodic save to DB every 10th update
        self._update_count = getattr(self, '_update_count', 0) + 1
        if self._update_count % 10 == 0 and hasattr(self, '_conn'):
            self.save_to_db(self._conn)

        logger.debug(
            "Personality: "
            f"energy={self.energy_level:.2f}, "
            f"sass={self.sass_level:.2f}, "
            f"engagement={self.engagement:.2f}"
        )

    def set_mood_preset(self, preset: str) -> bool:
        """Apply a named mood preset from the control panel.

        This exists so external callers (the control panel route) mutate
        state through one method call instead of reaching in and setting
        ``energy_level`` / ``sass_level`` / ``engagement`` as three separate
        statements. Three separate statements means any code that reads this
        object between statement 1 and statement 3 sees a half-applied mood —
        not a crash, but a real correctness bug (e.g. a mid-flight pipeline
        run building its tone modifier from an inconsistent mix of old and
        new values). Doing it in one method keeps the update atomic from the
        point of view of any other coroutine on the event loop, since nothing
        here awaits.

        Returns False for an unrecognized preset name instead of raising, so
        the route layer can turn that into a clean 400 rather than a 500.
        """
        presets: dict[str, dict[str, float]] = {
            'high_energy': {'energy_level': 1.0, 'engagement': 1.0},
            'neutral': {'energy_level': 0.5, 'sass_level': 0.5, 'engagement': 0.5},
            'sass': {'sass_level': 1.0},
            'chill': {'energy_level': 0.3, 'engagement': 0.4},
        }
        values = presets.get(preset)
        if values is None:
            return False
        for attr, value in values.items():
            setattr(self, attr, value)
        self.last_update = datetime.now()
        self._record_sample()
        logger.info("Mood preset applied via control panel: %s", preset)
        return True

    def get_tone_modifier(self) -> str:
        """Get tone guidance for LLM"""
        modifiers: list[str] = []

        if self.energy_level > 0.65:
            modifiers.append("Be energetic and punchy")
        elif self.energy_level < 0.35:
            modifiers.append("Be chill and low-energy")

        if self.sass_level > 0.65:
            modifiers.append("You can be sarcastic, witty, and a little mean")
        elif self.sass_level < 0.35:
            modifiers.append("Be straightforward and genuine")

        if self.engagement > 0.65:
            modifiers.append("Show real interest and ask follow-ups")
        elif self.engagement < 0.35:
            modifiers.append("Keep it short, don't drag the conversation")

        if modifiers:
            return ". ".join(modifiers) + "."

        return "Be natural and a little playful."


