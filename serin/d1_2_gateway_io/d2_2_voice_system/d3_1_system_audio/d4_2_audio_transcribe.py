"""Audio transcription — Gemma direct input and Whisper fallback."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from serin.d1_2_gateway_io.d2_4_io_di import get_logger


async def _transcribe_and_store(self: Any, item: dict[str, Any]) -> None:
    """
    Process a voice audio chunk end-to-end.

    When the model supports direct audio (Gemma with input_audio):
      - Converts PCM → 16kHz mono WAV base64
      - Builds context from recent voice messages, memories, and personality
      - Sends audio + contextual prompt directly to the LLM
      - Queues TTS for the response
      - Skips Whisper STT, memory storage, and the full pipeline context builder

    When the model does NOT support direct audio:
      - Falls back to Whisper STT → VoiceMemoryPipeline → LLM response → TTS

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

        get_logger().info(f" Processing audio from {username} ({len(audio_data)} bytes)...")

        if self.llm_connector and self.supports_audio:
            try:
                model_info = self.llm_connector.get_model_info()
                use_direct = 'gemma' in model_info.get('model_type', '').lower()
            except Exception:
                get_logger().exception("Failed to check model info for direct audio support")
                use_direct = False

            if use_direct:
                # ── Direct Audio Path (Gemma) ──
                # Gemma understands audio natively via input_audio.  We build
                # context from recent voice history and memories (same as the
                # text pipeline) and inject it alongside the audio so Gemma
                # has conversational awareness.

                max_audio_bytes = 5_760_000
                if len(audio_data) > max_audio_bytes:
                    get_logger().info(f" Audio truncated from {len(audio_data)} to {max_audio_bytes} bytes (30s limit)")
                    audio_data = audio_data[:max_audio_bytes]

                wav_b64 = self._pcm_to_wav_base64(audio_data)

                # ── Build context from recent voice history + memories ──
                formatted_context = ""
                vp = getattr(self, 'voice_pipeline', None)
                if vp is not None:
                    recent_voice: list[dict[str, Any]] = vp.get_recent_context(channel_id, limit=5)
                    user_messages: list[dict[str, Any]] = []
                    for msg in recent_voice:
                        user_messages.append({
                            "user_id": msg["user_id"],
                            "user_name": msg["username"],
                            "content": msg["content"],
                            "timestamp": msg["timestamp"],
                        })
                    if not any(m["content"] == "" for m in user_messages):
                        user_messages.append({
                            "user_id": user_id,
                            "user_name": username,
                            "content": "",
                            "timestamp": datetime.now().isoformat(),
                        })

                    mm = getattr(vp, 'message_manager', None)
                    if mm is not None:
                        cb = getattr(mm, 'context_builder', None)
                        if cb is not None:
                            context = cb.build_context(
                                user_messages=user_messages,
                                channel_id=channel_id,
                            )
                            formatted_context = cb.format_context_for_llm(context)

                        bp = getattr(mm, 'bot_personality', None)
                        if bp is not None:
                            pc = bp.get_personality_context()
                            if pc:
                                formatted_context += f"\n\n{pc}"

                formatted_context += "\n\n[SYSTEM: You are speaking in a voice channel. Keep responses concise and natural. Avoid lists or code blocks.]"

                messages: list[Any] = []
                if formatted_context.strip():
                    messages.append({
                        'role': 'system',
                        'content': formatted_context,
                    })
                messages.append({
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': f'{username} is speaking. Respond directly in first person (I, me, my). Never describe yourself or the speaker in third person. Be conversational.'},
                        {'type': 'input_audio', 'input_audio': {'data': wav_b64, 'format': 'wav'}},
                    ],
                })

                try:
                    response = await self.llm_connector.chat_completion(
                        messages,
                        max_tokens=300,
                        temperature=1.0,
                        top_p=0.95,
                        extra_body={'chat_template_kwargs': {'enable_thinking': False}},
                    )
                except Exception as e:
                    get_logger().error(f" Direct audio LLM call failed: {e}")
                    self.stats['errors'] += 1
                    return

                if response and response.strip():
                    get_logger().info(f" Voice Response: '{response[:200]}'")
                    if self.voice_output_manager:
                        try:
                            await self.voice_output_manager.speak(response, int(guild_id))
                            get_logger().info(f" TTS queued for guild {guild_id} ({len(response)} chars)")
                        except Exception as e:
                            get_logger().error(f" TTS failed for guild {guild_id}: {e}")
                    else:
                        get_logger().warning("voice_output_manager not available — response not spoken")
                else:
                    get_logger().warning("Empty response from LLM — nothing to speak")

                self.stats['transcriptions_completed'] += 1
                return

        # ── Whisper STT Path (no direct audio or non-Gemma model) ──
        transcription = await self.transcriber.transcribe(audio_data, language='en')
        if transcription and len(transcription.strip()) > 0:
            get_logger().info(f" Transcribed: '{transcription}'")
            await self.voice_pipeline.process_voice_message(
                user_id=user_id,
                username=username,
                guild_id=guild_id,
                channel_id=channel_id,
                transcription=transcription,
                timestamp=timestamp,
            )
            self.stats['transcriptions_completed'] += 1
        else:
            get_logger().debug(f" Empty transcription from {username}")

    except Exception as e:
        get_logger().exception(f" Error processing audio: {e}")
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
