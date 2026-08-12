# CONNECTIONS.md — cross-cutting / unexpected edges (FINALIZED, Phase 4)

Purpose: the edges that are **not obvious from folder structure** — cross-layer imports, shared
in-memory state, schema dependencies, dead duplicates, and the Python↔Rust seams. Every edge below
was confirmed against the live source in the Phase-3 deep passes (Subsystems 1–14, docs in
`SUBSYSTEM_*.md`); Phase-1 TODO markers are resolved here. Format:
`file_A:func/line --[edge]--> file_B:func/line — why`.

> **Path correctness:** all paths below were re-verified against the tree on 2026-08-11 (Phase 4).
> Notable corrections from the earlier draft: the PyO3 seams `thinking_filter` + `bm25_index` live in
> **d1_3_state_core** (not d1_1); `search_store` lives in the **remember** flow (not think); the panel
> server directory is `d1_5_ops_tooling/d2_1_control_panel/d3_2_panel_server/` (not `d2_4_server/d4_8_server`); and
> `d4_1_main_entry` lives in the **gateway** `pipeline_init` dir (not config_base).

A note on the test suite: many of these edges are **pinned by tests** — see `SUBSYSTEM_tests.md`
and the "What the tests pin" section at the bottom.

---

## Top-level system map (how the layers fit)

```
                        ┌──────────────────────────────────────────────┐
   Discord (gateway)    │  d1_2_gateway_io                              │
   py-cord events ────► │  discord_bot ──► on_ready ──► PipelineInitializer│
                        │  on_message ──► EnhancedMessageManagerV3     │
                        │  voice: RustVoiceBridge ◄── voice_receiver    │
                        │           (subprocess, songbird Driver)      │
                        └───────────────┬──────────────────────────────┘
                                        │ objects via serin_di (Rule 5)
                                        ▼
                        ┌──────────────────────────────────────────────┐
                        │  d1_1_pipeline_flow  (the FEEDERS)           │
                        │  perceive ──► ingest ──► act 10-stage        │
                        │  MemoryWriteStage ──► remember (schema+store) │
                        │  think: personality, response_planner        │
                        └───────────────┬──────────────────────────────┘
                                        │ (MessageContext, dynamics_engine,
                                        │  affect_engine, Fact/Belief via core_store)
                                        ▼
                        ┌──────────────────────────────────────────────┐
                        │  d1_3_state_core  (the LOW layer: state)     │
                        │  db: Qdrant memory + SQLite (Bayesian schema)│
                        │  context: MessageContext, ConversationDynamics│
                        │  model_system + core_memory: BM25 / thinking │
                        │  core_voice: VoiceTracker, voice_profiles    │
                        └───────────────┬──────────────────────────────┘
                                        │ read/write via panel routes
                                        ▼
                        ┌──────────────────────────────────────────────┐
                        │  d1_5_ops_tooling  (control panel + bg work) │
                        │  d2_1_control_panel: panel server (WS+debug) │
                        │  background, passive_monitor, voice_manager, │
                        │  hot_reloader (dev subprocess)               │
                        └──────────────────────────────────────────────┘

   Rust side (3 crates): serin_core (PyO3, OPTIONAL accelerator) ·
                         voice_receiver (voice subprocess) ·
                         undef-var-scanner (dev/CI CLI, test-only)
   Wiring: d1_1/serin_di.py is the Rule-5 composition root; gateway gets
   pipeline/state objects ONLY via its create_*/get_* factories.
```

The one structural surprise for a reader coming from folder structure: **the control panel (d1_5)
is imported by the pipeline (d1_1) — the highest layer is reached DOWN from the core loop**, not the
other way round. That's edge A.

---

## Verified cross-layer edges

### A. Pipeline → Control Panel (d1_1 → d1_5) — observability pipe, shared-memory buffer ⭐
The message pipeline reaches DOWN into the ops layer to stream live events to panel clients. Four
confirmed call sites, all importing from the **live panel server**
`d1_5_ops_tooling/d2_1_control_panel/d3_2_panel_server/`:
- `d1_1_pipeline_flow/d2_1_flow_act/d3_1_act_runners/d4_2_runners_pipeline.py:29-30` → `d4_8_server/d5_2_server_websocket.py:broadcast_event`
  — every message run broadcasts a decision event to connected panel WebSocket clients.
