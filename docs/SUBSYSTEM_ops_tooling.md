# SUBSYSTEM: ops_tooling — control panel + background tooling + hot reload (d1_5)

Checklist: 38/38 files read (PLAN said 38 — confirmed). Status: DRAFT (wip).
Finalize name: `SUBSYSTEM_ops_tooling.md`.

Root: `serin/d1_5_ops_tooling/`

## Scope & role in the system

Everything that *operates* Serin rather than *thinking* for it: the **FastAPI control panel**
(a web dashboard + WebSocket live feed + a huge set of `/api/...` routes), the **background
summary/impression processor**, the **passive monitor**, the **TTS voice manager**, and the **hot
reloader** subprocess. It is the plane of d1_5 — cross-cutting tooling that is *not* part of the
message/voice/state core (d1_1..d1_3) but is wired to all of them.

Topology (3 dirs + 2 loose modules):

1. **`d2_1_control_panel/`** — the FastAPI app. Two sibling trees:
   - `d3_3_panel_lifecycle.py` + `d3_4_panel_routes.py` (top-level) and `d3_1_panel_panels/` and
     `d3_2_panel_server/` (packages).
2. **`d2_2_tooling_background/`** — `BackgroundProcessor` (summary) + summarization mixin.
3. **`d2_3_hot_reloader.py`, `d2_4_passive_monitor.py`, `d2_5_voice_manager.py`** — standalone modules.

**The single most important structural fact:** the control panel has **TWO worlds that both call
themselves the panel**, and only ONE of them is live:

- **LIVE** = `d3_2_panel_server/` — the FastAPI `app`, `bot_state` hub, `state_access`, route
  registrars wired in `panel_server/__init__.py`, WebSocket server, and lifecycle. This is what the
  gateway starts (`PipelineInitializer` calls `init_bot_state` + `start_server`).
- **DEAD** = `d3_1_panel_panels/` (6 substantive files: `d4_1_panel_control.py` + the
  `d4_2_voice_routes/` five route files) **and** `d3_4_panel_routes.py` (the `register_enhanced_routes`
  Qdrant wrapper). Their `register_*` functions have **ZERO importers/callers anywhere** — confirmed
  by repo-wide grep. They are legacy/duplicate route definitions superseded by the panel_server world.

## Files

### d2_1_control_panel/ — the FastAPI control panel

**`d3_3_panel_lifecycle.py` — `init_bot_state` + `start_server` + `WebSocketLogHandler`** ⭐ (the
gateway seam).
- `init_bot_state(discord_client, message_manager, background_processor, passive_monitor,
  message_crawler, memory_system, voice_listener, tts_engine, voice_manager)` — **populates the
  `bot_state` shared dict** (defined in `state_access`). Called by `PipelineInitializer`.
- `start_server(app=None, host="127.0.0.1", port=8080)` — launches uvicorn with port-retry (+1 on
  busy). **Security hardening:** refuses to bind a non-`127.0.0.1` host unless `CONTROL_PANEL_KEY` is
  set (it can restart the bot, rewrite `LLM_BASE_URL`, and read every memory — so remote reach without
  auth is refused outright). Called by `PipelineInitializer` as a background task on
  `config.CONTROL_PANEL_PORT`.
- `WebSocketLogHandler(logging.Handler)` — `emit()` fires `asyncio.create_task(broadcast_log(...))`.
  **NOTE: `register_lifecycle_routes` (which attaches this handler to the root logger) has NO
  caller** — so the log→WebSocket push path is defined but never activated.

**`d3_4_panel_routes.py` — `register_enhanced_routes(app, bot_state, broadcast_func)` — DEAD.**
Registers `/api/enhanced/...` (status/search/memories/users/cleanup/test-connection) that probe for a
Qdrant `memory_system` (hybrid search, `add_memory_enhanced`, `cleanup_old_memories`). Takes a
`broadcast_func` param. **Never imported or called** — superseded by `d6_1_memory_routes.py`.

**`d3_2_panel_server/` — the LIVE panel server world** ⭐.

`d3_2_panel_server/__init__.py` — **the composition/registration root of the panel.** Builds the app
by importing symbols and then calling each registrar with try/except guarding:
`register_memory_routes`, `register_personality_routes`, `register_ops_routes`,
`register_missing_routes` (d6_1), `register_test_routes`, `register_debug_routes` — each wrapped so a
route failure logs but doesn't kill the panel. Ends by side-effect-importing `d5_3_server_status`
("imported for its module-level side effects"). Re-exports the full panel API surface (app,
bot_state, models, broadcast fns, status/stats/health/model/controls/getters).

