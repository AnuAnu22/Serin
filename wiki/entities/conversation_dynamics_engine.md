---
type: entity
tags: [state, decision, dynamics, persistence]
created: 2026-08-16
updated: 2026-08-26
sources: [docs/SUBSYSTEM_state_core_context.md, docs/CONNECTIONS.md, serin/d1_3_state_core/d2_5_state_conversation/d3_1_dynamics_engine.py]
status: live
---

# ConversationDynamicsEngine

## What it is

A continuous physics simulation that replaces 12 Boolean `should_respond()` rules with
mathematical models — the engine that decides reply / react / ignore and paces timing:

- **Markowitz Portfolio Theory** — global channel attention allocation.
- **Kuramoto Oscillator** — per-channel momentum/phase/frequency.
- **KL Divergence** — topic-shift detection (shatters momentum).
- **Boltzmann Distribution** — action selection (reply/react/ignore).
- **Hawkes Process** — response/reaction timing.

`observe_message()` is called for EVERY message the bot sees. Hard overrides (creator,
@mention, bot-name) are checked BEFORE the engine. Exposes `get_state_for_panel()` for the
control panel.

## Where it lives

`serin/d1_3_state_core/d2_5_state_conversation/d3_1_dynamics_engine.py`

## A THREE-subsystem shared object (CONNECTIONS G)

- **d1_1 ingest** (`d4_4_core_manager.py:141`) constructs it and passes it into the message
  pipeline; act stages consult it for decision/timing.
- **d1_1 act** stages (`d4_1_decision_temporal.py`, `d5_2_dispatch_send.py`) read it.
- **d1_5 ops** reads it live: `get_state_for_panel()` (debug routes), `decide_action`
  (personality routes), `allocate_attention()` (background maintenance).

## Persistence (added 2026-08-26)

The engine's per-channel physics state survives restarts via the `channel_dynamics`
SQLite table (authoritative DDL in `d4_3_schema_store.py`; row functions in
`d4_1_core_storage/d5_4_dynamics_store.py`):

- **Boot**: `d4_4_core_manager` calls `load_persisted_snapshots()` +
  `restore_from_snapshots()` right after constructing the engine — momentum,
  phase, frequency, temperature, message history, word counts, and participants
  are rebuilt before the first message flows.
- **Write path**: `flush_to_store(store)` upserts every observed channel; called
  throttled (`FLUSH_INTERVAL_S = 60`) and force-flushed by `run_maintenance()`
  and by `main()`'s shutdown `finally` (covers hot_reloader SIGTERM restarts).
- **Layering**: d1_3 engine → d1_1 store functions via function-scoped import,
  duck-typed `store.conn` — the same edge-B pattern as [[bayesian_beliefs]]'
  AffectEngine; no depth-DAG violation (import-linter green).
- **Causality compliance**: restore is deterministic state rehydration — clamps
  only guard against corrupt rows, never re-roll behavior. Pinned by
  `tests/test_dynamics_persistence.py` (roundtrip, malformed-row degradation,
  throttle, identical-state-after-restore).

## Notes / Known issues

- Uses stdlib `logging.getLogger("serin")` directly — note this is the SAME
  logger object `d2_3_core_logger.setup()` configures (verified 2026-08-26);
  the historical "divergence" concern was about configuration order, not a
  separate logging pipeline.
- Energy equations pinned by `tests/test_boltzmann_bias.py`; the decision stage's selectivity
  (ambient stranger messages ignored by default) verified by the pipeline inspector.

## See also

[[message_pipeline]] · [[message_flow]] · [[causality_not_performance]] · [[index]]
