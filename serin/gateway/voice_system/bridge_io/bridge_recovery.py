"""Bridge crash recovery and reconnection."""

    def _handle_process_death(self) -> None:
        """Handle Rust process unexpected death — log diagnostics and trigger supervisor."""
        self.stats['errors'] += 1

        # Retry poll() a few times — OS may not have reaped the process yet
        exit_code = None
        if self.proc:
            import time
            for _ in range(10):
                self.proc.poll()
                exit_code = self.proc.returncode
                if exit_code is not None:
                    break
                time.sleep(0.05)

        if exit_code is None:
            logger.error("voice.process_died", extra={
                "exit_code": "unknown",
                "detail": "pipe closed but process not reaped",
                "guild_id": str(self._guild_id),
            })
        elif exit_code < 0:
            signal_name = {-6: "SIGABRT", -9: "SIGKILL", -11: "SIGSEGV", -13: "SIGPIPE"}.get(exit_code, f"signal {-exit_code}")
            logger.error("voice.process_killed", extra={
                "exit_code": exit_code,
                "signal": signal_name,
                "guild_id": str(self._guild_id),
            })
        else:
            logger.error("voice.process_exited", extra={
                "exit_code": exit_code,
                "guild_id": str(self._guild_id),
            })

        # Dump stderr ring buffer for diagnostics
        if self._stderr_buf:
            logger.error("voice.process_stderr", extra={
                "line_count": len(self._stderr_buf),
                "lines": "\n".join(self._stderr_buf[-20:]),
                "guild_id": str(self._guild_id),
            })

        # Signal supervisor to attempt re-spawn
        self._death_event.set()

    # -----------------------------------------------------------------------
    # Supervisor: monitors Rust process health and re-spawns on crash
    # -----------------------------------------------------------------------

    async def _supervise_rust_process(self) -> None:
        """
        Background supervisor task: waits for the Rust process to die,
        then attempts to re-spawn it with rate limiting.

        Rate limiting: max 5 restart attempts within a 60-second window.
        If the rate limit is exceeded, the supervisor gives up to avoid
        infinite crash loops.

        On successful re-spawn, calls the reconnect callback (if set) so
        the voice listener can re-attach any state.
        """
        while not self._shutdown_requested:
            await self._death_event.wait()
            if self._shutdown_requested:
                return

            # Rate limiting: check restart frequency
            now = time.monotonic()
            self._restart_timestamps.append(now)
            if len(self._restart_timestamps) >= 5:
                # 5 restarts in the deque — check if they're within 60s
                oldest = self._restart_timestamps[0]
                if now - oldest < 60.0:
                    logger.critical("voice.supervisor_giving_up", extra={
                        "restarts": len(self._restart_timestamps),
                        "window_seconds": 60,
                        "guild_id": str(self._guild_id),
                        "requires_intervention": True,
                    })
                    self.stats['errors'] += 1
                    return

            logger.warning("voice.process_restarting", extra={
                "restart_attempt": len(self._restart_timestamps),
                "guild_id": str(self._guild_id),
            })
            self.stats['restarts'] += 1
            await asyncio.sleep(2)

            # Clean up old process references
            self.proc = None
            self.reader = None
            self._running = False

            # Re-spawn using the same method that was originally used
            success = False
            guild_id = self._guild_id
            channel_id = self._channel_id
            if guild_id is None or channel_id is None:
                logger.error("Guild or channel ID missing — cannot restart")
                return
            try:
                if self._start_mode == "voice_client" and self._voice_client:
                    success = await self.start(
                        guild_id, channel_id, self._voice_client
                    )
                elif self._last_connection_info:
                    success = await self.start_with_info(
                        guild_id, channel_id, self._last_connection_info
                    )
                else:
                    logger.error("No connection info available for restart — giving up")
                    return
            except Exception as e:
                logger.exception(f"Failed to restart Rust process: {e}")

            if success:
                logger.info("Rust voice process restarted successfully")
                if self._reconnect_callback:
                    try:
                        await self._reconnect_callback()
                    except Exception as e:
                        logger.error(f"Reconnect callback failed: {e}")
                # Clear death event so supervisor waits for next death
                self._death_event.clear()
            else:
                logger.error("Failed to restart Rust process — will retry")
                # Allow retry by clearing death event and looping
                self._death_event.clear()

    def set_reconnect_callback(self, callback: Optional[Callable]) -> None:
        """
        Set a callback to be called when the Rust process is re-spawned after a crash.

        The callback should be an async callable that re-attaches any state
        needed after reconnection (e.g., the voice listener re-attaching audio streams).
        """
        self._reconnect_callback = callback

    # -----------------------------------------------------------------------
    # Internal: stderr reader (Rust tracing/diagnostics → Python logger)
    # -----------------------------------------------------------------------
    # The Rust binary writes tracing output to stderr (eprintln!/tracing).
    # We read this in a background thread and forward it to the Python logger
    # with appropriate log levels. A ring buffer of the last 200 lines is
    # kept for crash diagnostics.

    def _start_stderr_reader(self) -> None:
        """Spawn a daemon thread to read Rust stderr into a ring buffer and Python logger."""
        if not self.proc or not self.proc.stderr:
            return

        def _reader():
            try:
                import io as _io
                stderr_text = _io.TextIOWrapper(
                    self.proc.stderr,
                    encoding='utf-8',
                    errors='replace',
                    line_buffering=True,
                )
                for line in stderr_text:
                    line = line.rstrip()
                    if not line:
                        continue
                    self._stderr_buf.append(line)
                    # Route to appropriate log level based on content
                    if any(kw in line for kw in ['ERROR', 'JOIN_FAILED', 'PANIC']):
                        logger.error(f"   [rust] {line}")
                    elif any(kw in line for kw in ['CONNECTED', 'READY', 'GOT_INFO']):
                        logger.info(f"   [rust] {line}")
                    elif 'RTP' in line or 'SPEAKING' in line:
                        logger.debug(f"   [rust] {line}")
                    else:
                        logger.debug(f"   [rust] {line}")
            except Exception as e:
                logger.debug(f"   [stderr reader] exited: {e}")

        threading.Thread(target=_reader, name="rust-stderr-reader", daemon=True).start()

    # -----------------------------------------------------------------------
    # Public: update username mapping for logging
    # -----------------------------------------------------------------------

    def set_username(self, user_id: str, username: str) -> None:
        """Map a user_id to a display name for logging purposes."""
        self._usernames[user_id] = username

    # -----------------------------------------------------------------------
    # Public: send TTS audio to Rust binary for voice channel playback
    # -----------------------------------------------------------------------
