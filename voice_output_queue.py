"""
Voice Output Queue - Manage TTS Output
Handles queueing, prioritization, and interruption of voice responses.

Features:
- Priority queue for TTS requests
- Interrupt detection (cancel if user speaks)
- Per-channel queue management
- Discord voice output integration
"""
import asyncio
import io
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from collections import deque
from logger_config import logger
import discord


class VoiceOutputRequest:
    """Single TTS output request"""
    
    def __init__(
        self,
        text: str,
        channel_id: str,
        guild_id: str,
        profile: str = 'default',
        priority: int = 5,
        user_id: Optional[str] = None
    ) -> None:
        self.text = text
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.profile = profile
        self.priority = priority  # 1-10, lower = higher priority
        self.user_id = user_id
        self.timestamp = datetime.now()
        self.id = f"{guild_id}_{channel_id}_{int(self.timestamp.timestamp() * 1000)}"
    
    def __lt__(self, other: Any) -> bool:
        """For priority queue sorting"""
        return self.priority < other.priority


class VoiceOutputQueue:
    """Manage TTS output queue"""
    
    def __init__(self, tts_engine: Any, audio_processor: Any, discord_client: Any) -> None:
        """
        Initialize voice output queue.
        
        Args:
            tts_engine: TTSEngine instance
            audio_processor: AudioStreamProcessor instance
            discord_client: Discord client
        """
        self.tts_engine = tts_engine
        self.audio_processor = audio_processor
        self.client = discord_client
        
        # Per-guild queues
        self.queues: Dict[str, asyncio.PriorityQueue] = {}
        
        # Currently playing
        self.currently_playing: Dict[str, VoiceOutputRequest] = {}  # guild_id -> request
        
        # Processing tasks
        self.is_running = False
        self.processing_tasks: Dict[str, asyncio.Task] = {}
        
        # Stats
        self.stats = {
            'total_queued': 0,
            'total_played': 0,
            'total_interrupted': 0,
            'errors': 0
        }
        
        logger.info("✅ Voice output queue initialized")
    
    async def start(self) -> None:
        """Start queue processing"""
        if self.is_running:
            logger.warning("⚠️ Voice output queue already running")
            return
        
        self.is_running = True
        logger.info("▶️ Voice output queue started")
    
    async def stop(self) -> None:
        """Stop queue processing"""
        self.is_running = False
        
        # Cancel all tasks
        for task in self.processing_tasks.values():
            task.cancel()
        
        # Clear queues
        self.queues.clear()
        self.currently_playing.clear()
        
        logger.info("⏹️ Voice output queue stopped")
    
    async def enqueue(
        self,
        text: str,
        guild_id: str,
        channel_id: str,
        profile: str = 'default',
        priority: int = 5,
        user_id: Optional[str] = None
    ) -> None:
        """
        Add TTS request to queue.
        
        Args:
            text: Text to synthesize
            guild_id: Guild ID
            channel_id: Voice channel ID
            profile: Voice profile
            priority: Priority (1=highest, 10=lowest)
            user_id: User who triggered this (for interrupt detection)
        """
        try:
            request = VoiceOutputRequest(
                text=text,
                channel_id=channel_id,
                guild_id=guild_id,
                profile=profile,
                priority=priority,
                user_id=user_id
            )
            
            # Create queue for guild if doesn't exist
            if guild_id not in self.queues:
                self.queues[guild_id] = asyncio.PriorityQueue(maxsize=20)
            
            # Add to queue
            await self.queues[guild_id].put((priority, request))
            self.stats['total_queued'] += 1
            
            logger.info(f"📋 Queued TTS: '{text[:50]}...' (priority: {priority})")
            
            # Start processing task if not running
            if guild_id not in self.processing_tasks or self.processing_tasks[guild_id].done():
                self.processing_tasks[guild_id] = asyncio.create_task(
                    self._process_queue(guild_id)
                )
        
        except asyncio.QueueFull:
            logger.warning(f"⚠️ TTS queue full for guild {guild_id}")
        except Exception as e:
            logger.error(f"❌ Error enqueueing TTS: {e}")
            self.stats['errors'] += 1
    
    async def _process_queue(self, guild_id: str) -> None:
        """
        Process queue for a specific guild.
        
        Args:
            guild_id: Guild ID
        """
        logger.info(f"🔄 Started TTS queue processor for guild {guild_id}")
        
        while self.is_running:
            try:
                # Get next request (wait up to 30 seconds)
                try:
                    priority, request = await asyncio.wait_for(
                        self.queues[guild_id].get(),
                        timeout=30.0
                    )
                except asyncio.TimeoutError:
                    # No requests for 30s, stop task
                    logger.debug(f"⏰ TTS queue idle for guild {guild_id}, stopping")
                    break
                
                # Check for interrupts before processing
                if request.user_id and self.audio_processor.check_interrupt(request.user_id):
                    logger.info(f"⛔ Interrupted: User {request.user_id} is speaking")
                    self.stats['total_interrupted'] += 1
                    continue
                
                # Mark as currently playing
                self.currently_playing[guild_id] = request
                
                # Process request
                await self._play_tts(request)
                
                # Remove from currently playing
                if guild_id in self.currently_playing:
                    del self.currently_playing[guild_id]
                
                self.stats['total_played'] += 1
            
            except asyncio.CancelledError:
                logger.info(f"🛑 TTS queue processor cancelled for guild {guild_id}")
                break
            except Exception as e:
                logger.error(f"❌ Error in TTS queue processor: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(1)
        
        # Cleanup
        if guild_id in self.processing_tasks:
            del self.processing_tasks[guild_id]
        
        logger.info(f"🛑 TTS queue processor stopped for guild {guild_id}")
    
    async def _play_tts(self, request: VoiceOutputRequest) -> None:
        """
        Synthesize and play TTS audio.
        
        Args:
            request: VoiceOutputRequest
        """
        try:
            logger.info(f"🎙️ Synthesizing TTS: '{request.text[:50]}...'")
            
            # Synthesize audio
            audio_data = await self.tts_engine.synthesize(
                text=request.text,
                profile=request.profile
            )
            
            if not audio_data:
                logger.error("❌ TTS synthesis failed")
                return
            
            # Get voice connection
            guild = self.client.get_guild(int(request.guild_id))
            if not guild:
                logger.error(f"❌ Guild {request.guild_id} not found")
                return
            
            voice_client = guild.voice_client
            if not voice_client or not voice_client.is_connected():
                logger.error(f"❌ Not connected to voice in guild {request.guild_id}")
                return
            
            # Play audio
            logger.info(f"🔊 Playing TTS audio in {guild.name}")
            
            # Convert audio data to Discord audio source
            audio_source = discord.FFmpegPCMAudio(
                io.BytesIO(audio_data),
                pipe=True
            )
            
            # Play (this blocks until done or interrupted)
            voice_client.play(
                audio_source,
                after=lambda e: logger.info(f"✅ TTS playback finished") if not e else logger.error(f"❌ TTS playback error: {e}")
            )
            
            # Wait for playback to finish
            while voice_client.is_playing():
                await asyncio.sleep(0.1)
                
                # Check for interrupts during playback
                if request.user_id and self.audio_processor.check_interrupt(request.user_id):
                    logger.info(f"⛔ Playback interrupted")
                    voice_client.stop()
                    self.stats['total_interrupted'] += 1
                    break
        
        except Exception as e:
            logger.exception(f"❌ Error playing TTS: {e}")
            self.stats['errors'] += 1
    
    def cancel_current(self, guild_id: str) -> None:
        """
        Cancel currently playing TTS in a guild.
        
        Args:
            guild_id: Guild ID
        """
        try:
            if guild_id in self.currently_playing:
                guild = self.client.get_guild(int(guild_id))
                if guild and guild.voice_client and guild.voice_client.is_playing():
                    guild.voice_client.stop()
                    logger.info(f"⛔ Cancelled TTS playback in guild {guild_id}")
                    self.stats['total_interrupted'] += 1
        except Exception as e:
            logger.error(f"❌ Error cancelling TTS: {e}")
    
    def clear_queue(self, guild_id: str) -> None:
        """
        Clear pending TTS queue for a guild.
        
        Args:
            guild_id: Guild ID
        """
        try:
            if guild_id in self.queues:
                # Create new empty queue
                self.queues[guild_id] = asyncio.PriorityQueue(maxsize=20)
                logger.info(f"🗑️ Cleared TTS queue for guild {guild_id}")
        except Exception as e:
            logger.error(f"❌ Error clearing queue: {e}")
    
    def get_queue_size(self, guild_id: str) -> int:
        """Get queue size for a guild"""
        if guild_id in self.queues:
            return self.queues[guild_id].qsize()
        return 0
    
    def is_playing(self, guild_id: str) -> bool:
        """Check if currently playing in a guild"""
        return guild_id in self.currently_playing
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        total_queued = sum(q.qsize() for q in self.queues.values())
        
        return {
            'total_queued': self.stats['total_queued'],
            'total_played': self.stats['total_played'],
            'total_interrupted': self.stats['total_interrupted'],
            'errors': self.stats['errors'],
            'current_queue_size': total_queued,
            'active_guilds': len(self.currently_playing),
            'is_running': self.is_running
        }
