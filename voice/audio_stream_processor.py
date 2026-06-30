"""
Audio Stream Processor — Per-User Audio Buffer, VAD & Pipeline Orchestrator

This is the core of the voice conversation pipeline. It:

  1. Receives raw PCM audio chunks (48kHz stereo 16-bit) from the Rust songbird bridge
  2. Runs energy-based Voice Activity Detection on each chunk
  3. Buffers audio per-user while they speak
  4. Detects when the user stops speaking (silence threshold = 1.5s of consecutive non-voice frames)
  5. Queues the buffered audio for transcription (either direct to Gemma or via Whisper STT)
  6. Sets a processing lock so new speech during LLM/TTS is buffered silently
  7. The lock is released by a TTS_DONE signal from Rust when playback actually finishes

Noise filtering:
  - Audio under 1 second total (192KB) is discarded entirely
  - Brief voice bursts under 0.5s (25 frames) don't reset the silence counter
  - This prevents pops, clicks, and Discord audio dropouts from extending the response window

Processing lock lifecycle:
  1. User stops speaking → silence timer fires → _queue_for_transcription → _set_lock(30s)
  2. LLM generates, TTS synthesizes, audio sent to Rust bridge
  3. Rust songbird plays TTS through the voice channel
  4. When playback finishes, Rust sends TTS_DONE → Python receives it → _release_lock()
  5. Next user utterance is processed immediately (no artificial delay)

  The 30s lock duration is purely a safety net — TTS_DONE normally releases it much sooner.
"""
import asyncio
import base64
import io
import numpy as np
import os
import struct
import time
import wave
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union
from collections import deque
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import logger


