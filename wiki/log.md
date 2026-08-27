# Serin Wiki — Log

Append-only chronology (`## [YYYY-MM-DD] <op> | <title>`). Latest first.

## [2026-08-26] ingest | Goals engine C3 - pursuit reaches the live pipeline
C3 of [[goals_engine]]: goals now CAUSE behavior through accumulated state. ResponseDecisionStage
gets goals_engine and a _goal_salience_bonus helper (0.10 x salience per active goal, bounded,
deterministic, no RNG) that lifts engagement salience; it also records ctx.metadata[active_goals].
ResponsePlannerStage gets goals_engine and injects the top active goal verbatim as a binding
constraint + ctx.response_plan[active_goals] (slots ahead of per-message belief constraints but
honors the 3-slot cap). Pipeline build() gained a goals_engine param threaded into both stages,
and the initializer passes the managers engine (mirrors dynamics/affect). Tests:
tests/test_goals_pursuit.py (6 tests: bonus math, metadata surfacing, verbatim constraint, cap
priority, no-engine noop). Docs synced: SUBSYSTEM_pipeline_act stage list. ruff + mypy strict +
structure gates green; 40 tests pass across goals layers.

## [2026-08-26] ingest | Goals engine C4 - persistence (boot restore + shutdown flush)
C4 of [[goals_engine]]: goals now SURVIVE restarts (SERIN_VISION Growth - accumulated
state outlives the process). GoalsEngine gained restore_from_store() and
flush_to_store(force=False) mirroring ConversationDynamicsEngine. Boot: core_manager
folds goals-engine creation into the dynamics restore try and calls
restore_from_store() (loads live rows, verifies schema round-trips, logs count). Shutdown:
main_entry finally-block calls flush_to_store(force=True) which issues a final COMMIT
so a hot reload SIGTERM cannot strand uncommitted goal rows. Mutations write through
to the DB immediately, so flush is a durability barrier, not a state transfer. Tests:
tests/test_goals_persistence.py (5 tests: restore loads live/skips terminal, never raises
on broken store, throttle vs force, broken-store noop, interval constant). ruff + mypy
strict + law structure green; 35 goals tests pass.

## [2026-08-26] ingest | Goals engine C2 — formation + review machinery wired
C2 of [[goals_engine]]: `d3_4_goals_engine.py` (GoalsEngine) added to d1_3 state layer with
`build_formation_prompt`/`parse_formation` (verbatim, clamps salience, rejects malformed/empty/
overlong), `review_due` (deterministic decay; auto-drop below floor), `promote_ready`,
`pursuit_snapshot`, `touch_on_mention` (reinforcement from conversation overlap). Wired into
`EnhancedMessageManagerV3` (shared with pipeline + BackgroundProcessor via the dynamics/affect
pattern) and into `run_maintenance` via new `_run_goals_maintenance()` — threshold-gated by
material volume, live-goal cap (MAX_ACTIVE_GOALS=5), and LLM connectivity. Tests:
tests/test_goals_engine.py (13 tests: parse variants, decay/drop, promotion, pursuit, touch,
stats). Docs synced: SUBSYSTEM_state_core_context (d3_4 section), SUBSYSTEM_ops_tooling
(maintenance note), SUBSYSTEM_pipeline_remember (carried to currency in C1). Law-compliant
(d4_4_core_manager held at 497 lines; trimmed pre-existing comment blocks).

