"""
TTS Voice Manager - Voice File Management for Voice Cloning
Manage voice reference files for TTS voice cloning.

Features:
- List available voice files
- Load voice files for cloning
- Validate audio formats
- Voice file metadata
"""
import os
from pathlib import Path
from typing import List, Dict, Optional
from serin.core.logger import logger


class TTSVoiceManager:
    """
    Manage TTS voice reference files for voice cloning.
    Works with Coqui XTTS v2 voice cloning feature.
    """
    
    def __init__(self, voices_dir: str = "tts/voices"):
        """
        Initialize TTS voice manager.
        
        Args:
            voices_dir: Directory containing voice files
        """
        self.voices_dir = Path(voices_dir)
        
        # Create directory if it doesn't exist
        if not self.voices_dir.exists():
            self.voices_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Created voices directory: {self.voices_dir}")
            self._create_readme()
        
        # Supported formats
        self.supported_formats = ['.wav', '.mp3', '.pth', '.pt']
        
        logger.info(" TTS voice manager initialized")
        logger.info(f"   📂 Voices directory: {self.voices_dir}")
    
    def _create_readme(self):
        """Create README in voices directory"""
        readme_path = self.voices_dir / "README.md"
        if not readme_path.exists():
            readme_content = """# TTS Voice Files

Place voice reference files here for voice cloning.

## Supported Formats
- WAV (.wav) - Recommended
- MP3 (.mp3)
- PyTorch (.pth, .pt)

## Requirements for Best Results
- **Duration**: 6-30 seconds of clear speech
- **Quality**: High quality, minimal background noise
- **Sample Rate**: 22050 Hz or higher
- **Format**: Mono or stereo
- **Content**: Natural speech, avoid music/effects

## Example Files
- `female_voice.wav` - Female voice reference
- `male_voice.wav` - Male voice reference
- `energetic.wav` - High-energy voice
- `calm.wav` - Calm, soothing voice

## Usage
1. Place voice files in this directory
2. Use control panel to load voice
3. TTS will clone the voice characteristics
4. Clear to return to default voice

## Notes
- Longer samples = better quality cloning
- Clear speech = better results
- XTTS v2 works best with 6-30 second samples
"""
            readme_path.write_text(readme_content)
            logger.info(f" Created README: {readme_path}")
    
    def list_voices(self) -> List[Dict]:
        """
        List all available voice files.
        
        Returns:
            List of dicts with voice file info
        """
        voices = []
        
        try:
            for file_path in self.voices_dir.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                    voices.append({
                        'name': file_path.stem,
                        'file': file_path.name,
                        'path': str(file_path),
                        'size': file_path.stat().st_size,
                        'format': file_path.suffix.lower(),
                        'size_mb': round(file_path.stat().st_size / (1024 * 1024), 2)
                    })
            
            # Sort by name
            voices.sort(key=lambda x: x['name'])
            
            logger.debug(f" Found {len(voices)} voice files")
            return voices
        
        except Exception as e:
            logger.error(f" Error listing voices: {e}")
            return []
    
    def get_voice_path(self, filename: str) -> Optional[Path]:
        """
        Get full path to voice file.
        
        Args:
            filename: Voice filename
        
        Returns:
            Path to voice file or None
        """
        voice_path = self.voices_dir / filename
        
        if voice_path.exists() and voice_path.is_file():
            return voice_path
        else:
            logger.warning(f" Voice file not found: {filename}")
            return None
    
    def validate_voice_file(self, filename: str) -> Dict:
        """
        Validate voice file for TTS use.
        
        Args:
            filename: Voice filename
        
        Returns:
            Dict with validation results
        """
        result = {
            'valid': False,
            'errors': [],
            'warnings': [],
            'info': {}
        }
        
        voice_path = self.get_voice_path(filename)
        
        if not voice_path:
            result['errors'].append('File not found')
            return result
        
        # Check format
        if voice_path.suffix.lower() not in self.supported_formats:
            result['errors'].append(f'Unsupported format: {voice_path.suffix}')
            return result
        
        # Check size
        size_mb = voice_path.stat().st_size / (1024 * 1024)
        result['info']['size_mb'] = round(size_mb, 2)
        
        if size_mb < 0.1:
            result['errors'].append('File too small (< 100KB)')
        elif size_mb > 50:
            result['warnings'].append('File very large (> 50MB), may be slow')
        
        # For WAV files, check format details
        if voice_path.suffix.lower() == '.wav':
            try:
                import wave
                with wave.open(str(voice_path), 'rb') as wav:
                    result['info']['sample_rate'] = wav.getframerate()
                    result['info']['channels'] = wav.getnchannels()
                    result['info']['duration'] = wav.getnframes() / wav.getframerate()
                    
                    # Warnings
                    if result['info']['duration'] < 3:
                        result['warnings'].append('Very short audio (< 3s), may not clone well')
                    elif result['info']['duration'] > 60:
                        result['warnings'].append('Very long audio (> 60s), consider trimming')
                    
                    if result['info']['sample_rate'] < 16000:
                        result['warnings'].append('Low sample rate (< 16kHz), quality may suffer')
            
            except Exception as e:
                result['warnings'].append(f'Could not analyze WAV: {e}')
        
        # If no errors, mark as valid
        if not result['errors']:
            result['valid'] = True
        
        return result
    
    def load_voice(self, tts_engine, filename: str) -> bool:
        """
        Load voice file into TTS engine.
        
        Args:
            tts_engine: TTSEngine instance
            filename: Voice filename
        
        Returns:
            Success status
        """
        try:
            voice_path = self.get_voice_path(filename)
            if not voice_path:
                return False
            
            # Validate
            validation = self.validate_voice_file(filename)
            if not validation['valid']:
                logger.error(f" Voice validation failed: {validation['errors']}")
                return False
            
            if validation['warnings']:
                for warning in validation['warnings']:
                    logger.warning(f" {warning}")
            
            # Load into TTS engine
            tts_engine.set_voice_reference(str(voice_path))
            
            logger.info(f" Loaded voice: {filename}")
            if validation['info']:
                logger.info(f"   Info: {validation['info']}")
            
            return True
        
        except Exception as e:
            logger.error(f" Error loading voice: {e}")
            return False
    
    def clear_voice(self, tts_engine) -> bool:
        """
        Clear voice reference from TTS engine.
        
        Args:
            tts_engine: TTSEngine instance
        
        Returns:
            Success status
        """
        try:
            tts_engine.clear_voice_reference()
            logger.info(" Cleared voice reference")
            return True
        except Exception as e:
            logger.error(f" Error clearing voice: {e}")
            return False
    
    def get_voice_info(self, filename: str) -> Optional[Dict]:
        """
        Get detailed info about a voice file.
        
        Args:
            filename: Voice filename
        
        Returns:
            Dict with voice info or None
        """
        voices = self.list_voices()
        for voice in voices:
            if voice['file'] == filename:
                # Add validation info
                validation = self.validate_voice_file(filename)
                voice['validation'] = validation
                return voice
        return None
    
    def get_stats(self) -> Dict:
        """Get voice manager statistics"""
        voices = self.list_voices()
        
        total_size = sum(v['size'] for v in voices)
        
        formats = {}
        for voice in voices:
            fmt = voice['format']
            formats[fmt] = formats.get(fmt, 0) + 1
        
        return {
            'total_voices': len(voices),
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'formats': formats,
            'voices_dir': str(self.voices_dir),
            'supported_formats': self.supported_formats
        }