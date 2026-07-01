"""Audio utilities — PCM conversion, Gemma transcription."""
import asyncio
import base64
import io
import wave

import numpy as np

from serin.logger import logger


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

async def _transcribe_with_gemma(self, audio_data: bytes, username: str = "User") -> str | None:
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
        max_audio_bytes = 5_760_000
        if len(audio_data) > max_audio_bytes:
            logger.info(f" Truncating audio from {len(audio_data)} to {max_audio_bytes} bytes (30s limit)")
            audio_data = audio_data[:max_audio_bytes]
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
