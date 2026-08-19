---
type: entity
tags: [state, decision, dynamics]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/SUBSYSTEM_state_core_context.md, docs/CONNECTIONS.md]
status: seed
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

## Notes / Known issues

- Uses stdlib `logging.getLogger("serin")` directly, NOT the custom `d2_3_core_logger` —
  a noted divergence from the rest of the codebase.
- Energy equations pinned by `tests/test_boltzmann_bias.py`; the decision stage's selectivity
  (ambient stranger messages ignored by default) verified by the pipeline inspector.

## See also

[[message_pipeline]] · [[message_flow]] · [[causality_not_performance]] · [[index]]
