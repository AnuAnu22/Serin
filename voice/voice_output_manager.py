"""
Voice Output Manager - Handles TTS Generation and Playback
Manages the queue of sentences to speak, ensures smooth playback, and handles interruptions.
"""
import asyncio
import discord
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import logger

class VoiceOutputManager:
    def __init__(self, tts_engine: Any, voice_listener: Any) -> None:
        """
        Initialize Voice Output Manager.
        
        Args:
            tts_engine: TTSEngine instance
            voice_listener: VoiceListener instance (to get voice clients)
        """
        self.tts = tts_engine
        self.voice_listener = voice_listener
        
        # Queue of (text, guild_id) tuples
        self.sentence_queue = asyncio.Queue()
        
        # Current state
        self.is_speaking = False
        self.current_guild_id: Optional[int] = None
        self.interrupt_event = asyncio.Event()
        
        # Background task
        self.processing_task = None
        self.is_running = False
        
        logger.info("✅ Voice output manager initialized")
    
    async def start(self) -> None:
        """Start processing loop"""
        if self.is_running:
            return
        
        self.is_running = True
        self.processing_task = asyncio.create_task(self._process_queue())
        logger.info("▶️ Voice output manager started")
    
    async def stop(self) -> None:
        """Stop processing loop"""
        self.is_running = False
        if self.processing_task:
            self.processing_task.cancel()
        logger.info("⏹️ Voice output manager stopped")
    
    async def speak(self, text: str, guild_id: int, priority: bool = False) -> None:
        """
        Queue text to be spoken.
        
        Args:
            text: Text to speak
            guild_id: Guild ID
            priority: If True, clear queue and speak immediately (interrupt self)
        """
        if priority:
            await self.stop_speaking(guild_id)
        
        # Split into sentences if needed (simple split)
        # Better splitting should happen in MessageManager before calling this
        sentences = self._split_sentences(text)
        
        for sentence in sentences:
            if sentence.strip():
                await self.sentence_queue.put((sentence, guild_id))
                logger.debug(f"🗣️ Queued: '{sentence[:30]}...'")
    
    async def stop_speaking(self, guild_id: int) -> None:
        """
        Interrupt current speech and clear queue for guild.
        """
        # Clear queue for this guild (rebuild queue without this guild's items)
        # This is a bit hacky for a single queue, but simple for now
        # Ideally we'd have per-guild queues
        
        # Signal interrupt
        self.interrupt_event.set()
        
        # Stop Discord audio
        if guild_id in self.voice_listener.voice_connections:
            vc = self.voice_listener.voice_connections[guild_id]
            if vc.is_playing():
                vc.stop()
        
        self.is_speaking = False
        logger.info(f"🛑 Stopped speaking in guild {guild_id}")
    
    async def _process_queue(self) -> None:
        """Process sentence queue"""
        while self.is_running:
            try:
                # Get next sentence
                text, guild_id = await self.sentence_queue.get()
                
                self.current_guild_id = guild_id
                self.is_speaking = True
                self.interrupt_event.clear()
                
                # Check if we have a voice connection
                if guild_id not in self.voice_listener.voice_connections:
                    logger.warning(f"⚠️ No voice connection for guild {guild_id}, dropping speech")
                    self.sentence_queue.task_done()
                    continue
                
                vc = self.voice_listener.voice_connections[guild_id]
                
                # Generate Audio
                logger.debug(f"🎙️ Synthesizing: '{text[:30]}...'")
                audio_data = await self.tts.synthesize(text)
                
                if not audio_data:
                    logger.error("❌ TTS generation failed")
                    self.sentence_queue.task_done()
                    continue
                
                # Check interrupt before playing
                if self.interrupt_event.is_set():
                    logger.info("🛑 Interrupted before playback")
                    self.sentence_queue.task_done()
                    continue
                
                # Play Audio
                await self._play_audio(vc, audio_data)
                
                self.sentence_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error in voice output loop: {e}")
                await asyncio.sleep(1)
        
        self.is_speaking = False
    
    async def _play_audio(self, vc: discord.VoiceClient, audio_data: bytes) -> None:
        """Play audio data on VoiceClient"""
        try:
            # Create AudioSource
            # XTTS outputs 24kHz usually, Discord needs 48kHz stereo
            # discord.FFmpegPCMAudio handles this, but for raw bytes we need PCMVolumeTransformer
            
            # Save to temp file for FFmpeg (safest way to handle formats)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_data)
                temp_filename = f.name
            
            source = discord.FFmpegPCMAudio(temp_filename)
            
            # Wrap in transformer for volume control
            source = discord.PCMVolumeTransformer(source, volume=1.0)
            
            # Play
            vc.play(source, after=lambda e: self._cleanup_temp(temp_filename, e))
            
            # Wait for playback to finish
            while vc.is_playing():
                await asyncio.sleep(0.1)
                if self.interrupt_event.is_set():
                    vc.stop()
                    break
            
        except Exception as e:
            logger.error(f"❌ Error playing audio: {e}")
    
    def _cleanup_temp(self, filename: str, error: Optional[Exception]) -> None:
        """Cleanup temp file after playback"""
        try:
            if os.path.exists(filename):
                os.remove(filename)
            if error:
                logger.error(f"❌ Playback error: {error}")
        except:
            pass
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences for batching"""
        import re
        # Split by . ? ! but keep the delimiter
        # This is a simple regex, might need improvement
        parts = re.split(r'([.?!]+)', text)
        sentences = []
        current = ""
        for part in parts:
            current += part
            if re.match(r'[.?!]+', part):
                sentences.append(current.strip())
                current = ""
        if current.strip():
            sentences.append(current.strip())
        return sentences
