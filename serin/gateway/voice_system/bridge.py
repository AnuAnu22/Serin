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
import asyncio
import collections
import json
import os
import queue
import struct
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from serin.state.logger import logger


# ---------------------------------------------------------------------------
# Stdout protocol reader — runs in a background daemon thread
# ---------------------------------------------------------------------------
# The Rust binary writes a line-oriented protocol to stdout:
#   - AUDIO, JOIN, LEAVE have specific prefixes
#   - TTS_DONE is an exact match (no prefix, no payload)
#   - Everything else is a log message forwarded to Python logger
#
# This class runs in a thread to avoid blocking the asyncio event loop
# on I/O. It reads chunks from the pipe, splits on newlines, and puts
# parsed events on a thread-safe queue. The async _read_loop in
# RustVoiceBridge then pulls from this queue via run_in_executor.

class RustStdoutReader:
    """
    Reads the binary protocol from the Rust process stdout in a background thread.

    The protocol is line-oriented for commands, with raw binary payloads:
      AUDIO:{user_id}:{pcm_len}\\n followed by pcm_len bytes of PCM
      JOIN:{user_id}\\n
      LEAVE:{user_id}\\n
      TTS_DONE\\n
      Everything else → forwarded as [rust] log messages

    Thread safety: uses queue.Queue which is thread-safe. The async side
    reads via get(timeout) which returns None on timeout (vs _EOF sentinel
    which means the process died).
    """

    # Sentinel object for EOF (distinct from None which means timeout)
    _EOF = object()

    def __init__(self, proc: subprocess.Popen) -> None:
        self.proc = proc
        self.events: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="rust-stdout-reader", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """
        Background thread: reads stdout chunks, parses line-oriented protocol.

        The binary protocol has two message types:
          1. Lines ending with \\n (JOIN, LEAVE, TTS_DONE, log messages)
          2. AUDIO lines with raw PCM payload: "AUDIO:{user_id}:{pcm_len}\\n{pcm_bytes}"

        For AUDIO, the pcm_len field tells us how many raw bytes follow the newline.
        These bytes are read from the buffer (or directly from stdin if the buffer
        doesn't have enough). This is why we buffer at the bytearray level.
        """
        stdout = self.proc.stdout
        assert stdout is not None
        buf = bytearray()

        while True:
            chunk = stdout.read(8192)
            if not chunk:
                self.events.put(self._EOF)  # sentinel: process died
                break

            buf.extend(chunk)

            # Process complete lines from buffer.
            # We process as many lines as available in each chunk to keep up
            # with high-throughput audio events (50 chunks/sec per speaker).
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
                    # Format: AUDIO:{user_id}:{pcm_len}
                    # After the newline, exactly pcm_len bytes of raw PCM follow.
                    parts = line.split(':')
                    if len(parts) >= 3:
                        user_id = parts[1]
                        try:
                            pcm_len = int(parts[2])
                        except ValueError:
                            continue
                        # Read exact PCM bytes from buffer.
                        # If the buffer doesn't have enough, read more from stdin
                        # (this can happen if the PCM payload is split across chunks).
                        while len(buf) < pcm_len:
                            extra = stdout.read(pcm_len - len(buf))
                            if not extra:
                                break
                            buf.extend(extra)
                        pcm = bytes(buf[:pcm_len])
                        del buf[:pcm_len]
                        self.events.put(('audio', user_id, pcm))
                elif line.startswith('JOIN:'):
                    self.events.put(('join', line.split(':', 1)[1]))
                elif line.startswith('LEAVE:'):
                    self.events.put(('leave', line.split(':', 1)[1]))
                elif line == 'TTS_DONE':
                    # TTS playback finished signal — no payload needed.
                    # This is sent by Rust's track end handler when the audio
                    # track actually finishes playing on the Discord voice channel.
                    self.events.put(('tts_done',))
                else:
                    # Unknown lines are treated as log messages from Rust.
                    self.events.put(('log', line))

    def get(self, timeout: float = 0.5) -> Optional[tuple]:
        """
        Read next event from the queue.

        Args:
            timeout: How long to wait for an event (seconds)

        Returns:
            Event tuple (type, *args) or None on timeout

        Raises:
            EOFError: if the process has died and the pipe is closed
        """
        try:
            result = self.events.get(timeout=timeout)
            if result is self._EOF:
                raise EOFError("Rust stdout pipe closed")
            return result
        except queue.Empty:
            return None


# ---------------------------------------------------------------------------
# Rust Voice Bridge — manages Rust process lifecycle + audio pipeline
# ---------------------------------------------------------------------------
