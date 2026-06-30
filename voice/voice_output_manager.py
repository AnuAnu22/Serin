"""
Voice Output Manager — Handles TTS Generation and Playback

Manages a queue of text to speak, generates TTS audio via edge-tts, and
sends it to the Rust bridge for voice channel playback.

Key design:
  - The full response text is queued as ONE item (no sentence splitting).
    This avoids the Rust SPEAK command interrupting the previous track.
  - TTS_DONE signal from Rust releases the processing lock so the next
    user utterance can be processed immediately.
  - Interrupt detection: if the user speaks while TTS is playing, the
    processing lock prevents cascading and the interrupt stops playback.

Sentence splitting is intentionally disabled because:
  1. Rust's SPEAK handler calls handle.stop() before playing new audio
  2. Sending multiple SPEAK commands → each sentence cuts off the previous
  3. Edge-TTS handles multi-sentence text fine in one synthesis call
  4. The TTS_DONE signal from Rust handles lock release precisely
"""
import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple, Union
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import logger


class VoiceOutputManager:
    """
    Manages TTS generation, queuing, and playback via the Rust bridge.

    The processing flow:
      speak(text, guild_id) → _process_queue loop → tts.synthesize(text)
        → _play_audio_rust → bridge.send_tts_audio() → Rust SPEAK command
        → songbird plays audio → track ends → Rust sends TTS_DONE
        → Python releases processing lock → next utterance processed
    """

    def __init__(self, tts_engine: Any, voice_listener: Any) -> None:
        """
        Initialize Voice Output Manager.

        Args:
            tts_engine: TTSEngine instance (edge-tts or Coqui)
            voice_listener: VoiceListener instance (provides Rust bridge access)
        """
        self.tts = tts_engine
        self.voice_listener = voice_listener

        # Queue of (text, guild_id) tuples — processed one at a time
        self.sentence_queue = asyncio.Queue()

        # Current state
        self.is_speaking = False
        self.current_guild_id: Optional[int] = None

        # Interrupt event: set when user speaks during TTS playback.
        # Checked before each TTS synthesis call to avoid wasted compute.
        self.interrupt_event = asyncio.Event()

        # Background task
        self.processing_task = None
        self.is_running = False

        logger.info(" Voice output manager initialized")

    async def start(self) -> None:
        """Start the TTS processing loop."""
        if self.is_running:
            return

        self.is_running = True
        self.processing_task = asyncio.create_task(self._process_queue())
        logger.info(" Voice output manager started")

    async def stop(self) -> None:
        """Stop the TTS processing loop."""
        self.is_running = False
        if self.processing_task:
            self.processing_task.cancel()
        logger.info(" Voice output manager stopped")

    async def speak(self, text: str, guild_id: int, priority: bool = False) -> None:
        """
        Queue text to be spoken in the voice channel.

        The full response text is queued as a single item. Edge-TTS handles
        multi-sentence text in one synthesis call, producing a single WAV
        file that plays uninterrupted on the voice channel.

        NOTE: Sentence splitting is intentionally removed. Previously, the
        text was split by punctuation and each sentence was queued separately.
        This caused each sentence to be sent as a separate SPEAK command to
        Rust, and each new SPEAK would stop the previous track (songbird's
        SPEAK handler calls handle.stop() before playing). Result: sentences
        cutting each other off mid-playback.

        Args:
            text: Text to speak (full response, will be synthesized as one)
            guild_id: Guild ID to speak in
            priority: If True, stop current speech and speak this immediately
        """
        if priority:
            await self.stop_speaking(guild_id)

        if text.strip():
            await self.sentence_queue.put((text, guild_id))
            logger.debug(f" Queued: '{text[:50]}...'")

    async def stop_speaking(self, guild_id: int) -> None:
        """
        Interrupt current speech and clear queue for guild.

        Called when the user starts speaking while the bot is talking.
        Sets the interrupt event flag (checked before TTS synthesis) and
        sends an INTERRUPT command to the Rust binary (stops songbird track).
        """
        self.interrupt_event.set()

        # Stop Rust bridge TTS if active
        bridge = self.voice_listener.rust_bridge
        if bridge and bridge.is_running():
            await bridge.interrupt()

        self.is_speaking = False
        logger.info(f"Stopped speaking in guild {guild_id}")

    async def _process_queue(self) -> None:
        """
        Background loop: processes one TTS item at a time.

        For each item in the queue:
          1. Check voice connection status
          2. Check interrupt flag (skip if set — avoids wasted TTS compute)
          3. Synthesize TTS audio via edge-tts (or Coqui)
          4. Send to Rust bridge for voice channel playback
          5. Rust plays audio via songbird → sends TTS_DONE when finished
          6. Processing lock released → next utterance can be processed

        The flow is synchronous per-item: we wait for TTS synthesis + send
        before processing the next item. This is intentional — we only queue
        the full response as one item, so there's only one cycle per response.
        """
        while self.is_running:
            try:
                # Get next text item
                text, guild_id = await self.sentence_queue.get()

                self.current_guild_id = guild_id
                self.is_speaking = True
                self.interrupt_event.clear()

                # Check if Rust bridge is active
                if not self.voice_listener.is_in_voice(guild_id):
                    logger.warning(f"No voice connection for guild {guild_id}, dropping speech")
                    self.sentence_queue.task_done()
                    continue

                # Check interrupt before generating — don't waste TTS compute
                # if the user already started speaking
                if self.interrupt_event.is_set():
                    logger.info(f" Skipping synthesis — interrupted: '{text[:50]}...'")
                    self.sentence_queue.task_done()
                    continue

                # Generate TTS Audio
                logger.debug(f"Synth: '{text[:30]}...'")
                audio_data = await self.tts.synthesize(text)

                if not audio_data:
                    logger.error("TTS generation failed")
                    self.sentence_queue.task_done()
                    continue

                # Play Audio via Rust bridge
                # The TTS_DONE signal from Rust will release the processing lock.
                # Even if an interrupt arrived during synthesis, the bridge handles
                # it (INTERRUPT command stops the current track).
                if self.voice_listener.is_in_voice(guild_id):
                    await self._play_audio_rust(guild_id, audio_data)
                else:
                    logger.warning(f"No voice path available for guild {guild_id}")

                self.sentence_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in voice output loop: {e}")
                await asyncio.sleep(1)

        self.is_speaking = False

    async def _play_audio_rust(self, guild_id: int, audio_data: bytes) -> None:
        """
        Play audio through Rust bridge (songbird Driver).

        The Rust binary writes the WAV data to /tmp/serin_tts_output.wav and
        plays it via the songbird Driver. When playback finishes, the track
        end handler sends TTS_DONE to Python, which releases the processing lock.

        NOTE: This method does NOT manage the processing lock. The lock was
        already set in AudioStreamProcessor._queue_for_transcription() when
        the audio was queued. The TTS_DONE signal from Rust releases it.

        Args:
            guild_id: Guild ID
            audio_data: WAV audio bytes from TTS engine (16kHz mono 16-bit)
        """
        bridge = self.voice_listener.rust_bridge
        if not bridge or not bridge.is_running():
            logger.warning(f" Cannot play — bridge not running for guild {guild_id}")
            return

        logger.info(f" Sending {len(audio_data)} bytes to Rust bridge for playback")
        await bridge.send_tts_audio(audio_data)

    def _split_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences for batching.

        DEPRECATED: Sentence splitting was removed from speak() because it
        caused each sentence to interrupt the previous one (Rust SPEAK handler
        stops the current track before playing new audio).

        The method is kept for potential future use or external callers.
        """
        import re
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
