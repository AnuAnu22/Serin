# Serin Architecture (LIVING DOCUMENT)

## System Overview

Serin is a Discord AI companion that processes text and voice messages through a 10-stage message pipeline, backed by Qdrant vector search + SQLite for persistent memory, and an OpenAI-compatible LLM backend (llama-swap/vLLM). Voice transport uses a Rust subprocess for DAVE-decryption + songbird playback. The control panel is a FastAPI web server with WebSocket live updates.

**Entry points:**
- `discord_bot.py` (line 6): `asyncio.run(main())` where `main` is imported from `serin.d1_2_gateway_io.discord.bot_pipeline_init`
- `serin/__main__.py` (line 9): same `asyncio.run(main())` — allows `python -m serin`

Both resolve to `serin.d1_2_gateway_io.discord.bot_pipeline_init.main()` (line 431 of `bot_pipeline_init.py`).

---

## Package Layout (REAL, not aspirational)

| Path | Owns |
|---|---|
| `serin/d1_1_pipeline_flow/` | Message pipeline: act (stages+dispatch), ingest (manager, context, crawler), perceive (personality, analysis), remember (Qdrant, BM25, facts, beliefs, temporal), think (generator, planner, controller, personality) |
| `serin/d1_2_gateway_io/` | External I/O: discord client + event handlers + command handlers, voice_system (listener, output, TTS, Rust bridge, audio VAD/processor/transcribe), voice_transcribe (Whisper STT, memory pipeline, action decider) |
| `serin/d1_3_state_core/` | Shared state: logger, config-model, bm25_index, db_protect, memory (belief_store, evidence_store), message_context, model_system (connector, adapter, factory, interface), thinking_filter, voice (tracker, profiles, decider, mention_translator) |
| `serin/d1_4_config_base/` | BotConfig singleton, debug_logger |
| `serin/d1_5_ops_tooling/` | BackgroundProcessor, PassiveMonitor, Control Panel (FastAPI), TTSVoiceManager, HotReloader |
| `serin/_di.py` | Root DI container: global singletons for logger, mention_translator, message_manager, crawler, qdrant |
| `serin_core/` | Rust PyO3 module: `sanitize_fts_query`, `apply_contractions`, `filter_thinking` — optional acceleration |
| `control_panel/static/` | HTML/JS for dashboard UI |
| `bot_data/` | Runtime data: `bot_data.db` (SQLite), `memory_fts.db` (FTS5), Qdrant collection |

---

## Discord Gateway Wiring

**File:** `serin/d1_2_gateway_io/discord/bot.py`

`discord.Client(intents=...)` instantiated at line 107. Intents: `message_content`, `members`, `guilds`, `presences`, `voice_states`.

Event handlers are registered via decorators on the module-level `client`:

| Handler | File | Line | Trigger |
|---|---|---|---|
| `on_ready` | `bot_pipeline_init.py` | 66 | Bot connects — initializes ALL subsystems |
| `on_message` | `bot_pipeline_init.py` | 367 | Every text message |
| `on_voice_state_update` | `event_handlers.py` | 13 | User joins/leaves/switches VC |
| `on_error` | `event_handlers.py` | 42 | Discord.py errors |

**Startup flow** (`main()` at `bot_pipeline_init.py:431`):
1. Validate config, log settings
2. `serin.d1_1_pipeline_flow.think.response_generator.discord_client = client` (line 456)
3. `asyncio.create_task(event_handlers.run_maintenance())` — periodic every `MAINTENANCE_INTERVAL_HOURS`
4. `client.start(token)` with up to 5 retries, backoff 2^n capped at 30s
5. After connection, `on_ready()` fires and initializes:

