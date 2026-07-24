"""
Rust Voice Bridge I/O Mixin
----------------------------
I/O handling methods for RustVoiceBridge, extracted to keep files under 500 lines.
"""
# --- Imports ---
from __future__ import annotations

import asyncio
from typing import Any

from serin.d1_2_gateway_io.d2_4_io_di import get_logger

# --- Types ---
# (none)

# --- Constants ---
# (none)

# --- Entry ---


class RustVoiceBridgeIOMixin:
    """I/O handling methods for RustVoiceBridge."""

# --- Core ---
    def _start_stderr_reader(self) -> None:
        """Read stderr from the Rust process via an asyncio task."""

        async def _read_stderr() -> None:
            if self.proc is None or self.proc.stderr is None:
                return
            while self._running:
                try:
                    line: bytes = await self.proc.stderr.readline()
                    if not line:
                        break
                    decoded: str = line.decode('utf-8', errors='replace').rstrip()
                    self._stderr_buf.append(decoded)
                    get_logger().debug(f" [rust:err] {decoded}")
                except Exception:
                    break

        asyncio.create_task(_read_stderr())

    def _extract_voice_info(
        self, voice_client: Any, guild_id: int, channel_id: int
    ) -> dict[str, Any] | None:
        """
        Extract voice server connection info from a discord.py VoiceClient.

        Pycord's VoiceClient exposes:
          - voice_client.endpoint  → "hostname:port" (wss:// stripped)
          - voice_client.token     → voice server auth token
          - voice_client.session_id → voice session ID
          - voice_client.guild.me.id → bot's user ID

        Falls back to VoiceConnectionState introspection if direct attributes
        are not available (compatibility with different discord.py versions).

        Returns:
            Dict with ConnectionInfo fields, or None if not connected
        """
        try:
            endpoint = getattr(voice_client, 'endpoint', None)
            token = getattr(voice_client, 'token', None)
            session_id = getattr(voice_client, 'session_id', None)

            if not all([endpoint, token, session_id]):
                conn = getattr(voice_client, '_connection', None)
                if conn:
                    endpoint = endpoint or getattr(conn, 'endpoint', None)
                    token = token or getattr(conn, 'token', None)
                    session_id = session_id or getattr(conn, 'session_id', None)

            if not all([endpoint, token, session_id]):
                get_logger().error(
                    f" Missing voice server info: endpoint={endpoint is not None}, "
                    f"token={token is not None}, session_id={session_id is not None}"
                )
                return None

            bot_user_id = voice_client.guild.me.id

            return {
                "endpoint": endpoint,
                "token": token,
                "session_id": session_id,
                "guild_id": guild_id,
                "channel_id": channel_id,
                "user_id": bot_user_id,
            }

        except Exception as e:
            get_logger().exception(f" Error extracting voice info: {e}")
            return None

    async def _read_loop(self) -> None:
        """Async loop to read events from Rust stdout."""
        get_logger().info(" Rust stdout reader loop started")

        try:
            assert self.reader is not None
            async for event_type, event_data in self.reader:
                if event_type == 'audio':
                    user_id = str(event_data.get('user_id', '0'))
                    pcm_data = event_data.get('pcm_data', b'')
                    if pcm_data:
                        await self._handle_audio(user_id, pcm_data)
                elif event_type == 'join':
                    user_id = str(event_data.get('user_id', '0'))
                    await self._handle_join(user_id)
                elif event_type == 'leave':
                    user_id = str(event_data.get('user_id', '0'))
                    self._handle_leave(user_id)
                elif event_type == 'tts_done':
                    self._handle_tts_done()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            get_logger().error(f" Error in Rust reader loop: {e}")
            self.stats['errors'] += 1

        get_logger().info(" Rust stdout reader loop ended")

# --- Helpers ---
# (none)

# --- Errors ---
# (none)
