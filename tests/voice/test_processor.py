"""
Voice pipeline smoke test — verifies that AudioStreamProcessor can be
instantiated and that the silence-detection constants are correctly wired.

This test does NOT require a Discord connection or PyNaCl — it only tests
the in-process orchestration logic.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from voice.processor import (
    AudioStreamProcessor,
    VAD_AMPLITUDE_THRESHOLD,
    SILENCE_FRAMES_BEFORE_FLUSH,
    MIN_BUFFER_BYTES,
    PROCESSING_LOCK_SECONDS,
)


def test_constants_defined():
    """Constants should match expected values from the prompt spec."""
    assert VAD_AMPLITUDE_THRESHOLD == 150
    assert SILENCE_FRAMES_BEFORE_FLUSH == 75  # 1.5s at 50 fps
    assert MIN_BUFFER_BYTES == 192_000  # ~1s of 48kHz stereo PCM
    assert PROCESSING_LOCK_SECONDS == 30


def test_audio_stream_processor_instantiation():
    """AudioStreamProcessor should initialize without errors."""
    processor = AudioStreamProcessor(
        whisper_transcriber=MagicMock(),
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
        whisper_transcriber=MagicMock(),
        voice_pipeline=MagicMock(),
        llm_connector=MagicMock(),
    )
    assert processor.VAD_THRESHOLD == VAD_AMPLITUDE_THRESHOLD
    assert processor.MAX_BUFFER_BYTES >= 5_760_000  # Gemma minimum
