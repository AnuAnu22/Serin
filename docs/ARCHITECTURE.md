# Serin Architecture (LIVING DOCUMENT)

> **Generated 2026-08-11 from a full per-file deep pass of the live tree.** The previous version of
> this file was stale (it referenced paths that no longer match the tree). Everything below was
> re-verified against the current source. Per-subsystem detail lives in `SUBSYSTEM_*.md` (one per
> subsystem below); the cross-subsystem edge list lives in `CONNECTIONS.md`.

## System Overview

Serin is a Discord AI companion that processes text and voice messages through a 10-stage message
pipeline, backed by Qdrant vector search + SQLite for persistent memory, and an OpenAI-compatible LLM
backend (llama-swap/vLLM). Voice transport uses a **Rust subprocess** (`voice_receiver`) for
DAVE-decryption + songbird playback, and an **optional Rust PyO3 module** (`serin_core`) that
accelerates hot loops but degrades gracefully to Python when absent. The control panel is a FastAPI
web server with WebSocket live updates.

The codebase is a **layered architecture enforced by THE_LAW.md Rule 5** (Gateway Isolation): a single
composition root (`serin/d1_1_pipeline_flow/d1_1_serin_di.py`) owns all pipeline/state class imports,
and the gateway layer consumes objects through its `create_*`/`get_*` factories. Five numbered
directories (`d1_1` … `d1_5`) hold the layers in dependency order (low-numbered = higher in the DAG).

**Entry points (both canonical — entry duality):**
- `discord_bot.py` (repo root): `auto_start_qdrant()` (Docker) → `serin.d1_5_ops_tooling.d2_3_hot_reloader.main()`
  — spawns the bot as a watched subprocess (auto-restart on `*.py` change, `cargo build`/`maturin develop`,
  300s voice-receiver rebuild, `.restart.signal` file from `/api/bot/restart`).
- `python -m serin` → `serin/__main__.py` → `serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry.main()`
  — direct run: 5-attempt exponential-backoff retry, db_protect error handlers, keyboard-interrupt clean shutdown.

Both terminate in `main()` in `d4_1_main_entry.py` (note: `main_entry` lives in the **gateway**
`pipeline_init` dir, not in config_base — a common mis-remembering).

---

## Directory structure (REAL, verified 2026-08-11)

| Path | Owns |
|---|---|
| `serin/d1_1_pipeline_flow/` | Message pipeline feeders: `d2_1_flow_act` (10-stage DAG + dispatch), `d2_2_flow_ingest` (EnhancedMessageManagerV3, MentionTranslator canonical copy, perception), `d2_3_flow_perceive`, `d2_4_flow_remember` (**authoritative Bayesian schema** + Qdrant/SQLite store wiring), `d2_5_flow_think` (response_generator, response_planner, personality). Also `d1_1_serin_di.py` (Rule-5 composition root). |
| `serin/d1_2_gateway_io/` | Discord gateway + voice: `d2_1_io_discord` (discord_bot, on_ready/on_message, PipelineInitializer, main_entry), `d2_2_voice_system` (AudioStreamProcessor, RustVoiceBridge/io_bridge, TTS engine, VoiceListener, VoiceOutputManager, TTSEngine), `d2_3_voice_transcribe` (WhisperTranscriber, VoiceMemoryPipeline, VoiceTracker, VoiceActionDecider, VoiceProfileManager-dead), `d2_4_io_di.py` (logger holder). |
| `serin/d1_3_state_core/` | Shared state, LOWEST layer: `d2_1_logger`, `d2_2_core_memory` (QdrantMemorySystem, belief/evidence stores, **BM25 index + PyO3 seam**), `d2_3_model_system` (LLM connector/adapter/factory, **thinking_filter + PyO3 seam**), `d2_4_core_voice` (VoiceTracker, voice_profiles canonical, MentionTranslator-DEAD), `d2_5_state_conversation` (MessageContext envelope, ConversationDynamicsEngine, AffectEngine). |
| `serin/d1_4_config_base/` | `BotConfig` singleton, `RUST_VOICE_RECEIVER_PATH` (**DEAD+STALE** — see CONNECTIONS J). |
| `serin/d1_5_ops_tooling/` | Control panel + background: `d2_1_control_panel` (LIVE `d3_2_panel_server/`; DEAD `d3_1_panel_panels/` + `d3_4_panel_routes.py`), `d2_2_tooling_background` (BackgroundProcessor), `d2_3_hot_reloader`, `d2_4_passive_monitor`, `d2_5_voice_manager`. |
| `serin_core/` | Rust PyO3 module — `sanitize_fts_query`, `filter_thinking`, `rerank_candidates` + 6 unused exports (`apply_contractions` lost its only importer 2026-08-18 with the RNG humanizer). **Optional accelerator.** |
| `voice/rust_receiver/` | Rust voice binary (`voice_receiver` + `minimal_test`), vendored songbird 0.6.0 with one patch. **Required for voice.** |
| `scripts/undef-var-scanner/` | Rust dev/CI CLI — the only `{var}`-in-string detector; consumed by the test suite. |
| `control_panel/static/` | HTML/JS for dashboard UI. |
| `bot_data/` | Runtime data: `bot_data.db` (SQLite), `memory_fts.db` (FTS5), Qdrant collection. |
| `tests/` | 40-file pytest suite (see `SUBSYSTEM_tests.md`). |

