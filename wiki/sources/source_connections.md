---
type: source
tags: [source, edges, seams, dedup]
created: 2026-08-26
updated: 2026-08-26
sources: [docs/CONNECTIONS.md]
verified: 2026-08-26
status: live
---

# Source: CONNECTIONS.md

Provenance: `docs/CONNECTIONS.md` (FINALIZED Phase 4 + Phase-5 recommendations).
Informs: [[known_debt]], [[rust_voice_bridge]], [[qdrant_memory_system]], [[bayesian_beliefs]].

## Key contents

- Section H — dedup clusters: panel worlds, duplicate status routes, MentionTranslator
  twins, VoiceProfileManager twin, legacy belief stores, bridge recovery. STATUS after
  2026-08-26 session: all resolved except legacy belief stores (kept deliberately;
  `tests/test_fact_belief_gating.py` imports them — decision flagged to owner).
  CORRECTION recorded: Starlette serves FIRST-registered route; original shadowing
  direction was backwards; guarded by `tests/server/test_route_uniqueness.py`.
- Section J — live Python↔Rust seam: `RustVoiceBridge.start()` self-resolves binary,
  spawns subprocess, line-framed IPC; AudioStreamProcessor is a delegating façade.
- Section F — legacy-vs-Bayesian schema conflict lives in state_core_db.
- Phase-5 recommendations: items 1–3 executed 2026-08-26 (dedup commits); belief-store
  migration awaiting decision.

→ [[index]]
