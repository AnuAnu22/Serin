# SUBSYSTEM: gateway_transcribe — voice STT + voice memory + voice profiles (d1_2 d2_3)

Checklist: 7/7 files read (PLAN said 9 — corrected, there are 7 files). Status: DRAFT (wip).
Finalize name: `SUBSYSTEM_gateway_transcribe.md`.

Root: `serin/d1_2_gateway_io/d2_3_voice_transcribe/`

## Scope & role in the system

The upstream/downstream half of the voice pipeline on top of Subsystem 10's intake: **speech-to-text**
(`WhisperTranscriber`, faster-whisper), **voice memory** (`VoiceMemoryPipeline`, storing transcriptions +
routing to the legacy voice-response path), **voice chat awareness** (`VoiceTracker`, `VoiceActionDecider`),
and **TTS voice profiles** (`VoiceProfileManager`). For the *Gemma direct-audio* path in Subsystem 10
(`_transcribe_and_store`), this subsystem is largely bypassed; for the *Whisper STT* path it's the brain.

Four files of substance + two empty/package `__init__`s + one `d3_1_transcribe_models/` package:

1. **`d3_4_transcribe_transcriber.py` — `WhisperTranscriber`** — local faster-whisper STT (the actual
   `transcribe()` used by Subsystem-10 fallback; consumed by gateway `_init_voice_system`).
2. **`d3_3_transcribe_pipeline.py` — `VoiceMemoryPipeline`** — stores transcriptions as `[Voice]` memories,
   queues them to the background processor, and **calls back into the legacy ingest path**
   (`serin_di.process_voice_input` → d1_1 message_process) to generate a voice response.
3. **`d3_2_transcribe_decider.py` — `VoiceActionDecider`** — structured-output LLM decide join/leave/none.
4. **`d3_1_transcribe_models/`** — `d4_2_models_tracker.py` (`VoiceTracker`).
   (`d4_1_models_profiles.py` — the dead `VoiceProfileManager` duplicate — was deleted 2026-08-26;
   canonical profiles live in `d1_3_state_core/d2_4_core_voice/d3_3_voice_profiles.py`.)

## Files

### d3_4_transcribe_transcriber.py — WhisperTranscriber  ⭐
**`WhisperTranscriber(model_size="base", device="cuda", compute_type="float16")`** — local faster-whisper.
Module-level `WHISPER_AVAILABLE` computed from a guarded `from faster_whisper import WhisperModel`
(ImportError → warning "pip install faster-whisper"). `load_model()` async-loads via `asyncio.to_thread`.
`transcribe(audio_data, language="en")` — the core STT: converts Discord PCM (48kHz stereo 16-bit) → numpy
int16 → mono (left channel via `[::2]`) → resample 48k→16k (linear `np.interp`) → float32 `/32768` →
`asyncio.to_thread(model.transcribe, …, beam_size=5, vad_filter=True, vad_parameters={threshold:0.5,
min_silence_duration_ms:500})` → concatenates segment text. `_resample_audio` (linear interpolation).
`get_stats`. **This is the transcribe() that Subsystem-10's `_transcribe_and_store` calls in the Whisper
fallback path** — the d1_2 d2_2→d2_3 transcribe handoff.

### d3_3_transcribe_pipeline.py — VoiceMemoryPipeline  ⭐
**`VoiceMemoryPipeline(memory_system, background_processor, message_manager=None)`** — integrates voice
transcriptions into memory. `process_voice_message(user_id, username, guild_id, channel_id, transcription,
timestamp)`:
1. updates user profile (`memory.upsert_user`, `update_user_activity`);
2. strip/skip empty (<3 chars) or placeholder transcriptions (`[voice input]`, "no speech detected");
3. stores as a **`[Voice]`-prefixed memory** (`importance=0.7`);
4. appends to `recent_voice_messages[channel_id]` (last 10) — **this is the context
   `get_recent_context(channel_id, limit=5)` returns**, used by Subsystem-10's Gemma direct-audio path;
5. `bg_processor.queue_message(...)` → background processing;
6. **response generation by calling back into `serin_di.get_message_manager()` + `serin_di.process_voice_input`
   (→ d1_1 `d4_5_message_process.process_voice_input`)**, the legacy voice-response path (Subsystem 8).

**Important:** for the **Gemma direct-audio** path in Subsystem 10, `_transcribe_and_store` bypasses
`process_voice_message` entirely (per its docstring). This pipeline is the **Whisper-only** downstream.

### d3_2_transcribe_decider.py — VoiceActionDecider
**`VoiceActionDecider(model_connector)`** — decides `{"action": "join"|"leave"|"none", "reason"}`.
`decide(user_message, context, personality_state)` — **fast-path heuristic** `_has_voice_intent`
(voice keywords: "vc", "voice", "join", "leave", "come", "talk", …) skips the LLM call; else LLM
`send_input` with a structured JSON prompt (temperature 0.1, 200 tok) embedding `PersonalityState`
energy/sass; `_parse_decision` salvages JSON (regex `\{.*?\}` first, then close-unclosed-string + wrap-in-braces
fallback). `_build_prompt` includes CONTEXT / USER MESSAGE / energy+sass / output-format rules.

