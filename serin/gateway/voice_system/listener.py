"""
Voice Listener — Discord Voice Channel Manager

Phase 1: VoiceProtocol capture. Uses py-cord's documented VoiceProtocol API
to receive VOICE_SERVER_UPDATE + VOICE_STATE_UPDATE from the gateway.
NO UDP, NO voice websocket, NO DAVE from py-cord. Rust owns all voice transport.

Phase 2 (future): Rust gateway shard eliminates py-cord from voice entirely.
"""
import asyncio
import os
import sys
from typing import Any

import discord

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Import VoiceProtocol from _types to avoid requiring py-cord[voice] deps
from discord.voice._types import VoiceProtocol

from serin.logger import logger


class InfoCaptureProtocol(VoiceProtocol):
    """
    Captures voice ConnectionInfo from gateway events without establishing
    any actual voice connection (no UDP, no voice websocket, no DAVE).

    Used as:  protocol = await channel.connect(cls=InfoCaptureProtocol)

    After connect() returns, call protocol.get_info() to retrieve the
    endpoint, token, and session_id needed by Rust's songbird driver.
    """

    def __init__(self, client: discord.Client, channel: discord.VoiceChannel) -> None:
        super().__init__(client, channel)
        self.server_event = asyncio.Event()
        self.state_event = asyncio.Event()
        self.endpoint: str = ""
        self.token: str = ""
        self.session_id: str = ""
        self._info_gathered = False

    async def connect(self, *, timeout: float, reconnect: bool) -> None:
        """Join voice channel and wait for gateway events (NO UDP/DAVE)."""
        await self.channel.guild.change_voice_state(channel=self.channel)

        try:
            await asyncio.wait_for(
                asyncio.gather(self.server_event.wait(), self.state_event.wait()),
                timeout=timeout or 15.0,
            )
        except TimeoutError:
            await self.channel.guild.change_voice_state(channel=None)
            raise

        self._info_gathered = True

    async def on_voice_server_update(self, data) -> None:
        """Called by py-cord state machine when VOICE_SERVER_UPDATE arrives.
        data is RawVoiceServerUpdateEvent with .endpoint, .token, .guild_id attrs.
        """
        self.endpoint = data.endpoint or ""
        self.token = data.token
        self.server_event.set()

    async def on_voice_state_update(self, data) -> None:
        """Called by py-cord state machine when VOICE_STATE_UPDATE arrives.
        Called only for the bot's own voice state (py-cord filters in parse_voice_state_update).
        data is RawVoiceStateUpdateEvent with .session_id attr.
        """
        self.session_id = data.session_id
        self.state_event.set()

    async def disconnect(self, *, force: bool = False) -> None:
        """Leave voice channel and clean up."""
        if self._info_gathered or force:
            try:
                await self.channel.guild.change_voice_state(channel=None)
            except Exception:
                pass
        super().cleanup()
        self._info_gathered = False

    def get_info(self) -> dict[str, Any]:
        """Return ConnectionInfo dict for Rust songbird driver."""
        return {
            "endpoint": self.endpoint,
            "token": self.token,
            "session_id": self.session_id,
            "guild_id": self.channel.guild.id,
            "channel_id": self.channel.id,
            "user_id": self.client.user.id,
        }


