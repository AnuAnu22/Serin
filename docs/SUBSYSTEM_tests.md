# SUBSYSTEM: tests — the 60-file pytest suite (what it pins, what it misses)

Checklist: 40/40 files read at Phase-4 time (2026-08-11); re-counted 2026-08-25 the suite is now
60 `.py` files (52 test modules + inits + conftest). Status: DRAFT (wip).
Finalize name: `SUBSYSTEM_tests.md`.

Root: `tests/`

## Scope & role in the system

The test suite is **not** a homogeneous unit-test layer — it's four distinct kinds of test, and the mix is the story:

1. **Unit tests of LIVE pipeline/subsystem code** (the majority) — affect, decision, memory-retrieval, personality, perception, memory stores, voice audio constants, control panel.
2. **The contract/lint suite** — `test_runtime_contracts.py` (539 lines as of 2026-08-25) and `test_static_analysis.py` (120 lines): AST-based structural checks over the whole `serin/` tree plus shell-outs to ruff/mypy/pyright/semgrep/import-linter/bandit/detect-secrets.
3. **The Rust-integration tests** — `test_runtime_contracts.py` invokes the **`undef-var-scanner` Rust binary** (Layer 2), and `test_bridge.py` exercises the RustVoiceBridge Python half.
4. **One test gated on the DEAD legacy schema** — `test_fact_belief_gating.py` (tracked in git since 2026-08; previously untracked) is the ONLY file that imports the d1_1 `knowledge_belief` FactStore/BeliefStore copies (CONNECTIONS F).

**Headline finding: the suite overwhelmingly tests CURRENT code, not stale legacy paths.** The one exception is `test_fact_belief_gating.py`, which reproduces a live-state observation (facts/beliefs empty when small_llm absent) by driving the *legacy* d1_1 stores directly.

## Files

### The DI contract meta-test — test_di_contracts.py ⭐
Scans **every** `.py` under `serin/` for the `def get_X(...) → raise RuntimeError` getter pattern, finds the matching `set_X`/`init_X`, then asserts the setter is **called somewhere** in the codebase. This is a codebase-wide reachability check: any DI slot that is read-but-never-written fails at test time instead of runtime. Discover new patterns automatically (no hardcoded paths).

### test_runtime_contracts.py — the 6-layer structural gate ⭐
- **Layer 1 — whole-tree import:** parametrized over every module in `serin/` (`test_module_imports_cleanly`), so any import-time crash (circular import, missing symbol) is caught.
- **Layer 2 — Rust undefined-var scan:** builds/uses `scripts/undef-var-scanner/target/release/undef-var-scanner` on the whole tree; skips if not built (`pytest.skip`). **This is the ONLY consumer of the S13 scanner binary.** Parses its `{var} not defined` stderr output into a parametrized failure list.
- **Layer 3 — self-attr contract:** standalone `self:` functions must only touch `self.X` attrs that exist on their target class. Covers `process_voice_input` (d4_5_message_process) → `EnhancedMessageManagerV3` and `send_tts_audio`/`interrupt` (d4_2_bridge_commands) → `RustVoiceBridge` — **an AST-level CONNECTIONS J check**.
- **Layer 4 — dict-key contract:** `ContextBuilder.build_context` returned keys ⊇ `format_context_for_llm` bracket accesses; `VisualMemory.recall_image` keys ⊇ `process_voice_input`'s `top_match[...]` accesses.
- **Layer 5 — voice TTS contracts:** `process_voice_input` must accept `guild_id` (default None) and `d3_3_transcribe_pipeline` must pass it; `voice_output_manager is None` must log a warning, not stay silent.
- **Layer 6 — no-silent-except:** over 7 voice-pipeline files (audio_processor, audio_transcribe, audio_vad, system_output, bridge_commands, transcribe_pipeline, transcribe_transcriber) every `except` must log/raise/return, and `if self.X:` without `else:` must log. Plus `test_voice_available` asserts `voice_available is True` (requires faster-whisper installed in the test env).

