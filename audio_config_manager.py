"""
Audio Config Manager - Live Audio Settings Control
Update audio processor settings without restarting bot.

Features:
- Live VAD threshold adjustment
- Live silence threshold adjustment
- Transcription toggle
- No restart required
"""
from typing import Dict, Optional
from logger_config import logger


class AudioConfigManager:
    """
    Manage audio processing configuration at runtime.
    Allows live updates to VAD and silence detection settings.
    """
    
    def __init__(self, audio_processor):
        """
        Initialize audio config manager.
        
        Args:
            audio_processor: AudioStreamProcessor instance
        """
        self.audio_processor = audio_processor
        
        # Store original settings for reset
        self.original_settings = {
            'vad_threshold': audio_processor.VAD_THRESHOLD,
            'silence_threshold': audio_processor.silence_threshold,
            'silence_frames_threshold': audio_processor.SILENCE_FRAMES_THRESHOLD
        }
        
        logger.info("✅ Audio config manager initialized")
    
    def update_vad_threshold(self, threshold: int) -> bool:
        """
        Update VAD (Voice Activity Detection) threshold.
        Lower = more sensitive to voice.
        
        Args:
            threshold: RMS energy threshold (100-2000)
        
        Returns:
            Success status
        """
        try:
            if not 100 <= threshold <= 2000:
                logger.warning(f"⚠️ VAD threshold {threshold} out of range (100-2000)")
                return False
            
            old_threshold = self.audio_processor.VAD_THRESHOLD
            self.audio_processor.VAD_THRESHOLD = threshold
            
            logger.info(f"🎙️ VAD threshold updated: {old_threshold} → {threshold}")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error updating VAD threshold: {e}")
            return False
    
    def update_silence_threshold(self, seconds: float) -> bool:
        """
        Update silence detection threshold.
        How long to wait before processing audio chunk.
        
        Args:
            seconds: Silence duration in seconds (0.5-10.0)
        
        Returns:
            Success status
        """
        try:
            if not 0.5 <= seconds <= 10.0:
                logger.warning(f"⚠️ Silence threshold {seconds}s out of range (0.5-10.0)")
                return False
            
            old_threshold = self.audio_processor.silence_threshold
            self.audio_processor.silence_threshold = seconds
            
            # Update frames threshold
            self.audio_processor.SILENCE_FRAMES_THRESHOLD = int(
                seconds * self.audio_processor.FRAMES_PER_SECOND
            )
            
            logger.info(f"⏱️ Silence threshold updated: {old_threshold}s → {seconds}s")
            logger.info(f"   Frames: {self.audio_processor.SILENCE_FRAMES_THRESHOLD}")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error updating silence threshold: {e}")
            return False
    
    def update_settings(
        self,
        vad_threshold: Optional[int] = None,
        silence_threshold: Optional[float] = None
    ) -> Dict[str, bool]:
        """
        Update multiple settings at once.
        
        Args:
            vad_threshold: VAD threshold (optional)
            silence_threshold: Silence threshold in seconds (optional)
        
        Returns:
            Dict with success status for each setting
        """
        results = {}
        
        if vad_threshold is not None:
            results['vad'] = self.update_vad_threshold(vad_threshold)
        
        if silence_threshold is not None:
            results['silence'] = self.update_silence_threshold(silence_threshold)
        
        return results
    
    def reset_to_defaults(self) -> bool:
        """
        Reset all settings to original values.
        
        Returns:
            Success status
        """
        try:
            self.audio_processor.VAD_THRESHOLD = self.original_settings['vad_threshold']
            self.audio_processor.silence_threshold = self.original_settings['silence_threshold']
            self.audio_processor.SILENCE_FRAMES_THRESHOLD = self.original_settings['silence_frames_threshold']
            
            logger.info("🔄 Audio settings reset to defaults")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error resetting settings: {e}")
            return False
    
    def get_current_settings(self) -> Dict:
        """
        Get current audio settings.
        
        Returns:
            Dict with current settings
        """
        return {
            'vad_threshold': self.audio_processor.VAD_THRESHOLD,
            'silence_threshold': self.audio_processor.silence_threshold,
            'silence_frames_threshold': self.audio_processor.SILENCE_FRAMES_THRESHOLD,
            'frames_per_second': self.audio_processor.FRAMES_PER_SECOND,
            'is_running': self.audio_processor.is_running
        }
    
    def get_preset(self, preset_name: str) -> Optional[Dict]:
        """
        Get preset configuration.
        
        Args:
            preset_name: Preset name (quiet, normal, noisy, very_noisy)
        
        Returns:
            Dict with preset settings or None
        """
        presets = {
            'quiet': {
                'vad_threshold': 300,
                'silence_threshold': 2.0,
                'description': 'Quiet environment - high sensitivity'
            },
            'normal': {
                'vad_threshold': 500,
                'silence_threshold': 3.0,
                'description': 'Normal environment - balanced'
            },
            'noisy': {
                'vad_threshold': 1000,
                'silence_threshold': 4.0,
                'description': 'Noisy environment - low sensitivity'
            },
            'very_noisy': {
                'vad_threshold': 1500,
                'silence_threshold': 5.0,
                'description': 'Very noisy - minimal sensitivity'
            },
            'fast_response': {
                'vad_threshold': 500,
                'silence_threshold': 1.5,
                'description': 'Fast response - quick processing'
            },
            'patient': {
                'vad_threshold': 500,
                'silence_threshold': 5.0,
                'description': 'Patient - wait longer for pauses'
            }
        }
        
        return presets.get(preset_name)
    
    def apply_preset(self, preset_name: str) -> bool:
        """
        Apply a preset configuration.
        
        Args:
            preset_name: Preset name
        
        Returns:
            Success status
        """
        preset = self.get_preset(preset_name)
        if not preset:
            logger.warning(f"⚠️ Unknown preset: {preset_name}")
            return False
        
        try:
            results = self.update_settings(
                vad_threshold=preset['vad_threshold'],
                silence_threshold=preset['silence_threshold']
            )
            
            if all(results.values()):
                logger.info(f"✅ Applied preset: {preset_name} - {preset['description']}")
                return True
            else:
                logger.error(f"❌ Failed to apply preset: {preset_name}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Error applying preset: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """Get configuration stats"""
        current = self.get_current_settings()
        
        return {
            'current_vad': current['vad_threshold'],
            'current_silence': current['silence_threshold'],
            'original_vad': self.original_settings['vad_threshold'],
            'original_silence': self.original_settings['silence_threshold'],
            'is_modified': (
                current['vad_threshold'] != self.original_settings['vad_threshold'] or
                current['silence_threshold'] != self.original_settings['silence_threshold']
            ),
            'available_presets': list(self.get_preset('quiet').keys()) if self.get_preset('quiet') else []
        }