class VoiceListener:
    def __init__(self, client: discord.Client, audio_processor: Any) -> None:
        self.client = client
        self.audio_processor = audio_processor

        self.rust_bridge: Any | None = None
        self._protocol: InfoCaptureProtocol | None = None
        self._active_guild_id: int | None = None

        self.transcription_enabled = True
        self.auto_join_on_mention = True
        self._join_in_progress: set[int] = set()

        self.stats = {
            'connections': 0,
            'total_audio_chunks': 0,
            'active_channels': set(),
            'errors': 0,
        }

        logger.info("Voice listener initialized (InfoCaptureProtocol + Rust)")

    async def join_channel(self, guild_id: int, channel_id: int) -> bool:
        if guild_id in self._join_in_progress:
            logger.warning(f"Join already in progress for guild {guild_id}, skipping")
            return False
        self._join_in_progress.add(guild_id)
        try:
            guild = self.client.get_guild(guild_id)
            if not guild:
                logger.error(f"Guild {guild_id} not found")
                return False

            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                logger.error(f"Voice channel {channel_id} not found")
                return False

            # If already connected, move by disconnecting first
            if self._protocol is not None:
                await self._protocol.disconnect()
                self._protocol = None

            if self.rust_bridge and self.rust_bridge.is_running():
                await self.rust_bridge.stop()
                self.rust_bridge = None

            # Connect via VoiceProtocol (captures ConnectionInfo, NO UDP/DAVE)
            try:
                protocol = await channel.connect(
                    cls=InfoCaptureProtocol,
                    reconnect=False,
                    timeout=15.0,
                )
            except TimeoutError:
                logger.error("Timeout waiting for voice connection info from gateway")
                return False

            info = protocol.get_info()
            logger.info(
                f"Got ConnectionInfo: endpoint={info['endpoint']}, "
                f"token={info['token'][:8]}..., session_id={info['session_id'][:8]}..."
            )

            # Start Rust bridge with captured ConnectionInfo
            from serin.gateway.voice_system.bridge import RustVoiceBridge

            self.rust_bridge = RustVoiceBridge(
                audio_processor=self.audio_processor,
                voice_listener=self,
            )

            success = await self.rust_bridge.start_with_info(
                guild_id=guild_id,
                channel_id=channel_id,
                connection_info=info,
            )

            if not success:
                logger.error("Failed to start Rust voice receiver")
                await protocol.disconnect()
                return False

            self._protocol = protocol
            self._active_guild_id = guild_id
            self.stats['connections'] += 1
            self.stats['active_channels'].add(str(channel_id))
            logger.info(f"Joined {channel.name} in {guild.name} (Rust owns voice)")
            return True

        except Exception as e:
            logger.exception(f"Error joining voice channel: {e}")
            self.stats['errors'] += 1
            return False
        finally:
            self._join_in_progress.discard(guild_id)

    async def leave_channel(self, guild_id: int) -> bool:
        try:
            if self.rust_bridge and self.rust_bridge.is_running():
                await self.rust_bridge.stop()
                self.rust_bridge = None

            if self._protocol is not None:
                await self._protocol.disconnect()
                self._protocol = None

            self._active_guild_id = None
            self._join_in_progress.discard(guild_id)
            logger.info(f"Left voice channel in guild {guild_id}")
            return True

        except Exception as e:
            logger.error(f"Error leaving voice channel: {e}")
            self.stats['errors'] += 1
            return False

    async def leave_all_channels(self) -> None:
        if self._active_guild_id is not None:
            await self.leave_channel(self._active_guild_id)

    def is_in_voice(self, guild_id: int) -> bool:
        return (
            self.rust_bridge is not None
            and self.rust_bridge.is_running()
            and self._active_guild_id == guild_id
        )

    def is_connected(self) -> bool:
        return self.rust_bridge is not None and self.rust_bridge.is_running()

    def get_status(self) -> dict:
        connections = []

        if self._active_guild_id is not None and self.is_connected():
            guild = self.client.get_guild(self._active_guild_id)
            if guild:
                member_names = []
                try:
                    for m in guild.me.voice.channel.members if guild.me.voice else []:
                        member_names.append({
                            'id': str(m.id),
                            'name': m.name,
                            'display_name': m.display_name,
                            'is_bot': m.bot,
                        })
                except Exception:
                    member_names = []

                connections.append({
                    'guild_id': str(self._active_guild_id),
                    'guild_name': guild.name,
                    'channel_id': self._channel_id() or 'unknown',
                    'channel_name': str(guild.me.voice.channel.name) if guild.me.voice else 'unknown',
                    'members': len(member_names),
                    'member_names': member_names,
                    'receiver_mode': 'rust',
                    'rust_bridge_active': self.rust_bridge.is_running() if self.rust_bridge else False,
                })

        return {
            'connected': len(connections) > 0,
            'active_connections': connections,
            'total_connections': self.stats['connections'],
            'transcription_enabled': self.transcription_enabled,
            'receiver_mode': 'rust',
        }

    def get_stats(self) -> dict:
        stats = {
            'connected': self.is_connected(),
            'active_channels': len(self.stats['active_channels']),
            'total_connections': self.stats['connections'],
            'audio_chunks_processed': self.stats['total_audio_chunks'],
            'errors': self.stats['errors'],
            'receiver_mode': 'rust',
        }
        if self.rust_bridge:
            try:
                stats['rust_bridge'] = self.rust_bridge.get_stats()
            except Exception:
                pass
        return stats

    def _channel_id(self) -> str | None:
        if self._active_guild_id is None:
            return None
        guild = self.client.get_guild(self._active_guild_id)
        if guild and guild.me.voice and guild.me.voice.channel:
            return str(guild.me.voice.channel.id)
        return None

"""
Voice Output Manager — Handles TTS Generation and Playback

Manages a queue of text to speak, generates TTS audio via edge-tts, and
sends it to the Rust bridge for voice channel playback.

Key design:
  - The full response text is queued as ONE item (no sentence splitting).
    This avoids the Rust SPEAK command interrupting the previous track.
  - TTS_DONE signal from Rust releases the processing lock so the next
    user utterance can be processed immediately.
  - Interrupt detection: if the user speaks while TTS is playing, the
    processing lock prevents cascading and the interrupt stops playback.

Sentence splitting is intentionally disabled because:
  1. Rust's SPEAK handler calls handle.stop() before playing new audio
  2. Sending multiple SPEAK commands → each sentence cuts off the previous
  3. Edge-TTS handles multi-sentence text fine in one synthesis call
   4. The TTS_DONE signal from Rust handles lock release precisely
"""