```
on_ready() initialization order (bot_pipeline_init.py:66-363):
  1. MentionTranslator(client) → set in root DI
  2. init_database_protection() — validates SQLite
  3. initialize_llama() — ModelInterface via factory
  4. QdrantMemorySystem(data_dir, qdrant_host, qdrant_port) → set in root DI
  5. BackgroundProcessor(memory_system) → start()
  6. PassiveMonitor(memory, bg_processor, channels, translator)
  7. MessageCrawler(client, memory, bg_processor, translator) → start()
  8. MemorySyncMonitor(memory, bg_processor, crawler) → start_monitoring()
  9. If ENABLE_VOICE:
     a. WhisperTranscriber → load_model()
     b. VoiceMemoryPipeline(memory, bg_processor, message_manager)
     c. AudioStreamProcessor(transcriber, voice_pipeline, llm_connector)
     d. VoiceListener(client, audio_processor)
     e. If ENABLE_TTS: TTSEngine → TTSVoiceManager → VoiceOutputManager
  10. EnhancedMessageManagerV3(client, translator, memory, voice_output_manager)
  11. MessagePipeline.build(10 stages) → attached to manager.pipeline
  12. VoiceBehaviorManager(personality, listener, tracker) → start()
  13. Voice action callback wired to manager
  14. Control panel server started via uvicorn
```

---

## Text Message Execution Trace

```
discord.Client receives Gateway event
    ↓
bot_pipeline_init.py:367 on_message(message: discord.Message)
    ↓  (filters: own messages, non-TextChannel, empty content)
    ↓
bot_pipeline_init.py:400 passive_monitor.process_message(message, is_allowed_channel)
    ↓  (updates mention cache, upserts user, queues for BG processor)
    ↓
bot_pipeline_init.py:409-413 handle_*_command() — !profile, !stats, !help
    ↓  (returns True if handled, pipeline halts)
    ↓
bot_pipeline_init.py:425 message_manager.process_message(message)
```

**`EnhancedMessageManagerV3.process_message()`** (`ingest/core/manager.py:191`):

1. If no pipeline: builds `MessagePipeline.build(...)` with 10 stages
2. Creates `MessageContext(message, user_id, username, channel_id, guild_id, raw_content, metadata)`
3. Calls `pipeline.process(ctx)` → returns `ctx` with `final_response`

**`MessagePipeline.process()`** (`act/runners/pipeline.py:80`):

Iterates through 10 stages sequentially. Each stage is a `PipelineStage` subclass implementing `_run(ctx) -> ctx`:

| # | Stage | File | What it does |
|---|---|---|---|
| 1 | `ResponseDecisionStage(response_controller)` | `act/stages/decision_temporal.py:16` | Calls `response_controller.should_respond(message_content, channel_id, bot_mentioned, user_id, recent_messages)`. Returns `(bool, reason)`. If False, sets `ctx.halt_reason` and pipeline halts. |
| 2 | `MemoryRetrievalStage(memory_system, retrieval)` | `act/stages/memory_retrieval.py:17` | Calls `memory.get_user_profile(user_id)`, `retrieval.build_context(...)` which internally calls `memory.get_recent_conversation()` and `memory.search_memories()`. Applies garbage-pattern filter. Populates `ctx.facts`, `.beliefs`, `.evidence_memories`, `.episode_memories`, `.utterance_memories`, `.recent_messages`, `.relationships`. |
| 3 | `ResponsePlannerStage()` | `think/response_planner.py:54` | Scans `ctx.beliefs` for high-confidence items, detects user claims via regex, produces `ctx.response_plan` dict with `stance`, `constraints`, `contradictions`, `forbidden_moves`, `allowed_tones`. |
| 4 | `TemporalStage(temporal_context)` | `act/stages/decision_temporal.py:55` | Calls `temporal.resolve_dates(ctx.raw_content)`. Sets `ctx.temporal_refs`. |
| 5 | `PersonalityStage(personality, mood_state)` | `act/stages/personality_stage.py:17` | Gets tone modifier from `mood_state.get_tone_modifier()` or `personality.get_tone_modifier()`. Sets `ctx.tone_modifier` and `ctx.personality_context`. |
| 6 | `PromptAssemblyStage(mention_translator)` | `act/runners/prompt_assembly.py:64` | Builds system prompt from `build_natural_system_prompt()` + tone modifier + planner constraints. Builds typed context sections (facts, beliefs, evidence, episodes, utterances, personality, relationships, user profile). Assembles `ctx.built_messages` as `[{role, content}]` array. |
| 7 | `LLMCallStage(response_generator)` | `act/runners/dispatch/llm_call.py:16` | Calls `response_generator(built_messages, context_block, tone_modifier)`. Sets `ctx.raw_response`. |
| 8 | `ResponseCleaningStage(thinking_filter)` | `act/runners/response_cleaning.py:17` | Applies `thinking_filter.filter(raw)`, strips special tokens, name prefixes, discord mentions, truncates to 2000 chars. Sets `ctx.final_response`. |
| 9 | `SendStage()` | `act/runners/dispatch/send.py:22` | Sends `ctx.final_response` to `ctx.message.channel` with typing simulation (10ms/char + 0.2-0.8s random). Sets `ctx.metadata["message_sent"]`. |
| 10 | `MemoryWriteStage(memory_system)` | `act/stages/memory_write.py:16` | Calls `memory.add_memory_enhanced(content=final_response, user_id="serin", importance=0.1, memory_type="bot_response")`. |

