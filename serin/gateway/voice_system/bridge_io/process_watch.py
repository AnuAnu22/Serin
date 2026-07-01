"""Process supervision for Rust voice bridge."""
import asyncio
import collections
import json
import os
import subprocess
import threading
from collections.abc import Callable
from typing import Any

from serin.gateway.voice_system.bridge import RustStdoutReader
from serin.logger import logger


class RustVoiceBridge:
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
      - stdout reads happen in a background thread (RustStdoutReader)
      - stderr reads happen in a separate background thread
      - The async _read_loop pulls from the thread-safe event queue
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
            base = os.path.dirname(os.path.abspath(__file__))
            binary_path = os.path.join(base, "rust_receiver", "target", "release", "voice_receiver")
        self.binary_path = binary_path

        self.proc: subprocess.Popen | None = None
        self.reader: RustStdoutReader | None = None
        self._reader_task: asyncio.Task | None = None
        self._running = False
        self._guild_id: int | None = None
        self._channel_id: int | None = None

        # ── Stdin serialization lock ─────────────────────────────────────────
        self._stdin_lock = threading.Lock()

        # ── Supervisor / crash recovery ──────────────────────────────────────
        self._voice_client: Any | None = None
        self._last_connection_info: dict | None = None
        self._start_mode: str = "connection_info"  # "voice_client" or "connection_info"
        self._death_event = asyncio.Event()
        self._shutdown_requested = False
        self._supervisor_task: asyncio.Task | None = None
        self._reconnect_callback: Callable | None = None
        self._restart_timestamps: collections.deque = collections.deque(maxlen=5)

        # Username cache: maps user_id string → display name
        self._usernames: dict[str, str] = {}

        # Stderr ring buffer — captures last N lines for diagnostics on crash
        self._stderr_buf: collections.deque = collections.deque(maxlen=200)

        # Stats
        self.stats = {
            'audio_chunks': 0,
            'joins': 0,
            'leaves': 0,
            'restarts': 0,
            'errors': 0,
        }

        logger.info(f" Rust voice bridge initialized (binary: {self.binary_path})")

    async def start(self, guild_id: int, channel_id: int, voice_client: Any) -> bool:
        """
        Start the Rust voice receiver, connecting to the given voice channel.

        Extracts voice server info from the discord.py VoiceClient and passes
        it to the Rust binary as JSON on stdin.

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

        Returns:
            True if successfully started
        """
        if not os.path.exists(self.binary_path):
            logger.error(f" Rust binary not found: {self.binary_path}")
            logger.error("   Build with: cd voice/rust_receiver && cargo build --release")
            return False

        # Extract voice server info from discord.py VoiceClient
        info = self._extract_voice_info(voice_client, guild_id, channel_id)
        if info is None:
            logger.error(" Failed to extract voice server info from VoiceClient")
            return False

        logger.info(f" Starting Rust voice receiver for guild {guild_id}, channel {channel_id}")
        logger.info(f"   Endpoint: {info['endpoint']}")

        try:
            rust_env = os.environ.copy()
            rust_env["RUST_BACKTRACE"] = "full"
            self.proc = subprocess.Popen(
                [self.binary_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                env=rust_env,
            )

            # Send ConnectionInfo as JSON on stdin (first line).
            # The Rust binary reads this line synchronously before entering the main loop.
            info_json = json.dumps(info) + "\n"
            self.proc.stdin.write(info_json.encode('utf-8'))
            self.proc.stdin.flush()

            self.reader = RustStdoutReader(self.proc)
            self._guild_id = guild_id
            self._channel_id = channel_id
            self._running = True
            self._voice_client = voice_client
            self._last_connection_info = info
            self._start_mode = "voice_client"
            self._death_event.clear()
            self._shutdown_requested = False

            # Start async reader loop — dispatches events from RustStdoutReader
            self._reader_task = asyncio.create_task(self._read_loop())

            # Start supervisor — watches for process death and re-spawns
            self._supervisor_task = asyncio.create_task(self._supervise_rust_process())

            # Start stderr reader (Rust tracing output → Python logger)
            self._start_stderr_reader()

            logger.info(" Rust voice receiver started, waiting for audio...")
            return True

        except Exception as e:
            logger.exception(f" Failed to start Rust voice receiver: {e}")
            self.stats['errors'] += 1
            return False

    async def stop(self) -> None:
        """Stop the Rust voice receiver and clean up."""
        self._running = False
        self._shutdown_requested = True
        self._death_event.set()  # unblock supervisor so it can exit

        # Cancel supervisor first (prevents races with re-spawn)
        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()
            try:
                await self._supervisor_task
            except asyncio.CancelledError:
                pass

        # Cancel the async reader loop
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Send SHUTDOWN command to Rust, then wait for graceful exit
        if self.proc and self.proc.poll() is None:
            logger.info(" Stopping Rust voice receiver...")
            try:
                self.proc.stdin.write(b"SHUTDOWN\n")
                self.proc.stdin.flush()
            except Exception:
                pass

            # Give it a moment to exit gracefully (3 second timeout)
            try:
                self.proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

        self.proc = None
        self.reader = None
        logger.info(" Rust voice receiver stopped")

    # -----------------------------------------------------------------------
    # Internal: extract voice server info from discord.py VoiceClient
    # -----------------------------------------------------------------------
    # Discord voice connections require three pieces of info:
    #   endpoint — the voice server hostname
    #   token — voice authentication token
    #   session_id — Discord voice session identifier
    #
    # In discord.py/pycord, these are available from the VoiceClient after
    # the voice state update and voice server update events fire.
    # Pycord stores them as direct attributes; older discord.py may need
    # _connection introspection.

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
                # Try _connection (VoiceConnectionState) directly
                conn = getattr(voice_client, '_connection', None)
                if conn:
                    endpoint = endpoint or getattr(conn, 'endpoint', None)
                    token = token or getattr(conn, 'token', None)
                    session_id = session_id or getattr(conn, 'session_id', None)

            if not all([endpoint, token, session_id]):
                logger.error(
                    f" Missing voice server info: endpoint={endpoint is not None}, "
                    f"token={token is not None}, session_id={session_id is not None}"
                )
                return None

            # Bot's user ID — needed for the Driver to identify itself
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
            logger.exception(f" Error extracting voice info: {e}")
            return None

    # -----------------------------------------------------------------------
    # Internal: async loop to read events from Rust stdout
    # -----------------------------------------------------------------------

    async def _read_loop(self) -> None:
        """
        Asynchronous loop: reads events from RustStdoutReader and dispatches them.

        This runs as an asyncio task. It uses run_in_executor to read from the
        thread-safe RustStdoutReader queue without blocking the event loop.

        Event types:
          audio     → _handle_audio(user_id, pcm_data)
          join      → _handle_join(user_id)
          leave     → _handle_leave(user_id)
          tts_done  → _handle_tts_done()
          log       → forwarded to Python logger

        Critical: TTS_DONE handling
          When the Rust songbird driver finishes playing TTS audio, it sends
          TTS_DONE. This handler calls _release_lock() on the audio processor,
          which allows the next user utterance to be transcribed immediately.
          Without this, the processing lock would remain for the full 30s timeout.
        """
        logger.info(" Rust stdout reader loop started")

        try:
            while self._running and self.reader:
                # Read event in thread (non-blocking via run_in_executor)
                try:
                    event = await asyncio.get_event_loop().run_in_executor(
                        None, self.reader.get, 1.0
                    )
                except EOFError:
                    if self._running:
                        logger.warning(" Rust stdout EOF — process may have crashed")
                        self._handle_process_death()
                    break

                if event is None:
                    # Timeout — no events yet, just loop
                    continue

                event_type = event[0]

                if event_type == 'audio':
                    _, user_id, pcm_data = event
                    self._handle_audio(user_id, pcm_data)

                elif event_type == 'join':
                    user_id = event[1]
                    self._handle_join(user_id)

                elif event_type == 'leave':
                    user_id = event[1]
                    self._handle_leave(user_id)

                elif event_type == 'log':
                    msg = event[1]
                    # Filter important status messages to INFO, rest to DEBUG
                    if any(kw in msg for kw in ['CONNECTED', 'READY', 'JOIN_FAILED', 'GOT_INFO']):
                        logger.info(f"   [rust] {msg}")
                    else:
                        logger.debug(f"   [rust] {msg}")

                elif event_type == 'tts_done':
                    # ── TTS Playback Finished Signal ────────────────────────
                    # This is the most important event for the conversational loop.
                    # When Rust finishes playing TTS audio, we release the processing
                    # lock so the next user utterance can be transcribed immediately.
                    # Without this signal, we'd have to guess the TTS duration or
                    # use a fixed timer — both fragile approaches.
                    self._handle_tts_done()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f" Error in Rust reader loop: {e}")
            self.stats['errors'] += 1

        logger.info(" Rust stdout reader loop ended")

    def _handle_audio(self, user_id: str, pcm_data: bytes) -> None:
        """
        Route decoded PCM audio from Rust to AudioStreamProcessor.

        Each decoded frame from the Rust binary (48kHz stereo 16-bit PCM)
        is fed into process_audio_chunk for VAD, buffering, and transcription.

        Args:
            user_id: User ID string
            pcm_data: Decoded PCM audio chunk (48kHz, 16-bit, stereo)
        """
        self.stats['audio_chunks'] += 1

        # Resolve username from cache (set by set_username)
        username = self._usernames.get(user_id, f"user_{user_id}")

        # Log every 100th chunk to confirm audio is flowing (diagnostic)
        if self.stats['audio_chunks'] % 100 == 0:
            logger.debug(f"[DBG-AUDIO] chunk #{self.stats['audio_chunks']} user={username} bytes={len(pcm_data)}")

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
            logger.error(f" Error feeding audio to processor: {e}")

    def _handle_join(self, user_id: str) -> None:
        """A user started speaking in voice (SpeakingStateUpdate from Discord)."""
        self.stats['joins'] += 1
        username = self._usernames.get(user_id, f"user_{user_id}")
        logger.info(f" User speaking: {username} (ID: {user_id})")

    def _handle_leave(self, user_id: str) -> None:
        """A user stopped speaking in voice (no longer in VoiceTick.speaking)."""
        self.stats['leaves'] += 1

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
        logger.info("voice.tts_playback_done", extra={"guild_id": str(self._guild_id)})
        if hasattr(self.audio_processor, '_release_lock'):
            self.audio_processor._release_lock(str(self._guild_id))
