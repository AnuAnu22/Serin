---
type: overview
tags: [index, catalog]
created: 2026-08-16
updated: 2026-08-26
sources: [wiki/SCHEMA.md]
status: seed
---

# Serin Wiki — Index

The content catalog for the [[index|wiki]]. Every page lives under `wiki/`. Read this first
for any query, then drill into pages. Categories: overviews · entities · concepts ·
sources · queries.

## Overviews — cross-cutting maps

- [[architecture]] — five `d1_x` layers, subsystem map, entry duality, THE_LAW governance.
- [[message_flow]] — text message → 10-stage pipeline → reply; always-run MemoryWriteStage.
- [[voice_flow]] — Rust subprocess voice receive/send, DAVE, wire protocol, the TTS_DONE lock.
- [[testing]] — 60-file pytest suite (52 test modules): live unit tests, AST contract gates, CI tooling gate, pipeline inspector.
- [[known_debt]] — dead code clusters, stale config, schema conflicts, ideal-vs-real architecture gap; § Vendored-songbird patch records the 2026-08-25 ClientConnect-patch tripwires.

## Entities — concrete components

- [[message_pipeline]] — the 10-stage DAG + runner (`d4_2_runners_pipeline.py`).
- [[conversation_dynamics_engine]] — Boltzmann/Kuramoto/Markowitz decision engine; 3-subsystem shared; channel state persists across restarts (2026-08-26).
- [[qdrant_memory_system]] — Qdrant + BM25 + SQLite; authoritative Bayesian schema hub.
- [[serin_di]] — the Rule-5 composition root / DI container.
- [[enhanced_message_manager_v3]] — the ingest funnel that builds the pipeline per message.
- [[rust_voice_bridge]] — the Python↔Rust voice subprocess seam (`RustVoiceBridge`).
- [[bot_config]] — env-driven `BotConfig` singleton (+ its known stale key).

## Concepts — ideas & principles

- [[bayesian_beliefs]] — the belief/evidence state machine (PENDING→SUPPORTED→CONTESTED).
- [[the_law_rule5]] — depth-DAG import rule, and the ideal-tree-vs-real-tree conflict.
- [[dave_receive]] — the voice-receive saga: DAVE, the vendored songbird patch, the myth-busting.
- [[causality_not_performance]] — the Prime Directive mechanism (state causes behavior, never a die roll).
- [[gateway_isolation]] — gateway code gets objects via factories, never direct imports.

## Sources — distilled raw documents

*None yet. First ingest (per SCHEMA) should capture the major docs: ARCHITECTURE, CONNECTIONS,
THE_LAW, SERIN_VISION, and the `SUBSYSTEM_*.md` set, plus the `docs/wiki/` voice research wiki.*

## Queries — filed answers

- [[2026-08-18_vision_to_code_fix_plan]] — the approved vision-to-code fix plan: what violated "causality, not performance", what changed, and the semgrep enforcement added.
- [[2026-08-26_dynamics_persistence_plan]] — why the dynamics engine forgot everything on restart, and the `channel_dynamics` SQLite persistence added (boot-restore + maintenance/shutdown flushes).

## Special files

- [[SCHEMA]] — the wiki constitution: page types, conventions, ingest/query/lint workflows.
- [[log]] — the append-only chronology of ingests, queries, lint passes, and decisions.