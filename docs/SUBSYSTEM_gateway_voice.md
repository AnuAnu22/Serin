# SUBSYSTEM: gateway_voice — voice input (Rust) + TTS output (d1_2 d2_2)

Checklist: 18/18 files read (PLAN said 17 — corrected, there are 18). Status: DRAFT (wip).
Finalize name: `SUBSYSTEM_gateway_voice.md`.

Root: `serin/d1_2_gateway_io/d2_2_voice_system/`

## Scope & role in the system

The **voice side of the gateway**: the production Rust-voice bridge, per-user audio intake with VAD,
and TTS voice output. After the gateway (Subsystem 9) assembles the voice stack, this subsystem is what
actually *hears* and *speaks*.

Two independent anchors in one subsystem:

1. **`d3_2_bridge_io/`** — the **Python↔Rust subprocess seam** (CONNECTIONS J / the voice wire protocol
   documented in `docs/wiki/python-rust-voice-protocol.md`). Spawns and supervises the Rust
   `voice_receiver` binary; bridges PCM audio intake and TTS playback across a stdin/stdout line+binary
   protocol.
2. **`d3_1_system_audio/` + `d3_3_system_listener.py` + `d3_4_system_output.py` + `d3_5_tts_engine.py`** —
   per-user VAD buffering → transcription, the `VoiceListener` (VC join/leave via py-cord
   `InfoCaptureProtocol`), `VoiceBehaviorManager` (personality-driven auto join/leave), `VoiceOutputManager`
   (TTS queueing + playback), and `TTSEngine` (edge-tts / Coqui).

**The critical structural fact:** the `AudioStreamProcessor` is a **delegating façade** — its constructor
holds all state, but nearly every method lazy-imports its real implementation from split sibling modules
(`d4_3_audio_utils.py`, `d4_4_audio_vad.py`, `d4_2_audio_transcribe.py`) via function-return shims.
Splitting a big class across files (Rule 2), but *across module boundaries* rather than a folder package.

## Files

### d3_2_bridge_io — the Rust subprocess seam  ⭐
The **only production Python↔Rust voice seam.** `discord.py` joins the VC (py-cord) but **Rust owns all
voice transport** (UDP, voice websocket, decode) — avoiding a dual-gateway conflict (only one gateway
connection per bot token). Wire protocol (stdin/stdout, line-oriented commands + raw binary payloads):

- **stdin (Python→Rust):** line 1 = JSON `ConnectionInfo {endpoint, token, session_id, guild_id, channel_id, user_id}`;
  then `SPEAK:{pcm_len}\n` + WAV bytes; `INTERRUPT\n`; `SHUTDOWN\n`.
- **stdout (Rust→Python):** `AUDIO:{user_id}:{pcm_len}\n` + raw decoded PCM; `JOIN:{user_id}\n`;
  `LEAVE:{user_id}\n`; `TTS_DONE\n` (sent on songbird `TrackEvent::End`); anything else → Rust log line.

**`d4_1_io_bridge.py` (159 lines)** — `RustStdoutReader`: async task reading the stdout protocol, parsing
lines with binary payloads (`AUDIO:` reads `pcm_len` raw bytes), pushing `(type, *args)` tuples onto an
`asyncio.Queue` (also `_EOF` sentinel on pipe close). Ends with the `RustVoiceBridge` class docstring —
the class itself lives in `d4_4_process_watch/d5_1_process_watch.py`.