- `.../d3_2_act_stages/d4_1_decision_temporal.py:23-24` → `broadcast_event` — the response-decision
  stage broadcasts its decision (respond/skip + reason). Dedicated "decision" event type.
- `.../d4_1_runners_dispatch/d5_1_llm_call.py:34-35` → `d4_6_routes/d5_3_debug_routes/d6_2_debug_routes.py:update_last_prompt_debug`
  — after each LLM call records `(raw_response, latency_ms)` into the panel's in-memory prompt-debug buffer.
- `.../d4_3_prompt_assembly/d5_1_prompt_assembly.py:260-261` → `store_prompt_debug` — stores a full prompt
  snapshot dict (user, channel, system_prompt, memories, relationships, beliefs, user_message, full_prompt).

**This is a genuine cross-subsystem shared-memory channel:** the debug buffers (`_prompt_history`,
`_last_prompt` etc.) live as module state in `d6_2_debug_routes.py` (d1_5) and are written by d1_1
stages. `_ws_lock` in `d5_2_server_websocket.py` guards concurrent broadcast+disconnect. Lifecycle
wired by the gateway: `d1_2_gateway_io/d2_1_io_discord/d3_1_pipeline_init/d4_1_pipeline_initializer.py:414`
`init_bot_state` + `:427` `start_server(port)`.
**Pinned by tests:** `tests/server/test_websocket.py` (broadcast_event/broadcast_log), `tests/test_pipeline_smoke.py`
(_prompt_history grows per PromptAssemblyStage run).

### B. State → Pipeline (d1_3 → d1_1) — affect engine reaches into memory storage
- `d1_3_state_core/d2_5_state_conversation/d3_3_affect_engine.py:100,125,161,181` lazily imports
  `get_user_affect` / `upsert_user_affect` from
  `d1_1_pipeline_flow/d2_4_flow_remember/d3_1_remember_core/d4_1_core_storage/d5_2_sqlite_store.py`.
  Function-scoped imports dodge the circular import **and** keep the d1_3→d1_1 import direction legal
  for Rule-5 DAG compliance (the docstring explicitly says the store is "never imported here").

### C. Ops → Pipeline / Gateway (d1_5 → d1_1 / d1_2) — ops tools reach down
- `d1_5_ops_tooling/d2_4_passive_monitor.py:14` → `d1_1_pipeline_flow/d2_2_flow_ingest/d3_1_ingest_context/d4_3_mention_translator.py`
  — PassiveMonitor uses the (canonical, pipeline) MentionTranslator to strip mentions from every
  message before queuing for background summarization.
- `d1_5_ops_tooling/d2_2_tooling_background/d5_1_tooling_background.py` → `d5_2_sqlite_store.py`
  — BackgroundProcessor reads conversation history; `run_maintenance` → `allocate_attention()` (:298).
- `d1_5_ops_tooling/d2_5_voice_manager.py` → `d1_2_gateway_io/d2_2_voice_system/d3_5_tts_engine.py`
  — TTSVoiceManager (panel) wraps TTSEngine (gateway) for Coqui voice cloning from the panel.

---

## Cross-language seams (graphify is BLIND to all three Rust crates)

### D. Python → Rust PyO3 (serin_core) — OPTIONAL accelerator, never required
`serin_core` (a PyO3 `#[pymodule]`) is imported at exactly **4 live sites**, every one try/except-guarded
with a pure-Python fallback — the bot's text correctness does not depend on Rust:
- `d1_1_pipeline_flow/d2_4_flow_remember/d3_1_remember_core/d4_1_core_storage/d5_1_search_store.py:168` → `rerank_candidates` (fallback `_rerank_results_simple`)
- `d1_1_pipeline_flow/d2_5_flow_think/d3_3_response_generator.py:352-354` → `apply_contractions` (fallback Python regex)
- `d1_3_state_core/d2_3_model_system/d3_5_model_helpers/d6_1_thinking_filter.py:70` → `filter_thinking` (via `importlib`, fallback `strip_special_tokens`) — **note: in d1_3, not d1_1**
- `d1_3_state_core/d2_2_core_memory/d3_5_memory_helpers/d6_1_bm25_index.py:46` → `sanitize_fts_query` (fallback Python loop) — **note: in d1_3, not d1_1**
**5 exported functions have NO live importer** (evans-peeled dead Rust or reserved): `validate_json_fast`,
`compute_text_similarity`, `extract_mentions`, `tokenize_words`, `sanitize_markdown`.
Build bridge: `d1_5_ops_tooling/d2_3_hot_reloader.py` runs `maturin develop` on `serin_core/src/lib.rs` change.
The 13 thinking-filter regexes document newer model tokens (`BEGIN_THINKING`, `|begin▁of▁thinking|`)
absent from the dated Python prose.

