"""Audio stream processor — per-user PCM buffer, VAD, and transcription pipeline."""

import asyncio
import os
import secrets
import sys
from typing import Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from serin.config.config import config
from serin.state.logger import logger


def _rand() -> float:
    return secrets.randbelow(10_000_000) / 10_000_000

def _uniform(a: float, b: float) -> float:
    return a + (b - a) * secrets.randbelow(10_000_000) / 10_000_000

# ── Constants ──────────────────────────────────────────────────────────────────
VAD_AMPLITUDE_THRESHOLD = 150           # RMS amplitude below which is considered silence
SILENCE_FRAMES_BEFORE_FLUSH = 75        # 1.5s at 50 frames/sec
MIN_BUFFER_BYTES = 192_000              # ~1 second of 48kHz stereo PCM
MAX_BUFFER_BYTES_GEMMA = 5_760_000      # ~30 seconds (Gemma audio limit)
MAX_BUFFER_BYTES_WHISPER = 50_000_000   # ~260 seconds (Whisper limit)
PROCESSING_LOCK_SECONDS = 30            # How long to lock after queueing audio
VOICE_BURST_IGNORE_FRAMES = 25          # Ignore bursts shorter than 0.5s


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

    def __init__(self, transcriber: Any, voice_pipeline: Any, silence_threshold: float = 3.0,
                 voice_output_manager: Any | None = None, llm_connector: Any | None = None) -> None:
        """
        Initialize audio stream processor.

        Args:
            transcriber: WhisperTranscriber instance (used for non-Gemma STT)
            voice_pipeline: VoiceMemoryPipeline instance (stores messages, triggers responses)
            silence_threshold: Seconds of consecutive silence before a chunk is queued for transcription
            voice_output_manager: VoiceOutputManager instance (handles TTS playback, needed for interrupts)
            llm_connector: Optional LLM connector (used for direct Gemma input_audio transcription)
        """
        self.transcriber = transcriber
        self.voice_pipeline = voice_pipeline
        self.silence_threshold = silence_threshold  # Seconds of silence before queueing
        self.voice_output_manager = voice_output_manager
        self.llm_connector = llm_connector
        # LLM_SUPPORTS_AUDIO=true means the LLM accepts direct audio input (Gemma unified format).
        # When True, audio is sent directly to the model instead of going through Whisper STT.
        self.supports_audio = config.LLM_SUPPORTS_AUDIO

        # Per-user audio buffers — accumulate raw PCM (48kHz stereo 16-bit) until silence triggers processing.
        self.user_buffers: dict[str, bytearray] = {}

        # Per-user silence counters (in frames at 50 fps = 20ms each).
        # Incremented on every non-voice frame. When >= SILENCE_FRAMES_THRESHOLD, buffer is queued.
        self.user_silence_frames: dict[str, int] = {}

        # Per-user silence timers — a fallback for when the Rust bridge stops sending chunks entirely.
        # The timer fires after silence_threshold seconds. If audio arrives, the timer is cancelled/rescheduled.
        self._silence_timers: dict[str, asyncio.Task | None] = {}

        # Per-user voice burst counter — counts consecutive voice frames to distinguish real speech from noise.
        # Only resets the silence counter if the burst reaches 25 frames (0.5s of continuous voice).
        # Brief pops/clicks are buffered but don't extend the silence window.
        self.user_voice_burst: dict[str, int] = {}

        # Per-guild processing lock — prevents cascading response cycles.
        # Set when audio is queued for transcription; released by TTS_DONE signal from Rust.
        # During the lock window, new audio is silently buffered but not processed.
        # The lock is keyed by guild_id (string) to support multiple voice channels.
        self._processing_lock_until: dict[str, float] = {}

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
        self.VAD_THRESHOLD = VAD_AMPLITUDE_THRESHOLD
        self.FRAMES_PER_SECOND = 50
        self.SILENCE_FRAMES_THRESHOLD = int(silence_threshold * self.FRAMES_PER_SECOND)
        self.MAX_BUFFER_BYTES = MAX_BUFFER_BYTES_GEMMA if (self.llm_connector and self.supports_audio) else MAX_BUFFER_BYTES_WHISPER

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

        logger.info("voice.processor_initialized", extra={
            "vad_threshold": self.VAD_THRESHOLD,
            "silence_threshold_s": silence_threshold,
            "direct_audio": bool(self.llm_connector and self.supports_audio),
        })

    # ── Delegation to split-out modules ────────────────────────────────────
    def _detect_voice_activity(self, audio_data):
        from serin.gateway.voice_system.audio.audio_vad import _detect_voice_activity
        return _detect_voice_activity(self, audio_data)

    def process_audio_chunk(self, user_id, username, guild_id, channel_id, audio_data):
        from serin.gateway.voice_system.audio.audio_utils import (
            process_audio_chunk as _process_audio_chunk,
        )
        return _process_audio_chunk(self, user_id, username, guild_id, channel_id, audio_data)

    def _queue_for_transcription(self, user_id, audio_data, username):
        from serin.gateway.voice_system.audio.audio_vad import _queue_for_transcription
        return _queue_for_transcription(self, user_id, audio_data, username)

    def _cancel_silence_timer(self, user_id):
        from serin.gateway.voice_system.audio.audio_vad import _cancel_silence_timer
        return _cancel_silence_timer(self, user_id)

    def _schedule_silence_timer(self, user_id, username, audio_data, channel_id):
        from serin.gateway.voice_system.audio.audio_vad import _schedule_silence_timer
        return _schedule_silence_timer(self, user_id, username, audio_data, channel_id)

    def _is_locked(self, guild_id):
        from serin.gateway.voice_system.audio.audio_vad import _is_locked
        return _is_locked(self, guild_id)

    def _release_lock(self, guild_id):
        from serin.gateway.voice_system.audio.audio_vad import _release_lock
        return _release_lock(self, guild_id)

    def _set_lock(self, guild_id, duration=20.0):
        from serin.gateway.voice_system.audio.audio_vad import _set_lock
        return _set_lock(self, guild_id, duration)

    @staticmethod
    def _pcm_to_wav_base64(audio_data, sample_rate=16000):
        from serin.gateway.voice_system.audio.audio_utils import _pcm_to_wav_base64
        return _pcm_to_wav_base64(audio_data, sample_rate)

    async def _transcribe_with_gemma(self, audio_data, username="User"):
        from serin.gateway.voice_system.audio.audio_utils import _transcribe_with_gemma
        return await _transcribe_with_gemma(self, audio_data, username)

    async def _process_queue(self) -> None:
        from serin.gateway.voice_system.audio.audio_vad import _process_queue
        return await _process_queue(self)

    async def _transcribe_and_store(self, item: dict) -> None:
        from serin.gateway.voice_system.audio.audio_transcribe import (
            _transcribe_and_store,
        )
        return await _transcribe_and_store(self, item)

    def check_interrupt(self, user_id: str) -> bool:
        from serin.gateway.voice_system.audio.audio_transcribe import check_interrupt
        return check_interrupt(self, user_id)

    def get_active_speakers(self):
        from serin.gateway.voice_system.audio.audio_transcribe import (
            get_active_speakers,
        )
        return get_active_speakers(self)

    def get_buffer_size(self, user_id: str) -> int:
        from serin.gateway.voice_system.audio.audio_transcribe import get_buffer_size
        return get_buffer_size(self, user_id)

    def get_stats(self):
        from serin.gateway.voice_system.audio.audio_transcribe import get_stats
        return get_stats(self)

    async def start(self) -> None:
        from serin.gateway.voice_system.audio.audio_utils import start as _start
        return await _start(self)

    async def stop(self) -> None:
        from serin.gateway.voice_system.audio.audio_utils import stop as _stop
        return await _stop(self)