## [2026-08-26] ingest | Goals engine C1 — schema + storage layer
Landed the storage half of the goals engine ([[goals_engine]]): `goals` + `goal_evidence`
DDL added to the authoritative schema (`d4_3_schema_store.py`; status CHECK state machine,
salience, provenance, parent links), row functions in new package
`d4_1_core_storage/d5_6_goal_storage/d6_1_goals_store.py` (Rule-1-compliant split;
duck-typed store contract like d5_4_dynamics_store). Machinery only - statements stored
verbatim, no curation layer. Pinned by tests/test_goals_store.py (12 tests). Updated
SUBSYSTEM_pipeline_remember.md to full currency (added previously missing d5_4/d5_5
sections + user_mood_state/channel_dynamics/pipeline_runs table inventory) and
[[qdrant_memory_system]].
## [2026-08-26] ingest+lint | First source ingest (6 pages) + debt corrections
INGEST of the six major docs into `wiki/sources/`: [[source_architecture]],
[[source_connections]], [[source_the_law]], [[source_serin_vision]],
[[source_subsystem_tests]], [[source_voice_wiki_research]] — each with provenance,
verified-today key contents, and contradiction flags; index Sources section filled
(previously "None yet"). LINT corrections in the same pass: [[known_debt]] status-route
shadowing direction fixed (Starlette serves FIRST handler — d5_3 was dead, not d5_2;
live-probe verified) and all CONNECTIONS-H clusters marked resolved after the 2026-08-26
dedup commits (panel worlds, d5_3 routes, both twins, bridge_recovery, stale config key);
[[testing]] wire-framing gap marked closed (Plan 4 harness landed); [[bot_config]] entity
updated for the purged RUST_VOICE_RECEIVER_PATH key.
## [2026-08-26] query | Dynamics Persistence Plan
Filed `wiki/queries/2026-08-26_dynamics_persistence_plan.md` after implementing
SQLite persistence for `ConversationDynamicsEngine`: new `channel_dynamics`
table in the authoritative schema (`d4_3_schema_store.py`), row functions in
new `d4_1_core_storage/d5_4_dynamics_store.py` (extracted to respect the
Rule-2 500-line ceiling on `d5_2_sqlite_store.py`; storage dir 4→5 files,
Rule-1 compliant), snapshot/restore/throttled-flush methods on the engine,
boot-restore in ingest core_manager, force-flush in run_maintenance +
main() shutdown (covers hot-reloader SIGTERM). d1_3→d1_1 access is
function-scoped with a duck-typed store (edge-B). Updated
[[conversation_dynamics_engine]] (status: live), [[index]], CONNECTIONS edge G,
SUBSYSTEM_state_core_context; corrected the "stdlib logger divergence" note
(same logger object `d2_3_core_logger.setup()` configures — verified at
runtime). Gates: ruff/mypy clean, pyright clean on all touched files, semgrep
0 findings, import-linter pass, full suite 652 passed / 3 skipped.
## [2026-08-26] ingest | SMALL_LLM_* seam for Bayesian fact extraction
Implemented the "small LLM" supporting-connector seam that feeds the [[bayesian_beliefs]]
schema: `SMALL_LLM_MODEL/BASE_URL/API_KEY` env keys in `bot_config` (each aliasing the
main LLM when unset), a dedicated `__small__` cache slot in the model-system factory,
and a `serin_di.get_small_llm_connector()` Rule-5 accessor wired into
EnhancedMessageManagerV3 + PipelineInitializer. Positive accumulation path now pinned by
`tests/test_small_llm_accumulation.py` (fact row written; claim_hash corroboration
dedups); negative path unchanged ([[known_debt]] holdout still pins empty tables).
Updated [[message_flow]], [[bot_config]], and docs/ARCHITECTURE.md § message flow.
Gates: ruff/mypy clean, semgrep 0 findings, pyright baseline-neutral, 637+9 tests green.
## [2026-08-25] lint | Stale-claim sweep against live source
Full LINT pass over `wiki/` + `docs/` with every claim re-verified against the live tree
(two-pass: grep + line-level read before each edit). Fixed:
- `overviews/message_flow` — stage 8 no longer lists the deleted `apply_contractions`
  contraction pass (humanizer removal, 2026-08-18); stage 9 SendStage now records the
  `min_send_delay = 0.4` creator-override floor (`d5_2_dispatch_send.py:43-47`) instead of
  "skips dynamics delay".
- `overviews/testing`, `index`, `docs/ARCHITECTURE.md`, `docs/SUBSYSTEM_tests.md` — suite is
  60 files / 52 test modules (was 40); contracts file 539 lines (was 530);
  `test_fact_belief_gating.py` is tracked in git now (was untracked).