### F. State core memory depends on pipeline schema (d1_3 → d1_1, schema-level) — RESOLVED ⭐
**This was the sharpest Phase-1 open question and is now resolved.** Three facts representations exist;
exactly one is authoritative:
- **AUTHORITATIVE DDL:** `d1_1_pipeline_flow/d2_4_flow_remember/d3_1_remember_core/d4_3_schema_store.py:129,162,175` —
  `facts` = Bayesian (`subject_id, subject_name, claim, belief REAL, variance, log_odds,
  observation_count, corroboration_count, contradiction_count, primary_source, source_type,
  state DEFAULT 'PENDING', claim_hash UNIQUE`; **no `content/confidence/source_message_id`**);
  `beliefs` = `id, content, category, state, confidence, supporting_fact_ids,
  contradicting_fact_ids, evidence_count, claim_count, timestamp, updated_at, ...`; plus
  `user_affect` (the schema `tests/memory/test_user_affect.py` pins) and `fact_observations`.
- **REAL wiring:** `d4_4_core_store.py:78-80` imports `BeliefStore`/`FactStore`/`BayesianBeliefEngine`
  from D1_3 (`d3_1_belief_store`, `d3_2_evidence_store`, `d3_3_belief_dynamics`) and sets
  `self.belief_engine = BayesianBeliefEngine(self.conn)` — so the ACTIVE machinery lives in
  **d1_3 `d2_2_core_memory`** and the schema that feeds it is created in **d1_1 `d4_3_schema_store`**.
  The d1_3 `d3_4_memory_store.py` CREATE TABLE (legacy `facts = id, content, category, confidence,
  source_message_id, ...`) is DEAD/conflicting — never the schema in use. (Second instance of d1_3
  storage-tech staleness, after db_protect's ChromaDB.)
- **THIRD (legacy) representation — the CONNECTIONS F holdout:** the d1_1 `d2_4_flow_remember`
  `d5_1_belief_beliefs.BeliefStore` + `d5_2_belief_evidence.FactStore` INSERT
  `content/confidence/source_message_id/...` — columns absent from the authoritative `facts`
  (a real "no such column" risk). **NOTHING in `serin/` imports these two files**; their only
  consumer is the **untracked `tests/test_fact_belief_gating.py`**, which monkeypatches them onto a
  real connected SQLite `QdrantMemorySystem` to prove the live facts/beliefs gating behavior
  (empty when `small_llm=None`). Also dead in `d2_4_flow_remember`: `d4_3_memory_quality`,
  `d4_4_knowledge_retrieval` (zero refs).
- Two belief engines coexist: legacy `BeliefStore`/`FactStore` (keyword LIKE, string state machine) vs
  active `BayesianBeliefEngine` (log-odds, variance, temporal decay, claim_hash→corroboration).
  `d1_1_pipeline_flow/d2_2_flow_ingest/d3_2_ingest_core/d4_1_core_perception/d5_2_perception_classify.py:245-248`
  reaches in lazily for the engine.
- **Phase-4 verdict:** canonical entry is `d4_3_schema_store` + `d4_4_core_store` wiring (both in d1_1
  remember); the legacy d1_1 stores and `test_fact_belief_gating.py` should be migrated to the
  authoritative schema (and the test added to git). The legacy `memory_store` CREATE TABLE is dead.

### G. state_core_context → pipeline → ops (conversational state wire-up) ⭐
`d1_3_state_core/d2_5_state_conversation/d3_1_dynamics_engine.py:ConversationDynamicsEngine` is a
**THREE-subsystem shared object**:
- d1_1 ingest `d2_2_flow_ingest/d3_2_ingest_core/d4_4_core_manager.py:141` constructs it and passes
  it into the message pipeline (`d2_1_flow_act/d3_1_act_runners/d4_2_runners_pipeline.py:52,89`); act
  stages `d3_2_act_stages/d4_1_decision_temporal.py:5` and `d4_1_runners_dispatch/d5_2_dispatch_send.py:5`
  consult it for decision/timing (energy equations — pinned by `tests/test_boltzmann_bias.py`).
- d1_5 ops reads it live: `d6_2_debug_routes.py:306-309` → `get_state_for_panel()`; `d6_1_personality_routes.py:141`
  → `decide_action`; `d5_1_tooling_background.py:298-299` → `allocate_attention()` (run_maintenance).
- `_build_pipeline` also sets `background_processor.dynamics_engine` (ingest core_manager) — a fourth wire.
`MessageContext` (`d3_2_message_context.py`) is the pipeline-wide data envelope every d1_1 stage mutates.
`AffectEngine.record_sentiment`/`apply_impression` (edge B) feed the same conversation state — MemoryWriteStage
calls `record_sentiment` per message (edge G feedback loop, pinned by `tests/test_affect_wiring.py`).

### H. Dead duplicates / twin implementations — the dedup clusters ⭐
Resolved answers to each Phase-1 duplicate question:
- **MentionTranslator:** TWO exist — `d1_3_state_core/d2_4_core_voice/d3_1_mention_translator.py` and
  `d1_1_pipeline_flow/d2_2_flow_ingest/d3_1_ingest_context/d4_3_mention_translator.py`. **ALL ~10 import
  sites use the PIPELINE copy** (serin_di:27,115; core_manager:23; sync_crawler:24; message_process;
  discord_bot:39; pipeline_initializer; passive_monitor:14). The `core_voice` copy is dead → dedup.
- **Control panel has TWO worlds:** `d1_5_ops_tooling/d2_1_control_panel/d3_1_panel_panels/` (d4_1_panel_control
  + d4_2_voice_routes d5_1..d6_1) AND `d3_4_panel_routes.py` (`register_enhanced_routes`, Qdrant) are
  **DEAD** (zero importers/callers). LIVE = entirely `d3_2_panel_server/` (`init.py` wires
  memory/personality/ops/test/debug/missing registrars + side-effect import `d5_3_server_status`).
  Largest dedup cluster.
- **Duplicate live status routes:** `d4_7_state/d5_2_server_state` AND `d4_7_state/d5_3_server_status` both
  register `/ /api/status /api/stats /api/health`; `d5_3` is side-effect-imported LAST and **shadows**
  `d5_2` at runtime, while `debug_routes` still uses the `d5_2` copies — a live shadowing hazard.
- **VoiceProfileManager:** `d1_2_gateway_io/d2_3_voice_transcribe/d4_1_models_profiles` has ZERO importers;
  canonical twin is `d1_3_state_core/d2_4_core_voice/d3_3_voice_profiles.py` (panel d1_5 imports that).
  Stale cross-ref: `d6_2_missing_routes_voice` imports the wrong (dead) one.
- **Legacy message_process batch path** superseded by the act pipeline (S8).
- **Two sentiment tools** (vader vs nltk) coexist in ingest.

### I. DI/Gateway-Isolation seam + entry duality — RESOLVED ⭐
- `d1_1_pipeline_flow/d1_1_serin_di.py` is the LEGAL composition root (THE_LAW.md Rule 5 / Gateway
  Isolation): the only module that imports pipeline/state classes; gateway code gets objects via
  `create_*`/`get_*` factories. Holds singletons (logger, mention_translator, message_manager, crawler,
  qdrant) + lazy factories; module-level pokes for `response_generator` (`rg.discord_client`, `rg.llama`)
  are wrapped here so gateway never imports that module directly.
- **Entry duality (resolved): BOTH paths are canonical.**
  - `python -m serin` → `serin/__main__.py` → `d1_2_gateway_io/d2_1_io_discord/d3_1_pipeline_init/d4_1_main_entry.py:main()`
    — direct run, 5-attempt exponential-backoff retry, db_protect error handlers
    (pinned by `tests/bot_pipeline_init/test_main.py`). **Note: main_entry lives in the gateway
    pipeline_init dir, not config_base.**
  - `python discord_bot.py` (repo root) → `auto_start_qdrant()` (Docker) → `d2_3_hot_reloader.main()`
    (spawns bot subprocess with auto-restart + `*.py` watch + signal file). So the ROOT entry goes through
    the hot-reloader, not straight to main_entry. Both terminate at `main_entry.main()`.
- `d1_2_gateway_io/d2_4_io_di.py` is a lighter logger-holder (`init_gateway`/`get_logger`).

### J. Python ↔ Rust voice seam (voice_receiver subprocess) — CONNECTIONS J ⭐
(This supersedes the earlier "E" draft; the E-specific mechanics — threading.Lock stdin serialization,
200-line stderr ring buffer, 5-restarts/60s recovery supervisor — described DEAD code:
`d3_2_bridge_io/d4_3_bridge_recovery.py` has zero importers. The LIVE seam is below.)
- **Spawn:** `d1_2_gateway_io/d2_2_voice_system/d3_2_bridge_io/d4_4_process_watch/d5_1_process_watch.py:RustVoiceBridge.start()`
  (:116-180) self-resolves the binary via `os.pardir`×4 → `voice/rust_receiver/target/release/voice_receiver`,
  then `asyncio.create_subprocess_exec(binary, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=RUST_BACKTRACE=full)`.
  First stdin line = `ConnectionInfo` JSON (`{endpoint, token, session_id, guild_id, channel_id, user_id}`).
- **Wire protocol (newline-delimited):**
  - stdin (Python → Rust): `SPEAK:{len}` + WAV bytes → plays via songbird; `INTERRUPT` → stop; `SHUTDOWN` → clean exit.
  - stdout (Rust → Python): `AUDIO:{user_id}:{pcm_len}` + raw 48kHz stereo i16 PCM (20ms VoiceTick/50fps);
    `JOIN:{uid}` / `LEAVE:{uid}` (SSRC→uid mapping + active-set diffing); `TTS_DONE` (fires on `TrackEvent::End`
    via one-shot `TtsDoneNotifier`) — this is the **lock-release signal** for the Python per-guild processing lock.
- **Rust half:** `voice/rust_receiver/src/main.rs` uses `songbird::driver::Driver` connecting DIRECTLY to the
  Discord voice UDP endpoint — **no gateway client** (avoids the dual-gateway conflict with py-cord). SSRC→UID
  learned from `SpeakingStateUpdate` + `ClientConnect`; events → flume → stdout writer; main loop @20Hz.
  Vendored `vendor/songbird` 0.6.0 with ONE behavioral patch (ClientConnect SSRC mapping; DAVE tail-offset bug
  already fixed upstream) — see `docs/wiki/songbird-clientconnect-patch.md`.
- **Python half read side:** `d3_2_bridge_io/d4_1_io_bridge.py:RustStdoutReader` (events queue, read_loop, `_EOF`);
  `AudioStreamProcessor` is a DELEGATING FAÇADE (state in class, logic lazy-imported from `audio_vad`/`audio_utils`/
  `audio_transcribe` siblings). `d4_4_process_watch/d5_1_process_watch` + `d5_2` mixin = RustVoiceBridge + I/O mixin.
- **⚠️ DEAD+STALE config:** `d1_4_config_base/d2_1_base_config.py:66-68` sets `RUST_VOICE_RECEIVER_PATH` with a
  wrong default path and **no code reads it** — RustVoiceBridge computes the real path itself.
- **Testing gap:** `tests/integration/test_bridge.py` only exercises the missing-binary path; the wire protocol
  framing (AUDIO/JOIN/LEAVE/TTS_DONE) is covered only by AST contract checks in `test_runtime_contracts.py`
  (Layer 3 self-attr, Layer 5 guild_id passthrough), not by a live-subprocess integration test.

---

## Shared state / shared resources (the cross-cutting inventory)

These are the module-level or cross-object mutable channels — the places where "one process" assumptions live:

| Shared state | Defined in | Written by | Read by |
|---|---|---|---|
| `_prompt_history`, `_last_prompt` debug buffers | `d6_2_debug_routes.py` (d1_5) | act stages (edge A) | panel debug routes |
| `bot_state` dict | `d4_7_state/d5_2_server_state.py` (d1_5) | `init_bot_state` (gateway :414) + panel routes | `test_server/conftest.py` fixture + all panel routes |
| `ConversationDynamicsEngine` channels map | `d3_1_dynamics_engine.py` (d1_3) | ingest core_manager:141 + act stages | act stages, panel routes (:306,:141), bg maintenance (:298) |
| `PersonalityState` (mood history, maxlen 500) | d1_1 think (S6) | act Personality stage, ingest core, voice gateway system_output/voice_behavior | panel personality routes |
| `VoiceTracker` | `d2_3_voice_transcribe/.../transcribe_models` | constructed ingest core_manager:136, fed gateway `on_voice_state_update` | `VoiceBehaviorManager` (d1_2), voice_action callback |
| `_missed_messages` | decision_temporal (d1_1) | DecisionTemporalStage | PromptAssemblyStage |
| Affect rows (`user_affect`) | `d4_3_schema_store` + `d5_2_sqlite_store` | AffectEngine (`record_sentiment`), impression batch | affect_engine reads, panel |
| `fact_observations`/`facts`/`beliefs` tables | `d4_3_schema_store` (d1_1) | `BayesianBeliefEngine` (d1_3) via `d4_4_core_store` | retrieval + act context |
| Discord client / stats dict / db_protector | `d1_2_gateway_io/d2_1_io_discord/d3_2_discord_bot.py` | gateway events | whole process |
| `serin_di` singletons | `d1_1_serin_di.py` | `set_*`/`init_*` at boot | gateway factories (edge I) |
| LLM connector (`llama`/small/extractor) | response_generator / serin_di | boot | act LLMCall stage, bg summarizer, fact gate |

**Cross-subsystem reach-in pattern (unavoidable given the layering):** d1_1 stages lazily import d1_5
panel stores (A), d1_3 state lazily imports d1_1 stores (B/F), d1_5 ops lazily imports d1_1/d1_2 (C).
Every one of these is a function-scoped import inside a method — the codebase never top-level-imports
across a layer boundary.

---

## What the tests pin (edge → test)

- **A:** `tests/server/test_websocket.py` (broadcast_event/broadcast_log), `tests/test_pipeline_smoke.py` (_prompt_history).
- **F:** `tests/memory/test_user_affect.py` (authoritative `d4_3_schema_store` user_affect schema);
  `tests/test_fact_belief_gating.py` (the legacy-schema holdout).
- **G:** `tests/test_boltzmann_bias.py` (energy equations), `tests/test_affect_wiring.py` (record_sentiment + AST check),
  `tests/test_affect_engine.py`, `tests/test_affect_context.py`.
- **I:** `tests/bot_pipeline_init/test_main.py` (entry chain), `test_on_ready.py` (PipelineInitializer + re-exports),
  `test_on_message.py` (intake funnel), `test_di_contracts.py` (whole-tree DI reachability).
- **J/voice:** `tests/test_runtime_contracts.py` (Layer 3 self-attr contracts, Layer 5 guild_id, Layer 6 no-silent-except),
  `tests/integration/test_bridge.py` (missing-binary path), `tests/test_processor.py` (AudioStreamProcessor constants,
  mislabeled as messaging).
- **D:** no direct serin_core test; `test_runtime_contracts.py` Layer 2 is the ONLY consumer of the
  `undef-var-scanner` Rust binary (dev/CI). `tests/test_static_analysis.py` gates ruff/mypy/pyright/semgrep/
  import-linter (THE_LAW Rule 5)/bandit/detect-secrets.

---

## Open recommendations for Phase 5 (dedup/dead code, ranked)

1. Delete/consolidate the two dead panel worlds (`d3_1_panel_panels/`, `d3_4_panel_routes.py`) and the
   shadowed `d4_7_state/d5_3_server_status` duplicate routes.
2. Migrate `test_fact_belief_gating.py` to the authoritative `d4_3_schema_store` + `d4_4_core_store` wiring and
   `git add` it; drop the d1_1 `knowledge_belief` stores (`d5_1_belief_beliefs`, `d5_2_belief_evidence`) +
   `d4_3_memory_quality`, `d4_4_knowledge_retrieval`.
3. Delete `d3_2_bridge_io/d4_3_bridge_recovery.py` (0 importers) and the `RUST_VOICE_RECEIVER_PATH` config key (never read).
4. Dedup MentionTranslator (keep pipeline copy), VoiceProfileManager (keep core_voice twin).
5. Add a real `voice_receiver` subprocess integration test + a `serin_core` PyO3 smoke test (only gaps in the suite).