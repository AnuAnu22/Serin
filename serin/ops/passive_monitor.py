"""
Passive Monitor - Listens to ALL channels across ALL servers
Stores information without responding (unless in allowed channels)
"""
from __future__ import annotations

import discord

from datetime import datetime
from typing import Set, Dict, Any, TYPE_CHECKING
from serin.state.logger import logger

if TYPE_CHECKING:
    from serin.ops.background import BackgroundProcessor
    from serin.state.voice.mention_translator import MentionTranslator


class PassiveMonitor:
    def __init__(
        self,
        memory_system: Any,
        background_processor: BackgroundProcessor,
        allowed_channel_ids: Set[int],
        mention_translator: MentionTranslator,
    ) -> None:
        """
        Initialize passive monitor.
        
        Args:
            memory_system: UnifiedMemorySystem instance
            background_processor: BackgroundProcessor instance
            allowed_channel_ids: Set of channel IDs where bot can respond
        """
        self.memory = memory_system
        self.bg_processor = background_processor
        self.allowed_channels = allowed_channel_ids
        self.mention_translator = mention_translator
        
        self.stats: Dict[str, Any] = {
            'passive_messages_seen': 0,
            'active_messages_seen': 0,
            'total_messages': 0,
            'servers_monitored': set(),
            'channels_monitored': set()
        }
        
        logger.info(" Passive monitor initialized")
    
    async def process_message(self, message: discord.Message, is_allowed_channel: bool) -> None:
        """
        Process a message from ANY channel.
        
        Args:
            message: Discord message object
            is_allowed_channel: True if in allowed channel (will respond)
        """
        try:
            # Update stats
            self.mention_translator.update_cache(message.author)
            self.stats['total_messages'] += 1
            self.stats['servers_monitored'].add(str(message.guild.id) if message.guild else 'DM')
            self.stats['channels_monitored'].add(str(message.channel.id))
            
            cleaned_content = self.mention_translator.clean_for_bot(message.content, message)
            cleaned_content = self.mention_translator.clean_bot_self_mention(cleaned_content)
        
            if is_allowed_channel:
                self.stats['active_messages_seen'] += 1
            else:
                self.stats['passive_messages_seen'] += 1
            
            # Extract message data
            user_id = str(message.author.id)
            username = message.author.display_name
            content = message.content.strip()
            channel_id = str(message.channel.id)
            server_id = str(message.guild.id) if message.guild else 'DM'
            
            # Skip empty messages or messages with only mentions/commands
            if not content or len(cleaned_content.strip()) < 5:
                return
            
            # Update user profile (always, across all servers)
            self.memory.upsert_user(user_id, username, username)
            self.memory.update_user_activity(user_id, len(cleaned_content))
            
            # Only queue messages with meaningful content for background processing
            if len(cleaned_content.strip()) >= 10:  # Require at least 10 meaningful characters
                self.bg_processor.queue_message(
                    content=cleaned_content,
                    user_id=user_id,
                    username=username,
                    channel_id=channel_id,
                    server_id=server_id,
                    timestamp=message.created_at.isoformat()
                )
            
            # Log based on channel type
            if is_allowed_channel:
                logger.debug(f" Active: {username} in #{message.channel.name}")
            else:
                logger.debug(f" Passive: {username} in #{message.channel.name} (monitoring only)")
            
        except Exception as e:
            logger.error(f" Error in passive monitor: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics"""
        return {
            'passive_messages': self.stats['passive_messages_seen'],
            'active_messages': self.stats['active_messages_seen'],
            'total_messages': self.stats['total_messages'],
            'servers_monitored': len(self.stats['servers_monitored']),  # Convert set to int
            'servers_list': list(self.stats['servers_monitored']),  # Add list version
            'channels_monitored': len(self.stats['channels_monitored']),  # Convert set to int
            'channels_list': list(self.stats['channels_monitored'])  # Add list version
        }