---

## LLM Connector Architecture

**File:** `serin/d1_3_state_core/model_system/connector.py`

`LLMConnector` implements `ModelInterface` (abstract in `interface.py:9`). Uses OpenAI Python SDK pointed at `config.LLM_BASE_URL` (default `http://localhost:8080/v1`).

**Connection flow:**
1. `load_model()` — calls `_try_connect()` (synchronous, up to 3 attempts)
2. `_try_connect()` — creates `OpenAI(base_url, api_key)` client, calls `models.list()` for model discovery
3. On failure: spawns daemon thread retrying every 15s (`_retry_loop`)
4. `chat_completion()` — runs `blocking_chat_completion()` in executor (synchronous HTTP call)

**`blocking_chat_completion()`** (line 123):
- Calls `self.adapter.format_messages(messages)` — currently a no-op identity
- Builds params dict with model, messages, max_tokens, temperature, top_p
- For gemma/deepseek: injects `chat_template_kwargs` into `extra_body`
- Calls `self.client.chat.completions.create(**params)`
- Extracts `response.choices[0].message.content` → passes through `adapter.clean_response()`

**`ModelAdapter`** (`adapter.py:133`):
- `ModelDetector.detect_type()` matches on model name: qwen, deepseek, gemma, phi, mistral, gpt, claude, llama (default)
- `MODEL_CONFIG` dict provides per-model: `stop_tokens`, `strip_tokens`, `thinking_patterns`
- `clean_response()` strips tokens, removes thinking tags, removes name prefixes, collapses whitespace

**Model factory** (`factory.py`):
- `get_model_connector(provider, model_name)` — always returns `LLMConnector(model_name)` regardless of provider argument
- `load_model_if_needed()` — caches in `loaded_models` dict

---

## Memory System Architecture

### Qdrant + SQLite Hybrid

**Class:** `QdrantMemorySystem` (`remember/core/store.py:105`)

**Constructor:**
1. `_connect_with_retry(host, port)` → `QdrantClient(host, port, timeout=5)`, tries 3 times, then falls back to Docker auto-start via `docker-py`
2. `SentenceTransformer('all-MiniLM-L6-v2')` for embeddings (dim=384, cosine distance)
3. `SQLiteBM25Index` at `bot_data/memory_fts.db` — FTS5 virtual table
4. SQLite connection at `bot_data/bot_data.db` — schema: `users`, `relationships`, `activity_log`, `memory_fts`, `background_jobs`, `facts`, `beliefs`, `qdrant_collections`, `conversation_history`
5. `FactStore(conn)` and `BeliefStore(conn)` — SQLite-only stores
6. `_setup_collection()` — creates Qdrant collection "memories" with 384-dim COSINE vectors

**Write path:** `add_memory_enhanced()` (delegated to `storage/write_store.py`):
1. `filter_for_memory(content)` — strips thinking tags
2. `_chunk_content()` — splits into sentences, groups into chunks of 200-600 tokens (4 chars/token)
3. `_build_payload()` — creates dict with: text, person_id, person_display, timestamp, importance, channel_id, memory_type, compressed, evidence_class, etc.
4. If `qdrant_client` exists: embeds via model, calls `client.upsert()`
5. If `bm25_index` exists: calls `bm25_index.add_document()`
6. Returns UUID (either deterministic from source_message_id or random UUID4)

**Search path:** `search_hybrid()` (delegated to `storage/search_store.py:16`):
1. BM25 candidates: `bm25_index.search(query, user_id, channel_id, limit=20)`
2. Vector candidates: embed query → `qdrant_client.query_points(collection="memories", query=embedding, filter=filter, limit=50)`
3. `_merge_candidates()` — combines BM25 + vector results deduplicating by ID
4. `_rerank_results_simple()` — RRF (Reciprocal Rank Fusion) rescoring
5. `_condense_results()` — removes payload keys, flattens

