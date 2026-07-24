"""
Process supervision for Rust voice bridge.
"""
# --- Imports ---
from __future__ import annotations

import asyncio
import collections
import json
import os
import threading
from collections.abc import Callable
from typing import Any

from serin.d1_2_gateway_io.d2_2_voice_system.d3_2_bridge_io.d4_1_io_bridge import (
    RustStdoutReader,
)
from serin.d1_2_gateway_io.d2_2_voice_system.d3_2_bridge_io.d4_4_process_watch.d5_2_process_watch_io import (
    RustVoiceBridgeIOMixin,
)
from serin.d1_2_gateway_io.d2_4_io_di import get_logger

# --- Types ---
# (none)

# --- Constants ---
# (none)

# --- Entry ---


class RustVoiceBridge(RustVoiceBridgeIOMixin):
    """
    Production bridge between the Rust voice receiver and Serin's audio pipeline.

    Responsibilities:
      1. Spawns and manages the Rust voice_receiver subprocess
      2. Parses stdout binary protocol into AudioStreamProcessor calls
      3. Forwards TTS audio to Rust binary via stdin for voice channel playback
      4. Handles the TTS_DONE signal to release the processing lock
      5. Manages crash recovery (minimal — caller must reconnect)

    Thread safety:
      - stdin writes are serialized via threading.Lock() to prevent interleaving
        between send_tts_audio() and interrupt() calls. Without this lock,
        concurrent writes could corrupt the protocol framing.
      - stdout reads happen in an asyncio task (RustStdoutReader.read_loop)
      - stderr reads happen in a background thread
      - The async _read_loop pulls from the async event queue
    """

    def __init__(
        self,
        audio_processor: Any,
        voice_listener: Any,
        binary_path: str | None = None,
    ) -> None:
        """
        Initialize the Rust voice bridge.

        Args:
            audio_processor: AudioStreamProcessor instance (receives decoded PCM)
            voice_listener: VoiceListener instance (has voice_connections dict)
            binary_path: Path to the voice_receiver binary.
                         Defaults to voice/rust_receiver/target/release/voice_receiver
        """
        self.audio_processor = audio_processor
        self.voice_listener = voice_listener

        if binary_path is None:
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), *([os.pardir] * 4)))
            binary_path = os.path.join(base, "voice", "rust_receiver", "target", "release", "voice_receiver")
        self.binary_path = binary_path

        self.proc: asyncio.subprocess.Process | None = None
        self.reader: RustStdoutReader | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._reader_consumer_task: asyncio.Task[None] | None = None
        self._running = False
        self._guild_id: int | None = None
        self._channel_id: int | None = None

        # ── Stdin serialization lock ─────────────────────────────────────────
        self._stdin_lock = threading.Lock()

        # ── Supervisor / crash recovery ──────────────────────────────────────
        self._voice_client: Any | None = None
        self._last_connection_info: dict[str, Any] | None = None
        self._start_mode: str = "connection_info"  # "voice_client" or "connection_info"
        self._death_event = asyncio.Event()
        self._shutdown_requested = False
        self._supervisor_task: asyncio.Task[None] | None = None
        self._reconnect_callback: Callable[..., Any] | None = None
        self._restart_timestamps: collections.deque[float] = collections.deque(maxlen=5)

        # Username cache: maps Rust user_id (SSRC string) to display name
        self._usernames: dict[str, str] = {}
        # Reverse: maps Discord member ID to assigned SSRC (for multi-speaker tracking)
        self._ssrc_by_member_id: dict[int, str] = {}

        # Stderr ring buffer — captures last N lines for diagnostics on crash
        self._stderr_buf: collections.deque[str] = collections.deque(maxlen=200)

        # Stats
        self.stats = {
            'audio_chunks': 0,
            'joins': 0,
            'leaves': 0,
            'restarts': 0,
            'errors': 0,
        }

        get_logger().info(f" Rust voice bridge initialized (binary: {self.binary_path})")

