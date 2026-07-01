"""
Whisper Transcriber - Real-time Speech-to-Text
Uses faster-whisper for efficient local transcription.

Features:
- Local Whisper model (no API calls)
- Real-time processing
- Multiple model sizes
- Automatic language detection
"""
import asyncio
import os
import sys
from typing import Any

import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from serin.state.logger import logger

# Import faster-whisper (install: pip install faster-whisper)
try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    logger.warning(" faster-whisper not installed. Run: pip install faster-whisper")
    WHISPER_AVAILABLE = False


class WhisperTranscriber:
    def __init__(self, model_size: str = "base", device: str = "cuda", compute_type: str = "float16") -> None:
        """
        Initialize Whisper transcriber with CUDA support.

        Args:
            model_size: Model size (tiny, base, small, medium, large)
            device: Device to use (cuda for GPU, cpu for CPU)
            compute_type: Computation type (float16 for CUDA, int8 for CPU)
        """
        self.model_size = model_size
        self.device = device

        # Auto-select compute type based on device
        if device == "cuda":
            self.compute_type = "float16"  # Best for CUDA
        else:
            self.compute_type = "int8"  # Best for CPU

        self.model: WhisperModel | None = None

        # Stats
        self.stats = {
            'total_transcriptions': 0,
            'total_duration': 0.0,
            'errors': 0,
            'cuda_enabled': device == "cuda"
        }

        if not WHISPER_AVAILABLE:
            logger.error(" faster-whisper not available")
            return

        logger.info(" Whisper transcriber initialized")
        logger.info(f"    Model: {model_size}")
        logger.info(f"    Device: {device.upper()}")
        logger.info(f"    Compute: {self.compute_type}")

    async def load_model(self) -> bool:
        """Load Whisper model"""
        if not WHISPER_AVAILABLE:
            logger.error(" Cannot load Whisper model - faster-whisper not installed")
            return False

        try:
            logger.info(f" Loading Whisper model '{self.model_size}'...")

            # Load model in background thread
            self.model = await asyncio.to_thread(
                WhisperModel,
                self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )

            logger.info(f" Whisper model '{self.model_size}' loaded")
            return True

        except Exception as e:
            logger.error(f" Error loading Whisper model: {e}")
            self.stats['errors'] += 1
            return False

    async def transcribe(self, audio_data: bytes, language: str = "en") -> str | None:
        """
        Transcribe audio data to text.

        Args:
            audio_data: Raw PCM audio data (16-bit, mono, 48kHz from Discord)
            language: Language code (default: "en")

        Returns:
            Transcribed text or None
        """
        if not self.model:
            logger.error(" Whisper model not loaded")
            return None

        try:
            # Convert Discord audio format to format Whisper expects
            # Discord: 48kHz, 16-bit PCM, stereo
            # Whisper: 16kHz, 16-bit PCM, mono

            audio_array = np.frombuffer(audio_data, dtype=np.int16)

            # Convert stereo to mono (take every other sample)
            if len(audio_array) % 2 == 0:
                audio_mono = audio_array[::2]  # Take left channel
            else:
                audio_mono = audio_array

            # Resample from 48kHz to 16kHz (Whisper requirement)
            audio_16k = self._resample_audio(audio_mono, 48000, 16000)

            # Normalize to float32 in range [-1, 1]
            audio_float = audio_16k.astype(np.float32) / 32768.0

            # Transcribe in background thread
            logger.debug(" Transcribing audio...")

            segments, info = await asyncio.to_thread(
                self.model.transcribe,
                audio_float,
                language=language,
                beam_size=5,
                vad_filter=True,  # Voice activity detection
                vad_parameters=dict(
                    threshold=0.5,
                    min_silence_duration_ms=500
                )
            )

            # Combine all segments
            transcription = ""
            for segment in segments:
                transcription += segment.text + " "

            transcription = transcription.strip()

            self.stats['total_transcriptions'] += 1

            if transcription:
                logger.info(f" Transcription: '{transcription}'")
                return transcription
            else:
                logger.debug(" Empty transcription")
                return None

        except Exception as e:
            logger.error(f" Error transcribing audio: {e}")
            self.stats['errors'] += 1
            return None

    def _resample_audio(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """
        Resample audio to target sample rate.
        Simple linear interpolation resampling.

        Args:
            audio: Audio array
            orig_sr: Original sample rate
            target_sr: Target sample rate

        Returns:
            Resampled audio array
        """
        try:
            duration = len(audio) / orig_sr
            target_length = int(duration * target_sr)

            # Simple linear interpolation
            indices = np.linspace(0, len(audio) - 1, target_length)
            resampled = np.interp(indices, np.arange(len(audio)), audio)

            return resampled.astype(np.int16)

        except Exception as e:
            logger.error(f" Error resampling audio: {e}")
            return audio

    def get_stats(self) -> dict[str, Any]:
        """Get transcriber statistics"""
        return {
            'total_transcriptions': self.stats['total_transcriptions'],
            'errors': self.stats['errors'],
            'model_loaded': self.model is not None,
            'model_size': self.model_size
        }


class WhisperTranscriberFallback:
    """
    Fallback transcriber if faster-whisper not available.
    Uses OpenAI Whisper API (requires API key).
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        logger.warning(" Using Whisper API fallback (requires API key)")

    async def load_model(self) -> bool:
        return bool(self.api_key)

    async def transcribe(self, audio_data: bytes, language: str = "en") -> str | None:
        logger.error(" Whisper API fallback not implemented")
        return None

    def get_stats(self) -> dict[str, Any]:
        return {'error': 'Fallback transcriber not implemented'}
