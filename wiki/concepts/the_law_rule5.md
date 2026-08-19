---
type: concept
tags: [law, architecture, rules]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/THE_LAW.md, docs/ARCHITECTURE.md]
status: seed
---

# THE_LAW — Rule 5 (Depth DAG) and the governance ruleset

## What it is

THE_LAW.md is the physical law of the codebase: not a style guide, a set of invariant rules with
no exceptions. Rule 5 (the Depth DAG) is the load-bearing one for layering:
**a file may only import from files with a strictly shallower depth digit** (`d2` can import
`d1`, never `d2`/siblings). Top-level branches share dependencies only via dependency
injection from the composition root (see [[serin_di]], [[gateway_isolation]]).

## The other rules

- **Rule 1 (5/5 Horizon)** — no dir > 5 files + 5 subdirs.
- **Rule 2 (500-line ceiling)** — a `.py` becomes a folder at 501 lines (temp 1-line redirect
  scaffold allowed).
- **Rule 3 (depth-sequence naming)** — `d{depth}_{seq}_{word}_{word}`; the name is the address.
- **Rule 4 (Buoyancy)** — general concerns float to depth 1; the import-grep decides, not you.
- **Rule 6** — required file section anatomy (Imports/Types/Constants/Entry/Core/Helpers/Errors).
- **Rule 7** — no junk drawers (`utils/`, `helpers/`, `common/`, ...).

## Verification

`scripts/law/check_structure.py` (Rules 1-3) + `check_imports.py` (Rule 5) run in CI and via
`test_static_analysis.py` / import-linter. A green hook is the definition of "follows the Law."

## ⚠️ Known contradiction (flag, don't resolve)

THE_LAW's prose describes the IDEAL tree (`serin/pipeline/ gateway/ state/ config/ ops` with a
root DI in `discord_bot.py`) — but the VERIFIED live tree (ARCHITECTURE.md, 2026-08-11) is the
`d1_1…d1_5` numbered layout. The checks target the real layout; the prose targets the ideal.
Both are authoritative in their own frame; the wiki records the verified tree as ground truth and
THE_LAW as the ruleset it obeys. (See [[known_debt]].)

## See also

[[architecture]] · [[serin_di]] · [[gateway_isolation]] · [[known_debt]] · [[index]]
