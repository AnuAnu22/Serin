"""
Rust Voice Bridge — Production bridge between Rust voice receiver and Serin bot.

Architecture:
  discord.py joins the voice channel (handles gateway + voice state).
  This bridge extracts voice server info from the VoiceClient,
  passes it to the Rust binary which connects directly to Discord's
  voice UDP. This avoids a dual-gateway conflict (Discord allows only
  one gateway connection per bot token).

Protocol:
  Stdin (Python → Rust):
    Line 1: JSON ConnectionInfo { endpoint, token, session_id, guild_id, channel_id, user_id }
    SPEAK:{pcm_len}\\n followed by pcm_len bytes of WAV audio
    INTERRUPT\\n
    SHUTDOWN\\n

  Stdout (Rust → Python):
    AUDIO:{user_id}:{pcm_len}\\n followed by pcm_len bytes of decoded PCM
    JOIN:{user_id}\\n
    LEAVE:{user_id}\\n
    TTS_DONE\\n  (sent when TTS track finishes playing via songbird TrackEvent::End)
    Other lines → treated as log messages

Key design decisions:
  - The Rust binary handles ALL voice UDP directly (no discord.py audio dependency)
  - TTS_DONE signal enables precise lock release (no duration guessing)
  - stdin writes are serialized via threading.Lock() to prevent protocol corruption
  - Crash recovery is minimal: the caller must rejoin (simpler than reconnection logic)

TTS_DONE Lifecycle:
  1. VoiceOutputManager._process_queue synthesizes TTS → calls _play_audio_rust
  2. _play_audio_rust → bridge.send_tts_audio() → Rust SPEAK command
  3. Rust writes WAV to /tmp/serin_tts_output.wav → plays via songbird Driver
  4. Rust attaches TrackEvent::End handler → writes TTS_DONE when track finishes
  5. Python _read_loop receives TTS_DONE → _handle_tts_done() → _release_lock()
  6. Processing lock released → next user utterance is processed immediately
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Raw-SSRC attribution guard — the loud failure mode for a lost SSRC→user map.
# ---------------------------------------------------------------------------
#
# The vendored-songbird ClientConnect patch feeds Rust's SSRC→user_id map (see
# docs/wiki/songbird-clientconnect-patch.md). When that mapping is missing, the
# receiver falls back to attributing audio by RAW SSRC. Discord snowflake user
# ids are always >= 2**32 (they exceed 32 bits by design), while an SSRC is a
# 32-bit value — so a "user id" below 2**32 on an AUDIO/JOIN event is proof the
# map was incomplete for that packet. Without this check the misattribution is
# silent: transcripts land on the wrong (or no) user and nobody notices.

_SNOWFLAKE_MIN_32BIT = 2**32  # smallest real Discord snowflake exceeds any u32 SSRC
_RAW_SSRC_WARN_INTERVAL = 300.0  # seconds between repeated raw-SSRC warnings


class _RawSsrcWarner:
    """Rate-limited warning for AUDIO/JOIN events carrying a raw-SSRC 'user id'."""

    def __init__(self) -> None:
        self._last_warned: float = 0.0

    def check(self, user_id: str) -> bool:
        """Return True if `user_id` looks like a raw SSRC (sub-2**32)."""
        try:
            numeric: int = int(user_id)
        except ValueError:
            return False
        if numeric <= 0 or numeric >= _SNOWFLAKE_MIN_32BIT:
            return False
        now: float = time.monotonic()
        if now - self._last_warned >= _RAW_SSRC_WARN_INTERVAL:
            self._last_warned = now
            stderr_message: str = (
                "voice.raw_ssrc_attribution "
                f"user_id={user_id} outcome=audio_attributed_by_raw_ssrc "
                "degradation_reason='SSRC→user map missing (ClientConnect patch "
                "lost?) — see docs/wiki/songbird-clientconnect-patch.md'"
            )
            try:
                from serin.d1_2_gateway_io.d2_4_io_di import get_logger

                get_logger().warning(
                    "voice.raw_ssrc_attribution",
                    extra={
                        "user_id": user_id,
                        "outcome": "audio_attributed_by_raw_ssrc",
                        "degradation_reason": (
                            "SSRC→user map missing (ClientConnect patch lost?) — see "
                            "docs/wiki/songbird-clientconnect-patch.md"
                        ),
                    },
                )
            except RuntimeError:
                # Gateway DI not wired (bare process/unit context) — this warning
                # must NEVER kill the stdout read loop, so fall back to stderr,
                # which is where Rust-side logs surface anyway.
                print(f"[rust-bridge] {stderr_message}", file=sys.stderr)
        return True

# ---------------------------------------------------------------------------
# Stdout protocol reader — runs as an asyncio task
# ---------------------------------------------------------------------------

class RustStdoutReader:
    """
    Reads the binary protocol from the Rust process stdout via asyncio.

    The protocol is line-oriented for commands, with raw binary payloads:
      AUDIO:{user_id}:{pcm_len}\\n followed by pcm_len bytes of PCM
      JOIN:{user_id}\\n
      LEAVE:{user_id}\\n
      TTS_DONE\\n
      Everything else → forwarded as [rust] log messages

    Read loop runs as an asyncio task calling read_loop(). Events are placed
    on an asyncio.Queue for consumption by the async _read_loop consumer.
    """

    _EOF = object()

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self.proc = proc
        self.events: asyncio.Queue[Any] = asyncio.Queue()
        self._ssrc_guard = _RawSsrcWarner()

    async def read_loop(self) -> None:
        """
        Async task: reads stdout chunks, parses line-oriented protocol.

        The binary protocol has two message types:
          1. Lines ending with \\n (JOIN, LEAVE, TTS_DONE, log messages)
          2. AUDIO lines with raw PCM payload: "AUDIO:{user_id}:{pcm_len}\\n{pcm_bytes}"

        For AUDIO, the pcm_len field tells us how many raw bytes follow the newline.
        """
        stdout = self.proc.stdout
        if stdout is None:
            raise RuntimeError("Process stdout is None")
        buf = bytearray()

        while True:
            chunk = await stdout.read(8192)
            if not chunk:
                await self.events.put(self._EOF)
                break

            buf.extend(chunk)

            while True:
                nl = buf.find(b'\n')
                if nl < 0:
                    break

                line_bytes = bytes(buf[:nl])
                del buf[:nl + 1]

                try:
                    line = line_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    continue

                if line.startswith('AUDIO:'):
                    parts = line.split(':')
                    if len(parts) >= 3:
                        user_id = parts[1]
                        self._ssrc_guard.check(user_id)
                        try:
                            pcm_len = int(parts[2])
                        except ValueError:
                            continue
                        while len(buf) < pcm_len:
                            extra = await stdout.read(pcm_len - len(buf))
                            if not extra:
                                break
                            buf.extend(extra)
                        pcm = bytes(buf[:pcm_len])
                        del buf[:pcm_len]
                        await self.events.put(('audio', user_id, pcm))
                elif line.startswith('JOIN:'):
                    join_uid = line.split(':', 1)[1]
                    self._ssrc_guard.check(join_uid)
                    await self.events.put(('join', join_uid))
                elif line.startswith('LEAVE:'):
                    await self.events.put(('leave', line.split(':', 1)[1]))
                elif line == 'TTS_DONE':
                    await self.events.put(('tts_done',))
                else:
                    await self.events.put(('log', line))

    async def get(self, timeout: float = 0.5) -> tuple[Any, ...] | None:
        """
        Read next event from the async queue.

        Args:
            timeout: How long to wait for an event (seconds)

        Returns:
            Event tuple (type, *args) or None on timeout

        Raises:
            EOFError: if the process has died and the pipe is closed
        """
        try:
            result: Any = await asyncio.wait_for(self.events.get(), timeout=timeout)
            if result is self._EOF:
                raise EOFError("Rust stdout pipe closed")
            event: tuple[Any, ...] = result  # narrowed from Any for pyright
            return event
        except TimeoutError:
            return None


# ---------------------------------------------------------------------------
# Rust Voice Bridge — manages Rust process lifecycle + audio pipeline
# ---------------------------------------------------------------------------