### d3_1_transcribe_models/ — voice profiles (DEAD) + voice tracker
**`d4_1_models_profiles.py` — `VoiceProfileManager` + `VoiceProfile` — DEAD/duplicate.** ⭐
A complete voice-profile manager (default/casual/energetic/calm/sarcastic/serious/excited/tired presets with
speed/temperature/length_penalty/repetition_penalty; `create_custom_profile`, `set_active`,
`get_profile_for_mood` mood→profile map, `get_stats`, module singletons `get_profile_manager`/
`get_voice_profiles`/`get_active_profile_name`/`create_profile`/`set_active_profile`/`delete_profile`).
**HAS ZERO importers anywhere in serin/tests.** The panel (d1_5 `d4_1_panel_control`, `d6_2_missing_routes_voice`)
imports `get_voice_profiles` from the **d1_3 canonical copy** `d1_3_state_core/d2_4_core_voice/d3_3_voice_profiles.py`
instead. → A **CONNECTIONS-H-style duplicate** (this d2_3 copy is the dead one). Phase-4 dedup candidate.

**`d4_2_models_tracker.py` — `VoiceTracker`** ⭐ (live elsewhere). Tracks VC activity, storing joins/leaves/
switches **as memories** (`importance` 0.3–0.6 by session duration; durations <5m=0.3 … >120m=0.6). Per-user
`current_voice_states`/`session_start_times`; `on_voice_update(member, before, after)` (join/leave/switch +
mute/deaf debug logging), `is_in_voice`, `get_voice_info`, `get_all_in_voice`, `get_voice_duration`, `get_stats`.
Also exposes natural-reaction helpers `get_voice_join_reaction` (30% chance) / `get_voice_duration_reaction`
(>30 min, 40% chance) with `VOICE_JOIN_REACTIONS`/`VOICE_LONG_SESSION_REACTIONS` templates. **LIVE consumers:
d1_1 `d4_4_core_manager:136-138` (`self.voice_tracker = VoiceTracker(self.memory)`) and the gateway
`on_voice_state_update` (Subsystem 9) calls `voice_tracker.on_voice_update`** — so this "transcribe models"
file feeds the ingest core's voice awareness + `VoiceBehaviorManager.get_voice_info` (Subsystem 10).

`__init__.py` (voice_transcribe) — empty; `d3_1_transcribe_models/__init__.py` — "intentionally empty".

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **`d4_1_models_profiles.py` (`VoiceProfileManager`) is DEAD code — zero importers.** Its canonical twin is
   `d1_3_state_core/d2_4_core_voice/d3_3_voice_profiles.py` (imported by the d1_5 control panel routes).
   A CONNECTIONS-H-style **duplicate**: the d2_3 copy is un-referenced. Phase-4 dedup candidate.
2. **Voice response re-enters the legacy ingest path.** `VoiceMemoryPipeline.process_voice_message` calls
   `serin_di.get_message_manager()` + `serin_di.process_voice_input()` → d1_1 `d4_5_message_process.process_voice_input`
   (the Subsystem-8 legacy/self-bound batch function). So the voice flow (voice → memory → response) *also*
   funnels through the older text-message_response route, not the Subsystem-7 act pipeline. CONNECTIONS I/J
   edge worth noting: `serin_di.process_voice_input` is the composition-root bridge.
3. **Two STT paths coexist** (mirrors Subsystem-8 two-sentiment, Subsystem-10 dual-transcription): Gemma
   direct-audio (Subsystem 10) bypasses Whisper; **Whisper STT is the fallback** and its transcription feeds
   `VoiceMemoryPipeline.process_voice_message`. So this subsystem's pipeline is only reached in the non-Gemma
   / non-direct-audio case.
4. **`VoiceTracker` lives in the "transcribe models" package but is the cross-subsystem voice-awareness
   object**: constructed by d1_1 ingest `core_manager`, fed by the gateway `on_voice_state_update`, and read by
   d1_2 `VoiceBehaviorManager`. A real d1_2↔d1_1 shared-data touchpoint (CONNECTIONS J-adjacent).
5. **`VoiceActionDecider` is also wired at the ingest core** (`d4_4_core_manager:188-193` constructs it with a
   `va_connector` for structured voice-action output) — complementing/doubling `VoiceBehaviorManager`'s
   probabilistic auto-join in Subsystem 10. Two voice-action mechanisms (structured LLM vs heuristic) coexist.
6. **Placeholder/empty transcription guards** in `process_voice_message` expect Whisper placeholder strings
   ("[voice input]", "no speech detected") — a coupling to the transcriber's output conventions.
7. **`WhisperTranscriber` is the gateway's `voice_available` dependency** — imported by `d3_2_discord_bot` in
   the try/except `voice_available` block and instantiated by `PipelineInitializer._init_voice_system`.

## What's NOT here
- The Rust bridge voice *intake* (d1_2 d2_2, Subsystem 10) — feeds `WhisperTranscriber.transcribe()` from here.
- The response-LLM / structured output pipeline (Subsystem 6/7) — `VoiceActionDecider` uses `model_connector`;
  `process_voice_input` bridges to d1_1 ingest (Subsystem 8), not the act pipeline.
- The control-panel voice routes (d1_5, Subsystem 12) — consume the *canonical d1_3* voice profiles, and
  `TTSVoiceManager` (d1_5) wraps the Subsystem-10 TTS engine.
- The canonical `VoiceProfileManager` — it's in d1_3 `core_voice` (Subsystem 3's subtree), not here.