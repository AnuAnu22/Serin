"""Voice activity detection and audio queue management."""

from datetime import datetime
    def _detect_voice_activity(self, audio_data: bytes) -> bool:
        """
        Detect if audio contains voice using energy-based VAD.

        Uses RMS (Root Mean Square) energy of the PCM signal. This is a simple
        but effective VAD for conversational speech in quiet-to-moderate noise.
        The threshold (150) was chosen empirically with garbled Opus audio.

        Why not a ML-based VAD (Silero, WebRTC)?
          - Energy-based VAD is fast (no model loading/inference)
          - Works reliably with close-mic speech in quiet environments
          - With the 25-frame burst filter, brief noise misclassifications are harmless
          - Garbled audio from DAVE decode errors still has discernible energy patterns

        Args:
            audio_data: Raw PCM audio chunk (48kHz stereo 16-bit)

        Returns:
            True if the RMS energy exceeds VAD_THRESHOLD (voice detected)
        """
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
            return rms > self.VAD_THRESHOLD
        except Exception as e:
            logger.error(f" Error in VAD: {e}")
            return False

    def _queue_for_transcription(
        self,
        user_id: str,
        username: str,
        guild_id: str,
        channel_id: str
    ) -> None:
        """
        Queue audio buffer for transcription.

        This is the critical handoff point between the VAD pipeline and the
        LLM/response pipeline. It:
          1. Takes the accumulated audio buffer for the user
          2. Validates minimum length (1 second = 192KB at 48kHz stereo 16-bit)
          3. Sets the processing lock to prevent cascading response cycles
          4. Puts the audio data on the async processing queue

        The processing lock is the key to preventing cascading:
          - Set here (30s safety net) when audio is queued
          - Released early by TTS_DONE signal from Rust when playback finishes
          - During the lock: audio is silently buffered but not processed

        Args:
            user_id: User ID string
            username: Username (for logging and context)
            guild_id: Guild ID string
            channel_id: Voice channel ID string
        """
        try:
            buffer = self.user_buffers.get(user_id)

            # Minimum buffer check: 192KB ≈ 1 second of audio.
            # Anything shorter is likely a noise burst, pop, or accidental mic activation.
            # This prevents the bot from responding to brief sounds.
            # Formula: 48000 samples/s × 2ch × 2bytes × 1.0s = 192,000 bytes
            if not buffer or len(buffer) < 192000:
                logger.debug(f" Skipping empty/short buffer for {username}")
                if user_id in self.user_buffers:
                    self.user_buffers[user_id] = bytearray()
                return

            # Copy the buffer and clear it for the next utterance.
            audio_data = bytes(buffer)
            self.user_buffers[user_id] = bytearray()

            # ── Processing Lock ─────────────────────────────────────────────
            # Set the processing lock for this guild. While the lock is active:
            #   - All new audio chunks are silently appended to user buffers
            #   - No VAD, silence counting, or timer scheduling occurs
            #   - The interrupt path is not triggered
            #   - The lock is released when TTS_DONE is received from Rust
            #
            # The 30-second duration is a safety net only. In normal operation,
            # TTS_DONE releases the lock within 3-15 seconds (LLM + TTS time).
            # If TTS_DONE never arrives (Rust crash), the lock auto-expires
            # after 30 seconds to prevent permanent lockout.
            self._set_lock(guild_id, 30.0)

            # Queue for async processing (one at a time).
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
                logger.debug(f" Queued {len(audio_data)} bytes for transcription: {username}")

            except asyncio.QueueFull:
                logger.warning(f" Transcription queue full, dropping audio from {username}")

        except Exception as e:
            logger.error(f" Error queueing transcription: {e}")
            self.stats['errors'] += 1

    def _cancel_silence_timer(self, user_id: str) -> None:
        """Cancel pending silence timer for a user (audio arrived, user is still active)."""
        task = self._silence_timers.pop(user_id, None)
        if task is not None and not task.done():
            task.cancel()

    def _schedule_silence_timer(
        self,
        user_id: str,
        username: str,
        guild_id: str,
        channel_id: str
    ) -> None:
        """
        Schedule a timer to force transcription after silence_threshold of no audio chunks.

        This is a fallback mechanism for when the Rust bridge stops sending chunks
        entirely (e.g., the user stopped talking and Discord stopped transmitting).
        The primary silence detection (frame-based counter in process_audio_chunk)
        handles the case where silence chunks keep arriving.

        The timer is cancelled and rescheduled on every chunk. If the timer fires,
        it means no chunks arrived for the full silence window. The buffer is then
        queued for transcription.

        The guard `if user_id in self.currently_speaking` prevents the timer from
        firing for users who were never detected as speaking (prevents processing
        of empty/background buffers).
        """
        async def _timer() -> None:
            await asyncio.sleep(self.silence_threshold)
            # Check if user still has buffered audio and was detected as speaking
            if user_id in self.user_buffers and len(self.user_buffers[user_id]) > 0:
                if user_id in self.currently_speaking:
                    logger.debug(f"[DBG-VAD] Silence timer fired for {username} ({len(self.user_buffers[user_id])}B) — queueing transcription")
                    self._queue_for_transcription(
                        user_id=user_id,
                        username=username,
                        guild_id=guild_id,
                        channel_id=channel_id
                    )
                    self.currently_speaking.discard(user_id)
        try:
            loop = asyncio.get_running_loop()
            self._silence_timers[user_id] = loop.create_task(_timer())
        except (RuntimeError, ValueError) as e:
            logger.debug(f"Could not schedule silence timer: {e}")

    def _is_locked(self, guild_id: str) -> bool:
        """
        Check if guild is in a processing lock window.

        The lock is a simple time-based check:
          expire = self._processing_lock_until[guild_id]
          if time.time() < expire → locked
          else → unlocked (and entry cleaned up)

        Returns:
            True if the guild is currently locked (new speech should be buffered silently)
        """
        expire = self._processing_lock_until.get(guild_id, 0)
        if time.time() < expire:
            return True
        # Clean expired locks to prevent unbounded dict growth
        self._processing_lock_until.pop(guild_id, None)
        return False

    def _release_lock(self, guild_id: str) -> None:
        """
        Release processing lock for guild — allow new speech to be processed.

        Called by TTS_DONE handler when the Rust binary signals that TTS playback
        has finished. This allows the next user utterance to trigger transcription.

        If there's no lock for this guild (already expired or never set), this is a no-op.
        """
        self._processing_lock_until.pop(guild_id, None)
        logger.debug(f" Processing lock released for guild {guild_id}")

    def _set_lock(self, guild_id: str, duration: float = 20.0) -> None:
        """
        Set processing lock for guild — new speech during the response cycle is buffered silently.

        The lock duration should be long enough to cover:
          - LLM generation time (typically 3-8 seconds)
          - TTS synthesis time (typically 0.5-3 seconds)
          - TTS playback time (typically 1-10 seconds)

        In normal operation, the lock is released early by the TTS_DONE signal,
        so the duration is a safety net. If TTS_DONE never arrives (Rust crash),
        the lock auto-expires after the duration.

        Args:
            guild_id: Guild ID string
            duration: Lock duration in seconds (default 20.0, overridden to 30.0 in _queue_for_transcription)
        """
        self._processing_lock_until[guild_id] = time.time() + duration
        logger.debug(f" Processing lock set for guild {guild_id} ({duration}s)")

    async def _process_queue(self) -> None:
        """Background task to process transcription queue — one item at a time."""
        logger.info(" Started transcription queue processor")

        while self.is_running:
            try:
                # Wait up to 1 second for the next transcription item.
                # The timeout allows the loop to check self.is_running periodically.
                try:
                    item = await asyncio.wait_for(
                        self.processing_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Transcribe and store the result (sends to LLM or Whisper, triggers response)
                await self._transcribe_and_store(item)

                self.stats['chunks_processed'] += 1

            except asyncio.CancelledError:
                logger.info(" Transcription queue processor cancelled")
                break
            except Exception as e:
                logger.error(f" Error in transcription queue: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(0.5)

        logger.info(" Transcription queue processor stopped")
