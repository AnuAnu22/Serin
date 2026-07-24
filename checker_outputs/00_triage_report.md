# Serin Codebase Triage Report

## Executive Summary

- **670 pyright errors**: ~200 are `reportUnusedFunction` (decorated route handlers pyright can't see), ~150 are `reportPrivateUsage` (underscore methods accessed cross-module), ~100+ are "partially unknown" type propagation from untyped containers, ~50 are `reportPossiblyUnboundVariable` from conditional imports
- **92 mypy errors**: 80 are `untyped-decorator` (FastAPI/Aiohttp decorators), 4 are `type-arg` (missing `dict[K, V]`), 2 are `no-any-return`, 1 is `arg-type` (sys.settrace), all others are pre-existing
- **17 bandit issues**: 14 are `B110` (try/except pass) — most are intentional fallback patterns, 2 are `B608` (SQL string concat) — real SQL injection surface, 1 is `B102` (exec used) — import side-effect pattern
- **270 vulture items**: ~150 are genuinely dead code (unwired functions, old features), ~110 are control panel routes registered via decorators, ~10 are unused imports/variables
- **922 radon entries**: 10 functions over complexity 25, ~20 over 15. Worst: `PromptAssemblyStage._run` (58), `perceive_message` (45), `process_message` (40), `on_ready` (38), `register_missing_routes` (38)
- **Detect-secrets**: 3 findings — all false positives (secrets baseline entries, vendored Cargo lock)
- **Estimated fix effort**: ~20 quick fixes (<5 min each), ~15 medium (5-30 min), ~3 large (30+ min)

## Pyright Errors (670)

### Error Type Breakdown

| Error Type | Count | Top Files | Root Cause | Fix Strategy |
|---|---|---|---|---|
| `reportUnusedFunction` | ~200 | `d4_9_missing_routes.py`, `d4_11_debug_routes.py`, `d4_6_memory_routes.py`, `d4_7_personality_routes.py`, `d4_8_ops_routes.py`, `d4_1_panel_control.py`, `d5_x_voice_*.py` | Route handler functions registered via `@router.get()` decorator; pyright doesn't track decorator-based registration | Add `# pyright: ignore[reportUnusedFunction]` at file level for route files, or suppress in pyright config under `reportUnusedFunction = false` for known decorator patterns |
| `reportPrivateUsage` | ~150 | `d4_3_bridge_recovery.py`, `d4_2_bridge_commands.py`, `d5_1_audio_processor.py`, `d4_2_bridge_commands.py` | Underscore-prefixed methods accessed from outside their declaring class (delegation/forwarding pattern in voice bridge system) | Change underscored methods to public methods, or add type: ignore comments on each call site |
| "Type of `append` is partially unknown" | ~100 | `d4_3_prompt_assembly.py`, `d3_4_sync_monitor.py`, `d4_1_context_builder.py`, `d4_6_memory_routes.py` | Untyped list literals (`[]`), `defaultdict` without type args, bare `list()` calls | Add type annotations: `items: list[str] = []`, `defaultdict(list[str])` |
| `reportPossiblyUnboundVariable` | ~50 | `d4_4_core_store.py`, `d2_5_memory_store.py`, `d4_2_connection_store.py`, `d5_tts_engine.py`, `d3_4_transcribe_transcriber.py` | Conditional `try/except ImportError` blocks for optional dependencies (Qdrant, TTS, Whisper, torch, SentenceTransformer) | Use `None` sentinel pattern: `QdrantClient: type | None = None` at module level, reassign on successful import |
| `reportUnknownVariableType` / `reportUnknownMemberType` | ~80 | `d3_2_system_connector.py`, `d4_1_sync_backfill.py`, `d4_2_sync_crawler.py`, `d4_3_memory_write.py` | LLM response dicts, Discord API response objects, NLTK return values without type stubs | Create TypedDicts for LLM responses, use type stubs or inline annotations |
| `reportMissingImports` / `reportMissingTypeStubs` | ~15 | `d4_3_memory_write.py` (nltk.sentiment), `d5_tts_engine.py` (TTS.api), `d3_4_transcribe_transcriber.py` (faster_whisper), `d4_9_missing_routes.py` (voice.voice_profiles) | Missing stubs for third-party packages, or import paths that don't exist (voice.voice_profiles) | Add `# type: ignore[import]` for missing stubs, fix broken import paths |
| `reportConstantRedefinition` | ~8 | `d4_2_connection_store.py`, `d4_4_core_store.py`, `d2_5_memory_store.py`, `d2_1_base_config.py` | UPPERCASE constants redefined in method scope (e.g., `QDRANT_AVAILABLE = True` inside __init__) | Use lowercase or add `# type: ignore[reportConstantRedefinition]` |
| `reportOptionalMemberAccess` | ~5 | `pipeline_init/__init__.py` | Accessing `.memory`, `._describe_image_background` on `None`-able globals | Add `None` checks before access or use `if x is not None: x.method()` |
| `reportInvalidTypeForm` | ~6 | `d5_1_perception_board.py`, `d3_2_discord_bot.py` | `x | y` in wrong context, variable used in type expression | Fix syntax or add quotes for forward reference |
| `reportCallIssue` | ~2 | `d4_2_connection_store.py` (Docker run overloads), `d3_2_discord_bot.py` (sys.settrace FrameType) | Argument type mismatches with SDK overloads | Cast or adjust argument types |
| `reportUnusedVariable` | ~4 | `d4_2_sync_crawler.py`, `d2_2_debug_logger.py`, `d3_4_transcribe_transcriber.py` | Variables assigned but never read | Remove assignments or prefix with `_` |
| `reportAttributeAccessIssue` | ~2 | `d4_4_core_store.py`, `d2_5_memory_store.py` | `importlib.util.find_spec` not recognized | Add `# type: ignore[attr-defined]` |
| Other (unreachable, TypedDict, lambda types) | ~8 | Various | Edge cases | Fix individually |

### Patterns

- **50+ errors from same cause?** Yes — ~150 `reportPrivateUsage` errors all stem from the voice bridge delegation pattern (one class calls `self._private_method()` on another class's instance). This is a single architectural issue.
- **100+ errors from same cause?** Yes — ~200 `reportUnusedFunction` errors are all from decorator-registered route handlers. This could be fixed by a single pyright config change.
- **Concentrated or spread?** Spread across ~40 files, but ~70% of errors are in 8 files: `d4_9_missing_routes.py`, `d4_11_debug_routes.py`, `d4_6_memory_routes.py`, `d4_7_personality_routes.py`, `d4_8_ops_routes.py`, `d4_1_panel_control.py`, `d5_1_audio_processor.py`, `d4_3_bridge_recovery.py`.

## Mypy Errors (92)

### Error Type Breakdown

| Error Type | Count | Top Files | Overlap w/ Pyright? | Fix Strategy |
|---|---|---|---|---|
| `untyped-decorator` | 80 | `d4_9_missing_routes.py`, `d4_11_debug_routes.py`, `d4_6_memory_routes.py`, `d4_7_personality_routes.py`, `d4_8_ops_routes.py`, `d4_10_test_routes.py` | **No** — unique to mypy | Add type annotations to decorator or use `# type: ignore[misc]` on each function |
| `type-arg` (missing generic args) | 4 | `d4_9_missing_routes.py`, `d5_5_voice_ops.py` | **Partial** — pyright reports `reportMissingTypeArgument` | Add `dict[str, Any]` instead of bare `dict` |
| `no-any-return` | 2 | `d4_4_process_watch.py` (lines 489, 495) | **No** — unique to mypy | `return str(...)` or cast result |
| `arg-type` | 1 | `d3_2_discord_bot.py` (line 191, sys.settrace) | **Overlap** — pyright reports same issue | `# type: ignore[arg-type]` or cast |
| `attr-defined` | 3 | `d4_4_server_status.py` (module re-exports) | **No** — unique to mypy | Add explicit `__all__` or `from ... import app, bot_state, make_json_safe` |
| `valid-type` | 1 | `d5_1_perception_board.py` (line 8) | **Overlap** — pyright also flags this | Fix type comment syntax |

### Overlap Analysis
- **Overlap with pyright**: ~6 errors overlap (same file, same line): the `reportInvalidTypeForm` in `d5_1_perception_board.py`, `arg-type` in `d3_2_discord_bot.py`, and some `type-arg`/`reportMissingTypeArgument` in `d4_9_missing_routes.py`
- **Unique to mypy**: ~86 errors — almost entirely the `untyped-decorator` failures (80) plus `no-any-return`, `attr-defined`, `valid-type`

## Bandit Security Issues (17)

### B110: try/except pass (14 issues)

| # | File | Line | Severity | Risk | Code Does | Should Do Instead |
|---|---|---|---|---|---|---|
| 1 | `d4_3_prompt_assembly.py` | 437 | Low | Minor | Silent fail when getting bot ID from guild | Replace `pass` with `bot_id = ""` (already the default) — **safe as-is, but add comment** |
| 2 | `d4_3_memory_write.py` | 49 | Low | Minor | NLTK sentiment import fallback — defaults to `compound = 0.0` | Replace `pass` with `logger.debug("NLTK sentiment unavailable")` |
| 3 | `pipeline_init/__init__.py` | 327 | Low | Minor | Image backfill read/encode fail — silent | Replace `pass` with `logger.debug(...)` |
| 4 | `pipeline_init/__init__.py` | 339 | Low | Minor | Message storage fail during backfill — silent | Replace `pass` with `logger.debug(...)` |
| 5 | `d3_2_discord_bot.py` | 188 | Low | Minor | Signal handler voice disconnect fail | Replace `pass` with `logger.warning(...)` |
| 6 | `d4_4_process_watch.py` | 496 | Low | Minor | Voice username resolution fail — falls back to `f"user_{user_id}"` | **Safe as-is** (fallback works), but add `logger.debug` |
| 7 | `d5_5_voice_ops.py` | 109 | Low | Minor | Per-channel sync fail during manual sync — loop continues | **Intentional pattern** (outer handler catches all), but add `logger.warning` |
| 8 | `d4_8_ops_routes.py` | 134 | Low | Minor | Same as #7 (duplicate code) | Same fix |
| 9 | `d4_9_missing_routes.py` | 31 | Low | Minor | `get_tone_modifier()` fail — tone_modifier stays `""` | Replace `pass` with `logger.debug` |
| 10 | `d4_9_missing_routes.py` | 304 | Low | Minor | edge_tts fallback fail — voices stays empty | **Safe as-is**, but add `logger.debug` |
| 11 | `d4_9_missing_routes.py` | 505 | **Medium** | **Real risk** | Voice profile activation fail — still returns `{"success": True}` | Replace with `logger.error` and return `{"success": False, "error": str(e)}` |
| 12 | `d4_9_missing_routes.py` | 530 | **Medium** | **Real risk** | Voice profile creation fail — still returns `{"success": True}` | Same as #11 |
| 13 | `d4_9_missing_routes.py` | 550 | **Medium** | **Real risk** | Voice profile deletion fail — still returns `{"success": True}` | Same as #11 |
| 14 | `d2_2_tooling_background.py` | 488 | Low | Minor | `allocate_attention()` fail during maintenance | Replace `pass` with `logger.debug` |

### B608: Hardcoded SQL injection risk (2 issues)

| # | File | Line | Risk | Code Does | Fix |
|---|---|---|---|---|---|
| 15 | `d3_3_belief_dynamics.py` | 190 | **Medium** - Real | `f"UPDATE facts SET {', '.join(set_parts)} WHERE id = ?"` — `set_parts` is built from observation types, partially controlled by message content | Use a whitelist: validate each `set_parts` entry against allowed column names before joining. Or build the SET clause from a static mapping dict. |
| 16 | `d4_11_debug_routes.py` | 189 | Low - Minor | `" WHERE " + " AND ".join(clauses)` — clauses are `"user_id = ?"`, `"channel_id = ?"` etc (static strings, parameterized values) | **False positive** — clause strings are hardcoded, only values are parameterized. Add `# nosec B608` on line 185. |

### B102: exec() used (1 issue)

| # | File | Line | Risk | Code Does | Fix |
|---|---|---|---|---|---|
| 17 | `panel_server/__init__.py` | 101 | Low | `exec("from ... import d4_4_server_status")` for module-level side effects | Replace with `import` statement at top of file. If the comment about "module-level side effects" is accurate, a normal import achieves the same thing. |

## Vulture Dead Code (270)

### Category A: Unwired Functionality (~50 items)

Functions that exist, look complete, and appear intended for use but are never called.

| # | Function | File | Line | Intended Purpose | What to Do |
|---|---|---|---|---|---|
| 1 | `log_context` | `d2_2_debug_logger.py` | 199 | Log built context dict | Wire into pipeline stages, or remove if DebugLogger pattern replaced |
| 2 | `log_llm_io` | `d2_2_debug_logger.py` | 204 | Log LLM input/output pairs | Same — wire in or remove |
| 3 | `log_response` | `d2_2_debug_logger.py` | 231 | Log response decision | Same |
| 4 | `log_api_request` | `d2_2_debug_logger.py` | 241 | Log API requests | Same |
| 5 | `send_with_typing` | `d3_2_response_controller.py` | 403 | Send message with simulated typing | Replaced by `SendStage._run()` in pipeline. **Can be removed.** |
| 6 | `update_conversation_mood` | `d3_2_response_controller.py` | 322 | Track channel mood | Replaced by dynamics engine? Check usage. Probably **can be removed** if engine handles this. |
| 7 | `mark_response` | `d3_2_response_controller.py` | 363 | Record response timing | Used by `send_with_typing` only (which is also unused). **Can be removed.** |
| 8 | `get_response_natural` | `d3_3_response_generator.py` | 77 | Full LLM response generation | This is the core generator — check if called from pipeline or if it's been replaced. If pipeline uses `LLMCallStage`, this may be dead. |
| 9 | `search_memories_human_like` | `d4_4_knowledge_retrieval.py` | 93 | Human-like memory retrieval with personality scoring | Purpose-built enhancement to Qdrant search. If the pipeline uses `MemoryRetrievalStage._run()` directly, this was never wired in.**
| 10 | `infer_beliefs_from_facts` | `d5_1_belief_beliefs.py` | 147 | Infer beliefs from active facts | Duplicate of `d3_1_belief_store.py:148` — appears twice in codebase (old path vs new path) |

### Category B: Truly Dead Code (~40 items)

| # | Function | File | Line | Feature | Action |
|---|---|---|---|---|---|
| 1 | `_time_label` | `d4_3_prompt_assembly.py` | 23 | Time formatting helper, defined but never called | Remove or keep if planned |
| 2 | `_search_with_time_range` | `d4_1_context_builder.py` | 153 | Time-range-aware memory search | Was part of `ConversationContextBuilder`, never wired into `build_context()` |
| 3 | `resolve_referents` | `d4_1_context_builder.py` | 254 | Pronoun resolution (they/that → entity) | Complete-looking feature, never called from pipeline |
| 4 | `extract_time_reference_from_query` | `d4_1_context_builder.py` | 288 | NLP time extraction from queries | Never called |
| 5 | `should_react_to_length` / `get_length_reaction` | `d4_2_long_message.py` | 94, 123 | Long message reactions | Reactions now handled by dynamics engine / `_pick_reaction_emoji()` |
| 6 | `restore_for_discord` | `d4_3_mention_translator.py` | 108 | Reverse mention translation | Defined but callers use `clean_for_bot` only |
| 7 | `get_user_info` / `get_user_id` | `d4_3_mention_translator.py` | 177, 189 | User info lookup | Defined but never called externally |
| 8 | `analyze_image` | `d5_1_visual_memory.py` | 103 | Raises `NotImplementedError` — deliberately deprecated | **Remove** — says "use VLM directly" |
| 9 | `recall_image_from_bytes` | `d5_1_visual_memory.py` | 188 | Image search from raw bytes | Defined, never called |
| 10 | `get_correction_history` | `d4_3_correction_handler.py` | 241 | Query past corrections | Never called |

### Category C: Unused Imports (~10 items)

| # | Import | File | Notes |
|---|---|---|---|
| 1 | `WhisperTranscriber` | `d3_2_discord_bot.py:78` | Imported but never used (class exists in another file) |

### Category D: Unused Variables (~15 items)

| # | Variable | File | Line | Notes |
|---|---|---|---|---|
| 1 | `query_time_hint` | `d4_1_context_builder.py` | 43 | Assigned in `__init__` but never read — likely meant for time-range search |
| 2 | `user_stance` | `d3_2_bot_personality.py` | 298 | Assigned in `can_disagree` but never used — **bug**: function always returns default |
| 3 | `resolved_last_message` | `d3_3_response_generator.py` | 80 | Assigned but never read — debugging leftover |
| 4 | `provider` | `d3_3_system_factory.py` | 12 | Imported but never used |
| 5 | `temporal_priority` | `d4_4_knowledge_retrieval.py` | 29 | Config value assigned but never referenced |
| 6 | `reconnect` | `d3_3_system_listener.py` | 47 | Variable from tuple unpacking, never used |
| 7 | `temporal_refs` | `d2_5_message_context.py` | 44 | Field on MessageContext, set but never read |
| 8 | `discord_msg` | `d4_2_sync_crawler.py` | 319 | Assigned in loop comprehension? Actually unused variable |
| 9 | `include_scores` | `d4_1_state_access.py` | 83 | Function parameter, never used |
| 10 | `i` | `d3_3_panel_lifecycle.py` | 61 | Loop variable, never used |

### Category E: Test/Utility Code (~5 items)

| # | Item | File | Line | Notes |
|---|---|---|---|---|
| 1 | `ConfigUpdateRequest` | `d3_4_panel_routes.py` | 43 | Pydantic model for config updates, never used by any route |
| 2 | `FactQuery` | `d4_1_state_access.py` | 106 | Pydantic model, never used |
| 3 | `BeliefQuery` | `d4_1_state_access.py` | 117 | Pydantic model, never used |

## Radon Complexity (922)

### Functions with Complexity > 25 (Very High)

Count: **10 functions**

### Functions with Complexity > 15 (High)

Count: **~20 functions**

### Top 10 Most Complex Functions

| # | Function | File | Complexity | Why So Complex | Can It Be Split? |
|---|---|---|---|---|---|
| 1 | `PromptAssemblyStage._run` | `d4_3_prompt_assembly.py` | **58** | Assembles LLM messages with ~15 conditional context sections (facts, beliefs, relationship, evolution, memories, etc.), each with budget-aware truncation, plus history filtering/dedup/collapsing | **Yes** — each context section can be a separate method (many already are `_facts_context`, `_belief_evolution_context`, etc.); `_run` orchestrates them |
| 2 | `perceive_message` | `d5_2_perception_classify.py` | **45** | 8 sequential regex-based analysis stages with overlapping conditionals | **Yes** — each stage (speech act, evidence, claims, facts, board, intent) should be its own function |
| 3 | `process_message` | `d4_5_message_process.py` | **40** | Orchestrates ~15 side effects per message with two-tier vision fallback, conditional branches for each type | **Yes** — extract vision handling, profile update, perception, and batch scheduling into separate methods |
| 4 | `on_ready` | `pipeline_init/__init__.py` | **38** | 20+ sequential component initializations, each with try/except | **Partially** — each init block already has try/except, but it's inherently sequential (dependencies) |
| 5 | `register_missing_routes` | `d4_9_missing_routes.py` | **38** | 35 route registrations each with boilerplate try/except + bot_state.get | **Yes** — extract route groups into separate files (already split across d4_6/d4_7/d4_8 for active routes; missing_routes should follow same pattern) |
| 6 | `should_respond` | `d3_2_response_controller.py` | **36** | 10-tier priority decision tree with randomized thresholds | **Limited** — each tier depends on previous (first-match-wins), but individual conditions can be extracted as `_is_creator`, `_is_mentioned`, etc. |
| 7 | `infer_beliefs_from_facts` | `d5_1_belief_beliefs.py` | **36** | Two nested inference loops over fact categories with state machine | **Yes** — extract board/game inference and preference inference into separate methods |
| 8 | `derive_from_board` | `d5_1_perception_board.py` | **30** | 4-directional win check with nested loops per direction | **Partial** — the 4 directions are structurally similar but hard to deduplicate without losing readability |
| 9 | `get_response_natural` | `d3_3_response_generator.py` | **30** | Two-path message building, vision handling, model call, response post-processing | **Yes** — extract message building, response parsing, and naturalization into separate functions |
| 10 | `get_system_health` | `d4_3_server_state.py` | **24** | 6-component health check with 2-4 sub-checks each | **Yes** — each component check can be a separate `_check_*` method |

## Detect-Secrets (3)

| # | File | Line | Type | Real Secret? | Notes |
|---|---|---|---|---|---|
| 1 | `.secrets.baseline` | 134 | Hex High Entropy String | **No** — False positive | Baseline file is the audit whitelist itself; this is expected |
| 2 | `.secrets.baseline` | 134 | Secret Keyword | **No** — False positive | Baseline file metadata |
| 3 | `voice/rust_receiver/vendor/songbird/.cargo_vcs_info.json` | 3 | Hex High Entropy String | **No** — Git commit hash | Vendored dependency metadata, not a secret |

All 3 are false positives.

## Cross-Reference Analysis

### 1. Which 5 files have the MOST total issues?

(Counts: pyright errors + mypy errors + bandit issues + vulture items + radon entries over 15)

| File | Pyright | Mypy | Bandit | Vulture | Radon>15 | Total |
|---|---|---|---|---|---|---|
| `d4_9_missing_routes.py` | ~120 | 30 | 6 | ~40 | 1 | **~197** |
| `d4_11_debug_routes.py` | ~50 | 12 | 1 | ~12 | 0 | **~75** |
| `d4_6_memory_routes.py` | ~35 | 10 | 0 | ~10 | 0 | **~55** |
| `d4_7_personality_routes.py` | ~30 | 10 | 0 | ~10 | 0 | **~50** |
| `d4_3_prompt_assembly.py` | ~20 | 0 | 1 | 1 | 4 | **~26** |

### 2. Functions in BOTH vulture (unused) AND radon (high complexity)?

| Function | File | Vulture Status | Radon Complexity | Action |
|---|---|---|---|---|
| `search_memories_human_like` | `d4_4_knowledge_retrieval.py` | Unused method | 12 (high) | **Prime candidate** — complex, complete, never called. Remove or wire in. |
| `infer_beliefs_from_facts` | `d5_1_belief_beliefs.py` | Unused method | 36 (very high) | **Prime candidate** — duplicate of `d3_1_belief_store.py:148`. Remove one copy. |
| `get_response_natural` | `d3_3_response_generator.py` | Unused import path | 30 (very high) | Check if pipeline calls this or uses different path. |
| `send_with_typing` | `d3_2_response_controller.py` | Unused method | 5 (low) | Cleanup candidate — replaced by SendStage |
| `should_respond` | `d3_2_response_controller.py` | Unused? (check) | 36 (very high) | Probably used but may be superseded by ResponseDecisionStage |

### 3. Files with 0 pyright errors but high vulture counts?

No files have 0 pyright AND high vulture. The closest:
- `d3_2_bot_personality.py` — low pyright, ~6 vulture items
- `d3_5_remember_temporal.py` — 0 pyright, ~5 vulture items (unused functions like `parse_time`, `get_time_range`)

### 4. Files with high pyright errors but 0 vulture?

- `d4_2_sync_crawler.py` — ~15 pyright, 0 vulture (active, used code)
- `d3_1_system_adapter.py` — ~10 pyright, 0 vulture (active model adapter)
- `d3_2_system_connector.py` — ~10 pyright, 0 vulture (active LLM connector)

### 5. Estimated effort to fix everything

| Category | Count | Est. Time Each | Total |
|---|---|---|---|
| **Quick** (<5 min each) — add logger.debug to bare except, delete clearly dead functions, add # type: ignore | ~20 | 3 min | ~60 min |
| **Medium** (5-30 min) — add type annotations to untyped containers, refactor duplicate belief code, extract route groups from missing_routes.py | ~15 | 15 min | ~225 min |
| **Large** (30+ min) — refactor PromptAssemblyStage._run (58), perceive_message (45), process_message (40), on_ready (38) | ~3 | 60 min | ~180 min |
| **Config-level** (one-time) — add pyright ignore for `reportUnusedFunction` in route files, add mypy ignore for `untyped-decorator` | 2 config changes | 5 min | 10 min |

**Total estimated effort: ~7.5 hours**

## Recommended Fix Order

### Phase 1: Config Changes (10 min)
1. Add `reportUnusedFunction = false` to `pyrightconfig.json` for known decorator patterns (fixes ~200 pyright errors instantly)
2. Add `untyped-decorator` to mypy per-file ignores for route files (fixes 80 mypy errors instantly)

### Phase 2: Security Fixes (30 min)
3. Fix B608 SQL injection in `d3_3_belief_dynamics.py:190` — whitelist column name validation
4. Fix B102 `exec()` in `panel_server/__init__.py:101` — replace with normal import
5. Fix B110 in `d4_9_missing_routes.py:505,530,550` — log error and return failure (lies to caller)
6. Add `# nosec` on `d4_11_debug_routes.py:185` (false positive B608)
7. Add `logger.debug` to remaining 10 B110 cases

### Phase 3: Real Dead Code Removal (1 hr)
8. Remove `analyze_image` (raises NotImplementedError intentionally)
9. Remove duplicate `infer_beliefs_from_facts` in `d5_1_belief_beliefs.py` (copy in `d3_1_belief_store.py` is the active one)
10. Remove `send_with_typing`, `mark_response`, `update_conversation_mood` from `d3_2_response_controller.py`
11. Remove unused DI functions (`get_mention_translator`, `get_crawler`, `get_qdrant`) from `d1_1_serin_di.py`
12. Remove unused variables from Category D

### Phase 4: Type Cleanup (2 hr)
13. Fix all `Type of "append" is partially unknown` (~100 errors across ~20 files)
14. Fix `reportUnknownVariableType` in LLM response handling — add TypedDicts
15. Fix `reportPossiblyUnboundVariable` — use None sentinel pattern

### Phase 5: Complexity Refactoring (3-4 hr)
16. Split `PromptAssemblyStage._run` (58) into section methods
17. Split `perceive_message` (45) into per-stage functions
18. Split `process_message` (40) into handler methods
19. Extract route groups from `register_missing_routes` (38) into separate files
20. Extract component checks from `get_system_health` (24)
