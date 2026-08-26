---
type: source
tags: [source, testing, ci, contracts]
created: 2026-08-26
updated: 2026-08-26
sources: [docs/SUBSYSTEM_tests.md]
verified: 2026-08-26
status: live
---

# Source: SUBSYSTEM_tests.md

Provenance: `docs/SUBSYSTEM_tests.md`. Informs: [[testing]], [[the_law_rule5]].

## Key contents (verified against tree)

- Four test kinds: live unit tests of pipeline/subsystem code; contract/lint suite
  (`test_runtime_contracts.py` 6 layers + `test_static_analysis.py` shell-outs);
  Rust-integration tests (`undef-var-scanner`, `test_bridge.py`); legacy-schema-gated
  `test_fact_belief_gating.py`.
- DI meta-test (`test_di_contracts.py`): whole-tree getter/init reachability scan.
- Pipeline inspector (`tools/pipeline_inspector/`): drives the real 10-stage pipeline
  offline with faked LLM/memory/Discord; caught dropped-planner-constraint wiring bug.
- Known gaps after 2026-08-26: wire-protocol gap CLOSED by Plan 4 integration harness
  (`tests/integration/test_wire_protocol.py`, `test_protocol_sync_guard.py`); live-audio
  DAVE smoke still open (issue #39); PyO3 smoke test still open.
- Route registration guard added 2026-08-26: `tests/server/test_route_uniqueness.py`.

→ [[index]]
