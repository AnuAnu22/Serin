# TTS Voice Files

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
