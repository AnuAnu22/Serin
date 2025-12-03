"""
TTS Engine - Text-to-Speech using Coqui XTTS v2
Local, high-quality voice synthesis with GPU acceleration.

Features:
- XTTS v2 (best quality)
- CUDA GPU acceleration
- Multiple voice profiles
- Voice cloning support
- Natural prosody
"""
import asyncio
import io
import numpy as np
import torch
from typing import Optional, Dict
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import logger

# Import Coqui TTS (idiap fork - supports Python 3.12+)
try:
    from TTS.api import TTS
    TTS_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ Coqui TTS not installed. Run: uv add coqui-tts[all]")
    TTS_AVAILABLE = False


class TTSEngine:
    def __init__(
        self,
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        device: str = "cuda"
    ):
        """
        Initialize TTS engine with XTTS v2.
        
        Args:
            model_name: Coqui TTS model (default: XTTS v2)
            device: Device to use (cuda for GPU, cpu for CPU)
        """
        self.model_name = model_name
        self.device = device
        self.tts: Optional[TTS] = None
        
        # Check CUDA availability
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("⚠️ CUDA not available, falling back to CPU")
            self.device = "cpu"
        
        # Voice profiles (XTTS v2 supports speed adjustment)
        self.profiles = {
            'default': {
                'speed': 1.0,
                'temperature': 0.7,
                'length_penalty': 1.0,
                'repetition_penalty': 5.0
            },
            'fast': {
                'speed': 1.1,
                'temperature': 0.75,
                'length_penalty': 1.0,
                'repetition_penalty': 5.0
            },
            'slow': {
                'speed': 0.9,
                'temperature': 0.65,
                'length_penalty': 1.0,
                'repetition_penalty': 5.0
            }
        }
        
        # Current active profile
        self.active_profile = 'default'
        
        # Voice reference (for voice cloning)
        self.voice_reference = None
        
        # Stats
        self.stats = {
            'total_generations': 0,
            'total_duration': 0.0,
            'errors': 0,
            'cuda_enabled': self.device == "cuda"
        }
        
        if not TTS_AVAILABLE:
            logger.error("❌ Coqui TTS not available")
            return
        
        logger.info("✅ TTS engine initialized")
        logger.info(f"   🎙️ Model: XTTS v2")
        logger.info(f"   💻 Device: {self.device.upper()}")
        if self.device == "cuda":
            try:
                logger.info(f"   🎮 GPU: {torch.cuda.get_device_name(0)}")
                logger.info(f"   💾 VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
            except:
                pass
    
    async def load_model(self):
        """Load XTTS v2 model"""
        if not TTS_AVAILABLE:
            logger.error("❌ Cannot load TTS model - Coqui TTS not installed")
            return False
        
        try:
            logger.info(f"📥 Loading XTTS v2 model...")
            logger.info(f"   Device: {self.device}")
            logger.info(f"   This may take 30-60 seconds...")
            
            # Load model in background thread
            self.tts = await asyncio.to_thread(
                TTS,
                model_name=self.model_name,
                progress_bar=True,
                gpu=(self.device == "cuda")
            )
            
            # Move to device
            if self.device == "cuda":
                self.tts.to(self.device)
                logger.info(f"   ✅ Model loaded on GPU")
            else:
                logger.info(f"   ✅ Model loaded on CPU")
            
            # Get speaker info if available
            if hasattr(self.tts, 'speakers') and self.tts.speakers:
                logger.info(f"   🎤 Available speakers: {len(self.tts.speakers)}")
            
            logger.info(f"✅ XTTS v2 model ready!")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error loading TTS model: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats['errors'] += 1
            return False
    
    async def synthesize(
        self,
        text: str,
        profile: str = None,
        speaker: str = None,
        language: str = "en"
    ) -> Optional[bytes]:
        """
        Synthesize speech from text using XTTS v2.
        
        Args:
            text: Text to synthesize
            profile: Voice profile to use
            speaker: Speaker name (if model supports multiple speakers)
            language: Language code (en, es, fr, de, it, pt, pl, tr, ru, nl, cs, ar, zh-cn, ja)
        
        Returns:
            Audio data as bytes (WAV format)
        """
        if not self.tts:
            logger.error("❌ TTS model not loaded")
            return None
        
        try:
            # Use specified profile or current active
            profile = profile or self.active_profile
            profile_settings = self.profiles.get(profile, self.profiles['default'])
            
            logger.info(f"🎙️ Synthesizing: '{text[:50]}...' (profile: {profile}, lang: {language})")
            
            # XTTS v2 synthesis parameters
            synthesis_kwargs = {
                'text': text,
                'language': language,
                'speed': profile_settings['speed']
            }
            
            # Add speaker if specified
            if speaker and hasattr(self.tts, 'speakers') and speaker in self.tts.speakers:
                synthesis_kwargs['speaker'] = speaker
            
            # Add voice reference if available (for voice cloning)
            if self.voice_reference:
                synthesis_kwargs['speaker_wav'] = self.voice_reference
            
            # Generate speech in background thread
            wav = await asyncio.to_thread(
                self.tts.tts,
                **synthesis_kwargs
            )
            
            # Convert to numpy array if needed
            if isinstance(wav, list):
                wav = np.array(wav, dtype=np.float32)
            elif not isinstance(wav, np.ndarray):
                wav = np.array(wav, dtype=np.float32)
            
            # Normalize and convert to int16
            wav = np.clip(wav, -1.0, 1.0)
            wav_int16 = (wav * 32767).astype(np.int16)
            
            # Get sample rate
            sample_rate = self.tts.synthesizer.output_sample_rate if hasattr(self.tts, 'synthesizer') else 24000
            
            # Create WAV file in memory
            wav_buffer = io.BytesIO()
            import wave
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(wav_int16.tobytes())
            
            wav_buffer.seek(0)
            audio_data = wav_buffer.read()
            
            self.stats['total_generations'] += 1
            duration = len(wav_int16) / sample_rate
            self.stats['total_duration'] += duration
            
            logger.info(f"✅ Generated {len(audio_data)} bytes ({duration:.2f}s)")
            
            return audio_data
        
        except Exception as e:
            logger.error(f"❌ Error synthesizing speech: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats['errors'] += 1
            return None
    
    def set_voice_reference(self, audio_path: str):
        """
        Set voice reference for voice cloning.
        
        Args:
            audio_path: Path to reference audio file (WAV, MP3)
        """
        try:
            import os
            if os.path.exists(audio_path):
                self.voice_reference = audio_path
                logger.info(f"✅ Voice reference set: {audio_path}")
            else:
                logger.error(f"❌ Voice reference file not found: {audio_path}")
        except Exception as e:
            logger.error(f"❌ Error setting voice reference: {e}")
    
    def clear_voice_reference(self):
        """Clear voice reference (use default voice)"""
        self.voice_reference = None
        logger.info("✅ Voice reference cleared")
    
    def set_profile(self, profile: str):
        """
        Set active voice profile.
        
        Args:
            profile: Profile name
        """
        if profile in self.profiles:
            self.active_profile = profile
            logger.info(f"🎙️ Voice profile set to: {profile}")
        else:
            logger.warning(f"⚠️ Unknown profile: {profile}")
    
    def get_available_speakers(self) -> list:
        """Get list of available speakers"""
        if self.tts and hasattr(self.tts, 'speakers'):
            return self.tts.speakers or []
        return []
    
    def get_stats(self) -> Dict:
        """Get TTS statistics"""
        return {
            'total_generations': self.stats['total_generations'],
            'total_duration': round(self.stats['total_duration'], 2),
            'errors': self.stats['errors'],
            'model_loaded': self.tts is not None,
            'active_profile': self.active_profile,
            'available_profiles': list(self.profiles.keys()),
            'device': self.device,
            'cuda_enabled': self.stats['cuda_enabled'],
            'available_speakers': len(self.get_available_speakers()),
            'voice_cloning_active': self.voice_reference is not None
        }
