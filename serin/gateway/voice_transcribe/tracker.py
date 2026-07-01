"""
Voice Tracker - Track voice channel activity
Monitors who joins/leaves voice channels and session durations.

UPDATED: Debug logging added
"""
from datetime import datetime
from secrets import choice, randbelow
from typing import Any

from serin.config.debug_logger import log_voice
from serin.logger import logger


def _rand() -> float:
    return randbelow(10_000_000) / 10_000_000


class VoiceTracker:
    """
    Track voice channel activity across all servers.
    Stores voice sessions in memory system for context awareness.
    """

    def __init__(self, memory_system: Any) -> None:
        """
        Initialize voice tracker.

        Args:
            memory_system: UnifiedMemorySystem instance
        """
        self.memory = memory_system
        self.current_voice_states = {}  # user_id -> VoiceState dict
        self.session_start_times = {}   # user_id -> datetime

        logger.info(" Voice tracker initialized")

    async def on_voice_update(self, member: Any, before: Any, after: Any) -> None:
        """
        Handle voice state changes.
        Called by Discord bot when voice state updates.

        Args:
            member: Discord Member object
            before: Previous VoiceState
            after: New VoiceState
        """
        try:
            username = member.display_name

            # Joined VC
            if after.channel and not before.channel:
                await self._handle_join(member, after.channel)

            # Left VC
            elif before.channel and not after.channel:
                await self._handle_leave(member, before.channel)

            # Switched channels
            elif before.channel and after.channel and before.channel != after.channel:
                await self._handle_switch(member, before.channel, after.channel)

            # Muted/unmuted, deafened/undeafened (track but don't store)
            elif before.channel and after.channel:
                if before.self_mute != after.self_mute:
                    action = "muted" if after.self_mute else "unmuted"
                    logger.debug(f" {username} {action}")

                if before.self_deaf != after.self_deaf:
                    action = "deafened" if after.self_deaf else "undeafened"
                    logger.debug(f" {username} {action}")

        except Exception as e:
            logger.error(f" Error handling voice update: {e}")

    async def _handle_join(self, member: Any, channel: Any) -> None:
        """User joined voice channel"""
        user_id = str(member.id)
        username = member.display_name
        channel_id = str(channel.id)
        channel_name = channel.name
        server_id = str(channel.guild.id)

        # Track session start
        self.session_start_times[user_id] = datetime.now()
        self.current_voice_states[user_id] = {
            'channel_id': channel_id,
            'channel_name': channel_name,
            'server_id': server_id,
            'joined_at': datetime.now()
        }

        # Store in memory
        self.memory.add_memory(
            content=f"{username} joined voice channel '{channel_name}'",
            user_id=user_id,
            username=username,
            channel_id=channel_id,
            participants=[user_id],
            emotional_tone='neutral',
            importance=0.4
        )
        log_voice("JOIN", username, channel_name)
        logger.info(f" {username} joined VC: {channel_name}")

    async def _handle_leave(self, member: Any, channel: Any) -> None:
        """User left voice channel"""
        user_id = str(member.id)
        username = member.display_name
        channel_id = str(channel.id)
        channel_name = channel.name

        # Calculate session duration
        if user_id in self.session_start_times:
            duration = datetime.now() - self.session_start_times[user_id]
            duration_minutes = int(duration.total_seconds() / 60)

            # Determine importance based on duration
            if duration_minutes < 5:
                importance = 0.3  # Brief join
            elif duration_minutes < 30:
                importance = 0.4  # Short session
            elif duration_minutes < 120:
                importance = 0.5  # Normal session
            else:
                importance = 0.6  # Long session
            log_voice("LEAVE", username, channel_name, duration_minutes)
            # Store in memory
            self.memory.add_memory(
                content=f"{username} was in voice channel '{channel_name}' for {duration_minutes} minutes",
                user_id=user_id,
                username=username,
                channel_id=channel_id,
                participants=[user_id],
                emotional_tone='neutral',
                importance=importance
            )

            # Cleanup
            del self.session_start_times[user_id]
            if user_id in self.current_voice_states:
                del self.current_voice_states[user_id]

            logger.info(f" {username} left VC after {duration_minutes} min")
        else:
            logger.warning(f" {username} left VC but no session start time found")

    async def _handle_switch(self, member: Any, old_channel: Any, new_channel: Any) -> None:
        """User switched voice channels"""
        user_id = str(member.id)
        username = member.display_name
        old_name = old_channel.name
        new_name = new_channel.name

        # Update current state
        if user_id in self.current_voice_states:
            self.current_voice_states[user_id]['channel_id'] = str(new_channel.id)
            self.current_voice_states[user_id]['channel_name'] = new_name

        # Store switch in memory (low importance)
        self.memory.add_memory(
            content=f"{username} switched from '{old_name}' to '{new_name}'",
            user_id=user_id,
            username=username,
            channel_id=str(new_channel.id),
            participants=[user_id],
            emotional_tone='neutral',
            importance=0.3
        )

        logger.info(f" {username} switched: {old_name} → {new_name}")

    def is_in_voice(self, user_id: str) -> bool:
        """
        Check if user is currently in voice channel.

        Args:
            user_id: User ID to check

        Returns:
            True if user is in voice
        """
        return user_id in self.current_voice_states

    def get_voice_info(self, user_id: str) -> dict[str, Any] | None:
        """
        Get current voice state for user.

        Args:
            user_id: User ID

        Returns:
            Dict with voice info, or None if not in voice
            {
                'channel_id': str,
                'channel_name': str,
                'server_id': str,
                'joined_at': datetime,
                'duration_minutes': int
            }
        """
        if user_id not in self.current_voice_states:
            return None

        state = self.current_voice_states[user_id].copy()

        # Calculate current duration
        if user_id in self.session_start_times:
            duration = datetime.now() - self.session_start_times[user_id]
            state['duration_minutes'] = int(duration.total_seconds() / 60)
        else:
            state['duration_minutes'] = 0

        return state

    def get_all_in_voice(self) -> dict[str, dict[str, Any] | None]:
        """
        Get all users currently in voice.

        Returns:
            Dict mapping user_id to voice info
        """
        result = {}
        for user_id in self.current_voice_states.keys():
            result[user_id] = self.get_voice_info(user_id)
        return result

    def get_voice_duration(self, user_id: str) -> int | None:
        """
        Get current voice session duration in minutes.

        Args:
            user_id: User ID

        Returns:
            Duration in minutes, or None if not in voice
        """
        if user_id not in self.session_start_times:
            return None

        duration = datetime.now() - self.session_start_times[user_id]
        return int(duration.total_seconds() / 60)

    def get_stats(self) -> dict[str, Any]:
        """
        Get voice tracker statistics.

        Returns:
            Dict with stats
        """
        return {
            'users_in_voice': len(self.current_voice_states),
            'active_sessions': len(self.session_start_times)
        }