### FactStore (`state_core/memory/evidence_store.py:31`)

SQLite table `facts`: id, content, category, confidence, source_message_id, source_user_id, source_username, source_type, timestamp, is_active, superseded_by.

Categories: `observation`, `board_state`, `game_result`, `reference`, `personality`, `preference`.
Source types: `evidence_extracted` (0.8-1.0), `user_claim` (0.1-0.3), `bot_assertion` (0.7-0.9), `verified`.

Auto-supersede: new `board_state`/`game_result`/`reference` facts set `is_active=0` on older facts of same category.

Retrieval: keyword-based via LIKE operators, scoring by keyword frequency.

### BeliefStore (`state_core/memory/belief_store.py:35`)

SQLite table `beliefs`: id, content, category, confidence, state, evidence_count, claim_count, supporting_fact_ids, contradicting_fact_ids, is_active, timestamp.

State machine: `PENDING → SUPPORTED ↔ CONTESTED → SUPERSEDED → UNKNOWN`

Confidence: `0.3 + 0.7 * (evidence / (evidence + claims))` — Bayesian update.

Retrieval: keyword-based LIKE search, ordered by confidence DESC.

### SQLite BM25 Index (`state_core/bm25_index.py:8`)

Two modes:
1. **Rust-accelerated** (preferred): `serin_core.sanitize_fts_query()` — single-pass sanitization
2. **Python fallback**: strips special chars `+-*<>":()^~{}[]\\!?.\',`

FTS5 table `documents_fts(id, text, person_id, channel_id)`. Search via `rank_bm25` library with BM25Okapi scoring.

---

## Voice System

### Voice Listener (`voice_system/listener.py:101`)

Uses `InfoCaptureProtocol` (line 27), a `VoiceProtocol` subclass that:
1. Sends `change_voice_state(channel=channel)` via gateway
2. Waits for `VOICE_SERVER_UPDATE` and `VOICE_STATE_UPDATE` gateway events
3. Captures `endpoint`, `token`, `session_id` — does NOT establish UDP/DAVE connection
4. Returns `ConnectionInfo` dict to `VoiceListener.join_channel()`

**`VoiceListener.join_channel()`** (line 123):
1. Gets `discord.VoiceChannel` from guild
2. Connects via `channel.connect(cls=InfoCaptureProtocol, timeout=15.0)`
3. Creates `RustVoiceBridge(audio_processor, voice_listener)`
4. Calls `rust_bridge.start_with_info(guild_id, channel_id, connection_info)`
5. Rust binary handles all UDP voice transport

### Rust Voice Bridge (`voice_system/bridge_io/process_watch.py:16`)

**`RustVoiceBridge`** manages the Rust `voice_receiver` subprocess.

**Stdout protocol** (`RustStdoutReader`, `bridge.py:52`):
```
Rust → Python (lines):
  AUDIO:{user_id}:{pcm_len}\n followed by pcm_len bytes of PCM
  JOIN:{user_id}\n
  LEAVE:{user_id}\n
  TTS_DONE\n
  anything else → log message
```

**Stdin protocol** (`bridge_commands.py`):
```
Python → Rust:
  Line 1: JSON ConnectionInfo{endpoint, token, session_id, guild_id, channel_id, user_id}
  SPEAK:{pcm_len}\n followed by pcm_len bytes of WAV audio
  INTERRUPT\n
  SHUTDOWN\n
```

**Key design:** stdin writes serialized via `threading.Lock()` (line 68 of process_watch.py). Stderr captured in ring buffer (200 lines) for crash diagnostics.

**Crash supervisor** (`bridge_recovery.py:63`):
- Watches `_death_event` (set on process death)
- Rate-limited restarts: max 5 in 60s window
- On rate limit exceeded: logs `voice.supervisor_giving_up` and stops

### Audio Processing Pipeline

**`AudioStreamProcessor`** (`voice_system/audio/process/audio_processor.py:32`):

