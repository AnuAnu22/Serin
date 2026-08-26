---
type: overview
tags: [debt, dead-code, stale]
created: 2026-08-16
updated: 2026-08-25
sources: [docs/CONNECTIONS.md, docs/todo.md, docs/ENGINEERING_STANDARDS.md, docs/SUBSYSTEM_ops_tooling.md]
status: live
---

# Known Debt & Dead Code

Consolidated from CONNECTIONS.md (Phase-4 deep passes), todo.md, and ENGINEERING_STANDARDS.md.
Anything with a fix recommendation is ranked roughly by impact.

## Dead code clusters (dedup candidates — CONNECTIONS H)

- **~~Two dead control-panel worlds~~ RESOLVED 2026-08-26**: `d3_1_panel_panels/` +
  `d3_4_panel_routes.py` deleted (zero-importer proof + full gates).
- **~~Duplicate live status routes~~ RESOLVED 2026-08-26**: `d4_7_state/d5_3_server_status`
  deleted. CORRECTION of this page's earlier claim: Starlette serves the **FIRST**-registered
  handler, so it was `d5_3` that was mounted-but-dead, not `d5_2`; `debug_routes` importing
  the d5_2 helpers was always consistent with what HTTP actually served. Live probe:
  duplicate `/api/status` registrations answer with the first handler. Guarded now by
  `tests/server/test_route_uniqueness.py` (no path may register twice; canonical handlers
  pinned to `d5_2_server_state`).
- **~~MentionTranslator twins~~ RESOLVED 2026-08-26**: the `d1_3 core_voice` copy deleted
  (pipeline copy canonical; zero-importer verified repo-wide).
- **~~VoiceProfileManager duplicate~~ RESOLVED 2026-08-26**: gateway `d4_1_models_profiles`
  deleted; canonical twin is `d1_3 ... d3_3_voice_profiles.py`. Follow-up: `d6_2_missing_routes_voice`
  had FOUR lazy imports of a **phantom path** (`serin.d1_3_state_core.voice.voice_profiles` — never
  existed, errors swallowed by except) — repointed to the canonical module, top-level imports,
  API drift repaired (`create_voice_profile`→`create_profile`, `delete_voice_profile`→`delete_profile`).
- **~~Dead bridge recovery~~ RESOLVED 2026-08-26**: `d4_3_bridge_recovery.py` deleted.
- **Legacy belief stores**: `d1_1 d2_4_flow_remember` `d5_1_belief_beliefs` +
  `d5_2_belief_evidence` + `d4_3_memory_quality` + `d4_4_knowledge_retrieval` — nothing
  imports them except `tests/test_fact_belief_gating.py` (tracked in git as of 2026-08-25;
  it was untracked when this page was seeded — see [[bayesian_beliefs]]).
- **Dead bridge recovery**: `d3_2_bridge_io/d4_3_bridge_recovery.py` (0 importers).

## Vendored-songbird patch — guarded (was: dies silently on re-vendor)

The ClientConnect SSRC-mapping patch ([[dave_receive]]) was the one behavioral
patch in `voice/rust_receiver/vendor/songbird` and died silently on any
re-vendor. **Guarded 2026-08-25**:

- `tests/test_songbird_patch_contract.py` — fails CI if `[patch.crates-io]`
  disappears, Cargo.lock resolves songbird from the registry, or the patched
  lines vanish from `ws.rs` / `events/core.rs` / `events/context/mod.rs`.
- CI job `voice-receiver` (`.github/workflows/test.yml`) runs
  `cargo check --locked` on the crate — a broken vendor tree fails loudly.
- Runtime loudness: Rust emits `UNKNOWN_SSRC ssrc=…` (once per SSRC) when audio
  falls back to raw-SSRC attribution; Python (`d4_1_io_bridge.py`
  `_RawSsrcWarner`) warns `voice.raw_ssrc_attribution` on any AUDIO/JOIN whose
  "user id" is below 2^32 (real snowflakes always exceed u32).
- `hot_reloader.get_mtimes()` also watches `vendor/songbird/src/**`, so patch
  edits trigger rebuilds like `src/` changes.

Remaining exit strategy: upstream the ClientConnect patch so the vendor tree can
be dropped by design (docs/wiki/songbird-clientconnect-patch.md § Maintenance warning).

## Stale config & stale refs

- ~~`RUST_VOICE_RECEIVER_PATH`~~ RESOLVED 2026-08-26: deleted from `d2_1_base_config.py`
  (pointed at a wrong default, no code read it — RustVoiceBridge computes its own binary
  path; panel frontend key-list updated to match. See [[bot_config]]).
- db_protect (`d3_2_protect_core.py`) hardcodes ChromaDB dirs + a `required_tables` list that
  lags the real (Bayesian) schema; the d1_3 `d3_4_memory_store.py` CREATE TABLE is a stale
  legacy-schema duplicate of the authoritative `d4_3_schema_store` (CONNECTIONS F).
  NOTE 2026-08-26: verified `required_tables = ['users','relationships','recent_messages']`
  all exist in the live schema — only the ChromaDB dir machinery is stale; full excision of
  db_protect's chroma paths queued as follow-up (own commit, has tests to migrate).
- ~~`docs/troubleshooting_guide.md` + `docs/deployment_checklist.md` reference the pre-Qdrant
  ChromaDB world~~ RESOLVED 2026-08-26: both rewritten for Qdrant/SQLite.

## Architecture governance gaps (docs-level conflicts)

- **THE_LAW ideal vs. real tree**: THE_LAW.md describes `pipeline/gateway/state/config/ops`
  with a root DI; the verified tree is `d1_1…d1_5` numbered dirs. The checks
  (`scripts/law/check_structure.py`, `check_imports.py`) target the real layout; the prose
  targets the ideal. See [[the_law_rule5]].
- **ENGINEERING_STANDARDS.md target restructure** (`cognition/`, `memory/`, `personality/`,
  split of the 1896-line qdrant.py-era god object) is *planned, not done*; the docs note
  "this is the next restructure, not yet done".

## Still-over-500-line files (todo.md)

~~Worst offenders at migration time: memory store ~1500, control-panel server ~1400, ingest
manager ~1050, voice bridge ~940, database protector ~920, Discord bot entry ~820, audio
processor ~830.~~ **RESOLVED — re-measured 2026-08-25**: no `.py` under `serin/` exceeds the
500-line ceiling anymore (largest: `d4_4_core_manager.py` at 478). No directory violates the
5-files/5-subdirs horizon either.

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