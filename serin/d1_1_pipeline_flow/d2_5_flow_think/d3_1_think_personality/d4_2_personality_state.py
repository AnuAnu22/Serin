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
        # Per-user mood vectors for emotional persistence (CODING_GUIDELINES
        # §4): user_id → {energy_level, sass_level, engagement, last_update}.
        # The global fields above remain the "default mood" a new relationship
        # is seeded from and the fallback for user_id=None callers (e.g. the
        # control panel's global mood widget). A per-user entry, once created,
        # persists independently so a mood set with one user never bleeds into
        # another.
        self._users: dict[str, dict[str, Any]] = {}

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
            # Persist each per-user mood vector.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_mood_state (
                    user_id TEXT PRIMARY KEY,
                    energy_level REAL NOT NULL DEFAULT 0.5,
                    sass_level REAL NOT NULL DEFAULT 0.5,
                    engagement REAL NOT NULL DEFAULT 0.5,
                    updated_at REAL NOT NULL
                )
            """)
            for uid, mood in self._users.items():
                cursor.execute("""
                    INSERT INTO user_mood_state
                        (user_id, energy_level, sass_level, engagement, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        energy_level = excluded.energy_level,
                        sass_level = excluded.sass_level,
                        engagement = excluded.engagement,
                        updated_at = excluded.updated_at
                """, (uid, mood["energy_level"], mood["sass_level"],
                      mood["engagement"], mood["last_update"].timestamp()))
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
            # Load per-user mood vectors so emotional persistence survives a
            # restart.
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_mood_state (
                        user_id TEXT PRIMARY KEY,
                        energy_level REAL NOT NULL DEFAULT 0.5,
                        sass_level REAL NOT NULL DEFAULT 0.5,
                        engagement REAL NOT NULL DEFAULT 0.5,
                        updated_at REAL NOT NULL
                    )
                """)
                cursor.execute(
                    "SELECT user_id, energy_level, sass_level, engagement, updated_at "
                    "FROM user_mood_state"
                )
                for row in cursor.fetchall():
                    self._users[row[0]] = {
                        "energy_level": row[1],
                        "sass_level": row[2],
                        "engagement": row[3],
                        "last_update": datetime.fromtimestamp(row[4]),
                    }
                logger.info("Loaded per-user mood state from DB: %d users", len(self._users))
            except Exception as e:
                logger.debug("Failed to load per-user mood state: %s", e)
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
        time_of_day: int,
        user_id: str | None = None,
        relationship: str | None = None,
    ) -> None:
        """Update personality state.

        With ``user_id`` supplied this updates (or seeds) that relationship's
        per-user mood vector instead of the global mood — the mechanism behind
        emotional persistence. ``relationship`` (one of the buckets from
        ``relationship_category``) biases the update toward the user's standing
        with Serin once per interaction.
        """
        if user_id is not None:
            self._update_per_user(conversation_mood, user_traits, time_of_day,
                                  user_id, relationship)
            return

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

    def _update_per_user(
        self,
        conversation_mood: str,
        user_traits: list[str],
        time_of_day: int,
        user_id: str,
        relationship: str | None,
    ) -> None:
        """Update a single relationship's mood vector.

        Mirrors the global update logic but keyed by user. A new relationship
        is seeded from the current global default so it starts on neutral
        ground rather than inheriting whatever mood was set for someone else.
        """
        mood = self._users.get(user_id)
        if mood is None:
            mood = {
                "energy_level": self.energy_level,
                "sass_level": self.sass_level,
                "engagement": self.engagement,
                "last_update": self.last_update,
            }
            self._users[user_id] = mood

        # Natural decay towards baseline if this relationship went quiet.
        hours = (datetime.now() - mood["last_update"]).total_seconds() / 3600
        if hours > 1:
            for key in ("energy_level", "sass_level", "engagement"):
                mood[key] += (0.5 - mood[key]) * 0.1

        # Energy varies by time of day
        if 0 <= time_of_day < 6:
            mood["energy_level"] = max(0.2, mood["energy_level"] - 0.1)
        elif 6 <= time_of_day < 12:
            mood["energy_level"] = min(0.8, mood["energy_level"] + 0.1)
        elif 12 <= time_of_day < 18:
            mood["energy_level"] = 0.7
        else:
            mood["energy_level"] = 0.6

        # Match conversation mood
        if conversation_mood == 'energetic':
            mood["energy_level"] = min(1.0, mood["energy_level"] + 0.2)
            mood["engagement"] = min(1.0, mood["engagement"] + 0.1)
        elif conversation_mood == 'chill':
            mood["energy_level"] = max(0.7, mood["energy_level"] - 0.1)
            mood["engagement"] = max(0.8, mood["engagement"] - 0.1)

        # Adapt sass level from traits
        if 'humorous' in user_traits:
            mood["sass_level"] = min(0.8, mood["sass_level"] + 0.1)
        if 'polite' in user_traits:
            mood["sass_level"] = max(0.3, mood["sass_level"] - 0.1)

        # Relationship bias — friend vs stranger vs enemy respond differently.
        if relationship == "enemy":
            mood["sass_level"] = max(mood["sass_level"], 0.6)
            mood["engagement"] = min(mood["engagement"], 0.4)
        elif relationship == "friend":
            mood["engagement"] = max(mood["engagement"], 0.6)

        mood["last_update"] = datetime.now()

        # Periodic save to DB every 10th per-user update.
        self._per_user_update_count = getattr(self, "_per_user_update_count", 0) + 1
        if self._per_user_update_count % 10 == 0 and hasattr(self, '_conn'):
            self.save_to_db(self._conn)

        logger.debug(
            "Personality[%s]: relationship=%s, "
            f"energy={mood['energy_level']:.2f}, "
            f"sass={mood['sass_level']:.2f}, "
            f"engagement={mood['engagement']:.2f}",
            user_id, relationship,
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

    def get_tone_modifier(self, user_id: str | None = None) -> str:
        """Get tone guidance for the LLM, scoped to a relationship.

        Without ``user_id`` (or for a user with no mood vector yet) this falls
        back to the global default mood. With a known user it applies that
        relationship's mood so a friend reads warmer than an enemy.
        """
        if user_id is not None:
            mood = self._users.get(user_id)
            if mood is not None:
                energy = mood["energy_level"]
                sass = mood["sass_level"]
                engagement = mood["engagement"]
                # Apply the same quiet-relationship decay read-time so a stale
                # vector drifts toward baseline even before the next write.
                hours = (datetime.now() - mood["last_update"]).total_seconds() / 3600
                if hours > 1:
                    energy += (0.5 - energy) * 0.1
                    sass += (0.5 - sass) * 0.1
                    engagement += (0.5 - engagement) * 0.1
                return self._build_tone_modifier(energy, sass, engagement)
        return self._build_tone_modifier(self.energy_level, self.sass_level, self.engagement)

    @staticmethod
    def _build_tone_modifier(energy_level: float, sass_level: float, engagement: float) -> str:
        """Build a continuous, state-caused tone line from the mood triple.

        Vision-driven change (2026-08-18): the previous version was a set of
        threshold cliffs (>0.65 / <0.35) with a silent dead middle band, phrased
        as instructions to the model ("Be energetic and punchy") — exactly the
        "describe the desired mood in the prompt and hope the model complies"
        pattern the vision rejects. This version:
          - maps the WHOLE range with graduated bands (no cliffs, no dead zone),
          - phrases the result as Serin's current state, not as a directive,
          - still returns a stable string so per-user moods compare differently
            and a fresh user equals the global default.
        """
        parts: list[str] = []

        if energy_level >= 0.80:
            parts.append("running hot and quick")
        elif energy_level >= 0.62:
            parts.append("pretty energized")
        elif energy_level >= 0.50:
            parts.append("at a normal sort of energy")
        elif energy_level >= 0.38:
            parts.append("a bit low on energy")
        elif energy_level >= 0.20:
            parts.append("running on fumes")
        else:
            parts.append("completely drained")

        if sass_level >= 0.80:
            parts.append("sassier than usual")
        elif sass_level >= 0.62:
            parts.append("dry and a little witty")
        elif sass_level >= 0.38:
            parts.append("fairly straightforward")
        elif sass_level >= 0.20:
            parts.append("quieter and more careful")
        else:
            parts.append("totally deadpan")

        if engagement >= 0.80:
            parts.append("fully hooked on the conversation")
        elif engagement >= 0.62:
            parts.append("engaged and following along")
        elif engagement >= 0.50:
            parts.append("paying normal attention")
        elif engagement >= 0.38:
            parts.append("only half-listening")
        elif engagement >= 0.20:
            parts.append("distracted and drifting")
        else:
            parts.append("mentally elsewhere")

        return "Right now you're " + ", ".join(parts) + "."

        return "Be natural and a little playful."