Per-user state kept in dicts:
- `user_buffers: dict[str, bytearray]` — raw PCM (48kHz stereo 16-bit)
- `user_silence_frames: dict[str, int]` — count at 50 fps
- `user_voice_burst: dict[str, int]` — consecutive voice frames
- `_silence_timers: dict[str, Task]` — fallback timeout per user
- `_processing_lock_until: dict[str, float]` — per-guild lock (time-based)
- `currently_speaking: set[str]` — for interrupt detection

**VAD:** Energy-based RMS (`audio_vad.py:14`):
- `VAD_THRESHOLD = 150` (RMS amplitude)
- `FRAMES_PER_SECOND = 50` (20ms frames)
- Voice burst filter: 25 consecutive voice frames (0.5s) to reset silence counter
- Buffer overflow at 5.7MB (Gemma) or 50MB (Whisper) forces immediate transcription

**Transcription dispatch** (`_transcribe_and_store` in `audio_transcribe.py:10`):
1. If `llm_connector` AND `config.LLM_SUPPORTS_AUDIO` AND model_type contains "gemma":
   - Direct audio: truncate to 30s, convert to WAV base64, pass to voice pipeline with `wav_b64`
   - Transcription text set to `"[voice input]"` — LLM hears raw audio directly
2. Otherwise: `WhisperTranscriber.transcribe(audio_data)` — faster-whisper with VAD filter

**Processing lock lifecycle:**
- Set in `_queue_for_transcription()` (30s safety net)
- Released by `TTS_DONE` from Rust → `_release_lock()`
- During lock: audio buffered silently, no VAD, no transcription

### Whisper Transcriber (`voice_transcribe/transcriber.py:30`)

Uses `faster-whisper.WhisperModel`. Config: model_size="base", device="cuda", compute_type="float16".
- Converts Discord 48kHz stereo → 16kHz mono via linear interpolation
- Uses VAD filter: threshold=0.5, min_silence_duration_ms=500
- Falls back to `WhisperTranscriberFallback` — ⚠️ STUB: `transcribe()` returns None (line 214)

### TTS Engine (`voice_system/tts_engine.py:32`)

**Backend selection:** edge-tts > Coqui XTTS v2 > None
- edge-tts: cloud, free, no model download. Voices from `EDGE_VOICE_PRESETS` dict (6 presets by mood)
- Coqui: local neural TTS, requires GPU, model `tts_models/multilingual/multi-dataset/xtts_v2`

**`synthesize(text)` flow:**
1. edge-tts: `edge_tts.Communicate(text, voice, rate)` → stream chunks → MP3 → ffmpeg → WAV (16kHz mono 16-bit)
2. Coqui: `TTS.tts(text)` → numpy → WAV via `wave.open`

**`_mp3_to_wav()`:** Shells out to `ffmpeg -i pipe:0 -f wav -acodec pcm_s16le -ar 16000 -ac 1 pipe:1`. On ffmpeg not found, returns MP3 as-is. (line 213)

### Voice Memory Pipeline (`voice_transcribe/pipeline.py:22`)

`process_voice_message()` path (line 50):
1. `memory.upsert_user(user_id, username)`
2. `memory.add_memory(content=f"[Voice] {transcription}", importance=0.7)`
3. `bg_processor.queue_message(content, user_id, username, channel_id, server_id, timestamp)`
4. If `message_manager` and has `process_voice_input`: calls it — ⚠️ **This method does not exist on EnhancedMessageManagerV3**

**Voice Action Decider** (`voice_transcribe/decider.py:15`):
- Keyword pre-filter: checks for "vc", "voice", "join", "leave", etc.
- LLM call: `llm.send_input(prompt)` with temperature=0.1, max_tokens=200
- Returns `{"action": "join"|"leave"|"none", "reason": "..."}`
- JSON parsing has resilience: closes unclosed quotes, wraps in braces

### Voice Behavior Manager (`voice_system/audio/process/voice_behavior.py:14`)

Autonomous VC join/leave decisions. Configurable: `join_aggressiveness` (0.0-1.0), `leave_after_silence_seconds` (180), `max_session_minutes` (60).

**Join flow:**
1. `on_user_joined_vc()` → stores pending join with 45-90s random delay
2. Every 15s: `_evaluate_pending_joins()` checks if delay elapsed
3. Join chance based on energy level (0.03-0.25), evening boost (1.5x), aggressiveness multiplier

