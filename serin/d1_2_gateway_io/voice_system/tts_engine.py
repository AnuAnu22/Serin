from __future__ import annotations

import asyncio
import io
import os
import wave
from typing import Any

import numpy as np

from serin.d1_2_gateway_io._di import get_logger
from serin.d1_2_gateway_io.voice_system.output import (
    COQUI_TTS_AVAILABLE,
    EDGE_RATE_MAP,
    EDGE_TTS_AVAILABLE,
    EDGE_VOICE_PRESETS,
)

# Try importing backends
try:
    import edge_tts
except ImportError:
    pass

try:
    import torch
    from TTS.api import TTS
except ImportError:
    pass


class TTSEngine:
    def __init__(
        self,
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        device: str = "cuda"
    ) -> None:
        """Initialize TTS engine.
        Uses edge-tts by default (no model download needed).
        Falls back to Coqui XTTS v2 if available.
        """
        self.model_name = model_name
        self.device = device
        self.backend: str | None = None
        self.tts: Any = None  # Coqui TTS instance

        # Determine which backend to use
        if EDGE_TTS_AVAILABLE:
            self.backend = "edge-tts"
            self.voice = EDGE_VOICE_PRESETS['default']
            get_logger().info(" TTS engine initialized (edge-tts backend)")
            get_logger().info(f"    Voice: {self.voice}")
            get_logger().info("    Backend: Microsoft Edge TTS (cloud, free)")
        elif COQUI_TTS_AVAILABLE:
            self.backend = "coqui"
            if device == "cuda" and not torch.cuda.is_available():
                get_logger().warning(" CUDA not available, falling back to CPU")
                self.device = "cpu"
            get_logger().info(" TTS engine initialized (Coqui XTTS v2 backend)")
            get_logger().info(f"    Device: {self.device.upper()}")
        else:
            self.backend = None
            get_logger().error(" No TTS backend available. Install edge-tts (uv add edge-tts)")
            return

        # Voice profiles (Coqui-specific settings)
        self.profiles = {
            'default': {'speed': 1.0, 'temperature': 0.7},
            'fast': {'speed': 1.1, 'temperature': 0.75},
            'slow': {'speed': 0.9, 'temperature': 0.65},
            'energetic': {'speed': 1.05, 'temperature': 0.8},
            'calm': {'speed': 0.95, 'temperature': 0.6},
            'friendly': {'speed': 1.0, 'temperature': 0.7},
            'serious': {'speed': 0.98, 'temperature': 0.5},
        }

        self.active_profile = 'default'
        self.voice_reference: str | None = None

        self.stats: dict[str, Any] = {
            'total_generations': 0,
            'total_duration': 0.0,
            'errors': 0,
            'backend': self.backend,
        }

    async def load_model(self) -> bool:
        """Load TTS model (edge-tts has no model to load, Coqui does)"""
        if self.backend == "edge-tts":
            # edge-tts needs no loading
            get_logger().info(" edge-tts ready (no model loading needed)")
            return True

        if self.backend == "coqui":
            if not COQUI_TTS_AVAILABLE:
                get_logger().error(" Cannot load Coqui TTS - not installed")
                return False

            try:
                get_logger().info(" Loading XTTS v2 model...")
                get_logger().info(f"   Device: {self.device}")

                def _init_tts() -> Any:
                    return TTS(
                        model_name=self.model_name,
                        progress_bar=True,
                        gpu=(self.device == "cuda"),
                    )
                self.tts = await asyncio.to_thread(_init_tts)
                if self.device == "cuda":
                    self.tts.to(self.device)
                get_logger().info(" XTTS v2 model ready!")
                return True
            except Exception as e:
                get_logger().error(f" Error loading Coqui TTS: {e}")
                self.stats['errors'] += 1
                return False

        return False

    async def synthesize(
        self,
        text: str,
        profile: str | None = None,
        speaker: str | None = None,
        language: str = "en"
    ) -> bytes | None:
        """
        Synthesize speech from text.

        Args:
            text: Text to synthesize
            profile: Voice profile (default, fast, slow, energetic, calm, etc.)
            speaker: Speaker name (Coqui only)
            language: Language code (Coqui only)

        Returns:
            Audio data as bytes (WAV format)
        """
        if not self.backend:
            get_logger().error(" TTS backend not available")
            return None

        profile = profile or self.active_profile

        if self.backend == "edge-tts":
            return await self._synthesize_edge(text, profile)
        elif self.backend == "coqui":
            return await self._synthesize_coqui(text, profile, speaker, language)
        return None

    async def _synthesize_edge(self, text: str, profile: str) -> bytes | None:
        """Synthesize using edge-tts (Microsoft Edge cloud TTS)"""
        try:
            voice = EDGE_VOICE_PRESETS.get(profile, EDGE_VOICE_PRESETS['default'])
            rate = EDGE_RATE_MAP.get(profile, '+0%')

            get_logger().info(f" Synthesizing (edge-tts): '{text[:50]}...' voice={voice} rate={rate}")

            communicate = edge_tts.Communicate(text, voice, rate=rate)

            # Collect audio chunks
            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])

            if not audio_chunks:
                get_logger().error(" edge-tts returned no audio")
                self.stats['errors'] += 1
                return None

            mp3_data = b"".join(audio_chunks)

            # Convert MP3 to WAV using ffmpeg
            wav_data = await self._mp3_to_wav(mp3_data)

            if wav_data:
                self.stats['total_generations'] += 1
                # Estimate duration (rough: 16KB/s for 16kHz mono WAV)
                duration = len(wav_data) / (16000 * 2)  # 16-bit mono
                self.stats['total_duration'] += duration
                get_logger().info(f" Generated {len(wav_data)} bytes ({duration:.2f}s)")
            else:
                self.stats['errors'] += 1

            return wav_data

        except Exception as e:
            get_logger().error(f" Error in edge-tts synthesis: {e}")
            self.stats['errors'] += 1
            return None

    async def _mp3_to_wav(self, mp3_data: bytes) -> bytes | None:
        """Convert MP3 bytes to WAV bytes using ffmpeg"""
        try:
            proc = await asyncio.create_subprocess_exec(
                'ffmpeg', '-i', 'pipe:0',
                '-', 'wav', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1',
                'pipe:1',
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate(input=mp3_data)
            if proc.returncode == 0:
                return stdout
            else:
                get_logger().error(f"ffmpeg error: {stderr.decode()[:200]}")
                return None
        except FileNotFoundError:
            get_logger().error(" ffmpeg not found. Install it: sudo apt install ffmpeg")
            # Return MP3 as-is — discord.py can play MP3
            return mp3_data
        except Exception as e:
            get_logger().error(f" MP3 conversion error: {e}")
            return mp3_data

    async def _synthesize_coqui(
        self, text: str, profile: str, speaker: str | None, language: str
    ) -> bytes | None:
        """Synthesize using Coqui XTTS v2"""
        if not self.tts:
            get_logger().error(" Coqui TTS model not loaded")
            return None

        try:
            profile_settings = self.profiles.get(profile, self.profiles['default'])

            get_logger().info(f" Synthesizing (Coqui): '{text[:50]}...' profile={profile}")

            synthesis_kwargs = {
                'text': text,
                'language': language,
                'speed': profile_settings['speed']
            }

            if speaker and hasattr(self.tts, 'speakers') and speaker in self.tts.speakers:
                synthesis_kwargs['speaker'] = speaker

            if self.voice_reference:
                synthesis_kwargs['speaker_wav'] = self.voice_reference

            wav = await asyncio.to_thread(self.tts.tts, **synthesis_kwargs)

            if isinstance(wav, list):
                wav = np.array(wav, dtype=np.float32)
            elif not isinstance(wav, np.ndarray):
                wav = np.array(wav, dtype=np.float32)

            wav = np.clip(wav, -1.0, 1.0)
            wav_int16 = (wav * 32767).astype(np.int16)

            sample_rate = self.tts.synthesizer.output_sample_rate if hasattr(self.tts, 'synthesizer') else 24000

            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(wav_int16.tobytes())

            wav_buffer.seek(0)
            audio_data = wav_buffer.read()

            self.stats['total_generations'] += 1
            duration = len(wav_int16) / sample_rate
            self.stats['total_duration'] += duration

            get_logger().info(f" Generated {len(audio_data)} bytes ({duration:.2f}s)")
            return audio_data

        except Exception as e:
            get_logger().error(f" Error in Coqui synthesis: {e}")
            self.stats['errors'] += 1
            return None

    def set_voice_reference(self, audio_path: str) -> None:
        """Set voice reference for voice cloning (Coqui only)"""
        try:
            if os.path.exists(audio_path):
                self.voice_reference = audio_path
                get_logger().info(f" Voice reference set: {audio_path}")
            else:
                get_logger().error(f" Voice reference file not found: {audio_path}")
        except Exception as e:
            get_logger().error(f" Error setting voice reference: {e}")

    def clear_voice_reference(self) -> None:
        """Clear voice reference"""
        self.voice_reference = None
        get_logger().info(" Voice reference cleared")

    def set_profile(self, profile: str) -> None:
        """Set active voice profile"""
        if profile in self.profiles:
            self.active_profile = profile
            if self.backend == "edge-tts":
                self.voice = EDGE_VOICE_PRESETS.get(profile, EDGE_VOICE_PRESETS['default'])
            get_logger().info(f" Voice profile set to: {profile}")
        else:
            get_logger().warning(f" Unknown profile: {profile}")

    def get_available_speakers(self) -> list[str]:
        """Get list of available speakers"""
        if self.backend == "coqui" and self.tts and hasattr(self.tts, 'speakers'):
            return self.tts.speakers or []
        if self.backend == "edge-tts":
            return list(set(EDGE_VOICE_PRESETS.values()))
        return []

    def get_stats(self) -> dict[str, Any]:
        """Get TTS statistics"""
        return {
            'total_generations': self.stats['total_generations'],
            'total_duration': round(self.stats['total_duration'], 2),
            'errors': self.stats['errors'],
            'backend': self.backend,
            'model_loaded': True if self.backend == "edge-tts" else (self.tts is not None),
            'active_profile': self.active_profile,
            'available_profiles': list(self.profiles.keys()),
            'device': self.device if self.backend == "coqui" else "cloud",
            'voice_cloning_active': self.voice_reference is not None,
            'available_speakers': len(self.get_available_speakers()),
        }