### test_static_analysis.py — the CI tooling gate
Shells out to `ruff check` (all 5 d1_* dirs, zero errors), `mypy` (strict, whole serin/), `pyright` (must not crash; untyped third-party libs exempted), `semgrep` (`.semgrep/rules`, skipped if absent), `import-linter lint` (**references THE_LAW.md Rule 5**, skipped if absent), `bandit` (skip B101), `detect-secrets` (`.secrets.baseline`). This is the Rule-5 layer enforcement check.

### The LIVE act-pipeline tests (messaging/) ⭐
- `test_pipeline.py` — `MessagePipeline.build` returns exactly the **10 stages in order**: ResponseDecision → MemoryRetrieval → ResponsePlanner → Temporal → Personality → PromptAssembly → LLMCall → ResponseCleaning → Send → MemoryWrite (matches S7 byte-for-byte).
- `stages/test_decision.py` — Boltzmann decision stage: `'serin'` in message = hard override (engine not called), reply/react/ignore actions map to halt_reason, no-dynamics defaults to reply, `observe_message`/`allocate_attention` always called.
- `stages/test_affect_decision.py` — salience bump `0.1*familiarity`, user_valence/user_familiarity forwarded to `decide_action`, neutral defaults when no engine.
- `stages/test_creator_override.py` — creator_ids force reply + `metadata.instant_reply`, SendStage skips dynamics delay on instant (but @mention override keeps natural delay); build wires `creator_ids=config.CREATOR_IDS`.
- `stages/test_memory_retrieval.py` — memory population from build_context, empty-result handling.
- `test_processor.py` — **actually a VOICE test** (mislabeled): pins AudioStreamProcessor constants (VAD_AMPLITUDE_THRESHOLD=150, SILENCE_FRAMES_BEFORE_FLUSH=75, MIN_BUFFER_BYTES=192_000, PROCESSING_LOCK_SECONDS=30), silent audio doesn't queue. Module-level `init_gateway()` side effect.

### Affect tests (test_affect_*.py + test_boltzmann_bias.py) ⭐
- `test_affect_engine.py` — the UserAffectEngine spec: decay half-life exactness, valence clamp ±1, familiarity `1-exp(-n/50)`, snapshot cache, parse_impression.
- `test_affect_context.py` — T10 prompt-section spec: stranger (familiarity<0.1) → empty section (fixes the hostile-default bug), loved/warm/neutral/wary/disliked buckets with exact boundary tests (±0.51, 0.09/0.11).
- `test_affect_wiring.py` — MemoryWriteStage calls `record_sentiment` per message (or no-ops safely), and an **AST check** that EnhancedMessageManagerV3 assigns `affect_engine`.
- `test_boltzmann_bias.py` — **the physics spec**: exact reply/react/ignore energy equations with affect bias terms; familiar user replies more; disliked-but-familiar drop bounded <25pp at n=20000 (flakiness history documented in-source).

### Memory tests (memory/)
- `test_qdrant.py` — QdrantMemorySystem `__new__`-based: embedding failure → None, empty content → None, missing embedding model → graceful search_hybrid.
- `test_user_affect.py` — user_affect schema from the **authoritative `init_sqlite_schema` (d4_3_schema_store)** + upsert/get/get_users_due_impression (thresholds: since_impression≥25, familiarity≥10).

### test_sync_monitor_api_mismatch.py — the sync-monitor diagnostics spec ⭐
Pins `MemorySyncMonitor._check_api_mismatches` (d1_1 d2_4 `d3_4_sync_monitor.py`): the live
`BackgroundProcessor.queue_message` takes an **optional** `message_id` (default None — genuinely
required by the backfill `**msg` path, since `get_messages_around_timestamp` dicts carry it),
which must NOT be flagged as an API mismatch; only a *required* `message_id` (no default) is a
real contract break. Regression guard for the historical false positive that logged a 🔴 API
MISMATCH every 30s.