**Leave flow:** `_check_leave_conditions()` — silence > 3min, session > 60min, energy < 0.25

---

## Control Panel (FastAPI)

**File:** `serin/d1_5_ops_tooling/control_panel/server.py`

FastAPI app on port 8081 (configurable). Auth via `X-API-Key` header (optional, set via `CONTROL_PANEL_KEY`).

**API Routes:**

| Route | Method | What it does |
|---|---|---|
| `/` | GET | Serves `control_panel/static/index.html` |
| `/api/status` | GET | Discord client status, guilds, latency |
| `/api/stats` | GET | Aggregated stats from all subsystems |
| `/api/health` | GET | Component health: discord, memory, voice, TTS, background |
| `/api/model` | GET | LLM model info |
| `/api/channels/allowed` | GET | Allowed channel IDs |
| `/api/background/start` | POST | Start background processor |
| `/api/background/stop` | POST | Stop background processor |
| `/api/enhanced/status` | GET | Memory system status |
| `/api/enhanced/search` | POST | Hybrid memory search |
| `/api/enhanced/memories` | POST | Add memory |
| `/api/enhanced/users/{id}` | GET | User profile |
| `/api/enhanced/cleanup` | POST | Clean old memories |
| `/api/enhanced/test-connection` | POST | Test Qdrant connection |
| `/ws` | WS | WebSocket for real-time logs + heartbeat |

**WebSocket protocol:**
- Server sends: `{"type": "heartbeat", "latency": int, "gpu": float, "brain_state": str}` every ~1s
- Server sends: `{"type": "log", "msg": str}` for log streaming
- Server sends: `{"type": "decision", "status": str, "reason": str, "time": str}` for response decisions

Additional panel routes registered in `panels/panel_control.py` and `panels/panel_voice.py` (model control commands, voice channel management).

---

## Background Processor

**File:** `serin/d1_5_ops_tooling/background.py:24`

`BackgroundProcessor`: deque-based queue (maxlen=1000) → LLM-calls for conversation summarization.

**`queue_message()`** (line 93): Validates content (min 10 chars, filters empty patterns), thread-locked append.

**Processing loop** (`_processing_loop`, line 160):
- Batch of 3 when queue >= 3
- Idle flush: 1-2 messages after 10s idle
- Calls `_process_batch()` → `_group_by_conversation()` (same channel + 5min window) → `_create_conversation_summary()`

**`_create_conversation_summary()`** (line 292):
- Own `ModelInterface` instance (`self.extractor_llm`)
- Calls LLM with prompt asking for one-sentence summary, distinguishing observations from claims
- Stores via `memory.add_memory_enhanced(memory_type='summary', compressed=True, source_message_count, linked_ids)`
- Importance calculation: base 0.5, +0.1 for 5+ messages, +0.1 for 3+ participants, +0.15 for personal keywords, +0.1 for questions

---

## Passive Monitor

**File:** `serin/d1_5_ops_tooling/passive_monitor.py:20`

Called from `on_message()` for EVERY channel (allowed + non-allowed). Updates mention cache, upserts user profile, queues message for background processing (min 10 meaningful chars). Tracks stats per server/channel.

---

## Message Crawler

**File:** `serin/d1_1_pipeline_flow/ingest/sync/crawler.py:28`

Two background loops:
1. **Quick sync** (every 15 min): checks latest message per channel via SQLite
2. **Deep validation** (every 1 hour): checks every 100th message, detects gaps, triggers backfill

**BackfillMixin** (inherited via class hierarchy) fills missing messages with context-aware processing.

---

## Database Protector

**Directory:** `serin/d1_3_state_core/db_protect/`

Files: `core.py`, `backup.py`, `recovery.py`, `shutdown.py`.

**`DatabaseProtector`** validates SQLite integrity before writes, creates versioned backups at startup and on schedule, attempts recovery from corruption, and sets up graceful shutdown handlers.

---

## Logging System

**File:** `serin/d1_3_state_core/logger.py`

Root logger named `"serin"`. Custom `SUCCESS` level (25).

