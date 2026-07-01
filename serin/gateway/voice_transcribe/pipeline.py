"""
Voice Memory Pipeline - Integrate Voice Transcriptions into Memory System
Processes voice messages and stores them as memories.

Features:
- Voice message → Memory storage
- Context awareness
- Integration with background processor
- Voice-specific metadata
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from serin.state.logger import logger


class VoiceMemoryPipeline:
    def __init__(self, memory_system: Any, background_processor: Any, message_manager: Optional[Any] = None) -> None:
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
        self.recent_voice_messages = {}  # channel_id -> list of recent messages
        
        # Stats
        self.stats = {
            'total_voice_messages': 0,
            'stored_in_memory': 0,
            'queued_for_processing': 0,
            'responses_triggered': 0,
            'errors': 0
        }
        
        logger.info(" Voice memory pipeline initialized")
    
    async def process_voice_message(
        self,
        user_id: str,
        username: str,
        guild_id: str,
        channel_id: str,
        transcription: str,
        wav_b64: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> None:
        """
        Process a voice message transcription.
        
        Args:
            user_id: User ID
            username: Username
            guild_id: Guild ID
            channel_id: Voice channel ID
            transcription: Transcribed text (or placeholder)
            wav_b64: Optional WAV base64 for direct audio input to the model
            timestamp: Message timestamp
        """
        try:
            timestamp = timestamp or datetime.now()
            
            logger.info(f" Processing voice message from {username}: '{transcription}'")
            
            # Update user profile
            self.memory.upsert_user(user_id, username, username)
            self.memory.update_user_activity(user_id, len(transcription))
            
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
            if self.message_manager and hasattr(self.message_manager, 'process_voice_input'):
                logger.info(f" Triggering voice response for {username}")
                await self.message_manager.process_voice_input(
                    user_id=user_id,
                    username=username,
                    channel_id=channel_id,
                    transcription=transcription,
                    wav_b64=wav_b64
                )
                self.stats['responses_triggered'] += 1
            
            logger.debug(f" Voice message processed and stored")
        
        except Exception as e:
            logger.error(f" Error processing voice message: {e}")
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
    
    def get_recent_context(self, channel_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent voice messages for context.
        
        Args:
            channel_id: Channel ID
            limit: Number of recent messages
        
        Returns:
            List of recent messages
        """
        if channel_id in self.recent_voice_messages:
            return self.recent_voice_messages[channel_id][-limit:]
        return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics"""
        return {
            'total_voice_messages': self.stats['total_voice_messages'],
            'stored_in_memory': self.stats['stored_in_memory'],
            'queued_for_processing': self.stats['queued_for_processing'],
            'responses_triggered': self.stats['responses_triggered'],
            'errors': self.stats['errors']
        }