- **`d4_7_state/d5_1_state_access.py`** — **the panel hub (52 inbound).** Holds module-global state
  shared by every route file: `bot_state` dict, `active_websockets` list, `_rate_limit_store`,
  `_request_metrics`; `make_json_safe` (depth-capped JSON coercer); the FastAPI `app` + CORS + the
  **HTTP security/rate-limit middleware** (`X-API-Key` check when `CONTROL_PANEL_KEY` set, 100 req/min
  per-IP, `X-Response-Time`); pydantic request models (`ModelConfig`, `ChannelControl`,
  `VoiceChannelControl`, `VoiceLoad`, `SettingsUpdate`, `MemoryQuery`, `MemorySearchAdvanced`,
  `FactQuery`, `BeliefQuery`, `MoodUpdate`); static mount; `get_component`;
  `get_gpu_vram_usage` (nvidia-smi subprocess); `get_request_metrics`.
- **`d4_7_state/d5_2_server_state.py` — LIVE rich endpoints.** Registers `homepage`(/),
  `/api/status`, `/api/stats`, `/api/health`, `/api/performance`, `/api/pipeline/status` (reads
  `message_manager` + hardcodes the 10-act-DAG stage list + `manager._last_pipeline_time`), plus
  internal `_get_current_stats` (walks `bot_state` components) and `get_system_health`. ⭐ Consumed by
  `debug_routes` (imports `_get_current_stats` + `get_system_health`).
- **`d4_7_state/d5_3_server_status.py` — DUPLICATE status routes.** ALSO defines `homepage`, `/api/status`,
  `/api/stats`, `/api/health` (+ `get_current_stats`), reading the same `bot_state` fields. Side-effect
  imported LAST in `panel_server/__init__.py`, so **its (simpler) `/api/status|stats|health|` handlers
  shadow `d5_2_server_state`'s at runtime** (FastAPI last-route-definition-wins for same path+method),
  while `debug_routes` still uses `d5_2`'s copies. A live duplicate-route smell worth flagging.
- **`d4_8_server/d5_1_server_controls.py`** — operational control routes: `/api/model`, `/api/model/load`
  (model_connector switch), `/api/background/start|stop`, `/api/channels/allowed` (GET/POST, edits
  `config.ALLOWED_CHANNEL_IDS`), `/api/config` (GET/POST with `ALLOWED_CONFIG_KEYS` allow-list + a
  **`confirm` gate on sensitive keys** `LLM_BASE_URL`/`LLM_MODEL`).
- **`d4_8_server/d5_2_server_websocket.py`** ⭐ — **the WebSocket server + CONNECTIONS A target.**
  `websocket_endpoint("/ws")` (accepts, tracks in `active_websockets`, sends 1s heartbeats with
  latency/GPU/brain_state), `broadcast_log` (json `{type:"log",...}`), **`broadcast_event`**
  (json `{type, data}`). These two are the seam that d1_1's act pipeline reaches into
  (`broadcast_event("pipeline_stage"...)`, `broadcast_event("decision"...)`) and that the voice
  routes use (`voice_joined`/`voice_left`/`sync_complete`).