**Formatters:**
- `ColoredFormatter`: ANSI colors for console (CRITICAL=red bold, ERROR=red, WARNING=yellow, SUCCESS=green)
- `JSONFormatter`: Structured JSON with timestamp, level, logger, file, line, message, correlation_id, extra fields
- `TextFormatter`: Plain text `%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s`

**Handlers:**
- Console: INFO level, colored text or JSON
- File: `serin/logs/serin_ai.log`, rotating 5MB × 5 backups, DEBUG level

**`LoggerProtocol`** (runtime-checkable Protocol): enforces `debug`, `info`, `warning`, `error`, `exception`, `critical`, `success` methods.

---

## ⚠️ Broken / Stub / Missing Components

| Component | Issue | Location |
|---|---|---|
| Rust `voice_receiver` binary | Binary path `voice/rust_receiver/target/release/voice_receiver` does not exist. No `voice/` directory in repo. | `config.py:63`, `process_watch.py:56` |
| `WhisperTranscriberFallback.transcribe()` | Returns `None` — never implemented | `transcriber.py:214` |
| `RustVoiceBridge` class in `bridge.py` | File ends at line 159 before the class body. Class is in `process_watch.py` instead. | `bridge.py` is only the `RustStdoutReader` |
| `serin/state/` directory | Empty (only `__pycache__/`). No state files exist. | — |
| Memory re-export shim | `remember/qdrant.py` re-exports from `remember/core/store.py`, not matching old path `serin.memory.qdrant` | `qdrant.py:11` |
| Voice listener reference `guild.me.voice` | `listener.py:240` — property chain that crashes if `guild.me` is None or not in voice | `listener.py:240-255` |

---

## Dependency Graph (Layer Architecture)

Intended layering from pyproject.toml (`[tool.import_linter]`):
```
config → state → pipeline → gateway → ops
```

Actual imports observed:
- `d1_4_config_base` ← imported by ALL layers (config singleton)
- `d1_3_state_core` (logger, bm25, model_system, memory, thinking_filter, voice, message_context) ← imported by pipeline, gateway, ops
- `d1_1_pipeline_flow` ← imports state_core and config
- `d1_2_gateway_io` ← imports state_core, pipeline, config, ops (but NOT ops/control_panel directly — that's deferred)
- `d1_5_ops_tooling` ← imports state_core and config

Circular import risk managed via:
- Late imports inside functions (e.g., `bot_pipeline_init.py` imports inside `on_ready()`)
- TYPE_CHECKING guards for cross-layer type annotations
- `serin/_di.py` and `serin/d1_2_gateway_io/_di.py` as singleton DI containers

---

## Data Schema: SQLite Tables

**`bot_data/bot_data.db`** (created in `remember/core/schema_store.py`):

```sql
users(user_id TEXT PK, username, display_name, total_messages, avg_message_length,
      personality_traits TEXT, interests TEXT, communication_style TEXT,
      first_seen, last_seen)

relationships(id INTEGER PK, user_a_id, user_b_id, interaction_count, direct_mentions,
              relationship_strength REAL, last_interaction, UNIQUE(user_a_id, user_b_id))

activity_log(id INTEGER PK, user_id, channel_id, timestamp, message_length,
             sentiment_score, hour_of_day, day_of_week)

memory_fts -- VIRTUAL TABLE fts5(id, text, person_id, channel_id, memory_type, content=memories)

background_jobs(id INTEGER PK, job_type, memory_id, payload TEXT, status,
                created_at, priority, retry_count)

facts(id TEXT PK, content, category, confidence REAL, source_message_id,
      source_user_id, source_username, source_type, timestamp, updated_at,
      is_active INTEGER DEFAULT 1, superseded_by TEXT)

beliefs(id TEXT PK, content, category, confidence REAL, state TEXT,
        evidence_count, claim_count, supporting_fact_ids TEXT, contradicting_fact_ids TEXT,
        is_active INTEGER DEFAULT 1, timestamp, updated_at, last_contradicted_at, resolved_at)

qdrant_collections(collection_name, vector_size, distance_metric, status, created_at)

conversation_history(id INTEGER PK, channel_id, user_id, username, content, message_id, timestamp,
                     is_processed INTEGER DEFAULT 0)
```

**`bot_data/memory_fts.db`**:
```sql
documents_fts -- VIRTUAL TABLE fts5(id, text, person_id, channel_id)
```
