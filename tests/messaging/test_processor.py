"""
Voice pipeline smoke test — verifies that AudioStreamProcessor can be
instantiated and that the silence-detection constants are correctly wired.

This test does NOT require a Discord connection or PyNaCl — it only tests
the in-process orchestration logic.
"""
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from serin.gateway.voice_system.processor import (
    AudioStreamProcessor,
    VAD_AMPLITUDE_THRESHOLD,
    SILENCE_FRAMES_BEFORE_FLUSH,
    MIN_BUFFER_BYTES,
    PROCESSING_LOCK_SECONDS,
)


def make_pcm_bytes(amplitude: int, frames: int = 50) -> bytes:
    """Create fake PCM data with given RMS amplitude (48kHz stereo 16-bit)."""
    samples = np.full(frames * 960, amplitude, dtype=np.int16)
    return samples.tobytes()


def test_constants_defined():
    """Constants should match expected values from the prompt spec."""
    assert VAD_AMPLITUDE_THRESHOLD == 150
    assert SILENCE_FRAMES_BEFORE_FLUSH == 75  # 1.5s at 50 fps
    assert MIN_BUFFER_BYTES == 192_000  # ~1s of 48kHz stereo PCM
    assert PROCESSING_LOCK_SECONDS == 30


def test_audio_stream_processor_instantiation():
    """AudioStreamProcessor should initialize without errors."""
    processor = AudioStreamProcessor(
        transcriber=MagicMock(),
        voice_pipeline=MagicMock(),
        llm_connector=MagicMock(),
    )
    assert processor.VAD_THRESHOLD == 150
    assert processor.FRAMES_PER_SECOND == 50


def test_audio_stream_processor_constants_wired():
    """
    Verify that the processor's instance attributes match the module-level
    constants defined in voice/processor.py.
    """
    processor = AudioStreamProcessor(
        transcriber=MagicMock(),
        voice_pipeline=MagicMock(),
        llm_connector=MagicMock(),
    )
    assert processor.VAD_THRESHOLD == VAD_AMPLITUDE_THRESHOLD
    assert processor.MAX_BUFFER_BYTES >= 5_760_000  # Gemma minimum


def test_silent_audio_does_not_queue():
    """Audio below VAD threshold should not queue for transcription."""
    with patch.object(AudioStreamProcessor, "_queue_for_transcription") as mock_q:
        processor = AudioStreamProcessor(
            transcriber=MagicMock(),
            voice_pipeline=MagicMock(),
            llm_connector=MagicMock(),
        )
        # Reset state for test
        processor.user_buffers = {}
        processor.user_silence_frames = {}
        processor._silence_timers = {}
        processor.user_voice_burst = {}
        processor._processing_lock_until = {}
        processor.currently_speaking = set()
        processor.is_running = True

        silent_pcm = make_pcm_bytes(amplitude=10)  # below threshold of 150
        processor.process_audio_chunk(
            user_id="123",
            username="test",
            guild_id="456",
            channel_id="789",
            audio_data=silent_pcm,
        )
        mock_q.assert_not_called()