# --- Core ---
    async def start(
        self,
        guild_id: int,
        channel_id: int,
        voice_client: Any = None,
        connection_info: dict[str, Any] | None = None,
    ) -> bool:
        """
        Start the Rust voice receiver, connecting to the given voice channel.

        Extracts voice server info either from a discord.py VoiceClient or
        from a pre-built ConnectionInfo dict (from InfoCaptureProtocol).

        The Rust binary then:
          1. Parses the JSON ConnectionInfo
          2. Creates a songbird Driver (no gateway — just UDP voice)
          3. Connects to the Discord voice endpoint
          4. Starts decoding incoming Opus packets and writing PCM to stdout
          5. Listens for SPEAK/INTERRUPT/SHUTDOWN commands on stdin

        Args:
            guild_id: Discord guild ID
            channel_id: Discord voice channel ID
            voice_client: discord.VoiceClient instance (already connected)
            connection_info: Pre-built ConnectionInfo dict (alternative)

        Returns:
            True if successfully started
        """
        if not os.path.exists(self.binary_path):
            get_logger().error(f" Rust binary not found: {self.binary_path}")
            get_logger().error("   Build with: cd voice/rust_receiver && cargo build --release")
            return False

        if connection_info is None:
            if voice_client is None:
                get_logger().error(" Either voice_client or connection_info must be provided")
                return False
            info = self._extract_voice_info(voice_client, guild_id, channel_id)
        else:
            info = connection_info
        if info is None:
            get_logger().error(" Failed to get voice server info")
            return False

        get_logger().info(f" Starting Rust voice receiver for guild {guild_id}, channel {channel_id}")
        get_logger().info(f"   Endpoint: {info['endpoint']}")

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

            # Send ConnectionInfo as JSON on stdin (first line).
            # The Rust binary reads this line synchronously before entering the main loop.
            info_json = json.dumps(info) + "\n"
            if self.proc.stdin is None:
                get_logger().error(" Rust process stdin not available")
                return False
            self.proc.stdin.write(info_json.encode('utf-8'))
            await self.proc.stdin.drain()

            self.reader = RustStdoutReader(self.proc)
            self._reader_task = asyncio.create_task(self.reader.read_loop())
            self._guild_id = guild_id
            self._channel_id = channel_id
            self._running = True
            self._voice_client = voice_client
            self._last_connection_info = info
            self._start_mode = "voice_client"
            self._death_event.clear()
            self._shutdown_requested = False

            # Start async reader loop — dispatches events from RustStdoutReader
            self._reader_consumer_task = asyncio.create_task(self._read_loop())

            # Start supervisor — watches for process death and re-spawns
            self._supervisor_task = asyncio.create_task(self._supervise_rust_process())

            # Start stderr reader (Rust tracing output to Python logger)
            self._start_stderr_reader()

            get_logger().info(" Rust voice receiver started, waiting for audio...")
            return True

        except Exception as e:
            get_logger().exception(f" Failed to start Rust voice receiver: {e}")
            self.stats['errors'] += 1
            return False

    async def stop(self) -> None:
        """Stop the Rust voice receiver and clean up."""
        self._running = False
        self._shutdown_requested = True

        # Cancel tasks
        for task in [self._reader_task, self._reader_consumer_task, self._supervisor_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Terminate Rust process
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=5.0)
            except (ProcessLookupError, TimeoutError):
                self.proc.kill()
            except Exception as e:
                get_logger().debug(f" Error stopping Rust process: {e}")

        self.proc = None
        self.reader = None
        get_logger().info(" Rust voice receiver stopped")

    async def _supervise_rust_process(self) -> None:
        """Watch the Rust process and handle reconnection on crash."""
        try:
            await self._death_event.wait()
        except asyncio.CancelledError:
            pass