### test_fact_belief_gating.py — the CONNECTIONS F holdout ⭐
Reproduces a live observation: with `small_llm=None` (llamaswap down) the real MemoryWriteStage writes general memory (`recent_messages`) but facts/beliefs/fact_observations stay empty. It builds a REAL SQLite QdrantMemorySystem (`_init_sqlite_robust`) and wires **FactStore/BeliefStore from the d1_1 `knowledge_belief` copies** (`d5_2_belief_evidence`, `d5_1_belief_beliefs`) + BayesianBeliefEngine (d1_3 `d3_3_belief_dynamics`). Second test proves `store_fact` writes when invoked directly. **This is the only consumer of the DEAD d1_1 stores (S5 finding)** — tracked in git as of 2026-08-25 verification (it was untracked at Phase-4 time).

### Perception tests (perception/) — the ingest perception spec
- `test_board.py` — parse_board (Connect-4 6×7 / TicTacToe 3×3 detection, exact dimension rejection) + derive_from_board with **exact content assertions** (`"X has 4 in a row horizontally at row 6 (columns 1-4)"`, confidence 0.95 win / 0.9 board_state) and mutation-killer edge cases.
- `test_classify.py` (426 lines) — perceive_message spec: speech_act (question/joke/sarcasm/agreement/disagreement/evidence/instruction/statement with override ordering), intent (question/seek_explanation/seek_validation/command/social), evidence_class (world/conversation/social with `>0.7` compound threshold), claims categories, exact fact confidences (board 0.9, url 0.7, code 0.8, speech_claim 0.2), is_objective rules.
- `test_personality.py` — analyze_personality traits (humorous/polite/verbose>concise/enthusiastic), interests → `update_user_traits`, get_emotional_tone boundaries (0.5/0.51, -0.5/-0.51, 0.2/0.21), detect_topic keyword map.
- `test_profile.py` — get_user_profile / get_memory_stats (Qdrant availability flags).
- `test_result.py` — PerceptionResult defaults + pattern constants.

### Server tests (server/) — the LIVE panel (S12) ⭐
- `conftest.py` — bot_state_dict fixture populating `bot_state` (d5_2_server_state) with mocks; `client` = TestClient(app) against **the LIVE `d3_2_panel_server` app**.
- `test_websocket.py` — **CONNECTIONS A** directly: `broadcast_log`/`broadcast_event` send to connected WS, skip + remove disconnected, remove raisers, decision events pass through with `type`/`data` shape.
- `test_improvements.py` — `_condense_results` (search_store) score_breakdown; PersonalityState mood history (bounded 500) + `set_mood_preset`; **confirm-gated config** (`LLM_BASE_URL` blocked without `confirm:True`); `/api/bot/restart` requires confirm; logs-recent uses a real path; `_ws_lock` race regression test.
- `test_state.py` — auth middleware (`CONTROL_PANEL_KEY` + X-API-Key: 401 unauthorized), `get_gpu_vram_usage` (nvidia-smi parse 2048+1024→3.0GB, timeout→0).
- `test_routes.py` — /api/status (online/offline), /api/health (discord/memory ok, voice/tts disabled), /api/stats.
- `test_make_json_safe.py` — the JSON-sanitizer spec (tuples/sets→lists, datetime→ISO, custom objects, **circular ref bounded by depth guard**).

