"""
Voice Profiles - Manage TTS Voice Profiles
Different voice characteristics for different contexts/moods.
"""

from serin.state.logger import logger


class VoiceProfile:
    """Single voice profile with all settings"""

    def __init__(
        self,
        name: str,
        speed: float = 1.0,
        temperature: float = 0.7,
        length_penalty: float = 1.0,
        repetition_penalty: float = 5.0,
        description: str = ""
    ) -> None:
        self.name = name
        self.speed = speed
        self.temperature = temperature
        self.length_penalty = length_penalty
        self.repetition_penalty = repetition_penalty
        self.description = description

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'speed': self.speed,
            'temperature': self.temperature,
            'length_penalty': self.length_penalty,
            'repetition_penalty': self.repetition_penalty,
            'description': self.description
        }

    def __repr__(self) -> str:
        return f"VoiceProfile(name='{self.name}', speed={self.speed})"


class VoiceProfileManager:
    """Manage multiple voice profiles"""

    def __init__(self) -> None:
        self.profiles: dict[str, VoiceProfile] = {}
        self.active_profile = 'default'

        # Load default profiles
        self._load_default_profiles()

        logger.info(" Voice profile manager initialized")
        logger.info(f"    Loaded {len(self.profiles)} default profiles")

    def _load_default_profiles(self):
        """Load default voice profiles"""

        # Default - Standard voice
        self.add_profile(VoiceProfile(
            name='default',
            speed=1.0,
            temperature=0.7,
            length_penalty=1.0,
            repetition_penalty=5.0,
            description='Standard voice, neutral tone'
        ))

        # Casual - Relaxed, friendly
        self.add_profile(VoiceProfile(
            name='casual',
            speed=1.05,
            temperature=0.75,
            length_penalty=1.0,
            repetition_penalty=5.0,
            description='Relaxed, friendly, slightly faster'
        ))

        # Energetic - Fast, upbeat
        self.add_profile(VoiceProfile(
            name='energetic',
            speed=1.15,
            temperature=0.85,
            length_penalty=1.0,
            repetition_penalty=5.0,
            description='Fast-paced, enthusiastic'
        ))

        # Calm - Slow, soothing
        self.add_profile(VoiceProfile(
            name='calm',
            speed=0.9,
            temperature=0.65,
            length_penalty=1.0,
            repetition_penalty=5.0,
            description='Slow, soothing, measured'
        ))

        # Sarcastic - Slightly faster with variation
        self.add_profile(VoiceProfile(
            name='sarcastic',
            speed=1.1,
            temperature=0.9,
            length_penalty=1.0,
            repetition_penalty=4.5,
            description='Sarcastic tone with emphasis'
        ))

        # Serious - Formal, measured
        self.add_profile(VoiceProfile(
            name='serious',
            speed=0.95,
            temperature=0.6,
            length_penalty=1.0,
            repetition_penalty=5.5,
            description='Formal, serious, measured'
        ))

        # Excited - Very fast, high energy
        self.add_profile(VoiceProfile(
            name='excited',
            speed=1.25,
            temperature=0.95,
            length_penalty=0.9,
            repetition_penalty=4.0,
            description='Very excited, rapid speech'
        ))

        # Tired - Slow, low energy
        self.add_profile(VoiceProfile(
            name='tired',
            speed=0.85,
            temperature=0.55,
            length_penalty=1.1,
            repetition_penalty=5.5,
            description='Tired, slower, less variation'
        ))

    def add_profile(self, profile: VoiceProfile) -> None:
        """Add or update a profile"""
        self.profiles[profile.name] = profile
        logger.debug(f" Added profile: {profile.name}")

    def remove_profile(self, name: str) -> bool:
        """Remove a profile"""
        if name in self.profiles and name != 'default':
            del self.profiles[name]
            logger.info(f" Removed profile: {name}")
            return True
        return False

    def get_profile(self, name: str) -> VoiceProfile | None:
        """Get a profile by name"""
        return self.profiles.get(name)

    def set_active(self, name: str) -> bool:
        """Set active profile"""
        if name in self.profiles:
            self.active_profile = name
            logger.info(f" Active profile: {name}")
            return True
        return False

    def get_active(self) -> VoiceProfile:
        """Get active profile"""
        return self.profiles[self.active_profile]

    def list_profiles(self) -> list:
        """List all profile names"""
        return list(self.profiles.keys())

    def get_profile_for_mood(self, mood: str) -> VoiceProfile:
        """
        Get appropriate profile for a mood.

        Args:
            mood: Mood/emotion (happy, sad, angry, neutral, etc.)

        Returns:
            Appropriate VoiceProfile
        """
        mood_mappings = {
            'happy': 'energetic',
            'excited': 'excited',
            'sad': 'calm',
            'angry': 'serious',
            'tired': 'tired',
            'sarcastic': 'sarcastic',
            'neutral': 'casual',
            'friendly': 'casual',
            'formal': 'serious'
        }

        profile_name = mood_mappings.get(mood.lower(), 'default')
        return self.get_profile(profile_name) or self.get_active()

    def create_custom_profile(
        self,
        name: str,
        speed: float = 1.0,
        temperature: float = 0.7,
        description: str = ""
    ) -> VoiceProfile:
        """
        Create and add a custom profile.

        Args:
            name: Profile name
            speed: Speech speed (0.5-2.0)
            temperature: Variation (0.1-1.0)
            description: Profile description

        Returns:
            Created VoiceProfile
        """
        profile = VoiceProfile(
            name=name,
            speed=speed,
            temperature=temperature,
            description=description
        )
        self.add_profile(profile)
        return profile

    def get_stats(self) -> dict:
        """Get profile manager stats"""
        return {
            'total_profiles': len(self.profiles),
            'active_profile': self.active_profile,
            'available_profiles': self.list_profiles()
        }


# Global singleton
_profile_manager: VoiceProfileManager | None = None


def get_profile_manager() -> VoiceProfileManager:
    """Get or create the global profile manager singleton"""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = VoiceProfileManager()
    return _profile_manager


def get_voice_profiles() -> list:
    """Get all voice profiles (module-level convenience)"""
    return list(get_profile_manager().profiles.values())


def get_active_profile_name() -> str:
    """Get active profile name (module-level convenience)"""
    return get_profile_manager().active_profile


def create_profile(name: str, speed: float = 1.0, temperature: float = 0.7, description: str = "") -> VoiceProfile | None:
    """Create a new voice profile (module-level convenience)"""
    return get_profile_manager().create_custom_profile(name, speed, temperature, description)


def set_active_profile(name: str) -> bool:
    """Set active profile (module-level convenience)"""
    return get_profile_manager().set_active(name)


def delete_profile(name: str) -> bool:
    """Delete a profile (module-level convenience)"""
    return get_profile_manager().remove_profile(name)
