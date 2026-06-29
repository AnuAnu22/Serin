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
from logger_config import logger


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

    def __init__(self, proc: subprocess.Popen):
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
        binary_path: Optional[str] = None,
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

        self.proc: Optional[subprocess.Popen] = None
        self.reader: Optional[RustStdoutReader] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._running = False
        self._guild_id: Optional[int] = None
        self._channel_id: Optional[int] = None

        # ── Stdin serialization lock ─────────────────────────────────────────
        self._stdin_lock = threading.Lock()

        # ── Supervisor / crash recovery ──────────────────────────────────────
        self._voice_client: Optional[Any] = None
        self._last_connection_info: Optional[Dict] = None
        self._start_mode: str = "connection_info"  # "voice_client" or "connection_info"
        self._death_event = asyncio.Event()
        self._shutdown_requested = False
        self._supervisor_task: Optional[asyncio.Task] = None
        self._reconnect_callback: Optional[Callable] = None
        self._restart_timestamps: collections.deque = collections.deque(maxlen=5)

        # Username cache: maps user_id string → display name
        self._usernames: Dict[str, str] = {}

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

        logger.info(f"✅ Rust voice bridge initialized (binary: {self.binary_path})")

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
            logger.error(f"❌ Rust binary not found: {self.binary_path}")
            logger.error("   Build with: cd voice/rust_receiver && cargo build --release")
            return False

        # Extract voice server info from discord.py VoiceClient
        info = self._extract_voice_info(voice_client, guild_id, channel_id)
        if info is None:
            logger.error("❌ Failed to extract voice server info from VoiceClient")
            return False

        logger.info(f"🚀 Starting Rust voice receiver for guild {guild_id}, channel {channel_id}")
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

            logger.info("✅ Rust voice receiver started, waiting for audio...")
            return True

        except Exception as e:
            logger.exception(f"❌ Failed to start Rust voice receiver: {e}")
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
            logger.info("🛑 Stopping Rust voice receiver...")
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
        logger.info("⏹️ Rust voice receiver stopped")

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
    ) -> Optional[Dict[str, Any]]:
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
                    f"❌ Missing voice server info: endpoint={endpoint is not None}, "
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
            logger.exception(f"❌ Error extracting voice info: {e}")
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
        logger.info("🔄 Rust stdout reader loop started")

        try:
            while self._running and self.reader:
                # Read event in thread (non-blocking via run_in_executor)
                try:
                    event = await asyncio.get_event_loop().run_in_executor(
                        None, self.reader.get, 1.0
                    )
                except EOFError:
                    if self._running:
                        logger.warning("⚠️ Rust stdout EOF — process may have crashed")
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
            logger.error(f"❌ Error in Rust reader loop: {e}")
            self.stats['errors'] += 1

        logger.info("🔄 Rust stdout reader loop ended")

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
            logger.error(f"❌ Error feeding audio to processor: {e}")

    def _handle_join(self, user_id: str) -> None:
        """A user started speaking in voice (SpeakingStateUpdate from Discord)."""
        self.stats['joins'] += 1
        username = self._usernames.get(user_id, f"user_{user_id}")
        logger.info(f"🔊 User speaking: {username} (ID: {user_id})")

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
        logger.info("🔊 TTS playback finished — releasing processing lock")
        if hasattr(self.audio_processor, '_release_lock'):
            self.audio_processor._release_lock(str(self._guild_id))

    def _handle_process_death(self) -> None:
        """Handle Rust process unexpected death — log diagnostics and trigger supervisor."""
        self.stats['errors'] += 1

        # Retry poll() a few times — OS may not have reaped the process yet
        exit_code = None
        if self.proc:
            import time
            for _ in range(10):
                self.proc.poll()
                exit_code = self.proc.returncode
                if exit_code is not None:
                    break
                time.sleep(0.05)

        if exit_code is None:
            logger.error("❌ Rust process died — exit code unknown (pipe closed but process not reaped)")
        elif exit_code < 0:
            signal_name = {-6: "SIGABRT", -9: "SIGKILL", -11: "SIGSEGV", -13: "SIGPIPE"}.get(exit_code, f"signal {-exit_code}")
            logger.error(f"❌ Rust process killed by {signal_name} (code {exit_code})")
        else:
            logger.error(f"❌ Rust process exited with code {exit_code}")

        # Dump stderr ring buffer for diagnostics
        if self._stderr_buf:
            logger.error("--- Rust stderr (last {} lines) ---".format(len(self._stderr_buf)))
            for line in self._stderr_buf:
                logger.error(f"   |{line}")
            logger.error("--- end stderr ---")

        # Signal supervisor to attempt re-spawn
        self._death_event.set()

    # -----------------------------------------------------------------------
    # Supervisor: monitors Rust process health and re-spawns on crash
    # -----------------------------------------------------------------------

    async def _supervise_rust_process(self) -> None:
        """
        Background supervisor task: waits for the Rust process to die,
        then attempts to re-spawn it with rate limiting.

        Rate limiting: max 5 restart attempts within a 60-second window.
        If the rate limit is exceeded, the supervisor gives up to avoid
        infinite crash loops.

        On successful re-spawn, calls the reconnect callback (if set) so
        the voice listener can re-attach any state.
        """
        while not self._shutdown_requested:
            await self._death_event.wait()
            if self._shutdown_requested:
                return

            # Rate limiting: check restart frequency
            now = time.monotonic()
            self._restart_timestamps.append(now)
            if len(self._restart_timestamps) >= 5:
                # 5 restarts in the deque — check if they're within 60s
                oldest = self._restart_timestamps[0]
                if now - oldest < 60.0:
                    logger.critical("Rust process crashed 5 times in 60s — giving up")
                    self.stats['errors'] += 1
                    return

            logger.error("Rust voice process died unexpectedly, restarting in 2s...")
            self.stats['restarts'] += 1
            await asyncio.sleep(2)

            # Clean up old process references
            self.proc = None
            self.reader = None
            self._running = False

            # Re-spawn using the same method that was originally used
            success = False
            guild_id = self._guild_id
            channel_id = self._channel_id
            if guild_id is None or channel_id is None:
                logger.error("Guild or channel ID missing — cannot restart")
                return
            try:
                if self._start_mode == "voice_client" and self._voice_client:
                    success = await self.start(
                        guild_id, channel_id, self._voice_client
                    )
                elif self._last_connection_info:
                    success = await self.start_with_info(
                        guild_id, channel_id, self._last_connection_info
                    )
                else:
                    logger.error("No connection info available for restart — giving up")
                    return
            except Exception as e:
                logger.exception(f"Failed to restart Rust process: {e}")

            if success:
                logger.info("Rust voice process restarted successfully")
                if self._reconnect_callback:
                    try:
                        await self._reconnect_callback()
                    except Exception as e:
                        logger.error(f"Reconnect callback failed: {e}")
                # Clear death event so supervisor waits for next death
                self._death_event.clear()
            else:
                logger.error("Failed to restart Rust process — will retry")
                # Allow retry by clearing death event and looping
                self._death_event.clear()

    def set_reconnect_callback(self, callback: Optional[Callable]) -> None:
        """
        Set a callback to be called when the Rust process is re-spawned after a crash.

        The callback should be an async callable that re-attaches any state
        needed after reconnection (e.g., the voice listener re-attaching audio streams).
        """
        self._reconnect_callback = callback

    # -----------------------------------------------------------------------
    # Internal: stderr reader (Rust tracing/diagnostics → Python logger)
    # -----------------------------------------------------------------------
    # The Rust binary writes tracing output to stderr (eprintln!/tracing).
    # We read this in a background thread and forward it to the Python logger
    # with appropriate log levels. A ring buffer of the last 200 lines is
    # kept for crash diagnostics.

    def _start_stderr_reader(self) -> None:
        """Spawn a daemon thread to read Rust stderr into a ring buffer and Python logger."""
        if not self.proc or not self.proc.stderr:
            return

        def _reader():
            try:
                import io as _io
                stderr_text = _io.TextIOWrapper(
                    self.proc.stderr,
                    encoding='utf-8',
                    errors='replace',
                    line_buffering=True,
                )
                for line in stderr_text:
                    line = line.rstrip()
                    if not line:
                        continue
                    self._stderr_buf.append(line)
                    # Route to appropriate log level based on content
                    if any(kw in line for kw in ['ERROR', 'JOIN_FAILED', 'PANIC']):
                        logger.error(f"   [rust] {line}")
                    elif any(kw in line for kw in ['CONNECTED', 'READY', 'GOT_INFO']):
                        logger.info(f"   [rust] {line}")
                    elif 'RTP' in line or 'SPEAKING' in line:
                        logger.debug(f"   [rust] {line}")
                    else:
                        logger.debug(f"   [rust] {line}")
            except Exception as e:
                logger.debug(f"   [stderr reader] exited: {e}")

        threading.Thread(target=_reader, name="rust-stderr-reader", daemon=True).start()

    # -----------------------------------------------------------------------
    # Public: update username mapping for logging
    # -----------------------------------------------------------------------

    def set_username(self, user_id: str, username: str) -> None:
        """Map a user_id to a display name for logging purposes."""
        self._usernames[user_id] = username

    # -----------------------------------------------------------------------
    # Public: send TTS audio to Rust binary for voice channel playback
    # -----------------------------------------------------------------------

    async def send_tts_audio(self, audio_data: bytes) -> None:
        """
        Send TTS audio data to the Rust binary for voice channel playback.

        The Rust binary writes the WAV data to /tmp/serin_tts_output.wav and
        plays it through the songbird Driver. When playback finishes, the
        Rust binary sends TTS_DONE back to Python.

        Protocol:
          SPEAK:{len(audio_data)}\\n followed by audio_data bytes

        Args:
            audio_data: WAV audio bytes from TTS engine (16kHz mono 16-bit WAV)
        """
        if not self.proc or not self.proc.stdin:
            logger.warning("⚠️ Cannot send TTS: Rust process not running")
            return
        try:
            loop = asyncio.get_event_loop()
            header = f"SPEAK:{len(audio_data)}\n".encode('utf-8')
            logger.info(f"🗣️ Writing {len(header) + len(audio_data)} bytes to Rust stdin")
            # Write in a thread to avoid blocking the event loop
            await loop.run_in_executor(None, self._write_stdin, header + audio_data)
        except Exception as e:
            logger.error(f"❌ Error sending TTS audio: {e}")

    async def interrupt(self) -> None:
        """
        Interrupt current TTS playback.

        Sends INTERRUPT command to Rust binary, which stops the current
        songbird track (handle.stop()) and removes the temp WAV file.
        """
        if not self.proc or not self.proc.stdin:
            return
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_stdin, b"INTERRUPT\n")
        except Exception:
            pass

    def _write_stdin(self, data: bytes) -> None:
        """
        Thread-safe blocking write to Rust stdin.

        CRITICAL: All stdin writes MUST go through this method.
        The threading.Lock() prevents interleaving between send_tts_audio
        and interrupt commands. Without it, the binary protocol framing
        could be corrupted (e.g., "SPEAK:1000\n" split across two writes).

        This is a synchronous blocking call — should be called via
        run_in_executor to avoid blocking the event loop.
        """
        with self._stdin_lock:
            if self.proc and self.proc.stdin:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()

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
            logger.error(f"❌ Rust binary not found: {self.binary_path}")
            logger.error("   Build with: cd voice/rust_receiver && cargo build --release")
            return False

        logger.info(
            f"🚀 Starting Rust voice receiver for guild {guild_id}, "
            f"channel {channel_id} (gateway info)"
        )

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

            info_json = json.dumps(connection_info) + "\n"
            self.proc.stdin.write(info_json.encode('utf-8'))
            self.proc.stdin.flush()

            self.reader = RustStdoutReader(self.proc)
            self._guild_id = guild_id
            self._channel_id = channel_id
            self._running = True
            self._voice_client = None
            self._last_connection_info = connection_info
            self._start_mode = "connection_info"
            self._death_event.clear()
            self._shutdown_requested = False

            self._reader_task = asyncio.create_task(self._read_loop())

            # Start supervisor — watches for process death and re-spawns
            self._supervisor_task = asyncio.create_task(self._supervise_rust_process())

            self._start_stderr_reader()

            logger.info("✅ Rust voice receiver started (gateway info mode)")
            return True

        except Exception as e:
            logger.exception(f"❌ Failed to start Rust voice receiver: {e}")
            self.stats['errors'] += 1
            return False

    # -----------------------------------------------------------------------
    # Public: status
    # -----------------------------------------------------------------------

    def is_running(self) -> bool:
        """Check if the Rust process is alive (not None and still running)."""
        return self.proc is not None and self.proc.poll() is None

    def get_stats(self) -> Dict[str, Any]:
        """Get bridge statistics (chunks, joins, leaves, errors, etc.)."""
        return {
            **self.stats,
            'process_alive': self.is_running(),
            'guild_id': self._guild_id,
            'channel_id': self._channel_id,
        }
