---
type: overview
tags: [architecture, layers, wiring]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/ARCHITECTURE.md, docs/CONNECTIONS.md, docs/THE_LAW.md, docs/README.md]
status: seed
---

# Architecture Overview

Serin is a Discord AI companion: text + voice through a 10-stage message pipeline, Qdrant vector
memory + SQLite, a Bayesian belief/evidence system, affect & conversation-dynamics engines, an
OpenAI-compatible LLM backend (llama-swap/vLLM/Ollama), and a Rust voice subprocess for
DAVE-decryption + playback. A FastAPI control panel streams live telemetry over WebSockets.

## Five layers (`d1_1` … `d1_5`, in dependency order)

| Layer | Role | Key contents |
|---|---|---|
| `d1_1_pipeline_flow` | The feeders: ingest → perceive → think → remember → act | 10-stage act DAG, EnhancedMessageManagerV3, Bayesian schema, response generator/personality, `d1_1_serin_di.py` (composition root) |
| `d1_2_gateway_io` | I/O boundaries | discord_bot + on_ready/on_message + PipelineInitializer + main_entry; voice system (RustVoiceBridge, AudioStreamProcessor, TTS); transcribe (Whisper, VoiceMemoryPipeline) |
| `d1_3_state_core` | Shared state (lowest layer) | logger, core memory (QdrantMemorySystem, BM25, belief/evidence stores), model system (LLM connector + thinking filter), core voice (VoiceTracker, voice_profiles), conversation state (MessageContext, ConversationDynamicsEngine, AffectEngine) |
| `d1_4_config_base` | `BotConfig` singleton + debug logger | env-driven config; stale `RUST_VOICE_RECEIVER_PATH` key (see [[known_debt]]) |
| `d1_5_ops_tooling` | Operational machinery | LIVE control panel (`d3_2_panel_server`), BackgroundProcessor, hot reloader, PassiveMonitor, TTSVoiceManager |

Rules of the tree (see [[the_law_rule5]]): a file may only import from strictly shallower depth
digits; a single composition root (`d1_1_serin_di.py`) owns all pipeline/state class imports
(see [[gateway_isolation]]).

## Subsystem map (14 → `docs/SUBSYSTEM_*.md`)

Ordered by inbound-edge count (foundational first): config_base → state_core_db →
state_core_context → wiring_entry_di → pipeline_remember → pipeline_think → pipeline_act →
pipeline_ingest → gateway_discord → gateway_voice → gateway_transcribe → ops_tooling →
rust_accel → tests. Full one-liner table in `docs/ARCHITECTURE.md`.

## Entry duality (both canonical)

- `python -m serin` → `serin/__main__.py` → `d4_1_main_entry.main()` — direct run: 5-attempt
  exponential-backoff retry, db_protect error handlers, clean shutdown.
- `python discord_bot.py` (repo root) → `auto_start_qdrant()` (Docker) → `d2_3_hot_reloader.main()`
  — spawns the bot as a watched subprocess (auto-restart on `*.py`, `cargo build`/maturin,
  `.restart.signal` file from the panel).

Both terminate in `main()` in `d4_1_main_entry.py` (gateway pipeline_init dir — a common
mis-remembering; it is NOT in config_base).

## Notable structural surprise

The control panel (`d1_5`) is imported by the pipeline (`d1_1`) — the highest layer is reached
**down** from the core loop (CONNECTIONS edge A, observability pipe). Every cross-layer import in
the codebase is function-scoped inside a method to keep Rule-5 legal.

## See also

[[message_flow]] · [[voice_flow]] · [[testing]] · [[known_debt]] · [[serin_di]] · [[index]]
