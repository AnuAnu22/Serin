---
type: overview
tags: [debt, dead-code, stale]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/CONNECTIONS.md, docs/todo.md, docs/ENGINEERING_STANDARDS.md, docs/SUBSYSTEM_ops_tooling.md]
status: seed
---

# Known Debt & Dead Code

Consolidated from CONNECTIONS.md (Phase-4 deep passes), todo.md, and ENGINEERING_STANDARDS.md.
Anything with a fix recommendation is ranked roughly by impact.

## Dead code clusters (dedup candidates — CONNECTIONS H)

- **Two dead control-panel worlds**: `d3_1_panel_panels/` (6 files) + `d3_4_panel_routes.py`
  — zero importers. LIVE = `d3_2_panel_server/` only.
- **Duplicate live status routes**: `d4_7_state/d5_2_server_state` AND `d5_3_server_status`
  both register `/ /api/status /api/stats /api/health`; `d5_3` is side-effect-imported LAST
  and **shadows** `d5_2` at runtime while `debug_routes` still uses the `d5_2` copies.
- **MentionTranslator twins**: keep the pipeline copy
  (`d1_1 ... d4_3_mention_translator.py`); the `d1_3 core_voice` copy is dead (all ~10 import
  sites use the pipeline copy).
- **VoiceProfileManager duplicate**: gateway `d4_1_models_profiles` has zero importers;
  canonical twin is `d1_3 ... d3_3_voice_profiles.py`. `d6_2_missing_routes_voice` imports
  the wrong (dead) one.
- **Legacy belief stores**: `d1_1 d2_4_flow_remember` `d5_1_belief_beliefs` +
  `d5_2_belief_evidence` + `d4_3_memory_quality` + `d4_4_knowledge_retrieval` — nothing
  imports them except the untracked `tests/test_fact_belief_gating.py` (see [[bayesian_beliefs]]).
- **Dead bridge recovery**: `d3_2_bridge_io/d4_3_bridge_recovery.py` (0 importers).

## Stale config & stale refs

- `RUST_VOICE_RECEIVER_PATH` in `d2_1_base_config.py` points at a wrong default path and no
  code reads it — RustVoiceBridge computes its own binary path (see [[bot_config]]).
- db_protect (`d3_2_protect_core.py`) hardcodes ChromaDB dirs + a `required_tables` list that
  lags the real (Bayesian) schema; the d1_3 `d3_4_memory_store.py` CREATE TABLE is a stale
  legacy-schema duplicate of the authoritative `d4_3_schema_store` (CONNECTIONS F).
- `docs/troubleshooting_guide.md` + `docs/deployment_checklist.md` reference the pre-Qdrant
  ChromaDB world (e.g. `enhanced_api_routes.py`, `USE_QDRANT`) — stale.

## Architecture governance gaps (docs-level conflicts)

- **THE_LAW ideal vs. real tree**: THE_LAW.md describes `pipeline/gateway/state/config/ops`
  with a root DI; the verified tree is `d1_1…d1_5` numbered dirs. The checks
  (`scripts/law/check_structure.py`, `check_imports.py`) target the real layout; the prose
  targets the ideal. See [[the_law_rule5]].
- **ENGINEERING_STANDARDS.md target restructure** (`cognition/`, `memory/`, `personality/`,
  split of the 1896-line qdrant.py-era god object) is *planned, not done*; the docs note
  "this is the next restructure, not yet done".

## Still-over-500-line files (todo.md)

Worst offenders at migration time: memory store ~1500, control-panel server ~1400, ingest
manager ~1050, voice bridge ~940, database protector ~920, Discord bot entry ~820, audio
processor ~830 — re-measure with the Law checkers before splitting.

## Known behavioral debt (from the response-generation critique)

- ~~Two cleaning paths (generator ~400-char truncation vs. `ResponseCleaningStage` 2000) can
  disagree.~~ **RESOLVED 2026-08-18** — `ResponseCleaningStage` now delegates to the single
  canonical `clean_response` (`MAX_RESPONSE_LENGTH` = Discord's 2000-char hard limit) instead of
  duplicating its token list; see [[2026-08-18_vision_to_code_fix_plan]].
- ~~Scripted fallbacks (`"brain.exe stopped working"` trio) are fingerprintable bot tells.~~
  **RESOLVED 2026-08-18** — replaced with confused-human fallbacks (see
  [[2026-08-18_vision_to_code_fix_plan]]).
- ~~Post-hoc RNG humanization (typos/fillers) manufactures imperfection rather than letting a
  coherent voice emerge.~~ **RESOLVED 2026-08-18** — the humanizer module was deleted; see
  [[2026-08-18_vision_to_code_fix_plan]] and [[causality_not_performance]].

## See also

[[architecture]] · [[bayesian_beliefs]] · [[index]]