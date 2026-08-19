---
type: concept
tags: [architecture, di, gateway]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/SUBSYSTEM_wiring_entry_di.md, docs/CONNECTIONS.md, docs/THE_LAW.md]
status: seed
---

# Gateway Isolation (Rule-5 DI seam)

## What it is

The composition rule that keeps the gateway layer (d1_2) from importing pipeline/state classes:
the gateway gets objects **only** through `create_*`/`get_*` factories on [[serin_di]], the
single composition root. Gateway code may call a factory; it may not import and instantiate the
class directly.

## Why it matters

- Enforces [[the_law_rule5]] mechanically — the Depth DAG is meaningless if the gateway can
  reach down and construct anything.
- Keeps the dependency graph a DAG; the same rule is why every cross-layer import in the
  codebase is function-scoped inside a method.
- Makes testing possible: `test_di_contracts.py` scans the whole tree for read-but-never-written
  DI slots (getters that would raise RuntimeError at runtime).

## The second meaning: voice

The same word applies to the voice architecture: py-cord owns the single gateway connection;
the Rust `voice_receiver` deliberately runs **without** its own gateway client
([[gateway-less-voice-driver]], [[dave_receive]]) — a second gateway shard would cause session
invalidation and event races.

## See also

[[serin_di]] · [[the_law_rule5]] · [[architecture]] · [[index]]
