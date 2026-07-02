"""Audio transcription — Gemma direct input and storage."""

from __future__ import annotations

from typing import Any

from serin.d1_2_gateway_io._di import get_logger


async def _transcribe_and_store(self: Any, item: dict[str, Any]) -> None:
    """
    Transcribe audio and store in memory / trigger response.

    This is the processing step for each queued transcription item. It:
      1. Checks if the model supports direct audio (Gemma unified format)
      2. If yes: truncates audio to 30s max, converts to WAV base64,
         sends to voice pipeline with wav_b64 for direct model input
      3. If no: runs Whisper STT, sends transcription text to voice pipeline

    The voice pipeline (VoiceMemoryPipeline) then:
      - Stores the message in memory
      - Builds conversation context
      - Calls the LLM for a response
      - Queues TTS playback

    Args:
        item: Dict with keys:
            user_id, username, guild_id, channel_id, audio_data, timestamp
    """
    try:
        user_id = item['user_id']
        username = item['username']
        guild_id = item['guild_id']
        channel_id = item['channel_id']
        audio_data = item['audio_data']
        timestamp = item['timestamp']

        get_logger().info(f" Transcribing audio from {username} ({len(audio_data)} bytes)...")

        if self.llm_connector and self.supports_audio:
            # Check if the model actually supports direct audio.
            # supports_audio=True is set via env var, but we double-check
            # the actual model type from the connector.
            _use_direct_audio = False
            try:
                model_info = self.llm_connector.get_model_info()
                _use_direct_audio = 'gemma' in model_info.get('model_type', '').lower()
            except Exception:
                get_logger().exception("Failed to check model info for direct audio support")

            if _use_direct_audio:
                # Direct Audio Path (Gemma Unified)
                # Skip Whisper STT entirely. Feed the raw audio + conversation
                # context directly to Gemma in one shot. The model handles
                # both understanding the audio and generating a response.

                # Truncate to 30 seconds max (Gemma's model limit).
                max_audio_bytes = 5_760_000  # 48kHz stereo 16-bit × 30s
                truncated = False
                if len(audio_data) > max_audio_bytes:
                    get_logger().info(f" Audio truncated from {len(audio_data)} to {max_audio_bytes} bytes (30s limit)")
                    audio_data = audio_data[:max_audio_bytes]
                    truncated = True

                # Convert 48kHz stereo PCM to 16kHz mono WAV base64
                wav_b64 = self._pcm_to_wav_base64(audio_data)

                # If truncated, inform the model that audio was cut off.
                transcription = "[voice input]"
                if truncated:
                    transcription = "[voice input - user was talking for long, only last 30s of audio included]"

                await self.voice_pipeline.process_voice_message(
                    user_id=user_id,
                    username=username,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    transcription=transcription,
                    wav_b64=wav_b64,  # Direct audio blob for the model
                    timestamp=timestamp
                )
                self.stats['transcriptions_completed'] += 1
            else:
                # Whisper STT Path (Non-Gemma with supports_audio flag)
                transcription = await self.transcriber.transcribe(audio_data, language="en")
                if transcription and len(transcription.strip()) > 0:
                    get_logger().info(f" Transcribed: '{transcription}'")
                    await self.voice_pipeline.process_voice_message(
                        user_id=user_id,
                        username=username,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        transcription=transcription,
                        timestamp=timestamp
                    )
                    self.stats['transcriptions_completed'] += 1
        else:
            # Whisper STT Path (No LLM connector or audio not supported)
            transcription = await self.transcriber.transcribe(audio_data, language="en")
            if transcription and len(transcription.strip()) > 0:
                get_logger().info(f" Transcribed: '{transcription}'")
                await self.voice_pipeline.process_voice_message(
                    user_id=user_id,
                    username=username,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    transcription=transcription,
                    timestamp=timestamp
                )
                self.stats['transcriptions_completed'] += 1
            else:
                get_logger().debug(f" Empty transcription from {username}")

    except Exception as e:
        get_logger().exception(f" Error transcribing audio: {e}")
        self.stats['errors'] += 1


def check_interrupt(self: Any, user_id: str) -> bool:
    """
    Check if a user is currently flagged as speaking.

    Used by the TTS queue to check whether the bot should stop speaking.
    If the user starts speaking while the bot is talking, this returns True.

    Args:
        user_id: User ID string to check

    Returns:
        True if the user is in the currently_speaking set
    """
    return user_id in self.currently_speaking


def get_active_speakers(self: Any) -> set[str]:
    """Return a copy of the set of currently speaking user IDs."""
    result: set[str] = self.currently_speaking.copy()
    return result


def get_buffer_size(self: Any, user_id: str) -> int:
    """Return the current buffer size in bytes for a user (0 if no buffer)."""
    if user_id in self.user_buffers:
        return len(self.user_buffers[user_id])
    return 0


def get_stats(self: Any) -> dict[str, Any]:
    """Return processor statistics for monitoring and debugging."""
    return {
        'chunks_received': self.stats['chunks_received'],
        'chunks_processed': self.stats['chunks_processed'],
        'users_speaking': len(self.currently_speaking),
        'active_speakers': list(self.currently_speaking),
        'transcriptions_queued': self.stats['transcriptions_queued'],
        'transcriptions_completed': self.stats['transcriptions_completed'],
        'queue_size': self.processing_queue.qsize(),
        'vad_detections': self.stats['vad_detections'],
        'silence_detections': self.stats['silence_detections'],
        'errors': self.stats['errors'],
        'is_running': self.is_running
    }
