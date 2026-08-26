---
type: source
tags: [source, law, structure]
created: 2026-08-26
updated: 2026-08-26
sources: [docs/THE_LAW.md]
verified: 2026-08-26
status: live
---

# Source: THE_LAW.md

Provenance: `docs/THE_LAW.md` (256 lines). Informs: [[the_law_rule5]], [[architecture]],
[[serin_di]].

## Key contents

- Root shape law: two entry points + pyproject/README + serin/tests/scripts — nothing else.
- Directory horizon 5/5; file ceiling 500 lines; `d{depth}_{seq}_{word}_{word}` naming;
  every dir needs `__init__.py` docstring; no lazy imports (AGENTS.md codifies).
- Rule 5 layer DAG (config→state→pipeline→gateway→ops) enforced by import-linter;
  gateway gets objects via factories/DI, never direct imports ([[gateway_isolation]]).
- Init-pipeline contract: `bot_pipeline_init.on_ready()` annotated-variable discipline
  gives mypy/pyright free verification of component wiring.
- Pitfalls table: stale kwargs, moved-class imports, forward refs, `X | None` style.

## Contradictions / drift handled here

- Ideal-tree diagram vs real tree conflict tracked in [[the_law_rule5]] — unchanged.

→ [[index]]