class AudioStreamProcessor:
    """
    Processes audio streams per-user with VAD, noise filtering, and silence-based chunking.

    The processing pipeline:
      process_audio_chunk()  ← called for every decoded PCM frame from Rust
        ↓
      _detect_voice_activity()  ← energy-based RMS VAD
        ↓
      Buffer accumulates while user speaks
        ↓
      Silence threshold (1.5s) → _queue_for_transcription()
        ↓
      _set_lock() ← prevents new transcriptions during the response cycle
        ↓
      _transcribe_and_store() → direct to Gemma or Whisper STT
        ↓
      LLM response → TTS → Rust plays audio → TTS_DONE → _release_lock()
    """

    def __init__(self, whisper_transcriber: Any, voice_pipeline: Any, silence_threshold: float = 3.0,
                 voice_output_manager: Optional[Any] = None, llm_connector: Optional[Any] = None) -> None:
        """
        Initialize audio stream processor.

        Args:
            whisper_transcriber: WhisperTranscriber instance (used for non-Gemma STT)
            voice_pipeline: VoiceMemoryPipeline instance (stores messages, triggers responses)
            silence_threshold: Seconds of consecutive silence before a chunk is queued for transcription
            voice_output_manager: VoiceOutputManager instance (handles TTS playback, needed for interrupts)
            llm_connector: Optional LLM connector (used for direct Gemma input_audio transcription)
        """
        self.transcriber = whisper_transcriber
        self.voice_pipeline = voice_pipeline
        self.silence_threshold = silence_threshold  # Seconds of silence before queueing
        self.voice_output_manager = voice_output_manager
        self.llm_connector = llm_connector
        # LLM_SUPPORTS_AUDIO=true means the LLM accepts direct audio input (Gemma unified format).
        # When True, audio is sent directly to the model instead of going through Whisper STT.
        self.supports_audio = os.environ.get("LLM_SUPPORTS_AUDIO", "false").lower() in ("true", "1", "yes")

        # Per-user audio buffers — accumulate raw PCM (48kHz stereo 16-bit) until silence triggers processing.
        self.user_buffers: Dict[str, bytearray] = {}

        # Per-user silence counters (in frames at 50 fps = 20ms each).
        # Incremented on every non-voice frame. When >= SILENCE_FRAMES_THRESHOLD, buffer is queued.
        self.user_silence_frames: Dict[str, int] = {}

        # Per-user silence timers — a fallback for when the Rust bridge stops sending chunks entirely.
        # The timer fires after silence_threshold seconds. If audio arrives, the timer is cancelled/rescheduled.
        self._silence_timers: Dict[str, Optional[asyncio.Task]] = {}

        # Per-user voice burst counter — counts consecutive voice frames to distinguish real speech from noise.
        # Only resets the silence counter if the burst reaches 25 frames (0.5s of continuous voice).
        # Brief pops/clicks are buffered but don't extend the silence window.
        self.user_voice_burst: Dict[str, int] = {}

        # Per-guild processing lock — prevents cascading response cycles.
        # Set when audio is queued for transcription; released by TTS_DONE signal from Rust.
        # During the lock window, new audio is silently buffered but not processed.
        # The lock is keyed by guild_id (string) to support multiple voice channels.
        self._processing_lock_until: Dict[str, float] = {}

        # Set of user IDs currently flagged as speaking (used for interrupt detection).
        # When a user is in this set and the bot is speaking, an interrupt is triggered.
        # The user is removed from this set when their silence threshold fires.
        self.currently_speaking: set = set()

        # Async queue for transcription jobs — processed one at a time by _process_queue().
        # maxsize=50 prevents unbounded memory growth if the LLM falls behind.
        self.processing_queue = asyncio.Queue(maxsize=50)
        self.is_running = False
        self.processing_task = None

        # Voice Activity Detection settings
        # VAD_THRESHOLD: RMS energy level above which a frame is considered "voice".
        # 150 is relatively low — catches quieter speech and garbled audio from Opus decode errors.
        # FRAMES_PER_SECOND: Discord sends 20ms audio frames = 50 fps.
        # SILENCE_FRAMES_THRESHOLD: How many consecutive non-voice frames trigger processing.
        self.VAD_THRESHOLD = 150
        self.FRAMES_PER_SECOND = 50
        self.SILENCE_FRAMES_THRESHOLD = int(silence_threshold * self.FRAMES_PER_SECOND)

        # MAX_BUFFER_BYTES: Maximum buffer size before forced transcription.
        # For Gemma unified (direct audio, no Whisper): 30 seconds max (Gemma's input limit).
        #   Formula: 48kHz × 2ch × 2bytes × 30s = 5,760,000 bytes
        # For other models (Whisper STT): ~4 minutes (practical memory limit, not a model limit).
        #   Formula: 48kHz × 2ch × 2bytes × 260s ≈ 50,000,000 bytes
        self.MAX_BUFFER_BYTES = 5_760_000 if (self.llm_connector and self.supports_audio) else 50_000_000

        self.stats = {
            'chunks_received': 0,
            'chunks_processed': 0,
            'users_speaking': 0,
            'transcriptions_queued': 0,
            'transcriptions_completed': 0,
            'vad_detections': 0,
            'silence_detections': 0,
            'errors': 0
        }

        logger.info(" Audio stream processor initialized")
        logger.info(f"    VAD threshold: {self.VAD_THRESHOLD}")
        logger.info(f"    Silence threshold: {silence_threshold}s")
        if self.llm_connector and self.supports_audio:
            logger.info("    Direct audio support enabled (gemma12b input_audio)")

    @staticmethod
    def _pcm_to_wav_base64(audio_data: bytes, sample_rate: int = 16000) -> str:
        """
        Convert Discord PCM audio (48kHz stereo 16-bit) to 16kHz mono WAV base64.

        This conversion is necessary because:
          - Discord sends 48kHz stereo, but Gemma expects 16kHz mono
          - The model's input_audio field accepts base64-encoded WAV
          - WAV header provides format metadata the model needs

        Steps:
          1. Decode raw PCM bytes → numpy int16 array
          2. Stereo to mono: take every other sample (left channel)
          3. Resample 48kHz → 16kHz via linear interpolation
          4. Write WAV header + PCM to BytesIO → base64 encode

        Args:
            audio_data: Raw PCM audio data (48kHz stereo, 16-bit signed integer)
            sample_rate: Target sample rate (default 16000 for gemma12b)

        Returns:
            Base64-encoded WAV audio data string
        """
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # Stereo to mono: take left channel only.
        # Discord audio interleaves left/right samples: [L0, R0, L1, R1, ...]
        if len(audio_array) % 2 == 0:
            audio_mono = audio_array[::2]
        else:
            audio_mono = audio_array

        # Resample from 48kHz to target sample rate using linear interpolation.
        # Simple decimation (nearest-neighbor) would cause aliasing; linear interpolation
        # is good enough for speech and fast to compute with numpy.
        orig_sr = 48000
        if orig_sr != sample_rate:
            ratio = orig_sr / sample_rate
            target_length = int(len(audio_mono) / ratio)
            indices = np.linspace(0, len(audio_mono) - 1, target_length)
            audio_mono = np.interp(indices, np.arange(len(audio_mono)), audio_mono).astype(np.int16)

        # Write WAV file to an in-memory buffer.
        # WAV header includes: sample rate, channels=1, bits per sample=16.
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(audio_mono.tobytes())

        return base64.b64encode(buf.getvalue()).decode('ascii')

    async def _transcribe_with_gemma(self, audio_data: bytes, username: str = "User") -> Optional[str]:
        """
        Transcribe audio using Gemma's direct input_audio support.

        This bypasses Whisper entirely by sending the audio + a prompt to the LLM
        in a single call. The model transcribes the audio natively.

        WARNING: Gemma has a 30-second audio limit. Audio beyond that is truncated.
        The truncation happens BEFORE WAV conversion to avoid converting data that
        will be discarded anyway.

        Args:
            audio_data: Raw PCM audio data (48kHz stereo 16-bit)
            username: Username for the transcription prompt context

        Returns:
            Transcribed text string, or None on failure
        """
        try:
            # Gemma4 audio limit: truncate to 30 seconds max.
            # 48kHz × 2ch × 2bytes × 30s = 5,760,000 bytes
            MAX_AUDIO_BYTES = 5_760_000
            if len(audio_data) > MAX_AUDIO_BYTES:
                logger.info(f" Truncating audio from {len(audio_data)} to {MAX_AUDIO_BYTES} bytes (30s limit)")
                audio_data = audio_data[:MAX_AUDIO_BYTES]
            wav_b64 = self._pcm_to_wav_base64(audio_data)

            # Build the message with text + audio content.
            # The text prompt instructs the model to transcribe, and the audio is
            # attached via the input_audio field (OpenAI-compatible API format).
            messages = [{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': f'Transcribe exactly what {username} said. Output only the transcription, nothing else.'},
                    {'type': 'input_audio', 'input_audio': {'data': wav_b64, 'format': 'wav'}},
                ],
            }]

            # Use temperature=0.0 for deterministic transcription (no creativity needed).
            transcription = await self.llm_connector.chat_completion(
                messages,
                max_tokens=300,
                temperature=0.0
            )

            # Clean up the transcription: strip whitespace and any surrounding quotes.
            transcription = transcription.strip().strip('"\'')

            if transcription:
                logger.info(f" Gemma audio transcription: '{transcription}'")
                return transcription
            return None

        except Exception as e:
            logger.error(f" Gemma audio transcription error: {e}")
            return None

    async def start(self) -> None:
        """Start the background transcription queue processor."""
        if self.is_running:
            logger.warning(" Audio processor already running")
            return

        self.is_running = True
        self.processing_task = asyncio.create_task(self._process_queue())
        logger.info(" Audio stream processor started")

    async def stop(self) -> None:
        """Stop the background transcription queue processor."""
        self.is_running = False
        if self.processing_task:
            self.processing_task.cancel()
        logger.info(" Audio stream processor stopped")

    def process_audio_chunk(
        self,
        user_id: str,
        username: str,
        guild_id: str,
        channel_id: str,
        audio_data: bytes
    ) -> None:
        """
        Process incoming audio chunk from a user.

        This is the main entry point called for every decoded PCM frame from the Rust bridge.
        The flow:
          1. Check processing lock — if locked, silently buffer and return
          2. Cancel any pending silence timer (user is still active)
          3. Run VAD on the chunk
          4. Buffer the audio (always — even silence)
          5. If voice: increment burst counter. If burst >= 25 frames (0.5s), reset silence counter.
             Check buffer overflow. Mark user as speaking if first voice detection.
          6. If silence: reset burst counter, increment silence counter.
             If >= threshold, queue for transcription.
          7. Schedule fallback silence timer

        Called from:
          - RustVoiceBridge._handle_audio() for decoded PCM from the Rust binary
          - AudioSink.write() for the legacy discord.py audio pipeline

        Args:
            user_id: User ID string
            username: Username (for logging and context)
            guild_id: Guild ID string
            channel_id: Voice channel ID string
            audio_data: Raw PCM audio chunk (48kHz, 16-bit, stereo)
        """
        try:
            self.stats['chunks_received'] += 1

            # ── Processing Lock ──────────────────────────────────────────────
            # If this guild is currently in a response cycle (LLM generating or
            # TTS playing), buffer the audio silently and skip all VAD logic.
            # The lock is released by the TTS_DONE signal from the Rust binary
            # when TTS playback actually finishes. See _set_lock() and _release_lock().
            if self._is_locked(guild_id):
                if user_id not in self.user_buffers:
                    self.user_buffers[user_id] = bytearray()
                    self.user_silence_frames[user_id] = 0
                    self.user_voice_burst[user_id] = 0
                self.user_buffers[user_id].extend(audio_data)
                return

            # ── Initialize user state if first time seeing this user ─────────
            if user_id not in self.user_buffers:
                self.user_buffers[user_id] = bytearray()
                self.user_silence_frames[user_id] = 0
                self.user_voice_burst[user_id] = 0

            # Cancel pending silence timer — a new chunk arrived, so the user
            # is still active. The timer will be rescheduled at the end.
            self._cancel_silence_timer(user_id)

            # ── Voice Activity Detection ─────────────────────────────────────
            is_voice = self._detect_voice_activity(audio_data)

            # Log VAD state every 500 chunks for debugging audio flow
            if user_id in self.currently_speaking and self.stats['chunks_received'] % 500 == 0:
                buf_size = len(self.user_buffers.get(user_id, bytearray()))
                logger.debug(f"[DBG-VAD] user={user_id} speaking buf={buf_size}B silence_frames={self.user_silence_frames.get(user_id, 0)}")

            # Always buffer audio — both voice and silence accumulate.
            # This ensures the full utterance from start to finish is captured,
            # including brief pauses during natural speech.
            self.user_buffers[user_id].extend(audio_data)

            if is_voice:
                # ── Voice Frame Handling ────────────────────────────────────
                # Increment the voice burst counter. This counter tracks consecutive
                # voice frames. We use it to filter out brief noise bursts (pops,
                # clicks, Discord audio artifacts) that shouldn't extend the silence
                # window or reset the silence timer.
                self.user_voice_burst[user_id] = self.user_voice_burst.get(user_id, 0) + 1

                # Only reset the silence counter if the voice burst is sustained
                # for at least 25 frames (0.5 seconds at 50 fps). Brief noises
                # are buffered but don't restart the silence clock.
                # This prevents scenarios like:
                #   User speaks → stops → 1.2s silence → 0.2s noise → silence resets
                #   → wait another 1.5s → total 2.9s wait
                # Instead:
                #   User speaks → stops → 1.2s silence → 0.2s noise (burst=10, <25)
                #   → silence counter keeps ticking → at 1.5s total → queue
                if self.user_voice_burst[user_id] >= 25:
                    self.user_silence_frames[user_id] = 0

                # Buffer overflow: if the accumulated audio exceeds MAX_BUFFER_BYTES,
                # force transcription immediately. This handles the case where the
                # user speaks continuously without any silence gaps.
                if len(self.user_buffers[user_id]) >= self.MAX_BUFFER_BYTES:
                    logger.debug(f"[DBG-VAD] Buffer overflow ({len(self.user_buffers[user_id])}B) — forcing transcription")
                    self._queue_for_transcription(
                        user_id=user_id,
                        username=username,
                        guild_id=guild_id,
                        channel_id=channel_id
                    )
                    self.currently_speaking.discard(user_id)
                    return  # Don't schedule timer — this utterance is done

                # First voice frame for this user in this burst.
                # Add to currently_speaking set and trigger an interrupt if the
                # bot is currently talking (so the user can interrupt the bot).
                if user_id not in self.currently_speaking:
                    self.currently_speaking.add(user_id)
                    self.stats['vad_detections'] += 1
                    logger.debug(f" {username} started speaking")

                    # INTERRUPT: If the bot is speaking, stop it immediately so the
                    # user can interject. This creates a natural conversational flow
                    # where the bot yields to the user.
                    if self.voice_output_manager:
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(self.voice_output_manager.stop_speaking(int(guild_id)))
                        except (RuntimeError, ValueError, AttributeError) as e:
                            logger.debug(f"Could not interrupt TTS: {e}")

            else:
                # ── Silence Frame Handling ───────────────────────────────────
                # Reset the voice burst counter — the user is not speaking now.
                self.user_voice_burst[user_id] = 0

                # Increment the silence frame counter.
                self.user_silence_frames[user_id] += 1

                # Check if we've accumulated enough consecutive silence frames
                # to consider the user done speaking.
                if self.user_silence_frames[user_id] >= self.SILENCE_FRAMES_THRESHOLD:
                    self._queue_for_transcription(
                        user_id=user_id,
                        username=username,
                        guild_id=guild_id,
                        channel_id=channel_id
                    )

                    # Reset state for this user — they're done speaking
                    self.currently_speaking.discard(user_id)
                    self.user_silence_frames[user_id] = 0
                    self.stats['silence_detections'] += 1
                    return  # Don't schedule timer — user done

            # ── Fallback Silence Timer ──────────────────────────────────────
            # If no audio chunks arrive within silence_threshold seconds (e.g., the
            # Rust bridge stops sending frames because the user truly stopped talking),
            # this timer will fire and force transcription.
            # The timer is cancelled and rescheduled on every chunk. If the timer
            # fires, it means no chunks arrived for the full silence window.
            self._schedule_silence_timer(user_id, username, guild_id, channel_id)

        except Exception as e:
            logger.error(f" Error processing audio chunk: {e}")
            self.stats['errors'] += 1

    def _detect_voice_activity(self, audio_data: bytes) -> bool:
        """
        Detect if audio contains voice using energy-based VAD.

        Uses RMS (Root Mean Square) energy of the PCM signal. This is a simple
        but effective VAD for conversational speech in quiet-to-moderate noise.
        The threshold (150) was chosen empirically with garbled Opus audio.

        Why not a ML-based VAD (Silero, WebRTC)?
          - Energy-based VAD is fast (no model loading/inference)
          - Works reliably with close-mic speech in quiet environments
          - With the 25-frame burst filter, brief noise misclassifications are harmless
          - Garbled audio from DAVE decode errors still has discernible energy patterns

        Args:
            audio_data: Raw PCM audio chunk (48kHz stereo 16-bit)

        Returns:
            True if the RMS energy exceeds VAD_THRESHOLD (voice detected)
        """
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
            return rms > self.VAD_THRESHOLD
        except Exception as e:
            logger.error(f" Error in VAD: {e}")
            return False

    def _queue_for_transcription(
        self,
        user_id: str,
        username: str,
        guild_id: str,
        channel_id: str
    ) -> None:
        """
        Queue audio buffer for transcription.

        This is the critical handoff point between the VAD pipeline and the
        LLM/response pipeline. It:
          1. Takes the accumulated audio buffer for the user
          2. Validates minimum length (1 second = 192KB at 48kHz stereo 16-bit)
          3. Sets the processing lock to prevent cascading response cycles
          4. Puts the audio data on the async processing queue

        The processing lock is the key to preventing cascading:
          - Set here (30s safety net) when audio is queued
          - Released early by TTS_DONE signal from Rust when playback finishes
          - During the lock: audio is silently buffered but not processed

        Args:
            user_id: User ID string
            username: Username (for logging and context)
            guild_id: Guild ID string
            channel_id: Voice channel ID string
        """
        try:
            buffer = self.user_buffers.get(user_id)

            # Minimum buffer check: 192KB ≈ 1 second of audio.
            # Anything shorter is likely a noise burst, pop, or accidental mic activation.
            # This prevents the bot from responding to brief sounds.
            # Formula: 48000 samples/s × 2ch × 2bytes × 1.0s = 192,000 bytes
            if not buffer or len(buffer) < 192000:
                logger.debug(f" Skipping empty/short buffer for {username}")
                if user_id in self.user_buffers:
                    self.user_buffers[user_id] = bytearray()
                return

            # Copy the buffer and clear it for the next utterance.
            audio_data = bytes(buffer)
            self.user_buffers[user_id] = bytearray()

            # ── Processing Lock ─────────────────────────────────────────────
            # Set the processing lock for this guild. While the lock is active:
            #   - All new audio chunks are silently appended to user buffers
            #   - No VAD, silence counting, or timer scheduling occurs
            #   - The interrupt path is not triggered
            #   - The lock is released when TTS_DONE is received from Rust
            #
            # The 30-second duration is a safety net only. In normal operation,
            # TTS_DONE releases the lock within 3-15 seconds (LLM + TTS time).
            # If TTS_DONE never arrives (Rust crash), the lock auto-expires
            # after 30 seconds to prevent permanent lockout.
            self._set_lock(guild_id, 30.0)

            # Queue for async processing (one at a time).
            try:
                self.processing_queue.put_nowait({
                    'user_id': user_id,
                    'username': username,
                    'guild_id': guild_id,
                    'channel_id': channel_id,
                    'audio_data': audio_data,
                    'timestamp': datetime.now()
                })

                self.stats['transcriptions_queued'] += 1
                logger.debug(f" Queued {len(audio_data)} bytes for transcription: {username}")

            except asyncio.QueueFull:
                logger.warning(f" Transcription queue full, dropping audio from {username}")

        except Exception as e:
            logger.error(f" Error queueing transcription: {e}")
            self.stats['errors'] += 1

    def _cancel_silence_timer(self, user_id: str) -> None:
        """Cancel pending silence timer for a user (audio arrived, user is still active)."""
        task = self._silence_timers.pop(user_id, None)
        if task is not None and not task.done():
            task.cancel()

    def _schedule_silence_timer(
        self,
        user_id: str,
        username: str,
        guild_id: str,
        channel_id: str
    ) -> None:
        """
        Schedule a timer to force transcription after silence_threshold of no audio chunks.

        This is a fallback mechanism for when the Rust bridge stops sending chunks
        entirely (e.g., the user stopped talking and Discord stopped transmitting).
        The primary silence detection (frame-based counter in process_audio_chunk)
        handles the case where silence chunks keep arriving.

        The timer is cancelled and rescheduled on every chunk. If the timer fires,
        it means no chunks arrived for the full silence window. The buffer is then
        queued for transcription.

        The guard `if user_id in self.currently_speaking` prevents the timer from
        firing for users who were never detected as speaking (prevents processing
        of empty/background buffers).
        """
        async def _timer() -> None:
            await asyncio.sleep(self.silence_threshold)
            # Check if user still has buffered audio and was detected as speaking
            if user_id in self.user_buffers and len(self.user_buffers[user_id]) > 0:
                if user_id in self.currently_speaking:
                    logger.debug(f"[DBG-VAD] Silence timer fired for {username} ({len(self.user_buffers[user_id])}B) — queueing transcription")
                    self._queue_for_transcription(
                        user_id=user_id,
                        username=username,
                        guild_id=guild_id,
                        channel_id=channel_id
                    )
                    self.currently_speaking.discard(user_id)
        try:
            loop = asyncio.get_running_loop()
            self._silence_timers[user_id] = loop.create_task(_timer())
        except (RuntimeError, ValueError) as e:
            logger.debug(f"Could not schedule silence timer: {e}")

    def _is_locked(self, guild_id: str) -> bool:
        """
        Check if guild is in a processing lock window.

        The lock is a simple time-based check:
          expire = self._processing_lock_until[guild_id]
          if time.time() < expire → locked
          else → unlocked (and entry cleaned up)

        Returns:
            True if the guild is currently locked (new speech should be buffered silently)
        """
        expire = self._processing_lock_until.get(guild_id, 0)
        if time.time() < expire:
            return True
        # Clean expired locks to prevent unbounded dict growth
        self._processing_lock_until.pop(guild_id, None)
        return False

    def _release_lock(self, guild_id: str) -> None:
        """
        Release processing lock for guild — allow new speech to be processed.

        Called by TTS_DONE handler when the Rust binary signals that TTS playback
        has finished. This allows the next user utterance to trigger transcription.

        If there's no lock for this guild (already expired or never set), this is a no-op.
        """
        self._processing_lock_until.pop(guild_id, None)
        logger.debug(f" Processing lock released for guild {guild_id}")

    def _set_lock(self, guild_id: str, duration: float = 20.0) -> None:
        """
        Set processing lock for guild — new speech during the response cycle is buffered silently.

        The lock duration should be long enough to cover:
          - LLM generation time (typically 3-8 seconds)
          - TTS synthesis time (typically 0.5-3 seconds)
          - TTS playback time (typically 1-10 seconds)

        In normal operation, the lock is released early by the TTS_DONE signal,
        so the duration is a safety net. If TTS_DONE never arrives (Rust crash),
        the lock auto-expires after the duration.

        Args:
            guild_id: Guild ID string
            duration: Lock duration in seconds (default 20.0, overridden to 30.0 in _queue_for_transcription)
        """
        self._processing_lock_until[guild_id] = time.time() + duration
        logger.debug(f" Processing lock set for guild {guild_id} ({duration}s)")

    async def _process_queue(self) -> None:
        """Background task to process transcription queue — one item at a time."""
        logger.info(" Started transcription queue processor")

        while self.is_running:
            try:
                # Wait up to 1 second for the next transcription item.
                # The timeout allows the loop to check self.is_running periodically.
                try:
                    item = await asyncio.wait_for(
                        self.processing_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Transcribe and store the result (sends to LLM or Whisper, triggers response)
                await self._transcribe_and_store(item)

                self.stats['chunks_processed'] += 1

            except asyncio.CancelledError:
                logger.info(" Transcription queue processor cancelled")
                break
            except Exception as e:
                logger.error(f" Error in transcription queue: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(0.5)

        logger.info(" Transcription queue processor stopped")

    async def _transcribe_and_store(self, item: Dict[str, Any]) -> None:
        """
        Transcribe audio and store in memory / trigger response.

        This is the processing step for each queued transcription item. It:
          1. Checks if the model supports direct audio (Gemma unified format)
          2. If yes: truncates audio to 30s max, converts to WAV base64,
             sends to voice pipeline with wav_b64 for direct model input
          3. If no: runs Whisper STT, sends transcription text to voice pipeline

        The voice pipeline (VoiceMemoryPipeline) then:
          - Stores the message in memory
          - Builds conversation context
          - Calls the LLM for a response
          - Queues TTS playback

        Args:
            item: Dict with keys:
                user_id, username, guild_id, channel_id, audio_data, timestamp
        """
        try:
            user_id = item['user_id']
            username = item['username']
            guild_id = item['guild_id']
            channel_id = item['channel_id']
            audio_data = item['audio_data']
            timestamp = item['timestamp']

            logger.info(f" Transcribing audio from {username} ({len(audio_data)} bytes)...")

            if self.llm_connector and self.supports_audio:
                # Check if the model actually supports direct audio.
                # supports_audio=True is set via env var, but we double-check
                # the actual model type from the connector.
                _use_direct_audio = False
                try:
                    model_info = self.llm_connector.get_model_info()
                    _use_direct_audio = 'gemma' in model_info.get('model_type', '').lower()
                except Exception:
                    pass

                if _use_direct_audio:
                    # ── Direct Audio Path (Gemma Unified) ──────────────────
                    # Skip Whisper STT entirely. Feed the raw audio + conversation
                    # context directly to Gemma in one shot. The model handles
                    # both understanding the audio and generating a response.

                    # Truncate to 30 seconds max (Gemma's model limit).
                    MAX_AUDIO_BYTES = 5_760_000  # 48kHz stereo 16-bit × 30s
                    truncated = False
                    if len(audio_data) > MAX_AUDIO_BYTES:
                        logger.info(f" Audio truncated from {len(audio_data)} to {MAX_AUDIO_BYTES} bytes (30s limit)")
                        audio_data = audio_data[:MAX_AUDIO_BYTES]
                        truncated = True

                    # Convert 48kHz stereo PCM → 16kHz mono WAV base64
                    wav_b64 = self._pcm_to_wav_base64(audio_data)

                    # If truncated, inform the model that audio was cut off.
                    transcription = "[voice input]"
                    if truncated:
                        transcription = "[voice input - user was talking for long, only last 30s of audio included]"

                    await self.voice_pipeline.process_voice_message(
                        user_id=user_id,
                        username=username,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        transcription=transcription,
                        wav_b64=wav_b64,  # Direct audio blob for the model
                        timestamp=timestamp
                    )
                    self.stats['transcriptions_completed'] += 1
                else:
                    # ── Whisper STT Path (Non-Gemma with supports_audio flag) ──
                    transcription = await self.transcriber.transcribe(audio_data, language="en")
                    if transcription and len(transcription.strip()) > 0:
                        logger.info(f" Transcribed: '{transcription}'")
                        await self.voice_pipeline.process_voice_message(
                            user_id=user_id,
                            username=username,
                            guild_id=guild_id,
                            channel_id=channel_id,
                            transcription=transcription,
                            timestamp=timestamp
                        )
                        self.stats['transcriptions_completed'] += 1
            else:
                # ── Whisper STT Path (No LLM connector or audio not supported) ──
                transcription = await self.transcriber.transcribe(audio_data, language="en")
                if transcription and len(transcription.strip()) > 0:
                    logger.info(f" Transcribed: '{transcription}'")
                    await self.voice_pipeline.process_voice_message(
                        user_id=user_id,
                        username=username,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        transcription=transcription,
                        timestamp=timestamp
                    )
                    self.stats['transcriptions_completed'] += 1
                else:
                    logger.debug(f" Empty transcription from {username}")

        except Exception as e:
            logger.exception(f" Error transcribing audio: {e}")
            self.stats['errors'] += 1

    def check_interrupt(self, user_id: str) -> bool:
        """
        Check if a user is currently flagged as speaking.

        Used by the TTS queue to check whether the bot should stop speaking.
        If the user starts speaking while the bot is talking, this returns True.

        Args:
            user_id: User ID string to check

        Returns:
            True if the user is in the currently_speaking set
        """
        return user_id in self.currently_speaking

    def get_active_speakers(self) -> Set[str]:
        """Return a copy of the set of currently speaking user IDs."""
        return self.currently_speaking.copy()

    def get_buffer_size(self, user_id: str) -> int:
        """Return the current buffer size in bytes for a user (0 if no buffer)."""
        if user_id in self.user_buffers:
            return len(self.user_buffers[user_id])
        return 0

    def get_stats(self) -> Dict[str, Any]:
        """Return processor statistics for monitoring and debugging."""
        return {
            'chunks_received': self.stats['chunks_received'],
            'chunks_processed': self.stats['chunks_processed'],
            'users_speaking': len(self.currently_speaking),
            'active_speakers': list(self.currently_speaking),
            'transcriptions_queued': self.stats['transcriptions_queued'],
            'transcriptions_completed': self.stats['transcriptions_completed'],
            'queue_size': self.processing_queue.qsize(),
            'vad_detections': self.stats['vad_detections'],
            'silence_detections': self.stats['silence_detections'],
            'errors': self.stats['errors'],
            'is_running': self.is_running
        }
