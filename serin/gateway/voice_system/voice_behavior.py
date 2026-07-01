"""Autonomous voice channel join/leave decisions — personality-driven VC behavior."""

import asyncio
from datetime import datetime
from typing import Any

from serin.gateway.voice_system.audio_processor import _rand, _uniform
from serin.state.logger import logger


class VoiceBehaviorManager:
    """
    Manages autonomous voice channel join/leave decisions.

    Uses PersonalityState (energy_level, engagement, sass_level) from ResponseController
    combined with VoiceTracker awareness to decide when Serin should join or leave VC.

    Join triggers (delayed, never instant):
    - Someone is in VC for 45-90s and energy is high -> maybe pop in
    - The conversation in VC seems active -> higher chance
    - Time of day: evening more social, late night less

    Leave triggers:
    - Silence > leave_after_silence_seconds -> leave
    - Session > max_session_minutes -> leave
    - Energy drops below 0.3 while in VC -> leave

    Explicit join/leave requests go through voice_action_decider.py (structured output).
    """

    def __init__(
        self,
        personality: Any,
        voice_listener: Any,
        voice_tracker: Any = None,
        guild_text_channels: dict[int, Any] | None = None,
    ) -> None:
        """
        Initialize voice behavior manager.

        Args:
            personality: PersonalityState instance from ResponseController
            voice_listener: VoiceListener instance for join/leave operations
            voice_tracker: VoiceTracker instance for tracking user voice states (optional)
            guild_text_channels: Mapping of guild_id -> text channel for social reactions
        """
        self.personality = personality
        self.voice_listener = voice_listener
        self.voice_tracker = voice_tracker
        self.guild_text_channels = guild_text_channels or {}

        # Behavior settings (configurable via API)
        self.join_aggressiveness: float = 0.5
        self.leave_after_silence_seconds: int = 180
        self.max_session_minutes: int = 60
        self.creator_user_ids: set[str] = set()

        # Runtime state
        self._behavior_check_task: asyncio.Task | None = None
        self._is_running: bool = False
        self._vc_join_time: dict[int, datetime] = {}
        self._last_speech_time: dict[int, datetime] = {}
        self._voice_session_guilds: set[int] = set()

        # Pending join considerations: guild_id -> {channel_id, user_id, username, timestamp, delay_until}
        self._pending_joins: dict[int, dict[str, Any]] = {}

        # Stats
        self.stats: dict[str, Any] = {
            'auto_joins': 0,
            'auto_leaves': 0,
            'join_decisions': 0,
            'leave_decisions': 0,
            'rejected_joins': 0,
            'pending_evaluations': 0,
        }

        logger.info(
            "Voice behavior manager initialized (aggressiveness: %.1f)",
            self.join_aggressiveness
        )

    async def start(self) -> None:
        """Start the behavior check background loop."""
        if self._is_running:
            return
        self._is_running = True
        self._behavior_check_task = asyncio.create_task(self._behavior_check_loop())
        logger.info("Voice behavior manager started")

    async def stop(self) -> None:
        """Stop the behavior check background loop."""
        self._is_running = False
        if self._behavior_check_task:
            self._behavior_check_task.cancel()
            self._behavior_check_task = None
        logger.info("Voice behavior manager stopped")

    async def on_user_joined_vc(
        self,
        user_id: str,
        username: str,
        guild_id: int,
        channel_id: int,
        channel_name: str,
    ) -> None:
        """
        Called when a user joins a voice channel.

        Does NOT join immediately. Instead, records the event as a pending
        consideration. The behavior check loop will evaluate it after
        a random delay (45-90s) to decide if Serin should wander in.

        This makes Serin feel like it's socially aware, not an auto-join bot.

        Explicit join requests ("join vc?") are handled by the structured
        output pipeline in voice_action_decider.py.
        """
        self.stats['join_decisions'] += 1

        # Already in VC for this guild? Skip
        if self.voice_listener.is_in_voice(guild_id):
            return

        # Already considering this guild? Update, don't re-schedule
        if guild_id in self._pending_joins:
            return

        # Schedule delayed consideration (45-90s from now, so Serin seems to "notice" later)
        delay = _uniform(45.0, 90.0)
        consider_at = datetime.now().timestamp() + delay

        self._pending_joins[guild_id] = {
            'channel_id': channel_id,
            'channel_name': channel_name,
            'user_id': user_id,
            'username': username,
            'timestamp': datetime.now(),
            'consider_at': consider_at,
        }
        self.stats['pending_evaluations'] += 1

        logger.info(
            " Voice behavior: %s joined %s — will consider joining in %.0fs",
            username, channel_name, delay,
        )

    async def track_speech(self, guild_id: int) -> None:
        """Track that speech was heard in a guild's voice channel."""
        self._last_speech_time[guild_id] = datetime.now()

    async def _behavior_check_loop(self) -> None:
        """
        Periodic check loop (every 15s):
        - Evaluate pending join considerations (delayed auto-join)
        - Check leave conditions for active sessions
        """
        while self._is_running:
            try:
                await asyncio.sleep(15)
                await self._evaluate_pending_joins()
                await self._check_leave_conditions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in voice behavior check loop: %s", e)

    async def _evaluate_pending_joins(self) -> None:
        """
        Check if any pending join considerations are ready.
        If the delay has elapsed, decide whether to actually join.
        """
        now_ts = datetime.now().timestamp()
        ready_guilds = []

        for guild_id, info in list(self._pending_joins.items()):
            if now_ts < info['consider_at']:
                continue  # Not ready yet

            ready_guilds.append(guild_id)

            # Clean up if already connected somehow
            if self.voice_listener.is_in_voice(guild_id):
                self._pending_joins.pop(guild_id, None)
                continue

            # Check if the user is still in that channel
            if self.voice_tracker:
                user_info = self.voice_tracker.get_voice_info(info['user_id'])
                if not user_info:
                    # User left VC while we were considering
                    logger.info(
                        " Considered joining %s but %s already left",
                        info['channel_name'], info['username'],
                    )
                    self._pending_joins.pop(guild_id, None)
                    continue

            # Decide whether to join (modest chance, feels natural)
            energy = self.personality.energy_level
            hour = datetime.now().hour

            # Base chance: scale with energy
            if energy > 0.7:
                chance = 0.25
            elif energy > 0.5:
                chance = 0.15
            elif energy > 0.3:
                chance = 0.08
            else:
                chance = 0.03

            # Evening social boost
            if 18 <= hour <= 23:
                chance *= 1.5

            # Aggressiveness modifier
            chance *= self.join_aggressiveness * 2
            chance = min(chance, 0.5)

            if _rand() < chance:
                logger.info(
                    " Auto-join (delayed): %s in %s (energy=%.2f, chance=%.0f%%)",
                    info['username'], info['channel_name'], energy, chance * 100,
                )
                success = await self.voice_listener.join_channel(
                    guild_id, info['channel_id']
                )
                if success:
                    self._vc_join_time[guild_id] = datetime.now()
                    self._voice_session_guilds.add(guild_id)
                    self.stats['auto_joins'] += 1
            else:
                self.stats['rejected_joins'] += 1
                logger.debug(
                    " Decided not to join %s (energy=%.2f, chance=%.0f%%)",
                    info['channel_name'], energy, chance * 100,
                )

            self._pending_joins.pop(guild_id, None)

    async def _check_leave_conditions(self) -> None:
        """Check all active voice sessions for leave conditions."""
        now = datetime.now()

        for guild_id in list(self._voice_session_guilds):
            if not self.voice_listener.is_in_voice(guild_id):
                self._voice_session_guilds.discard(guild_id)
                continue

            self.stats['leave_decisions'] += 1
            reasons = []

            # Check silence duration
            last_speech = self._last_speech_time.get(guild_id)
            if last_speech:
                silence_seconds = (now - last_speech).total_seconds()
                if silence_seconds > self.leave_after_silence_seconds:
                    reasons.append(f"silence ({int(silence_seconds)}s)")

            # Check session length
            join_time = self._vc_join_time.get(guild_id)
            if join_time:
                session_minutes = (now - join_time).total_seconds() / 60
                if session_minutes > self.max_session_minutes:
                    reasons.append(f"session too long ({int(session_minutes)}m)")

            # Check energy drop
            if self.personality.energy_level < 0.25:
                reasons.append(f"low energy ({self.personality.energy_level:.2f})")

            if reasons and _rand() < 0.5:
                logger.info(
                    "Auto-leave guild %s: %s",
                    guild_id, ", ".join(reasons),
                )
                success = await self.voice_listener.leave_channel(guild_id)
                if success:
                    self._voice_session_guilds.discard(guild_id)
                    self._vc_join_time.pop(guild_id, None)
                    self._last_speech_time.pop(guild_id, None)
                    self.stats['auto_leaves'] += 1

    def get_settings(self) -> dict[str, Any]:
        """Get current behavior settings for API exposure."""
        return {
            'join_aggressiveness': self.join_aggressiveness,
            'leave_after_silence_seconds': self.leave_after_silence_seconds,
            'max_session_minutes': self.max_session_minutes,
            'creator_user_ids': list(self.creator_user_ids),
        }

    def update_settings(self, settings: dict[str, Any]) -> None:
        """Update behavior settings from API."""
        if 'join_aggressiveness' in settings:
            self.join_aggressiveness = max(0.0, min(1.0, float(settings['join_aggressiveness'])))
        if 'leave_after_silence_seconds' in settings:
            self.leave_after_silence_seconds = max(30, int(settings['leave_after_silence_seconds']))
        if 'max_session_minutes' in settings:
            self.max_session_minutes = max(5, int(settings['max_session_minutes']))
        logger.info(
            "Voice behavior settings updated: %.2f / %ds / %dm",
            self.join_aggressiveness,
            self.leave_after_silence_seconds,
            self.max_session_minutes,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get voice behavior stats for API exposure."""
        return dict(self.stats)
