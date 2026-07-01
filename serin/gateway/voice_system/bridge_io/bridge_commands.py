"""Commands sent to Rust voice bridge."""

import asyncio
import json
import os
from typing import Any

from serin.gateway.voice_system.bridge import RustStdoutReader
from serin.logger import logger


async def send_tts_audio(self, audio_data: bytes) -> None:
    """
    Send TTS audio data to the Rust binary for voice channel playback.

    The Rust binary writes the WAV data to /tmp/serin_tts_output.wav and
    plays it through the songbird Driver. When playback finishes, the
    Rust binary sends TTS_DONE back to Python.

    Protocol:
      SPEAK:{len(audio_data)}\n followed by audio_data bytes

    Args:
        audio_data: WAV audio bytes from TTS engine (16kHz mono 16-bit WAV)
    """
    if not self.proc or not self.proc.stdin:
        logger.warning(" Cannot send TTS: Rust process not running")
        return
    try:
        header = f"SPEAK:{len(audio_data)}\n".encode()
        logger.info(f" Writing {len(header) + len(audio_data)} bytes to Rust stdin")
        await self._write_stdin(header + audio_data)
    except Exception as e:
        logger.error(f" Error sending TTS audio: {e}")


async def interrupt(self) -> None:
    """
    Interrupt current TTS playback.

    Sends INTERRUPT command to Rust binary, which stops the current
    songbird track (handle.stop()) and removes the temp WAV file.
    """
    if not self.proc or not self.proc.stdin:
        return
    try:
        await self._write_stdin(b"INTERRUPT\n")
    except Exception:
        logger.exception("Failed to send INTERRUPT to Rust bridge")


async def _write_stdin(self, data: bytes) -> None:
    """
    Thread-safe async write to Rust stdin.

    CRITICAL: All stdin writes MUST go through this method.
    The threading.Lock() prevents interleaving between send_tts_audio
    and interrupt commands. Without it, the binary protocol framing
    could be corrupted (e.g., "SPEAK:1000\n" split across two writes).
    """
    with self._stdin_lock:
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(data)
            await self.proc.stdin.drain()


# -----------------------------------------------------------------------
# Public: start with raw ConnectionInfo (no discord VoiceClient)
# -----------------------------------------------------------------------


async def start_with_info(
    self, guild_id: int, channel_id: int, connection_info: dict
) -> bool:
    """
    Start the Rust voice receiver using pre-captured ConnectionInfo.

    Unlike start(), this does NOT require a discord.py VoiceClient.
    ConnectionInfo is captured from gateway events (on_voice_server_update
    + on_voice_state_update) by VoiceListener.

    Args:
        guild_id: Discord guild ID
        channel_id: Discord voice channel ID
        connection_info: Dict with keys:
            endpoint, token, session_id, guild_id, channel_id, user_id

    Returns:
        True if successfully started
    """
    if not os.path.exists(self.binary_path):
        logger.error(f" Rust binary not found: {self.binary_path}")
        logger.error("   Build with: cd voice/rust_receiver && cargo build --release")
        return False

    logger.info(
        f" Starting Rust voice receiver for guild {guild_id}, "
        f"channel {channel_id} (gateway info)"
    )

    try:
        rust_env = os.environ.copy()
        rust_env["RUST_BACKTRACE"] = "full"
        self.proc = await asyncio.create_subprocess_exec(
            self.binary_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=rust_env,
        )

        info_json = json.dumps(connection_info) + "\n"
        self.proc.stdin.write(info_json.encode('utf-8'))
        await self.proc.stdin.drain()

        self.reader = RustStdoutReader(self.proc)
        self._reader_task = asyncio.create_task(self.reader.read_loop())
        self._guild_id = guild_id
        self._channel_id = channel_id
        self._running = True
        self._voice_client = None
        self._last_connection_info = connection_info
        self._start_mode = "connection_info"
        self._death_event.clear()
        self._shutdown_requested = False

        self._reader_consumer_task = asyncio.create_task(self._read_loop())

        # Start supervisor — watches for process death and re-spawns
        self._supervisor_task = asyncio.create_task(self._supervise_rust_process())

        self._start_stderr_reader()

        logger.info(" Rust voice receiver started (gateway info mode)")
        return True

    except Exception as e:
        logger.exception(f" Failed to start Rust voice receiver: {e}")
        self.stats['errors'] += 1
        return False


# -----------------------------------------------------------------------
# Public: status
# -----------------------------------------------------------------------


def is_running(self) -> bool:
    """Check if the Rust process is alive (not None and still running)."""
    return self.proc is not None and self.proc.returncode is None


def get_stats(self) -> dict[str, Any]:
    """Get bridge statistics (chunks, joins, leaves, errors, etc.)."""
    return {
        **self.stats,
        'process_alive': self.is_running(),
        'guild_id': self._guild_id,
        'channel_id': self._channel_id,
    }