---

## Subsystem map (14 subsystems → `SUBSYSTEM_*.md`)

> Subsystems are ordered by inbound-edge count (foundational first), so later docs can reference
> earlier ones. Links point at the finalized docs in this directory.

| # | Subsystem | One-liner | Doc |
|---|---|---|---|
| 1 | **config_base** | `BotConfig` singleton + debug logger; log dir is file-relative; `RUST_VOICE_RECEIVER_PATH` stale/dead | `SUBSYSTEM_config_base.md` |
| 2 | **state_core_db** | Qdrant + SQLite stores, belief/fact engines, db_protect (stale ChromaDB); legacy-vs-Bayesian schema conflict lives here | `SUBSYSTEM_state_core_db.md` |
| 3 | **state_core_context** | `MessageContext` pipeline envelope; `ConversationDynamicsEngine` (3-subsystem shared object); `AffectEngine` lazy-imports d1_1 store | `SUBSYSTEM_state_core_context.md` |
| 4 | **wiring_entry_di** | `serin_di` = Rule-5 composition root; `io_di` logger holder; entry duality (`python -m serin` vs `discord_bot.py`→hot_reloader) | `SUBSYSTEM_wiring_entry_di.md` |
| 5 | **pipeline_remember** | **Authoritative Bayesian schema** (`d4_3_schema_store`); real wiring via `d4_4_core_store`; 4 dead knowledge files; compat shim | `SUBSYSTEM_pipeline_remember.md` |
| 6 | **pipeline_think** | Response generator/planner, personality, thinking filter; PyO3 seams; `PersonalityState` multi-subsystem | `SUBSYSTEM_pipeline_think.md` |
| 7 | **pipeline_act** | The 10-stage message pipeline DAG (Decision→Retrieval→Plan→Temporal→Personality→Assemble→LLM→Clean→Send→Write); CONNECTIONS A at 3 sites; `_missed_messages` shared state | `SUBSYSTEM_pipeline_act.md` |
| 8 | **pipeline_ingest** | `EnhancedMessageManagerV3` feeder; builds MessageContext + MessagePipeline; canonical MentionTranslator; perception module | `SUBSYSTEM_pipeline_ingest.md` |
| 9 | **gateway_discord** | THE wiring hub: discord_bot global state, on_ready/on_message intake funnel, PipelineInitializer orchestration | `SUBSYSTEM_gateway_discord.md` |
| 10 | **gateway_voice** | Voice input (Rust) + TTS output; CONNECTIONS J Python half; AudioStreamProcessor delegating façade; DEAD `d4_3_bridge_recovery` | `SUBSYSTEM_gateway_voice.md` |
| 11 | **gateway_transcribe** | Whisper STT + VoiceMemoryPipeline + VoiceTracker/VoiceActionDecider; dead VoiceProfileManager duplicate | `SUBSYSTEM_gateway_transcribe.md` |
| 12 | **ops_tooling** | Control panel (LIVE `d3_2_panel_server`), BackgroundProcessor, PassiveMonitor, hot_reloader, TTSVoiceManager; two dead panel worlds | `SUBSYSTEM_ops_tooling.md` |
| 13 | **rust_accel** | Three unrelated Rust crates: `serin_core` (PyO3, optional), `voice_receiver` (voice subprocess), `undef-var-scanner` (dev CLI) | `SUBSYSTEM_rust_accel.md` |
| 14 | **tests** | 40-file suite; de-facto SPEC of live code; contract/lint gates; one legacy-schema holdout | `SUBSYSTEM_tests.md` |

---

## How a message actually flows (integration narrative)

This is the Phase-4 "how it actually works end-to-end" walkthrough. Edge letters refer to
`CONNECTIONS.md`.

### Text message → reply
1. `discord_bot.on_message` (gateway) runs the intake funnel: skips own-messages/non-text/DM/
   empty-no-attachments, routes allowed vs passive channels, short-circuits command handlers
   (profile/stats/help), then calls `message_manager.process_message` ([gateway_discord]).
2. `EnhancedMessageManagerV3.process_message` ([pipeline_ingest]) builds a `MessageContext` envelope
   (d1_3), wiring a fresh `MessagePipeline` via `serin_di.build_message_pipeline(...)` with
   retrieval=context_builder, dynamics_engine, affect_engine — **gaining CONNECTIONS G at the source**.
3. The 10-stage act DAG runs ([pipeline_act]). The **ResponseDecisionStage** consults the
   `ConversationDynamicsEngine` (Boltzmann energy: reply/react/ignore) and `UserAffectEngine`
   (salience bump `0.1*familiarity`). Creator mentions force reply + `metadata.instant_reply`.
