"""
Audio Stream Processor — Per-User Audio Buffer, VAD & Pipeline Orchestrator

This is the core of the voice conversation pipeline. It:

  1. Receives raw PCM audio chunks (48kHz stereo 16-bit) from the Rust songbird bridge
  2. Runs energy-based Voice Activity Detection on each chunk
  3. Buffers audio per-user while they speak
  4. Detects when the user stops speaking (silence threshold = SILENCE_FRAMES_BEFORE_FLUSH / FRAMES_PER_SECOND)
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

# ── Constants ──────────────────────────────────────────────────────────────────
VAD_AMPLITUDE_THRESHOLD = 150           # RMS amplitude below which is considered silence
SILENCE_FRAMES_BEFORE_FLUSH = 75        # 1.5s at 50 frames/sec
MIN_BUFFER_BYTES = 192_000              # ~1 second of 48kHz stereo PCM
MAX_BUFFER_BYTES_GEMMA = 5_760_000      # ~30 seconds (Gemma audio limit)
MAX_BUFFER_BYTES_WHISPER = 50_000_000   # ~260 seconds (Whisper limit)
PROCESSING_LOCK_SECONDS = 30            # How long to lock after queueing audio
VOICE_BURST_IGNORE_FRAMES = 25          # Ignore bursts shorter than 0.5s
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
from serin.config.logger import logger


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
                 voice_output_manager: Optional[Any] = None, llm_connector: Optional[Any] = None) -> None:
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

    @staticmethod