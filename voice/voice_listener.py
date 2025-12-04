"""
Voice Listener - Discord Voice Channel Manager (discord.py compatible)
Handles joining/leaving voice channels and capturing audio streams.

Features:
- Join/leave VC programmatically
- Capture per-user audio streams
- Integration with audio processor
- Real-time status tracking
- discord.py 2.x compatible (no pycord dependency)
"""
import asyncio
import discord
from typing import Dict, Optional, Set
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import logger


class VoiceListener:
    def __init__(self, client, audio_processor):
        """
        Initialize voice listener.
        
        Args:
            client: Discord client
            audio_processor: AudioStreamProcessor instance
        """
        self.client = client
        self.audio_processor = audio_processor
        
        # Track active voice connections
        self.voice_connections: Dict[int, discord.VoiceClient] = {}  # guild_id -> VoiceClient
        
        # Settings
        self.transcription_enabled = True
        self.auto_join_on_mention = True
        
        # Stats
        self.stats = {
            'connections': 0,
            'total_audio_chunks': 0,
            'active_channels': set(),
            'errors': 0
        }
        
        logger.info("✅ Voice listener initialized (discord.py compatible)")
    
    async def join_channel(self, guild_id: int, channel_id: int) -> bool:
        """
        Join a voice channel.
        
        Args:
            guild_id: Guild ID
            channel_id: Voice channel ID
        
        Returns:
            Success status
        """
        try:
            guild = self.client.get_guild(guild_id)
            if not guild:
                logger.error(f"❌ Guild {guild_id} not found")
                return False
            
            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                logger.error(f"❌ Voice channel {channel_id} not found")
                return False
            
            # Check if already connected to this guild
            if guild_id in self.voice_connections:
                # Move to new channel
                await self.voice_connections[guild_id].move_to(channel)
                logger.info(f"🎤 Moved to {channel.name} in {guild.name}")
            else:
                # Join new channel
                voice_client = await channel.connect()
                self.voice_connections[guild_id] = voice_client
                
                # Start listening
                await self._start_listening(voice_client, guild_id, channel_id)
                
                logger.info(f"🎤 Joined {channel.name} in {guild.name}")
            
            self.stats['connections'] += 1
            self.stats['active_channels'].add(str(channel_id))
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Error joining voice channel: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats['errors'] += 1
            return False
    
    async def leave_channel(self, guild_id: int) -> bool:
        """
        Leave voice channel in a guild.
        
        Args:
            guild_id: Guild ID
        
        Returns:
            Success status
        """
        try:
            if guild_id not in self.voice_connections:
                logger.warning(f"⚠️ Not connected to voice in guild {guild_id}")
                return False
            
            voice_client = self.voice_connections[guild_id]
            
            # Stop listening
            await self._stop_listening(guild_id)
            
            # Disconnect
            await voice_client.disconnect()
            
            # Remove from tracking
            channel_id = str(voice_client.channel.id)
            del self.voice_connections[guild_id]
            self.stats['active_channels'].discard(channel_id)
            
            logger.info(f"🎤 Left voice channel in guild {guild_id}")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error leaving voice channel: {e}")
            self.stats['errors'] += 1
            return False
    

    async def _start_listening(self, voice_client: discord.VoiceClient, guild_id: int, channel_id: int):
        """Start listening using discord.py 2.x AudioSink"""
        try:
            # Create custom sink
            sink = AudioSink(
                audio_processor=self.audio_processor,
                guild_id=guild_id,
                channel_id=channel_id,
                stats=self.stats
            )
            
            # discord.py 2.x: Use listen() not start_recording()
            voice_client.listen(sink)
            logger.info(f"🎧 Started listening in channel {channel_id}")
        
        except Exception as e:
            logger.error(f"Error starting listener: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _stop_listening(self, guild_id: int):
        """
        Stop listening to audio.
        
        Args:
            guild_id: Guild ID
        """
        try:
            if guild_id in self.voice_connections:
                voice_client = self.voice_connections[guild_id]
                if voice_client.is_connected():
                    voice_client.stop_recording()
                    logger.info(f"🎧 Stopped listening in guild {guild_id}")
        except Exception as e:
            logger.error(f"❌ Error stopping recording: {e}")
    
    def _recording_callback(self, sink, user, audio):
        """Callback when recording finishes for a user"""
        logger.debug(f"📼 Recording callback triggered for user {user}")
    
    def _recording_error_callback(self, sink, error):
        """Callback when recording error occurs"""
        logger.error(f"❌ Recording error: {error}")
        self.stats['errors'] += 1
    
    def get_status(self) -> Dict:
        """Get current voice connection status"""
        connections = []
        
        for guild_id, voice_client in self.voice_connections.items():
            if voice_client.is_connected():
                connections.append({
                    'guild_id': str(guild_id),
                    'guild_name': voice_client.guild.name,
                    'channel_id': str(voice_client.channel.id),
                    'channel_name': voice_client.channel.name,
                    'members': len(voice_client.channel.members)
                })
        
        return {
            'connected': len(connections) > 0,
            'active_connections': connections,
            'total_connections': self.stats['connections'],
            'transcription_enabled': self.transcription_enabled
        }
    
    def get_stats(self) -> Dict:
        """Get voice listener statistics"""
        return {
            'connected': len(self.voice_connections) > 0,
            'active_channels': len(self.stats['active_channels']),
            'total_connections': self.stats['connections'],
            'audio_chunks_processed': self.stats['total_audio_chunks'],
            'errors': self.stats['errors']
        }

    def is_connected(self) -> bool:
        """
        Check if connected to any voice channel.
        Also cleans up stale connections.
        """
        active_connections = 0
        stale_guilds = []
        
        for guild_id, vc in self.voice_connections.items():
            if vc.is_connected():
                active_connections += 1
            else:
                stale_guilds.append(guild_id)
        
        # Cleanup stale
        for guild_id in stale_guilds:
            del self.voice_connections[guild_id]
            
        return active_connections > 0


class AudioSink(discord.sinks.Sink):
    """discord.py 2.x compatible audio sink"""
    
    def __init__(self, audio_processor, guild_id: int, channel_id: int, stats: Dict):
        super().__init__()
        self.audio_processor = audio_processor
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.stats = stats
    
    def write(self, data: bytes, user: discord.User):
        """Called for each audio frame (discord.py 2.x)"""
        try:
            self.audio_processor.process_audio_chunk(
                user_id=str(user.id),
                username=user.name,
                guild_id=str(self.guild_id),
                channel_id=str(self.channel_id),
                audio_data=data
            )
            self.stats['total_audio_chunks'] += 1
        except Exception as e:
            logger.error(f"Error in AudioSink.write: {e}")
    
    def cleanup(self):
        """Called when recording stops"""
        logger.debug(f"🎤 AudioSink cleanup")
    