4. **MemoryRetrievalStage** searches Qdrant/BM25 (with the `serin_core.rerank_candidates` PyO3
   accelerator, falling back to Python — edge D), filters `GARBAGE_PATTERNS`, deprioritizes summaries.
5. **ResponsePlanner** (S6) writes `ctx.response_plan`; **TemporalStage** resolves date references;
   **PersonalityStage** reads `PersonalityState`; **PromptAssemblyStage** builds the full prompt and —
   **edge A** — calls `store_prompt_debug` into the panel's `_prompt_history` buffer.
6. **LLMCallStage** calls the configured model and — **edge A** — `update_last_prompt_debug` with
   `(raw_response, latency_ms)`; the thinking filter (`filter_thinking`, edge D) strips thinking
   tags and basic cleanup (special tokens, name prefixes, whitespace, truncation) runs in
   **ResponseCleaningStage** — no contraction pass (the `apply_contractions` seam was deleted
   2026-08-18 with the RNG humanizer; see `docs/SERIN_VISION.md` § Operational Definitions row 1).
7. **SendStage** sends the reply (skipping the dynamics delay on instant replies); **MemoryWriteStage**
   ALWAYS runs (even on halt) — it perceives via `perceive_message` and stores via remember, calls
   `affect_engine.record_sentiment` (**edge G feedback loop**), and writes general memory. If the LLM
   is present it would also write facts/beliefs, but with `small_llm=None` those stay empty (the exact
   behavior `tests/test_fact_belief_gating.py` pins via the legacy stores — see edge F).

### The observability pipe (edge A) in the same run
As the pipeline runs, stages broadcast to panel WebSocket clients: `runners_pipeline` emits run
events, `decision_temporal` emits the decision, and the prompt-debug buffer grows. Panel clients on
the LIVE server (`d3_2_panel_server`) see decisions/logs live; `_ws_lock` guards the socket set.

### Voice message → response (edges J, CONNECTIONS J)
1. Gateway `on_voice_state_update` feeds `VoiceTracker` (constructed at ingest core_manager:136).
2. The Rust `voice_receiver` subprocess (spawned by `RustVoiceBridge`, edge J) decodes Discord voice
   UDP via songbird (no gateway client — avoids dual-gateway conflict with py-cord) and streams
   `AUDIO:{uid}:{len}` PCM lines to Python.
3. `AudioStreamProcessor` (delegating façade) buffers per-user PCM with VAD (RMS-150) and a per-guild
   processing lock; `VoiceMemoryPipeline` (S11) transcribes (Whisper) and either calls
   `process_voice_input` (legacy voice-response path) or the Whisper path reaches the STT pipeline.
4. The response is queued to `VoiceOutputManager` as ONE item, TTS'd (edge-tts→ffmpeg subprocess OR
   Coqui), sent to Rust as `SPEAK:{len}`+WAV; on playback end Rust emits `TTS_DONE`, which **releases
   the Python per-guild lock** (S10).

### Control panel operations (edges A/C/G)
- Panel routes read live `ConversationDynamicsEngine` state (`get_state_for_panel`, `decide_action`),
  `PersonalityState` mood history, and the `bot_state` dict (populated by `init_bot_state` at
  pipeline_initializer:414, served by `start_server(port)` at :427).
- `/api/bot/restart` writes `.restart.signal` (confirm-gated); the hot_reloader subprocess picks it up
  and restarts the bot.
- BackgroundProcessor summarizes RAW batches via the extractor LLM and runs
  `_run_impression_batch` → `get_users_due_impression` + `affect_engine` (edge G).
- PassiveMonitor watches all channels through the canonical MentionTranslator (edge C).

---

## Build / run / test

**Run (any of):**
```bash
python -m serin                          # direct
python discord_bot.py                    # Docker/root path → hot_reloader (auto-restart)
```

**Test:**
```bash
pytest                                   # 40-file suite; contract/lint gates included
cargo build --release --manifest-path scripts/undef-var-scanner/Cargo.toml   # enables Layer-2 Rust scan test
```

**Rust builds (voice requires the binary):**
```bash
cargo build --release --manifest-path voice/rust_receiver/Cargo.toml   # → target/release/voice_receiver
maturin develop                          # serin_core (optional accelerator; bot runs without it)
```

**Lint/tooling gate (CI):** ruff, mypy (strict), pyright, semgrep, import-linter (THE_LAW Rule 5),
bandit, detect-secrets — all shelled out by `tests/test_static_analysis.py`.

**Config:** `serin/d1_4_config_base/d2_1_base_config.py` `BotConfig` (env-driven). The
`RUST_VOICE_RECEIVER_PATH` key is dead — the voice bridge resolves its own binary path.

---

## Cross-cutting reference

- **`CONNECTIONS.md`** — the master edge list (A pipeline→panel observability; B affect→store; C ops→pipeline/;
  D PyO3; F schema conflict; G conversational-state; H dedup clusters; I DI/entry duality; J voice seam),
  shared-state inventory, edge→test pin map, and Phase-5 dedup recommendations.
- Per-subsystem detail: `SUBSYSTEM_*.md` in this directory.