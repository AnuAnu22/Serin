"""
Topic Fatigue - Track conversation topics and show natural boredom
Humans get less enthusiastic about topics after discussing them repeatedly
"""
import time
from collections import defaultdict

from serin.d1_3_state_core.logger import logger


class TopicFatigue:
    """
    Tracks topic repetition and affects personality state.
    After 10+ messages about same topic, bot becomes less enthusiastic.
    """

    def __init__(self) -> None:
        # channel_id -> {topic: [timestamps]}
        self.topic_history = defaultdict(lambda: defaultdict(list))

        # Thresholds
        self.FATIGUE_MESSAGE_COUNT = 10  # 10+ messages on same topic
        self.TOPIC_TIMEOUT = 600  # 10 minutes - topics expire

        logger.info(" Topic fatigue tracker initialized")

    def track_topic(
        self,
        channel_id: str,
        topic: str,
        timestamp: float | None = None
    ) -> None:
        """
        Track a topic mention in conversation.

        Args:
            channel_id: Channel ID
            topic: Topic string (e.g., "gaming", "food", "work")
            timestamp: Unix timestamp (defaults to now)
        """
        if not topic:
            return

        if timestamp is None:
            timestamp = time.time()

        # Clean old entries first
        self._clean_old_topics(channel_id)

        # Add new entry
        self.topic_history[channel_id][topic.lower()].append(timestamp)

        logger.debug(f" Tracked topic '{topic}' in channel {channel_id}")

    def get_topic_fatigue_level(
        self,
        channel_id: str,
        topic: str
    ) -> float:
        """
        Get fatigue level for a topic (0.0 = fresh, 1.0 = exhausted).

        Args:
            channel_id: Channel ID
            topic: Topic to check

        Returns:
            Fatigue level 0.0 to 1.0
        """
        if not topic:
            return 0.0

        topic_lower = topic.lower()

        # Clean old entries
        self._clean_old_topics(channel_id)

        # Count recent mentions
        mentions = len(self.topic_history[channel_id][topic_lower])

        if mentions == 0:
            return 0.0

        # Calculate fatigue
        # 0-5 messages: no fatigue
        # 5-10 messages: mild fatigue (0.0 to 0.5)
        # 10+ messages: high fatigue (0.5 to 1.0)

        if mentions <= 5:
            fatigue = 0.0
        elif mentions <= 10:
            # Gradual increase from 0.0 to 0.5
            fatigue = (mentions - 5) / 10
        else:
            # Cap at 0.9 (never completely disengaged)
            fatigue = min(0.9, 0.5 + (mentions - 10) / 20)

        logger.debug(
            f"😴 Topic '{topic}' fatigue: {fatigue:.2f} "
            f"({mentions} mentions)"
        )

        return fatigue

    def _clean_old_topics(self, channel_id: str) -> None:
        """Remove topic mentions older than TOPIC_TIMEOUT"""
        current_time = time.time()
        cutoff = current_time - self.TOPIC_TIMEOUT

        for topic in list(self.topic_history[channel_id].keys()):
            # Filter out old timestamps
            self.topic_history[channel_id][topic] = [
                ts for ts in self.topic_history[channel_id][topic]
                if ts > cutoff
            ]

            # Remove topic if no recent mentions
            if not self.topic_history[channel_id][topic]:
                del self.topic_history[channel_id][topic]

    def get_most_discussed_topics(
        self,
        channel_id: str,
        limit: int = 3
    ) -> list[tuple]:
        """
        Get most discussed topics in channel.

        Returns:
            List of (topic, mention_count) tuples
        """
        self._clean_old_topics(channel_id)

        topics = [
            (topic, len(timestamps))
            for topic, timestamps in self.topic_history[channel_id].items()
        ]

        # Sort by mention count
        topics.sort(key=lambda x: x[1], reverse=True)

        return topics[:limit]

    def apply_fatigue_to_personality(
        self,
        personality_state: dict,
        fatigue_level: float
    ) -> dict:
        """
        Modify personality state based on topic fatigue.

        Args:
            personality_state: Current personality state dict
            fatigue_level: Fatigue level 0.0 to 1.0

        Returns:
            Modified personality state
        """
        if fatigue_level < 0.3:
            # No significant fatigue
            return personality_state

        # Reduce energy and engagement
        energy_reduction = fatigue_level * 0.3  # Max 30% reduction
        engagement_reduction = fatigue_level * 0.4  # Max 40% reduction

        modified = personality_state.copy()
        modified['energy_level'] = max(
            0.2,
            personality_state.get('energy_level', 0.5) - energy_reduction
        )
        modified['engagement'] = max(
            0.2,
            personality_state.get('engagement', 0.5) - engagement_reduction
        )

        logger.debug(
            "😴 Applied fatigue: "
            f"energy {personality_state.get('energy_level', 0.5):.2f} → {modified['energy_level']:.2f}, "
            f"engagement {personality_state.get('engagement', 0.5):.2f} → {modified['engagement']:.2f}"
        )

        return modified

    def get_fatigue_context_note(self, fatigue_level: float) -> str:
        """
        Get context note for LLM about topic fatigue.
        """
        if fatigue_level >= 0.7:
            return "[Note: You've been discussing this topic a lot. You're getting a bit tired of it. Be less enthusiastic or suggest changing the subject.]"
        elif fatigue_level >= 0.4:
            return "[Note: This topic has come up several times recently. You're still engaged but less excited about it.]"
        return ""


# Global instance
_fatigue_tracker = None

def get_fatigue_tracker() -> TopicFatigue:
    """Get or create global fatigue tracker"""
    global _fatigue_tracker
    if _fatigue_tracker is None:
        _fatigue_tracker = TopicFatigue()
    return _fatigue_tracker


def track_topic(channel_id: str, topic: str) -> None:
    """
    Convenience function to track topic.

    Usage:
        track_topic(channel.id, "gaming")
    """
    get_fatigue_tracker().track_topic(channel_id, topic)


def get_topic_fatigue(channel_id: str, topic: str) -> float:
    """
    Convenience function to get fatigue level.

    Usage:
        fatigue = get_topic_fatigue(channel.id, "gaming")
    """
    return get_fatigue_tracker().get_topic_fatigue_level(channel_id, topic)