# Natural reactions to voice activity (for message_manager integration)
VOICE_JOIN_REACTIONS = [
    "oh hey you're in vc",
    "in vc? gaming session?",
    "voice channel vibes",
    "vc time?",
    "just joined vc?",
]

VOICE_LONG_SESSION_REACTIONS = [
    "damn {duration} {unit} vc session. productive or just vibing?",
    "that's a long vc session. {duration} {unit}",
    "{duration} {unit} in vc? dedicated",
    "been in vc for {duration} {unit} huh",
]


def get_voice_join_reaction() -> str | None:
    """
    Get natural reaction to voice join.
    Returns None 70% of the time (don't react to everything).
    """
    if _rand() < 0.3:  # 30% chance to react
        return choice(VOICE_JOIN_REACTIONS)
    return None


def get_voice_duration_reaction(duration_minutes: int) -> str | None:
    """
    Get natural reaction to long voice session.

    Args:
        duration_minutes: Session duration in minutes

    Returns:
        Reaction message, or None if duration not notable
    """
    # Only react to sessions >30 minutes
    if duration_minutes < 30:
        return None

    # Format duration
    if duration_minutes < 60:
        duration = duration_minutes
        unit = "min"
    else:
        duration = round(duration_minutes / 60, 1)
        unit = "hour" if duration == 1 else "hours"

    # 40% chance to react to long sessions
    if _rand() < 0.4:
        template = choice(VOICE_LONG_SESSION_REACTIONS)
        return template.format(duration=duration, unit=unit)

    return None