- `overviews/known_debt` + `docs/todo.md` — the >500-line file debt and the >5-files-per-dir
  debt are RESOLVED (re-measured 2026-08-25: largest serin file = core_manager at 478; no
  directory violates Rule 1).
- `entities/rust_voice_bridge` — supervision correction: the live `_supervise_rust_process`
  loop has NO timed restart-window enforcement; the "5-restarts/60s" numbers belong to the
  dead `d4_3_bridge_recovery.py` mixin. `start()` span corrected to :116-205.
- `concepts/bayesian_beliefs` — holdout-test tracking status updated.
- `docs/CONNECTIONS.md` — edge-A call-site paths fixed to real locations
  (`d3_1_act_runners/d4_1_runners_dispatch/d5_1_llm_call.py`, `.../d4_3_prompt_assembly/...`)
  with verified line numbers (:28-30, :23-25, :34-37, :260-270), `start()` :116-205,
  `tests/messaging/test_processor.py` path fix.
- `docs/ARCHITECTURE.md` — dead VoiceProfileManager twin's real path noted
  (`d2_3_voice_transcribe/d3_1_transcribe_models/d4_1_models_profiles.py`).

## [2026-08-25] harden | ClientConnect patch tripwires
Guarded the vendored-songbird ClientConnect patch against silent death
([[dave_receive]], [[known_debt]]): new `tests/test_songbird_patch_contract.py`
(Cargo.toml `[patch]` presence + registry-free lockfile resolution + the patched
lines in ws.rs/core.rs/context mod.rs + consumer handling in main.rs); CI
`voice-receiver` job (`cargo check --locked`) in `.github/workflows/test.yml`;
Rust once-per-SSRC `UNKNOWN_SSRC` stderr warning on raw-SSRC fallback; Python
`_RawSsrcWarner` in `d4_1_io_bridge.py` warning `voice.raw_ssrc_attribution`
for sub-2^32 user ids; hot_reloader now watches `vendor/songbird/src/**`.
Also repaired `tests/integration/test_bridge.py` (missing gateway-DI bootstrap —
both bridge tests had been failing since the DI refactor; suite now 629 passed,
3 skipped, 0 failed).

## [2026-08-16] scaffold | Serin Project Wiki
Created the wiki at `wiki/`: schema (SCHEMA.md), index, log, five overviews
(architecture, message_flow, voice_flow, testing, known_debt), seven entity pages
(message_pipeline, conversation_dynamics_engine, qdrant_memory_system, serin_di,
enhanced_message_manager_v3, rust_voice_bridge, bot_config), and five concept pages
(bayesian_beliefs, the_law_rule5, dave_receive, causality_not_performance, gateway_isolation).
All seed pages distilled from a full read of `docs/` (ARCHITECTURE, CONNECTIONS, THE_LAW,
SERIN_VISION, SUBSYSTEM_*, the voice wiki, superpowers) on 2026-08-16. No sources category yet —
first INGEST pass should add the major docs as `source` pages.
## [2026-08-18] query | Vision-to-Code Fix Plan
Filed `wiki/queries/2026-08-18_vision_to_code_fix_plan.md` after implementing the approved
fix plan (docs/SERIN_VISION.md "Operational Definitions" now governs). Removed the RNG
humanizer module (`d4_1_personality_humanization.py` deleted), made `can_disagree` and
`_express_unknown` deterministic, rewrote `detect_topic_stance` (textual-order markers +
pronoun referents), fixed planner M3/M4, added SendStage latency floor, replaced scripted
fallbacks, graduated `_affect_context` familiarity ramp, and added semgrep rules
`no-performative-randomness` + `no-mood-directive`. Verified: ruff/mypy clean, 7 semgrep
rules 0 findings, targeted suites green, full suite 623 passed (2 pre-existing documented
failures: A1 affect-engine event-loop flake; semgrep test blocked by sandbox read-only
`~/.semgrep` — passes when HOME is writable).