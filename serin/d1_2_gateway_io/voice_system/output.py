import asyncio
import importlib
from typing import Any

from serin.d1_2_gateway_io._di import get_logger


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
        self.current_guild_id: int | None = None

        # Interrupt event: set when user speaks during TTS playback.
        # Checked before each TTS synthesis call to avoid wasted compute.
        self.interrupt_event = asyncio.Event()

        # Background task
        self.processing_task = None
        self.is_running = False

        get_logger().info(" Voice output manager initialized")

    async def start(self) -> None:
        """Start the TTS processing loop."""
        if self.is_running:
            return

        self.is_running = True
        self.processing_task = asyncio.create_task(self._process_queue())
        get_logger().info(" Voice output manager started")

    async def stop(self) -> None:
        """Stop the TTS processing loop."""
        self.is_running = False
        if self.processing_task:
            self.processing_task.cancel()
        get_logger().info(" Voice output manager stopped")

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
            get_logger().debug(f" Queued: '{text[:50]}...'")

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
        get_logger().info(f"Stopped speaking in guild {guild_id}")

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
                    get_logger().warning(f"No voice connection for guild {guild_id}, dropping speech")
                    self.sentence_queue.task_done()
                    continue

                # Check interrupt before generating — don't waste TTS compute
                # if the user already started speaking
                if self.interrupt_event.is_set():
                    get_logger().info(f" Skipping synthesis — interrupted: '{text[:50]}...'")
                    self.sentence_queue.task_done()
                    continue

                # Generate TTS Audio
                get_logger().debug(f"Synth: '{text[:30]}...'")
                audio_data = await self.tts.synthesize(text)

                if not audio_data:
                    get_logger().error("TTS generation failed")
                    self.sentence_queue.task_done()
                    continue

                # Play Audio via Rust bridge
                # The TTS_DONE signal from Rust will release the processing lock.
                # Even if an interrupt arrived during synthesis, the bridge handles
                # it (INTERRUPT command stops the current track).
                if self.voice_listener.is_in_voice(guild_id):
                    await self._play_audio_rust(guild_id, audio_data)
                else:
                    get_logger().warning(f"No voice path available for guild {guild_id}")

                self.sentence_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                get_logger().error(f"Error in voice output loop: {e}")
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
            get_logger().warning(f" Cannot play — bridge not running for guild {guild_id}")
            return

        get_logger().info(f" Sending {len(audio_data)} bytes to Rust bridge for playback")
        await bridge.send_tts_audio(audio_data)

    def _split_sentences(self, text: str) -> list[str]:
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
"""
Voice Behavior Manager - Auto Join/Leave Voice Channels based on PersonalityState mood.
Bridges PersonalityState (energy/engagement/sass) with VoiceListener join/leave decisions.
Serin decides when to join VC like a human would - based on mood, who's there, time of day.

Join philosophy:
- NEVER join instantly when someone enters VC. That's bot behavior.
- Instead, log the event and after a random delay (45-90s), consider joining.
- This makes Serin feel like it's "noticing" and "deciding" to come in.
- Explicit invites to join VC are handled by the structured output pipeline (voice_action_decider.py).
"""
"""
TTS Engine - Text-to-Speech with multiple backends

Backends (tried in order):
1. edge-tts (default) - Microsoft Edge voices, free, no model download
2. Coqui XTTS v2 (optional) - local neural TTS, needs GPU

Features:
- Multiple voice profiles
- Voice cloning support (Coqui only)
- Natural prosody
"""
# Check TTS backend availability
EDGE_TTS_AVAILABLE = importlib.util.find_spec("edge_tts") is not None
COQUI_TTS_AVAILABLE = (
    importlib.util.find_spec("numpy") is not None
    and importlib.util.find_spec("torch") is not None
    and importlib.util.find_spec("TTS") is not None
)


# edge-tts voice presets by mood/style
EDGE_VOICE_PRESETS = {
    'default': 'en-US-GuyNeural',
    'energetic': 'en-US-ChristopherNeural',
    'calm': 'en-US-AriaNeural',
    'serious': 'en-US-DavisNeural',
    'friendly': 'en-US-JennyNeural',
    'fast': 'en-US-GuyNeural',
    'slow': 'en-US-AriaNeural',
}

# Edge TTS rate modifiers per profile
EDGE_RATE_MAP = {
    'default': '+0%',
    'fast': '+20%',
    'slow': '-15%',
    'calm': '-5%',
    'energetic': '+10%',
    'serious': '+0%',
    'friendly': '+5%',
}


