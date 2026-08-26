---
type: overview
tags: [testing, ci, contracts]
created: 2026-08-16
updated: 2026-08-25
sources: [docs/SUBSYSTEM_tests.md, docs/TESTING_PIPELINE.md, docs/README.md]
status: live
---

# Testing & CI Overview

A 60-file pytest suite (52 test modules; re-counted 2026-08-25 — it was 40 files at the
2026-08-16 seeding) in four distinct kinds of test:

1. **Unit tests of LIVE pipeline/subsystem code** (the majority) — affect, decision,
   memory-retrieval, personality, perception, memory stores, voice audio constants, panel.
2. **Contract/lint suite** — `test_runtime_contracts.py` (539 lines as of 2026-08-25, 6 layers) and
   `test_static_analysis.py` (120 lines): AST structural checks + shell-outs to
   ruff/mypy/pyright/semgrep/import-linter/bandit/detect-secrets.
3. **Rust-integration tests** — the `undef-var-scanner` CLI (Layer 2) + `test_bridge.py`
   (RustVoiceBridge missing-binary path).
4. **One test gated on the DEAD legacy schema** — `test_fact_belief_gating.py` (tracked in git;
   it was untracked at Phase-4 time; CONNECTIONS F — see [[known_debt]]).

## The 6-layer structural gate (`test_runtime_contracts.py`)

- **L1** whole-tree import (any import-time crash fails).
- **L2** Rust undefined-var scan (skips if binary not built).
- **L3** self-attr contract for standalone `self:` functions (AST-level CONNECTIONS J check).
- **L4** dict-key contract (`build_context` keys ⊇ `format_context_for_llm` accesses).
- **L5** voice TTS contracts (`guild_id` passthrough; no-silent-except).
- **L6** no-silent-except across 7 voice-pipeline files.

## DI meta-test (`test_di_contracts.py`)

Scans every `.py` for the `def get_X(...) → raise RuntimeError` getter pattern, finds the
matching `set_X`/init, asserts it's called somewhere — whole-tree DI reachability.

## CI tooling gate (`test_static_analysis.py`)

ruff (zero errors), mypy (strict), pyright (must not crash), semgrep (custom rules), import-linter
(Rule 5 layers), bandit (skip B101), detect-secrets (baseline). See also [[the_law_rule5]].

## Pipeline Inspector (`tools/pipeline_inspector/`)

A dev tool that drives the REAL 10-stage `MessagePipeline` with synthetic input — faked LLM/
memory/Discord, real stage classes — and lets you inspect/dump/diff/assert/mutate ctx at any
stage boundary, fully offline (dry mode). Caught real wiring bugs static analysis missed
(dropped planner constraints). Run: `uv run python -m tools.pipeline_inspector --content "..." --checks ...`.
Suite: `uv run python -m pytest tests/inspector/ -q`.

## Known gaps

- ~~No real `voice_receiver` subprocess integration test~~ **CLOSED 2026-08-26** (Plan 4,
  commit `96df250`): `tests/integration/test_wire_protocol.py` + `test_protocol_sync_guard.py`
  drive the real framer/parser against main.rs-pinned frames; live-audio DAVE smoke still open
  (tracked in GitHub issue #39).
- No `serin_core` PyO3 smoke test — last explicit gap in the suite (imports as an empty
  namespace package locally, so `hasattr` guards are load-bearing).
- Run non-integration tests: `uv run pytest tests/ -m "not integration" -q`.

> ⚠️ SUPERSEDED (2026-08-25): the songbird-patch "dies silently on re-vendor" risk is now
> guarded by `tests/test_songbird_patch_contract.py` + a CI `voice-receiver` job — see
> [[known_debt]] § Vendored-songbird patch.
> ⚠️ CORRECTED (2026-08-26): the wire-framing gap above was listed as open after Plan 4 had
> already closed it — verification against the tree before trusting this page's gap list.

## See also

[[architecture]] · [[known_debt]] · [[index]]
