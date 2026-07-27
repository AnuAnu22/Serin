"""
Voice Memory Pipeline - Integrate Voice Transcriptions into Memory System
Processes voice messages and stores them as memories.

Features:
- Voice message → Memory storage
- Context awareness
- Integration with background processor
- Voice-specific metadata
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from serin.d1_2_gateway_io.d2_4_io_di import get_logger


class VoiceMemoryPipeline:
    def __init__(self, memory_system: Any, background_processor: Any, message_manager: Any | None = None) -> None:
        """
        Initialize voice memory pipeline.

        Args:
            memory_system: UnifiedMemorySystem instance
            background_processor: BackgroundProcessor instance
            message_manager: MessageManagerV3 instance (optional, for response generation)
        """
        self.memory = memory_system
        self.bg_processor = background_processor
        self.message_manager = message_manager

        # Track recent voice messages for context
        self.recent_voice_messages: dict[str, list[dict[str, Any]]] = {}  # channel_id -> list of recent messages

        # Stats
        self.stats = {
            'total_voice_messages': 0,
            'stored_in_memory': 0,
            'queued_for_processing': 0,
            'responses_triggered': 0,
            'errors': 0
        }

        get_logger().info(" Voice memory pipeline initialized")

    async def process_voice_message(
        self,
        user_id: str,
        username: str,
        guild_id: str,
        channel_id: str,
        transcription: str,
        timestamp: datetime | None = None
    ) -> None:
        """
        Process a voice message transcription.

        Called by the Whisper STT path (AudioStreamProcessor delegates here
        for non-direct-audio scenarios).  For direct audio input the
        _transcribe_and_store function handles everything end-to-end and
        bypasses this method entirely.

        Args:
            user_id: User ID
            username: Username
            guild_id: Guild ID
            channel_id: Voice channel ID
            transcription: Transcribed text
            timestamp: Message timestamp
        """
        try:
            timestamp = timestamp or datetime.now()

            get_logger().info(f" Processing voice message from {username}: '{transcription}'")

            # Update user profile
            self.memory.upsert_user(user_id, username, username)
            self.memory.update_user_activity(user_id, len(transcription))

            # Skip empty or placeholder transcriptions
            transcription = transcription.strip()
            if not transcription or len(transcription) < 3:
                get_logger().debug(f"Skipping empty/short transcription from {username}")
                return
            if transcription.lower() in ('[voice input]', 'voice input', 'no speech detected', 'no audio'):
                get_logger().debug(f"Skipping placeholder transcription from {username}: {transcription}")
                return

            # Store as memory (with voice metadata)
            self.memory.add_memory(
                content=f"[Voice] {transcription}",
                user_id=user_id,
                username=username,
                channel_id=channel_id,
                participants=[user_id],
                emotional_tone='neutral',
                importance=0.7,
                message_id=None
            )

            self.stats['stored_in_memory'] += 1

            # Add to recent messages for context
            if channel_id not in self.recent_voice_messages:
                self.recent_voice_messages[channel_id] = []

            self.recent_voice_messages[channel_id].append({
                'user_id': user_id,
                'username': username,
                'content': transcription,
                'timestamp': timestamp.isoformat()
            })

            # Keep only last 10 messages
            if len(self.recent_voice_messages[channel_id]) > 10:
                self.recent_voice_messages[channel_id] = self.recent_voice_messages[channel_id][-10:]

            # Queue for background processing
            self.bg_processor.queue_message(
                content=transcription,
                user_id=user_id,
                username=username,
                channel_id=channel_id,
                server_id=guild_id,
                timestamp=timestamp
            )

            self.stats['queued_for_processing'] += 1
            self.stats['total_voice_messages'] += 1

            # Generate voice response
            get_logger().info(f" Triggering voice response for {username}")
            from serin.d1_1_serin_di import get_message_manager
            from serin.d1_1_serin_di import process_voice_input as _process_voice_input
            _manager = get_message_manager()
            await _process_voice_input(
                _manager,
                user_id=user_id,
                username=username,
                channel_id=channel_id,
                transcription=transcription,
                guild_id=guild_id,
            )
            self.stats['responses_triggered'] += 1

            get_logger().debug(" Voice message processed and stored")

        except Exception as e:
            get_logger().error(f" Error processing voice message: {e}")
            self.stats['errors'] += 1

    async def _should_respond_to_voice(
        self,
        user_id: str,
        username: str,
        channel_id: str,
        transcription: str
    ) -> bool:
        """
        Decide if bot should respond to voice message.
        Voice is conversational — always respond.
        """
        return True

    def get_recent_context(self, channel_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Get recent voice messages for context.

        Args:
            channel_id: Channel ID
            limit: Number of recent messages

        Returns:
            List of recent messages
        """
        if channel_id in self.recent_voice_messages:
            return list(self.recent_voice_messages[channel_id][-limit:])
        return []

    def get_stats(self) -> dict[str, Any]:
        """Get pipeline statistics"""
        return {
            'total_voice_messages': self.stats['total_voice_messages'],
            'stored_in_memory': self.stats['stored_in_memory'],
            'queued_for_processing': self.stats['queued_for_processing'],
            'responses_triggered': self.stats['responses_triggered'],
            'errors': self.stats['errors']
        }
