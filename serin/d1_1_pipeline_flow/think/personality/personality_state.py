"""PersonalityState — tone modifier from conversation mood."""
from datetime import datetime

from serin.d1_3_state_core.logger import logger


class PersonalityState:
    """Tracks bot's personality state"""

    def __init__(self) -> None:
        self.energy_level: float = 0.5
        self.sass_level: float = 0.5
        self.engagement: float = 0.5
        self.last_update: datetime = datetime.now()

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

        logger.debug(
            "Personality: "
            f"energy={self.energy_level:.2f}, "
            f"sass={self.sass_level:.2f}, "
            f"engagement={self.engagement:.2f}"
        )

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


