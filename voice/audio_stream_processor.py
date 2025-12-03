"""
Audio Stream Processor - Per-User Audio Buffer & VAD
Handles per-user audio streams with Voice Activity Detection (VAD).

Features:
- Per-user audio buffering
- Voice Activity Detection (energy-based)
- Silence detection & chunking
- Smart audio segmentation
- Interrupt detection for conversation flow
"""
import asyncio
import numpy as np
from datetime import datetime
from typing import Dict, Optional
from collections import deque
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import logger


class AudioStreamProcessor:
    """
    Process audio streams per-user with VAD and smart chunking.
    Buffers audio while user is speaking, chunks at natural pauses.
    """
    
    def __init__(self, whisper_transcriber, voice_pipeline, silence_threshold: float = 3.0, voice_output_manager=None):
        """
        Initialize audio stream processor.
        
        Args:
            whisper_transcriber: WhisperTranscriber instance
            voice_pipeline: VoiceMemoryPipeline instance
            silence_threshold: Seconds of silence before processing chunk
            voice_output_manager: VoiceOutputManager instance (for interrupts)
        """
        self.transcriber = whisper_transcriber
        self.voice_pipeline = voice_pipeline
        self.silence_threshold = silence_threshold
        self.voice_output_manager = voice_output_manager
        
        # Per-user audio buffers
        self.user_buffers: Dict[str, bytearray] = {}
        
        # Per-user silence counters (in frames)
        self.user_silence_frames: Dict[str, int] = {}
        
        # Track who's speaking (for interrupt detection)
        self.currently_speaking: set = set()
        
        # Processing queue
        self.processing_queue = asyncio.Queue(maxsize=50)
        self.is_running = False
        self.processing_task = None
        
        # Voice Activity Detection settings
        self.VAD_THRESHOLD = 500  # RMS energy threshold for voice
        self.FRAMES_PER_SECOND = 50  # Discord sends 20ms frames (50 fps)
        self.SILENCE_FRAMES_THRESHOLD = int(silence_threshold * self.FRAMES_PER_SECOND)
        
        # Stats
        self.stats = {
            'chunks_received': 0,
            'chunks_processed': 0,
            'users_speaking': 0,
            'transcriptions_queued': 0,
            'transcriptions_completed': 0,
            'vad_detections': 0,
            'silence_detections': 0,
            'errors': 0
        }
        
        logger.info("✅ Audio stream processor initialized")
        logger.info(f"   🔊 VAD threshold: {self.VAD_THRESHOLD}")
        logger.info(f"   ⏱️ Silence threshold: {silence_threshold}s")
    
    async def start(self):
        """Start processing queue"""
        if self.is_running:
            logger.warning("⚠️ Audio processor already running")
            return
        
        self.is_running = True
        self.processing_task = asyncio.create_task(self._process_queue())
        logger.info("▶️ Audio stream processor started")
    
    async def stop(self):
        """Stop processing queue"""
        self.is_running = False
        if self.processing_task:
            self.processing_task.cancel()
        logger.info("⏹️ Audio stream processor stopped")
    
    def process_audio_chunk(
        self,
        user_id: str,
        username: str,
        guild_id: str,
        channel_id: str,
        audio_data: bytes
    ):
        """
        Process incoming audio chunk from a user.
        Called by AudioSink for each audio frame.
        
        Args:
            user_id: User ID
            username: Username
            guild_id: Guild ID
            channel_id: Voice channel ID
            audio_data: Raw PCM audio (48kHz, 16-bit, stereo)
        """
        try:
            self.stats['chunks_received'] += 1
            
            # Initialize user buffer if needed
            if user_id not in self.user_buffers:
                self.user_buffers[user_id] = bytearray()
                self.user_silence_frames[user_id] = 0
            
            # Voice Activity Detection
            is_voice = self._detect_voice_activity(audio_data)
            
            if is_voice:
                # Voice detected - add to buffer
                self.user_buffers[user_id].extend(audio_data)
                self.user_silence_frames[user_id] = 0
                
                # Mark as speaking
                if user_id not in self.currently_speaking:
                    self.currently_speaking.add(user_id)
                    self.stats['vad_detections'] += 1
                    logger.debug(f"🎤 {username} started speaking")
                    
                    # INTERRUPT: If bot is speaking, stop it!
                    if self.voice_output_manager:
                        # We need to run this async, but we are in a sync callback (usually)
                        # AudioSink.write is sync.
                        # We can use asyncio.create_task if there is a running loop
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(self.voice_output_manager.stop_speaking(int(guild_id)))
                        except:
                            pass
            
            else:
                # Silence detected
                if user_id in self.currently_speaking:
                    self.user_silence_frames[user_id] += 1
                    
                    # Check if silence threshold reached
                    if self.user_silence_frames[user_id] >= self.SILENCE_FRAMES_THRESHOLD:
                        # Silence detected - process buffer
                        self._queue_for_transcription(
                            user_id=user_id,
                            username=username,
                            guild_id=guild_id,
                            channel_id=channel_id
                        )
                        
                        # Reset
                        self.currently_speaking.discard(user_id)
                        self.user_silence_frames[user_id] = 0
                        self.stats['silence_detections'] += 1
        
        except Exception as e:
            logger.error(f"❌ Error processing audio chunk: {e}")
            self.stats['errors'] += 1
    
    def _detect_voice_activity(self, audio_data: bytes) -> bool:
        """
        Detect if audio contains voice using energy-based VAD.
        
        Args:
            audio_data: Raw PCM audio
        
        Returns:
            True if voice detected
        """
        try:
            # Convert to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Calculate RMS energy
            rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
            
            # Compare to threshold
            return rms > self.VAD_THRESHOLD
        
        except Exception as e:
            logger.error(f"❌ Error in VAD: {e}")
            return False
    
    def _queue_for_transcription(
        self,
        user_id: str,
        username: str,
        guild_id: str,
        channel_id: str
    ):
        """
        Queue audio buffer for transcription.
        
        Args:
            user_id: User ID
            username: Username
            guild_id: Guild ID
            channel_id: Channel ID
        """
        try:
            # Get buffer
            buffer = self.user_buffers.get(user_id)
            
            if not buffer or len(buffer) < 16000:  # Minimum 0.5 seconds at 48kHz stereo
                logger.debug(f"⏭️ Skipping empty/short buffer for {username}")
                if user_id in self.user_buffers:
                    self.user_buffers[user_id] = bytearray()
                return
            
            # Copy buffer
            audio_data = bytes(buffer)
            
            # Clear buffer
            self.user_buffers[user_id] = bytearray()
            
            # Queue for processing
            try:
                self.processing_queue.put_nowait({
                    'user_id': user_id,
                    'username': username,
                    'guild_id': guild_id,
                    'channel_id': channel_id,
                    'audio_data': audio_data,
                    'timestamp': datetime.now()
                })
                
                self.stats['transcriptions_queued'] += 1
                logger.debug(f"📋 Queued {len(audio_data)} bytes for transcription: {username}")
            
            except asyncio.QueueFull:
                logger.warning(f"⚠️ Transcription queue full, dropping audio from {username}")
        
        except Exception as e:
            logger.error(f"❌ Error queueing transcription: {e}")
            self.stats['errors'] += 1
    
    async def _process_queue(self):
        """Background task to process transcription queue"""
        logger.info("🔄 Started transcription queue processor")
        
        while self.is_running:
            try:
                # Get next item (wait up to 1 second)
                try:
                    item = await asyncio.wait_for(
                        self.processing_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Transcribe
                await self._transcribe_and_store(item)
                
                self.stats['chunks_processed'] += 1
            
            except asyncio.CancelledError:
                logger.info("🛑 Transcription queue processor cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in transcription queue: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(0.5)
        
        logger.info("🛑 Transcription queue processor stopped")
    
    async def _transcribe_and_store(self, item: Dict):
        """
        Transcribe audio and store in memory.
        
        Args:
            item: Dict with user_id, username, guild_id, channel_id, audio_data, timestamp
        """
        try:
            user_id = item['user_id']
            username = item['username']
            guild_id = item['guild_id']
            channel_id = item['channel_id']
            audio_data = item['audio_data']
            timestamp = item['timestamp']
            
            logger.info(f"🎤 Transcribing audio from {username} ({len(audio_data)} bytes)...")
            
            # Transcribe
            transcription = await self.transcriber.transcribe(audio_data, language="en")
            
            if transcription and len(transcription.strip()) > 0:
                logger.info(f"✅ Transcribed: '{transcription}'")
                
                # Store in memory pipeline
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
                logger.debug(f"⭐ Empty transcription from {username}")
        
        except Exception as e:
            logger.error(f"❌ Error transcribing audio: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats['errors'] += 1
    
    def check_interrupt(self, user_id: str) -> bool:
        """
        Check if user is currently speaking (for interrupt detection).
        Used by TTS queue to stop bot if user starts speaking.
        
        Args:
            user_id: User ID to check
        
        Returns:
            True if user is speaking
        """
        return user_id in self.currently_speaking
    
    def get_active_speakers(self) -> set:
        """Get set of currently speaking user IDs"""
        return self.currently_speaking.copy()
    
    def get_buffer_size(self, user_id: str) -> int:
        """Get current buffer size for user"""
        if user_id in self.user_buffers:
            return len(self.user_buffers[user_id])
        return 0
    
    def get_stats(self) -> Dict:
        """Get processor statistics"""
        return {
            'chunks_received': self.stats['chunks_received'],
            'chunks_processed': self.stats['chunks_processed'],
            'users_speaking': len(self.currently_speaking),  # Convert set to int
            'active_speakers': list(self.currently_speaking),  # Convert set to list
            'transcriptions_queued': self.stats['transcriptions_queued'],
            'transcriptions_completed': self.stats['transcriptions_completed'],
            'queue_size': self.processing_queue.qsize(),
            'vad_detections': self.stats['vad_detections'],
            'silence_detections': self.stats['silence_detections'],
            'errors': self.stats['errors'],
            'is_running': self.is_running
        }