- **`d4_6_routes/d5_1_core_routes/`** — the live route family:
  - **`d6_1_memory_routes.py`** ⭐ — search/query routes against `memory_system`: hybrid advanced
    search (`/api/memory/search/advanced` with weighted `final_score` = 0.6·vector + 0.3·temporal +
    0.1·importance), simple search, **facts** search/stats (`get_relevant_facts` on legacy `facts`
    table with `belief` col), **beliefs** search/stats (`get_relevant_beliefs` on `beliefs` with
    `state` col), `/api/memory/distribution` (Qdrant scroll + sqlite counts), `/add`, `/cleanup`,
    `/users`, `/user/{id}`. Directly introspects `mem.conn` (sqlite) — so these routes are coupled to
    the CONNECTIONS-F legacy facts/beliefs schema.
  - **`d6_2_personality_routes.py`** — `/api/personality/state`, `/api/personality/mood` (writes
    `personality.energy_level` etc.), `/api/personality/conversation/{channel}`, `/api/personality/topic-fatigue`,
    `/api/brain/state`, `/api/brain/abort`, `/api/emergency-stop`, `/api/system_prompt` (GET/POST),
    and ⭐ **`/api/context/sever`** which DELETEs `manager.dynamics_engine.channels[channel_id]` —
    **a CONNECTIONS-G reader+writer** (resets a channel's conversation-physics state).
  - **`d6_3_ops_routes.py`** — `/api/crawler/trigger-sync` (+`_run_manual_sync` walking guilds),
    `/api/crawler/status`, background queue, `/api/logs/recent`, `/api/db/health` (PRAGMA integrity),
    **`/api/bot/restart`** (writes the `hot_reloader` `SIGNAL_FILE` → triggers reload), `/api/bot/uptime`.
- **`d4_6_routes/d5_2_voice_routes/`** — `d6_1_missing_routes.py` + `d6_2_missing_routes_voice.py`.
  These define mood/TTS/voice/audio/maintenance routes **guarded by an `existing_paths` set**
  (`{r.path for r in app.routes}`) so they only register a path if it isn't already present — an
  explicit collision-avoidance mechanism used because so many route files overlap. `d6_2_missing_routes_voice.py`
  has the LIVE `/api/voice/*` routes (join/leave/status/files/load/clear/channels/leave-all) and
  `/api/audio/*` (settings/settings-update/speakers/stats) and `/api/voice-profiles/*` (which import
  the **canonical d1_3 `voice/voice_profiles`** — a stale import path worth noting: `d1_3_state_core.voice.voice_profiles`,
  whereas the other live copy in `d4_1_panel_control`/`d1_5` uses `d1_3_state_core.d2_4_core_voice.d3_3_voice_profiles`).
- **`d4_6_routes/d5_3_debug_routes/`** ⭐ — **CONNECTIONS A live consumers + diagnostics.**
  - **`d6_2_debug_routes.py`** defines `store_prompt_debug` (bounded 50-entry prompt ring buffer) and
    `update_last_prompt_debug` (attaches the LLM result to the newest prompt) — **these two are imposted
    by the d1_1 act pipeline** (`prompt_assembly._store_prompt_debug`, `runners_dispatch.llm_call`). Routes:
    `/api/debug/prompts`, `/api/debug/prompts/{index}`, `/api/debug/conversation/{user_id}`,
    `/api/debug/personality-history`, `/api/debug/relationships` (**reads `user_affect`**, not the
    deprecated relationships table), `/api/memory/timeline`, `/api/alerts/*` (in-memory alert rules +
    checked against `_get_current_stats`/`get_gpu_vram_usage`), **`/api/dynamics/state`**
    (⭐ CONNECTIONS-G: `engine.get_state_for_panel()`), and `/api/debug/report` (a full health/stats/
    uptime/memory/personality/config report).
  - **`d6_1_test_routes.py`** — `/api/tests/run`, `/api/tests/list`, `/api/tests/run-single` — runs
    pytest as a subprocess from the panel and parses the output.

**`d3_1_panel_panels/` — DEAD subtree (the "other panel").**
`d4_1_panel_control.py` (`register_control_routes`: TTS/profile/settings/audio/voice-profiles/
background-queue/voice-behavior) and `d4_2_voice_routes/` (`d5_1_voice_channels`, `d5_2_voice_tts`,
`d5_3_voice_memory`, `d5_4_voice_brain`, `d5_5_voice_helpers/d6_1_voice_ops`). Each defines mostly
the SAME `/api/voice*`, `/api/tts*`, `/api/audio*`, `/api/brain*`, `/api/crawler*`, `/api/settings*`
routes as the panel_server world — **but their `register_*` functions have zero callers.** They do
broadcast (`broadcast_event("voice_joined")` etc.) from `d5_2_server_websocket` — but since they're
never registered, none of that fires. **Phase-4 cleanup candidate:** the panel_server world and the
panel_panels world are near-twin implementations of the same API; keep the live one, dedup the rest.

### d2_2_tooling_background/ — BackgroundProcessor

**`d5_1_tooling_background.py` — `BackgroundProcessor(BackgroundProcessorSummarizationMixin)`** ⭐.
A deque (maxlen 1000, thread-locked) of RAW messages → batched LLM conversation summaries, plus LLM
affect impressions. Constructed with `memory_system`; `dynamic_engine` attr is set externally.
- `start()` initializes a **separate extractor_llm** (`get_model_connector()`, temperature 0.3) — same
  model, different settings (SGLang concurrent generation). `stop()`. `queue_message(...)` pushes a
  raw message dict. `_processing_loop()`: batch of 3+ (up to 10) or idle-10s single flush, 5-min stats,
  5s idle poll. `_process_batch` → `_group_by_conversation` (same channel + <5min) → `_create_conversation_summary`
  (inherited). ⭐ `run_maintenance()`: flush queue, `dynamics_engine.allocate_attention()`
  (**CONNECTIONS-G touchpoint** — maintenance drives the conversation-physics attention allocator),
  and `_run_impression_batch()` which **reaches into `d1_1 d5_2_sqlite_store.get_users_due_impression`**
  and the memory's `affect_engine` to generate LLM sentiment impressions for due users.
  Maintenance now also runs **`_run_goals_maintenance()`** (when `goals_engine` is attached): it
  reviews/decays stale goals, promotes stable FORMING goals to ACTIVE, and — threshold-gated by
  material volume, live-goal cap, and LLM availability — asks the background LLM to form at most one
  new self-generated goal from recent conversation. Statements are stored verbatim; see [[goals_engine]].
- **`d5_2_tooling_background_summary.py` — `BackgroundProcessorSummarizationMixin`** — the summarization
  logic (split out to keep d5_1 under 500 lines, Rule 2 mixin style). `_create_conversation_summary`
  (JSON prompt, thinking-model handling via `filter_thinking` PyO3, username-prefix strip, garbage-pattern
  rejection), `_store_summary` (**stores as a `memory_type='summary', compressed=True` memory linked to
  source_ids** — summaries are fallback, not source-of-truth), `_calculate_importance`.

### d2_3_hot_reloader.py — the bot dev/reload subprocess ⭐

A **standalone `asyncio` script** (runnable as `python -m` or main) that supervises the bot and
rewatches source. Spawns `uv run -m serin`, and watches: all `*.py` (→ cooldown-gated restart),
`serin_core/src/lib.rs` + Cargo.toml (→ **`maturin develop --release`** rebuild), and
`voice/rust_receiver/src/*.rs` + Cargo.toml (→ **`cargo build --release`**, 300s timeout). Also
watches the **`SIGNAL_FILE = .restart.signal`** — the panel's `/api/bot/restart` writes this file to
trigger a reload. SIGINT/SIGTERM → graceful stop. This is the **subprocess seam** documented in
CONNECTIONS as the dev-controlled bot supervisor.

### d2_4_passive_monitor.py — the every-channel listener ⭐

**`PassiveMonitor(memory_system, background_processor, allowed_channel_ids, mention_translator)`** —
watches ALL messages across ALL servers (fed from the gateway on_ready funnel); stores profile info +
queues meaningful content to `BackgroundProcessor` WITHOUT responding unless in an allowed channel.
`process_message(message, is_allowed_channel)` uses the **MentionTranslator** (d1_1 seam) to clean
content for bot, upserts user + activity, skips <5 char, queues ≥10 char content to the background
processor, tracks per-server/channel stats. `get_stats`.

### d2_5_voice_manager.py — TTSVoiceManager ⭐ (LIVE)

**`TTSVoiceManager(voices_dir="tts/voices")`** — manages voice-reference files for Coqui XTTS v2
**voice cloning**. Creates the `tts/voices` dir (+README), `list_voices` (wav/mp3/pth/pt), `get_voice_path`,
`validate_voice_file` (wave header parsing for WAV: sample_rate/channels/duration, size bounds),
`load_voice(tts_engine, filename)` → `tts_engine.set_voice_reference`, `clear_voice`, `get_voice_info`, `get_stats`.
**Live consumers:** gateway `pipeline_initializer:198` + `discord_bot:48` construct it; the live panel
routes read `bot_state['voice_manager']`. Lives here (d1_5) but wraps the d1_2 `TTSEngine` (d3_5) — the
voice-cloning control surface for the Gateway voice subsystem.

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **THE panel has two worlds; `d3_1_panel_panels/` + `d3_4_panel_routes.py` are DEAD.** Their six
   `register_*` functions have zero importers/callers. They define near-twin copies of `/api/voice*`,
   `/api/tts*`, `/api/audio*`, `/api/brain*`, `/api/settings*`, and Qdrant `/api/enhanced*` routes.
   The LIVE panel is entirely `d3_2_panel_server/`, wired by its `__init__.py`. → **Phase-4 dedup**:
   this is the largest CONNECTIONS-H-style duplicate cluster found so far (6 route files + 1 wrapper).
2. **Duplicate live status routes:** `d5_2_server_state.py` and `d5_3_server_status.py` BOTH register
   `/`, `/api/status`, `/api/stats`, `/api/health`. `d5_3_server_status` is side-effect-imported last,
   so its handlers shadow `d5_2`'s at runtime for those paths, while `d6_2_debug_routes` still imports
   and uses `d5_2`'s `_get_current_stats`/`get_system_health`. Live shadowing, not just dead twin.
3. **CONNECTIONS A is the pipeline→panel seam, confirmed at 4 sites** (d1_1→d1_5):
   - `d1_1 act_runners/runners_pipeline.py:30` imports `broadcast_event` → `"pipeline_stage"` events.
   - `d1_1 act_stages/decision_temporal.py:24` imports `broadcast_event` → `"decision"` events.
   - `d1_1 act_runners/prompt_assembly/prompt_assembly.py:261` imports `store_prompt_debug`.
   - `d1_1 act_runners/runners_dispatch/llm_call.py:35` imports `update_last_prompt_debug`.
   All four resolve to `d4_8_server/d5_2_server_websocket.py` (`broadcast_event`/`broadcast_log`) and
   `d6_2_debug_routes.py` (`store_prompt_debug`/`update_last_prompt_debug`).
4. **CONNECTIONS G (dynamics_engine) is both read and WRITTEN by panel routes:**
   - Read: `/api/dynamics/state` (`engine.get_state_for_panel()`), `/api/debug/report`, plus the
     gateway-set attr on `BackgroundProcessor` (`run_maintenance → allocate_attention`).
   - Write/mutate: `/api/context/sever` **deletes `engine.channels[channel_id]`** — an operator can
     hard-reset a channel's conversation-physics state.
   - Earlier subsystems noted `debug_routes:306`, `personality_routes:141`, `tooling_background:298`
     as the three dynamics_engine readers — confirmed here (`/api/dynamics/state` is :306 region; the
     mood/personality and maintenance readers are the others).
5. **`WebSocketLogHandler` (log→ws push) is wired but never activated** — `register_lifecycle_routes`
   has no caller. So real-time log streaming to the panel is unimplemented despite the handler existing.
6. **Panel security is real:** `start_server` refuses non-local bind without `CONTROL_PANEL_KEY`; the
   `state_access` middleware enforces `X-API-Key` + per-IP rate limit; `server_controls` gates
   `LLM_BASE_URL`/`LLM_MODEL` behind an explicit `confirm`. But the panel still holds crash-and-read-any(
   memory) power — the runtime bind check is the backstop.
7. **Multiple subprocess seams in one subsystem:** the panel's `pytest` runner, `nvidia-smi` VRAM query,
   and `hot_reloader`'s `uv`/`maturin`/`cargo` invocations — all `asyncio.create_subprocess_exec`/
   `create_subprocess_exec`. The Rust build tools (`maturin`, `cargo`) are driven from Python tooling.
8. **Config mutation via panel is real, not cosmetic:** `/api/config` (`update_from_dict` on allowed keys),
   `/api/settings`, `/api/audio/settings/update` (`VAD_THRESHOLD`/`silence_threshold`), `/api/voice/behavior/settings`
   all mutate live state/config at runtime — the operator-facing tunning surface.
9. **Voice-profile import paths are inconsistent:** live voice-profiles routes import the canonical
   d1_3 copies, but `d6_2_missing_routes_voice.py` uses a **stale** `d1_3_state_core.voice.voice_profiles`
   path (vs `d1_3_state_core.d2_4_core_voice.d3_3_voice_profiles` elsewhere) — a latent import-path
   drift worth reconciling (ties to the CONNECTIONS-H VoiceProfileManager dedup from S11).
10. **`RouteCollisionGuard` pattern:** `d6_1_missing_routes.py` computes `existing_paths = {r.path for r
    in app.routes}` and passes it to each sub-registrar, which only registers a path if absent. This is
    a deliberate de-duplication technique because the overlapping route families (mood/TTS/voice/audio)
    are defined in multiple files — evidence the duplicate-route problem is known and being worked around.
11. **`hot_reloader` is the interactive dev seam** — the panel's `/api/bot/restart` writes `SIGNAL_FILE`,
    hot_reloader's `handle_signal_file` sees it and restarts the bot; source edits trigger maturin/cargo
    rebuilds. So there's a full operator loop: edit → reload → panel reflects new bot.

## What's NOT here
- The message/act pipeline (d1_1) — but its `broadcast_event`/`update_last_prompt_debug`/
  `store_prompt_debug` consumers reach INTO this subsystem (CONNECTIONS A).
- The voice bridge/transcription subsystems (d1_2) — but `TTSVoiceManager` (here) wraps its `TTSEngine`,
  and the panel voice routes drive `voice_listener`/`audio_processor`/`voice_behavior_manager`.
- The memory/state core (d1_3) — but the panel's memory routes introspect the memory_system's sqlite
  `conn` + Qdrant and the voice-profiles routes read the canonical d1_3 voice_profiles.
- The Rust accelerators (d1_13/serin_core + voice_receiver, Subsystem 13 adjacent) — driven here by
  `hot_reloader` (maturin/cargo).