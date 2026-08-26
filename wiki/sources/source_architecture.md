---
type: source
tags: [source, architecture, layers]
created: 2026-08-26
updated: 2026-08-26
sources: [docs/ARCHITECTURE.md]
verified: 2026-08-26
status: live
---

# Source: ARCHITECTURE.md

Provenance: `docs/ARCHITECTURE.md`. Distilled 2026-08-26 after tree verification.
Informs: [[architecture]], [[message_flow]], [[voice_flow]], [[serin_di]].

## Key contents (verified against tree)

- Five-layer dependency-ordered tree `d1_1_pipeline_flow` → `d1_2_gateway_io` →
  `d1_3_state_core` → `d1_4_config_base` → `d1_5_ops_tooling`; imports only from
  shallower depths; cross-layer sharing only as constructor args via `serin/d1_1_serin_di.py`.
- Subsystem map with one-liners and per-subsystem doc pointers (SUBSYSTEM_*.md set).
- Entry duality: `python -m serin` direct vs `discord_bot.py` → hot_reloader; both end at
  `d4_1_main_entry.main()`.
- Tooling gate list (ruff/mypy/pyright/semgrep/import-linter/bandit/detect-secrets)
  shelled out by `tests/test_static_analysis.py`.

## Contradictions / drift handled here

- Doc's dead-cluster annotations (panel world, twins, d5_3 routes, dead config key) were
  resolved in code on 2026-08-26 — see [[known_debt]]; annotations updated in the raw doc
  same day (stale-claims-marked policy, not silently rewritten).

→ [[index]]