**`d4_2_bridge_commands.py`** — module-level fns operating on an instance passed as `self`
(they're imported + called directly, not methods):
- `send_tts_audio` → `SPEAK:{len}\n` + bytes; `interrupt` → `INTERRUPT\n`;
- `_write_stdin` — **thread-safe**: wraps all stdin writes in `self._stdin_lock` (threading.Lock) to prevent
  protocol framing corruption between SPEAK/interrupt.
- `start_with_info(guild_id, channel_id, connection_info)` — spawns the binary via
  `asyncio.create_subprocess_exec`, writes ConnectionInfo JSON on line 1, wires `RustStdoutReader` +
  `_read_loop` + `_supervisor_task` + `_start_stderr_reader()`. Uses a `connection_info` start mode &
  requires `self.binary_path` exists (else "Build with: cd voice/rust_receiver && cargo build --release").
- `is_running`, `get_stats`.

**`d4_3_bridge_recovery.py` — DEAD CODE (zero importers).** Defines the *sophisticated* crash story:
`_handle_process_death` (exit-code/signal diagnostics + stderr ring-buffer dump via `voice.process_died`/
`process_killed`/`process_exited`), `_supervise_rust_process` (**rate-limited**: max 5 restart attempts
within a 60s window, then gives up; re-spawns via `start`/`start_with_info`, calls `_reconnect_callback`),
`set_reconnect_callback`, and a **thread-based** `_start_stderr_reader` (daemon thread, 200-line ring
buffer, keyword-based log-level routing). **Nothing imports this module** — the class's own
`_supervise_rust_process`/`_handle_process_death` (in `d5_1_process_watch.py`) and the *async*
`_start_stderr_reader` (in `d5_2_process_watch_io.py` mixin) supersede it. A Phase-4 cleanup candidate: the
rate-limiter + reconnect-callback machinery exists here but is never reached.

**`d4_4_process_watch/`** — the real bridge class:
- **`d5_1_process_watch.py` — `RustVoiceBridge(RustVoiceBridgeIOMixin)`** ⭐ — the class. `__init__`
  (audio_processor, voice_listener, binary_path→`voice/rust_receiver/target/release/voice_receiver`),
  holds `proc`/`reader`, `_stdin_lock` (threading.Lock), supervisor state (`_death_event`, restart deque),
  `_usernames`/`_ssrc_by_member_id` (SSRC↔Discord-member mapping), `_stderr_buf` ring buffer, `stats`
  (audio_chunks/joins/leaves/restarts/errors). `start()` spawns the bin + writes ConnectionInfo + wires
  the reader/supervisor/stderr; `stop()` cancels tasks, terminates (kill on timeout) the proc;
  **`_supervise_rust_process()` is trivial** (just `await self._death_event.wait()`; the real respawn
  logic in d4_3 is unbound); `_handle_audio` routes decoded PCM →
  `audio_processor.process_audio_chunk`; `_handle_join`/`_handle_leave` manage SSRC↔member mapping and
  free member slots on leave; `_resolve_username_from_vc` maps an SSRC to a display name by walking VC
  members; `_handle_tts_done` → `audio_processor._release_lock` + `._flush_buffered_audio`;
  `_handle_process_death` (simple) sets `_death_event`.
- **`d5_2_process_watch_io.py` — `RustVoiceBridgeIOMixin`** — I/O methods kept under the 500-line file
  cap (per header comment). Declares the attrs/handlers; provides `_start_stderr_reader` (**async task**
  reading `proc.stderr` line-by-line into `_stderr_buf` + `get_logger().debug(" [rust:err] …")`),
  `_extract_voice_info` (pulls endpoint/token/session_id from a py-cord `VoiceClient`, falling back to
  `_connection` introspection), and `_read_loop` (async-iterates reader events → dispatch `_handle_audio`/
  `_handle_join`/`_handle_leave`/`_handle_tts_done`).

### d3_1_system_audio — per-user intake  ⭐
**`d4_1_audio_process/d5_1_audio_processor.py` — `AudioStreamProcessor`** (the delegating façade ⭐).
Constructor holds ALL state: per-user raw-PCM `user_buffers` (48kHz stereo 16-bit), per-user
`user_silence_frames`/`user_voice_burst`, per-user `_silence_timers` (fallback when Rust stops sending),
per-guild `_processing_lock_until` (prevents cascading response cycles, keyed by guild), `currently_speaking`
set (interrupt detection), `processing_queue` (maxsize=50), `supports_audio` (`config.LLM_SUPPORTS_AUDIO`).
Constants: `VAD_AMPLITUDE_THRESHOLD=150`, `MAX_BUFFER_BYTES_GEMMA=30s`/`_WHISPER=260s`. The **public API
delegates**: `process_audio_chunk`→utils, `_detect_voice_activity`/`_queue_for_transcription`/
`_is_locked`/`_release_lock`/`_flush_buffered_audio`/`_set_lock`/`_cancel_silence_timer`/
`_schedule_silence_timer`/`_process_queue`→vad, `_transcribe_and_store`/`check_interrupt`/
`get_active_speakers`/`get_buffer_size`/`get_stats`→transcribe, `start`/`stop`/`_pcm_to_wav_base64`/
`_transcribe_with_gemma`→utils. Constructed with `(transcriber, voice_pipeline, silence_threshold,
voice_output_manager, llm_connector)`.

**`d4_4_audio_vad.py`** — VAD + queue state (the work). `_detect_voice_activity` = RMS-energy VAD
(`np.frombuffer` int16 → sqrt(mean(sq))), threshold 150, justified vs ML VADs (fast, no model, robust to
garbled Opus). `_queue_for_transcription`: lock-guarded; min-buffer 192KB (~1s); copies+clears buffer; sets
**300s processing lock** (safety net; TTS_DONE releases early); enqueues `{user_id,username,guild_id,
channel_id,audio_data,timestamp}`. `_cancel_silence_timer`/`_schedule_silence_timer` (fallback async timer,
guarded by `currently_speaking`). `_is_locked`/`_release_lock` (time-based, cleans expired)/
`_flush_buffered_audio` (post-release flush of best buffered user)/`_set_lock`. `_process_queue` = async
background loop, one item at a time (1s timeout to poll `is_running`), error-throttled.

**`d4_3_audio_utils.py`** — `process_audio_chunk` (the main per-chunk entry): lock-guard (silently buffer +
record `_last_username`/`_last_channel`); VAD classify; **always buffers** (voice+silence); voice handling
(burst counter resets silence only at ≥25 frames=0.5s, buffer-overflow forces transcription, first-voice
adds to `currently_speaking` + **interrupts bot** via `voice_output_manager.stop_speaking`); silence
handling (≥`SILENCE_FRAMES_THRESHOLD` → queue); then reschedules fallback silence timer. `_pcm_to_wav_base64`
(48kHz stereo→16kHz mono WAV b64 via numpy). `_transcribe_with_gemma` (30s-silence-truncate, WAV b64,
`input_audio` + "Transcribe exactly what {username} said", temp=0, 300 tok). `start`/`stop` (spawn/cancel
`_process_queue` task).

**`d4_2_audio_transcribe.py`** — `_transcribe_and_store` (end-to-end per item): **Gemma direct-audio path**
(if `llm_connector` + `supports_audio` + model_type contains 'gemma'): builds clean voice context
(`build_voice_system_prompt()` from serin_di + recent voice history via `voice_pipeline.get_recent_context`
+ "you are speaking in a voice channel; keep concise" + `input_audio` user turn), calls
`llm_connector.chat_completion` (temp=1.0, top_p=0.95, `enable_thinking:False`), then
`voice_output_manager.speak(response, guild_id)`; logs prompt with `<N bytes>` placeholder. Falls through to
**Whisper STT path**: `transcriber.transcribe(audio_data, 'en')` → `voice_pipeline.process_voice_message(...)`.
`check_interrupt` (user in `currently_speaking`), `get_active_speakers`, `get_buffer_size`, `get_stats`.

**`d5_2_voice_behavior.py` — `VoiceBehaviorManager`** ⭐ (the *canonical* copy — see CONNECTIONS note).
Personality-driven auto join/leave using **`PersonalityState`** (`energy_level`, `sass_level`, engagement)
from the message manager + `VoiceTracker` awareness. Consumes `_rand`/`_uniform` (secrets-based) from
`d5_1_audio_processor`. `on_user_joined_vc` records a **delayed** consideration (45–90s `_uniform`);
`_behavior_check_loop` (every 15s) → `_evaluate_pending_joins` (chance scaled by `personality.energy_level`
0.03–0.25 × evening boost × `join_aggressiveness*2`, cap 0.5; joins via `voice_listener.join_channel`) +
`_check_leave_conditions` (silence>`leave_after_silence_seconds`, session>`max_session_minutes`, energy<0.25;
50% random leave). `get_settings`/`update_settings` (API-exposed), `get_stats`. Explicit join/leave requests
go through `voice_action_decider.py` (structured output, elsewhere). **Cross-subsystem:** reads
`personality.energy_level` → a CONNECTIONS G-adjacent touchpoint (dynamics affect reaches the voice layer).

### d3_3_system_listener.py — VoiceListener + InfoCaptureProtocol  ⭐
**`InfoCaptureProtocol(discord.voice._types.VoiceProtocol)`** — py-cord VoiceProtocol that **captures
ConnectionInfo from gateway events WITHOUT any voice transport** (no UDP, no voice websocket, no DAVE —
imported from `discord.voice._types` to avoid py-cord[voice] deps). `connect()` → `change_voice_state`
then waits for `on_voice_server_update` (endpoint/token) + `on_voice_state_update` (session_id);
`get_info()` returns the ConnectionInfo dict for the Rust songbird driver. So py-cord only does the VC
*gateway* handshake; Rust does the voice UDP.
**`VoiceListener`** — owns `rust_bridge` + `_protocol`. `join_channel` (guarded by `_join_in_progress`) →
`channel.connect(cls=InfoCaptureProtocol)` → `protocol.get_info()` → constructs `RustVoiceBridge` and
`start(guild_id, channel_id, connection_info=info)`; `leave_channel` (stops bridge + disconnects);
`leave_all_channels`; `is_in_voice`/`is_connected`; `get_status`/`get_stats` (expose VC member info +
`rust_bridge_active`). The module docstring notes Phase 2 (future): a Rust gateway shard eliminates py-cord
from voice entirely.

### d3_4_system_output.py — VoiceOutputManager + shared TTS constants
**`VoiceOutputManager`** ⭐ — TTS queueing + playback via the Rust bridge. `speak(text, guild_id, priority)`:
full response queued as ONE item (sentence splitting intentionally removed — each sentence used to be a
separate SPEAK which cut off the previous track). `stop_speaking` (sets `interrupt_event`, sends
`INTERRUPT` to the bridge). `_process_queue` (background loop): checks voice connection, checks interrupt
before synthesis, `tts.synthesize(text)` → `_play_audio_rust` → `bridge.send_tts_audio()`. `_play_audio_rust`
sends WAV bytes via `d4_2_bridge_commands.send_tts_audio` to Rust → songbird plays → `TTS_DONE` →
`audio_processor` lock released. `_split_sentences` kept but **DEPRECATED**. Also declares the shared
TTS constants (`EDGE_TTS_AVAILABLE`, `COQUI_TTS_AVAILABLE`, `EDGE_VOICE_PRESETS` voice-per-mood map,
`EDGE_RATE_MAP`) imported by `d3_5_tts_engine.py`. **The bottom of this file has leftover `VoiceBehavior
Manager`/`TTS Engine` class-shaped docstrings — residue from a split: the real `VoiceBehaviorManager` is
`d5_2_voice_behavior.py` and `TTSEngine` is `d3_5_tts_engine.py`.**

### d3_5_tts_engine.py — TTSEngine (canonical)
`TTSEngine` — imports the shared presets/rates from `d3_4_system_output`. Backends: **edge-tts** (default,
cloud, no model) or **Coqui XTTS v2** (optional, GPU). `synthesize(text, profile, speaker, language)` →
edge (`_synthesize_edge`: edge-tts stream → MP3 → **ffmpeg subprocess** `_mp3_to_wav` to 16kHz mono WAV —
an additional subprocess seam) or Coqui (`_synthesize_coqui`: `asyncio.to_thread` XTTS → float32 → int16
WAV via `wave`). `load_model`, `set_voice_reference`/`clear_voice_reference` (Coqui cloning),
`set_profile`, `get_available_speakers`, `get_stats`.

## The voice data flow (end-to-end)

```
Rust voice_receiver  connects to Discord voice UDP (songbird driver)
   │ decoded PCM over stdout (AUDIO:{user_id}:{len}\n + bytes)
   ▼
RustStdoutReader.read_loop  →  RustVoiceBridge._read_loop  →  _handle_audio
   ▼
AudioStreamProcessor.process_audio_chunk   (VAD/buffer per user, per guild lock)
   │ silence 1.5s / buffer overflow → _queue_for_transcription (sets 300s lock)
   ▼
_process_queue  →  _transcribe_and_store
   ├─ (Gemma direct audio)  LLM chat  →  VoiceOutputManager.speak
   └─ (else Whisper)  WhisperTranscriber → VoiceMemoryPipeline.process_voice_message (→ may respond)
   ▼
VoiceOutputManager._process_queue  →  TTSEngine.synthesize  →  ffmpeg(edge) / coqui
   ▼
_play_audio_rust  →  send_tts_audio  →  Rust SPEAK → songbird plays
   ▼  TTS_DONE over stdin/stdout
RustVoiceBridge._handle_tts_done  →  AudioStreamProcessor._release_lock + _flush_buffered_audio
```

## Cross-cutting / notable findings (see CONNECTIONS.md / J)

1. **CONNECTIONS J / the production Rust seam is HERE.** Py-cord does only the VC *gateway* handshake
   (`InfoCaptureProtocol`), and **Rust `voice_receiver` owns all voice transport** (UDP + decode + songbird
   playback) to avoid a dual-gateway conflict. The exact wire protocol is in
   `docs/wiki/python-rust-voice-protocol.md`. This is separate from the PyO3 `serin_core` seam (Subsystem 13).
2. **`d4_3_bridge_recovery.py` is DEAD code** — **zero importers**. Its full crash-recovery (rate-limited
   restart ≤5/60s + reconnect callback + threaded stderr ring buffer) is unreached; the class uses the
   trivial inline `_supervise_rust_process` + async `_start_stderr_reader` (mixin). Phase-4 cleanup candidate
   (would need to *wire* the recovery, not just delete it — the ring-buffer diagnostics are valuable).
3. **`AudioStreamProcessor` is a delegating façade** — all state in the class, real logic lazy-imported from
   `audio_vad`/`audio_utils`/`audio_transcribe` siblings via function-returning shims. A class split across
   module boundaries (Rule 2 style, but not a folder package). Consumers must know the private methods are
   reachable on the instance (e.g. `bridge._release_lock`).
4. **Dual transcription paths** (mirrors Subsystem 8's two-sentiment-tool issue): direct **Gemma
   `input_audio`** vs **Whisper STT**; gate is `config.LLM_SUPPORTS_AUDIO` + `model_type` contains 'gemma'
   (with a fall-through to Whisper on LLM failure/empty response).
5. **Interrupt model:** user starts speaking → `currently_speaking` → `stop_speaking` (INTERRUPT to Rust,
   `interrupt_event` checked before synthesis to skip wasted compute); guild-level processing lock (300s
   safety net) released early by `TTS_DONE`.
6. **Personality → voice (CONNECTIONS G / B-adjacent):** `VoiceBehaviorManager` reads
   `personality.energy_level` (PersonalityState from the message manager, Subsystem 6) to gate auto-join
   probability — dynamics/affect state reaches the voice gateway. Also consumed by the voice routes/panel
   (Subsystem 12).
7. **Split-class by file count:** ex-professional Split-Class chain (`d5_1_process_watch` class +
   `d5_2_process_watch_io` mixin; `AudioStreamProcessor` + 3 sibling modules) is a deliberate
   <500-line-per-file rule (Rule 2) applied *across* modules.
8. **Two stderr readers exist** (async-task in mixin, thread+ring-buffer in dead d4_3); the *threaded* one
   with richer log-level routing is the more capable but is the dead one.

## What's NOT here
- The Whisper STT / voice-memory pipeline (`d1_2 d2_3 voice_transcribe`, Subsystem 11) — `VoiceMemoryPipeline`
  and `WhisperTranscriber` are *consumed* here (transcribe path) and imported by the gateway's `voice_available`.
- The gateway/startup assembly (Subsystem 9) — the voice stack is *constructed* by `PipelineInitializer`.
- The `serin_di` voice factory (`build_voice_system_prompt`) — defined in Subsystem 4, consumed here.
- The control-panel voice routes + `TTSVoiceManager` re-export (Subsystem 12) — `TTSVoiceManager` imported
  in the gateway init and `d1_5_ops_tooling/d2_5_voice_manager.py` wraps TTSEngine.
- The Rust receiver itself (`voice/rust_receiver/src/main.rs`, Subsystem 13) — adjacent, not Python.