### bot_pipeline_init/ — the entry chain (S9)
- `test_main.py` — `main()` (d4_1_main_entry): 5-attempt retry with exponential backoff (`min(30, 2**n)`), handles aiohttp/discord.ConnectionClosed/GatewayNotFound, **DatabaseValidationError → "Manual intervention required"**, **DatabaseRecoveryError → "Try restoring from backup"** (S2 db_protect), finally-close, keyboard interrupt.
- `test_on_ready.py` — post-refactor on_ready constructs `PipelineInitializer`, awaits `initialize()`, **re-exports subsystem singletons (message_manager, voice_behavior_manager, voice_listener) onto the bpi module globals**.
- `test_on_message.py` — the intake funnel: skips own-messages/non-text/DM/empty-no-attachments, allowed-vs-passive channel routing, command handlers (profile/stats/help) short-circuit, dispatches to `message_manager.process_message`, error stats.
- `test_voice_action.py` — the `_handle_voice_action` callback: VoiceActionDecider join/leave → `voice_listener.join_channel/leave_channel` + VoiceBehaviorManager stats (auto_joins/auto_leaves) + tracker gate (`is_in_voice`/`get_voice_info`) — the structured voice-action path wired at ingest core_manager:188 (S11).

### integration/test_bridge.py — the voice bridge Python half
RustStdoutReader interface (`events`, `read_loop`, `_EOF`), RustVoiceBridge constructor defaults, `start()` returns False when the Rust binary is missing (with `binary_path` explicit). Shallow — does not test the wire protocol against a live Rust process.

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **The suite is a de-facto SPEC of the live codebase.** The exact-content assertions (Boltzmann energy equations, 10-stage order, perception speech-act/intent rules, mood-history maxlen=500, board-confidence values) read as design documents for S5/S6/S7/S8/S12. Any refactor that changes behavior silently breaks a test.
2. **The DEAD-schema holdout is exactly one file.** `test_fact_belief_gating.py` is the only consumer of the d1_1 `knowledge_belief` FactStore/BeliefStore copies (CONNECTIONS F). It exists to *prove* the live facts/beliefs gating works — but it drives the legacy stores, not the authoritative `d4_3_schema_store` Bayesian schema. Phase-4 note: it should be migrated to `d4_3_schema_store` + `d4_4_core_store` wiring. (It has since been added to git — the "add to git" half of this note is done.)
3. **Rust has exactly one test-time consumer.** The `undef-var-scanner` binary is exercised by `test_runtime_contracts.py` Layer 2 (skipped if not built). `serin_core` is not directly tested anywhere (its seams are covered by the Python fallbacks in bm25_index/search_store/response_generator tests being absent — no Rust soak). `voice_receiver` has no integration test against a real subprocess (`test_bridge.py` only checks the missing-binary path).
4. **CONNECTIONS A and G are pinned by tests.** `test_websocket.py` directly tests `broadcast_event`/`broadcast_log`; `test_improvements.py` tests confirm-gated routes and `_ws_lock`; `test_pipeline_smoke.py` asserts PromptAssemblyStage appends to the `_prompt_history` debug store (store_prompt_debug) and MemoryWriteStage runs even on halt.
5. **The test env is assumed to have faster-whisper + tooling installed** (`test_voice_available`, `test_static_analysis` shells out). Some gates skip gracefully when a tool is absent (semgrep/import-linter/detect-secrets/undef-var-scanner).
6. **`test_processor.py` is a voice test in the messaging/ folder** — a naming wart, not a bug.
7. **Mutation-killer style.** Many tests (perception, board) are written to kill specific mutation-test operators (NumberReplacer, ReplaceAndWithOr, ReplaceComparisonOperator, AddNot, etc.) — the suite was built against a mutation-testing regimen.

## What's NOT here
- **No network/async integration tests** against live Discord, Qdrant, or LLM (all mocked/MagicMock).
- **No Rust `voice_receiver` subprocess integration test** (only the missing-binary path).
- **No `serin_core` PyO3 soak/smoke test** (optional-accelerator fallbacks not covered).
- **No coverage of the DEAD panel worlds** (d3_1_panel_panels, d3_4_panel_routes) — consistent with their dead status.
- **No tests for gateway_transcribe's VoiceMemoryPipeline** (S11) or the Rust bridge wire protocol parse (AUDIO/JOIN/LEAVE/TTS_DONE framing) — covered only by contract checks, not execution.
