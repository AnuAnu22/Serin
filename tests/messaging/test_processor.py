"""Voice pipeline smoke test — AudioStreamProcessor instantiation and constants."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from serin.d1_2_gateway_io._di import init_gateway
from serin.d1_3_state_core.logger import logger as _default_logger

# Initialize gateway DI so AudioStreamProcessor can call get_logger()
init_gateway(_default_logger)

from serin.d1_2_gateway_io.voice_system.audio.process.audio_processor import (
    MIN_BUFFER_BYTES,
    PROCESSING_LOCK_SECONDS,
    SILENCE_FRAMES_BEFORE_FLUSH,
    VAD_AMPLITUDE_THRESHOLD,
    AudioStreamProcessor,
)


def make_pcm_bytes(amplitude: int, frames: int = 50) -> bytes:
    samples = np.full(frames * 960, amplitude, dtype=np.int16)
    return samples.tobytes()


def test_constants_defined():
    assert VAD_AMPLITUDE_THRESHOLD == 150
    assert SILENCE_FRAMES_BEFORE_FLUSH == 75
    assert MIN_BUFFER_BYTES == 192_000
    assert PROCESSING_LOCK_SECONDS == 30


def test_audio_stream_processor_instantiation():
    processor = AudioStreamProcessor(
        transcriber=MagicMock(),
        voice_pipeline=MagicMock(),
    )
    assert processor.silence_threshold == 3.0


def test_audio_stream_processor_constants_wired():
    processor = AudioStreamProcessor(
        transcriber=MagicMock(),
        voice_pipeline=MagicMock(),
    )
    assert processor.MAX_BUFFER_BYTES >= 5_760_000


def test_silent_audio_does_not_queue():
    with patch("serin.d1_2_gateway_io.voice_system.audio.audio_vad._queue_for_transcription") as mock_q:
        processor = AudioStreamProcessor(
            transcriber=MagicMock(),
            voice_pipeline=MagicMock(),
        )
        processor.user_buffers = {}
        processor.user_silence_frames = {}
        processor._silence_timers = {}
        processor.user_voice_burst = {}
        processor._processing_lock_until = {}
        processor.currently_speaking = set()
        processor.is_running = True

        silent_pcm = make_pcm_bytes(amplitude=10)
        processor.process_audio_chunk(
            user_id="123",
            username="test",
            guild_id="456",
            channel_id="789",
            audio_data=silent_pcm,
        )
        mock_q.assert_not_called()
