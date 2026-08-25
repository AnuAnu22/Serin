---
type: query
tags: [dynamics, persistence, causality, sqlite, restart]
created: 2026-08-26
updated: 2026-08-26
sources: [docs/SERIN_VISION.md, docs/CONNECTIONS.md, serin/d1_3_state_core/d2_5_state_conversation/d3_1_dynamics_engine.py]
status: live
---

# Dynamics Persistence Plan (2026-08-26)

## What it is

Filed analysis + implementation record: `ConversationDynamicsEngine` held all
per-channel physics state (Kuramoto phase/momentum, Hawkes timing history,
word counts, participants) **in RAM only** — every restart (including the
hot_reloader's per-.py-change respawns) reset the simulation to zero. This
contradicted SERIN_VISION ("Growth: not the same entity today as next month")
and [[causality_not_performance]] (behavior from *persistent accumulated*
state). Sibling engines already persisted ([[bayesian_beliefs]] affect via
`user_affect`, personality mood via `user_mood_state`) — the decision engine
was the gap.

## What was implemented

| Piece | Where | Notes |
|---|---|---|
| `channel_dynamics` table | `d4_3_schema_store.py` | Authoritative DDL; one row/channel; JSON payloads for times/words/participants |
| Row functions | `d4_1_core_storage/d5_4_dynamics_store.py` | New file — `d5_2_sqlite_store.py` was near the Rule-2 500-line ceiling; dir went 4→5 files (Rule-1 compliant) |
| Engine API | `d3_1_dynamics_engine.py` | `snapshot_persist_state()` (pure), `restore_from_snapshots()` (clamped, corrupt-row-safe), `flush_to_store(store, force)` (60s throttle), static `load_persisted_snapshots(store)` |
| Boot restore | `d4_4_core_manager.py` | Right after engine construction; best-effort (failure never blocks boot) |
| Force flushes | `d3_4_event_handlers.py` (`run_maintenance`) + `d4_1_main_entry.py` (shutdown `finally`) | Covers hot-reloader SIGTERM restarts |

## Layering compliance

d1_3 engine → d1_1 store functions via **function-scoped import** with a
duck-typed `store.conn` — the edge-B pattern AffectEngine already uses
(CONNECTIONS B). import-linter green; mypy strict clean; pyright clean on all
touched files; ruff clean.

## Verification

`tests/test_dynamics_persistence.py` (7 tests): schema pin, roundtrip
equality of momentum/phase/frequency/word_counts/participants, upsert-no-dup,
never-observed-channel skip, malformed-snapshot degradation, restored-state
produces identical decision inputs (the causality pin), throttle behavior.
Full suite: **652 passed, 3 skipped** with writable HOME (the semgrep test's
documented environmental dependency).

## Follow-ups left open

- `delete_stale_channel_dynamics()` exists but nothing schedules it yet —
  natural home is `run_maintenance` once channel-retention policy is decided.
- Panel could surface "restored N channels" as a boot-health indicator.