# --- Helpers ---
    async def _handle_audio(self, user_id: str, pcm_data: bytes) -> None:
        """
        Route decoded PCM audio from Rust to AudioStreamProcessor.

        Each decoded frame from the Rust binary (48kHz stereo 16-bit PCM)
        is fed into process_audio_chunk for VAD, buffering, and transcription.

        Args:
            user_id: User ID string
            pcm_data: Decoded PCM audio chunk (48kHz, 16-bit, stereo)
        """
        self.stats['audio_chunks'] += 1

        # Resolve username from cache; fallback to voice channel member list
        username = self._usernames.get(user_id)
        if username is None:
            username = await self._resolve_username_from_vc(user_id)

        # Log every 100th chunk to confirm audio is flowing (diagnostic)
        if self.stats['audio_chunks'] % 100 == 0:
            get_logger().debug(f"[DBG-AUDIO] chunk #{self.stats['audio_chunks']} user={username} bytes={len(pcm_data)}")

        # Feed to audio pipeline (same interface as AudioSink.write)
        try:
            self.audio_processor.process_audio_chunk(
                user_id=user_id,
                username=username,
                guild_id=str(self._guild_id) if self._guild_id else "0",
                channel_id=str(self._channel_id) if self._channel_id else "0",
                audio_data=pcm_data,
            )
        except Exception as e:
            get_logger().error(f" Error feeding audio to processor: {e}")

    async def _handle_join(self, user_id: str) -> None:
        """A user started speaking in voice — resolve their Discord display name."""
        self.stats['joins'] += 1

        if user_id not in self._usernames:
            await self._resolve_username_from_vc(user_id)

        username = self._usernames.get(user_id, f"user_{user_id}")
        get_logger().info(f" User speaking: {username} (ID: {user_id})")

    async def _resolve_username_from_vc(self, user_id: str) -> str:
        """Resolve a Rust SSRC/user_id to a Discord display name via voice channel members."""
        # 1. Is this SSRC already mapped?
        if user_id in self._usernames:
            return self._usernames[user_id]

        try:
            guild = self.voice_listener.client.get_guild(self._guild_id)
            if guild is None or self._channel_id is None:
                return f"user_{user_id}"

            channel = guild.get_channel(self._channel_id)
            if channel is None or not hasattr(channel, 'members'):
                return f"user_{user_id}"

            bot_id = self.voice_listener.client.user.id
            members = channel.members  # type: ignore[attr-defined]

            # 2. Find a member not already mapped to an active SSRC
            for member in members:
                if member.id == bot_id:
                    continue
                if member.id not in self._ssrc_by_member_id:
                    self._ssrc_by_member_id[member.id] = user_id
                    self._usernames[user_id] = member.display_name
                    return str(member.display_name)

            # 3. All members are already speaking — reuse the first non-bot member
            for member in members:
                if member.id != bot_id:
                    self._usernames[user_id] = member.display_name
                    return str(member.display_name)
        except Exception as e:
            get_logger().debug("Failed to resolve username for %s: %s", user_id, e)

        return f"user_{user_id}"

    def _handle_leave(self, user_id: str) -> None:
        """A user stopped speaking in voice (no longer in VoiceTick.speaking)."""
        self.stats['leaves'] += 1
        # Free the member slot so a reconnecting speaker gets a fresh assignment
        user_name = self._usernames.pop(user_id, None)
        if user_name is not None:
            stale: list[int] = [mid for mid, sid in self._ssrc_by_member_id.items() if sid == user_id]
            for mid in stale:
                del self._ssrc_by_member_id[mid]

    def _handle_process_death(self) -> None:
        """Handle Rust process death — log diagnostics and signal supervisor."""
        get_logger().error(" Rust process died unexpectedly")
        self.stats['errors'] += 1
        self._death_event.set()

    def get_stats(self) -> dict[str, Any]:
        """Return current Rust voice bridge statistics."""
        try:
            stats: dict[str, Any] = {
                "active": self._running,
                "pid": self.proc.pid if self.proc else None,
                "guild_id": str(self._guild_id) if self._guild_id else None,
                "channel_id": str(self._channel_id) if self._channel_id else None,
                "receiver_mode": "rust",
            }
            stats["audio_chunks"] = self.stats.get("audio_chunks", 0)
            stats["joins"] = self.stats.get("joins", 0)
            stats["leaves"] = self.stats.get("leaves", 0)
            stats["restarts"] = self.stats.get("restarts", 0)
            stats["errors"] = self.stats.get("errors", 0)
            return stats
        except Exception:
            return {"active": False, "error": "stats unavailable"}

    def _handle_tts_done(self) -> None:
        """
        TTS playback finished — release the processing lock.

        This is called when the Rust binary sends TTS_DONE after the songbird
        TrackEvent::End fires. The processing lock was set in
        AudioStreamProcessor._queue_for_transcription() to prevent new speech
        during the LLM/TTS cycle. Releasing it allows the next utterance to
        be transcribed immediately.

        If there's no lock for this guild (already expired), this is a no-op.
        """
        get_logger().info("voice.tts_playback_done", extra={"guild_id": str(self._guild_id)})
        guild_id = str(self._guild_id)
        if hasattr(self.audio_processor, '_release_lock'):
            self.audio_processor._release_lock(guild_id)
        if hasattr(self.audio_processor, '_flush_buffered_audio'):
            self.audio_processor._flush_buffered_audio(guild_id)

# --- Errors ---
# (none)
