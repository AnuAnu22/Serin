# Serin Migration Map

## Naming Convention

Python packages cannot start with numbers. The Law's `{depth}-{sequence}_{name}` pattern
is adapted for Python as follows:
- **Directories**: `depth_sequence_name/` (underscore-separated, no leading digit on
  `__init__.py` since package name starts with digit)
- **Files**: `sequence_name.py` within their parent directory (depth is implied by
  directory nesting)
- **Root-level packages**: Prefixed with `p` to make valid Python identifiers:
  `p1_pipeline/`, `p2_gateway/`, `p3_state/`, `p4_config/`, `p5_ops/`

The directory structure conveys depth via nesting, not via filename prefixes.
Within each directory, files use `{sequence}_{word1-word2}.py` naming.

## Duplicate Pairs (Phase 2 — Resolve First)

| Pair | Canonical File | Duplicate | Importers of Duplicate | Action |
|---|---|---|---|---|
| Voice bridge | `voice/bridge.py` | `voice/rust_voice_bridge.py` | 0 files | Already deleted |
| Audio processor | `voice/processor.py` | `voice/audio_stream_processor.py` | 0 files | Already deleted |

## Files to Delete (Dead Code / Shims)

All files in this list have already been deleted in previous sessions:

| File | Reason |
|---|---|
| `voice/rust_voice_bridge.py` | Duplicate of `voice/bridge.py` (already deleted) |
| `voice/audio_stream_processor.py` | Duplicate of `voice/processor.py` (already deleted) |
| `voice/temp_voice_test/temp_voice_bridge.py` | Temporary test script (already deleted) |
| `serin/memory/qdrant.py` | Backward-compat shim (already deleted) |
| `serin/messaging/stages.py` | Deprecated shim (already deleted) |
| `utils/llama_connector.py` | Superseded by `models/` connectors (already deleted) |
| `serin/visual_memory_system.py` | Dead code (already deleted) |
| `models/__init__.py` | Replaced by proper re-exports |
| `serin/__init__.py` | Not needed under new structure |
| `serin/core/__init__.py` | Not needed |
| `serin/control_panel/__init__.py` | Not needed |
| `serin/personality/__init__.py` | Not needed |
| `serin/messaging/__init__.py` | Not needed |
| `serin/memory/__init__.py` | Not needed |
| `serin/utils/__init__.py` | Not needed |
| `voice/__init__.py` | Not needed |

---

## Target Architecture

### `p1_pipeline/` — The Processing Spine

```
p1_pipeline/
  0_spine/
    1_pipeline_runner.py      — MessagePipeline.build() factory + stage orchestration
    2_pipeline_stage_base.py  — PipelineStage ABC with timing instrumentation
  1_ingest/
    1_message_manager.py      — EnhancedMessageManagerV3 (decomposed from 1056 lines)
    1a_perception_result.py   — PerceptionResult dataclass (extracted from manager)
    2_corrections.py          — CorrectionHandler: detect user corrections
    3_length_analyzer.py      — LongMessage: wall-of-text detection + reactions
  2_perceive/
    1_conversation_analyzer.py — ConversationAnalyzer: topic/dynamics/type detection
    2_topic_fatigue.py        — TopicFatigue: per-channel topic repetition tracking
  3_think/
    1_active_search.py        — decides whether to search memory + query generation
    2_model_factory.py        — factory that selects LLM connector
    2a_model_adapter.py       — chat format template + thinking-tag patterns per model
    3_response_controller.py  — should_respond decision cascade + PersonalityState
    3a_decision_stage.py      — PipelineStage wrapping ResponseController
    3b_response_planner.py    — PipelineStage: beliefs/facts → structured decision
    4_voice_behavior.py       — autonomous VC join/leave manager
    4a_voice_action_decider.py — LLM decider for voice join/leave/stay
  4_remember/
    1_temporal_parser.py      — natural-time → absolute timestamp conversion
    1a_temporal_stage.py      — PipelineStage wrapping temporal parser
    2_background_processor.py — background episodic memory generation from messages
    2a_voice_memory_pipeline.py — stores voice transcriptions into memory
    3_qdrant_store.py         — QdrantMemorySystem I/O layer (decomposed from 1517 lines)
    3a_memory_write_stage.py  — PipelineStage: store response as memory
    4_evidence_store.py       — FactStore: atomic verifiable information
    4a_belief_store.py        — BeliefStore: state machine + Bayesian confidence
    4b_bot_personality.py     — BotPersonality: preferences, opinions, mood
    5_context_history.py      — in-memory context history + system prompt generation
    5a_context_builder.py     — builds structured context from Qdrant retrieval
    6_human_like_retriever.py — multi-stage retrieval + scoring + filtering
    6a_retrieval_stage.py     — PipelineStage wrapping memory retrieval
  5_act/
    1_fillers.py              — conversational filler injection
    1a_typos.py               — realistic typing mistake injection
    2_response_generator.py   — builds prompt, calls LLM, applies post-processing
    2a_llm_call_stage.py      — PipelineStage wrapping LLM invocation
    2b_prompt_assembly.py     — PipelineStage: builds final messages array
    3_personality_stage.py    — PipelineStage: inject personality into context
    4_send_stage.py           — PipelineStage: send response to Discord
    4a_response_cleaning.py   — PipelineStage: strip thinking tags + special tokens
```

### `p2_gateway/` — External Interfaces

```
p2_gateway/
  1_discord/
    1_bot_entry.py            — discord_bot.py: main entry point + lifecycle
    1a_command_handlers.py    — !profile, !stats, !help commands (extracted)
    2_mention_translator.py   — bidirectional Discord @mention ↔ username translation
    2a_message_crawler.py     — retroactive Discord channel backfill daemon
    3_passive_monitor.py      — listens to all channels, stores non-responded messages
    4_voice_tracker.py        — voice channel join/leave/switch activity tracking
  2_voice/
    1_tts_engine.py           — multi-backend TTS (edge-tts + Coqui XTTS)
    1a_voice_profiles.py      — TTS voice profile dataclass + mood presets
    2_rust_voice_bridge.py    — Rust songbird bridge subprocess + protocol parser
    2a_voice_listener.py      — Discord VC join + audio receive pipeline
    3_audio_processor.py      — per-user VAD + silence detection + transcription
    3a_whisper_transcriber.py — faster-whisper STT with CUDA + language detection
    3b_voice_output_manager.py — TTS queue + audio send to Rust bridge
  3_text/
    (reserved for future text channel adapters)
  4_media/
    (reserved for future media processing adapters)
  5_adapter/
    1_lm_studio_connector.py  — LM Studio OpenAI-compatible API connector
    2_sglang_connector.py     — SGLang server connector
    3_vllm_connector.py       — vLLM server connector + Gemma reasoning mode
```

### `p3_state/` — Cross-Cutting General Truths

```
p3_state/
  1_model_interface.py        — ModelInterface ABC: contract for all LLM connectors
  1a_thinking_filter.py       — strips thinking/reasoning tags from LLM output
  2_message_context.py        — MessageContext dataclass: pipeline data envelope
  3_shared_types.py           — shared type aliases, constants, base error classes (NEW)
  4_voice_profiles_data.py    — VoiceProfile dataclass (shared between TTS and voice)
```

Note: `3_shared_types.py` and `4_voice_profiles_data.py` are new files that will be
created during migration to hold shared type definitions extracted from other modules.
This follows Rule 4 (Buoyancy) — genuinely shared types float to the top.

### `p4_config/` — Configuration

```
p4_config/
  1_config.py                 — BotConfig singleton: all environment variables
  2_logger.py                 — centralized logging setup + formatters
  3_debug_logger.py           — debug trace logging for all subsystems
```

### `p5_ops/` — Operations & Maintenance

```
p5_ops/
  1_control_panel/
    1_routes.py               — FastAPI route definitions for web control panel
    2_server.py               — FastAPI server + WebSocket live-log + API endpoints
  2_hot_reloader.py           — dev file watcher + auto-restart
  3_duplicate_finder.py       — AST-based duplicate file detector script
  4_database_protector.py     — pre-startup validation + backup + corruption recovery
  5_sync_monitor.py           — memory sync diagnostic daemon
```

### `tests/` — Test Files (mirroring source structure)

```
tests/
  conftest.py                 — shared fixtures
  p1_pipeline/
    0_spine/
      test_pipeline.py        — pipeline build/process tests
    1_ingest/
      test_manager.py         — message manager tests
    3_think/
      test_decision.py        — decision stage tests
      test_response_controller.py
    4_remember/
      test_qdrant.py          — Qdrant memory store tests
      test_memory_retrieval.py — memory retrieval stage tests
    5_act/
      test_fillers.py
  p2_gateway/
    1_discord/
      test_discord_bot.py     — integration tests for discord_bot.py
      test_bridge.py          — bridge integration tests
    2_voice/
      test_processor.py       — voice processor tests
  shared/
    memory_testing_framework.py — shared test infrastructure
    test_qdrant_migration.py — Qdrant migration validation
    test_datetime_fixes.py   — datetime utility tests
    test_active_search_init.py
    test_active_search_loop.py
    test_fix_fts.py
    test_vision.py
    verify_active_search.py
    verify_active_search_live.py
    memory_system_demo.py
```

---

## File-by-File Migration (Source Files Only)

### Phase 2 — Duplicate Resolution (COMPLETE — files already deleted in previous sessions)
No action needed.

### Phase 3 — Branch `p3_state/` (first, everything imports from here)
| Source | Target | Notes |
|---|---|---|
| `models/model_interface.py` | `p3_state/1_model_interface.py` | |
| `serin/utils/thinking_filter.py` | `p3_state/1a_thinking_filter.py` | |
| `serin/messaging/context.py` | `p3_state/2_message_context.py` | |

### Phase 3 — Branch `p4_config/` (second, before pipeline)
| Source | Target | Notes |
|---|---|---|
| `serin/core/config.py` | `p4_config/1_config.py` | BotConfig singleton |
| `serin/core/logger.py` | `p4_config/2_logger.py` | Centralized logging |
| `serin/utils/debug_logger.py` | `p4_config/3_debug_logger.py` | Debug trace logging |

### Phase 3 — Branch `p2_gateway/` (third)
| Source | Target | Notes |
|---|---|---|
| `discord_bot.py` | `p2_gateway/1_discord/1_bot_entry.py` | Decompose: extract commands to 1a |
| `serin/messaging/mention_translator.py` | `p2_gateway/1_discord/2_mention_translator.py` | |
| `serin/messaging/crawler.py` | `p2_gateway/1_discord/2a_message_crawler.py` | |
| `serin/utils/passive_monitor.py` | `p2_gateway/1_discord/3_passive_monitor.py` | |
| `voice/tracker.py` | `p2_gateway/1_discord/4_voice_tracker.py` | |
| `tts/tts_engine.py` | `p2_gateway/2_voice/1_tts_engine.py` | |
| `voice/profiles.py` | `p2_gateway/2_voice/1a_voice_profiles.py` | |
| `voice/bridge.py` | `p2_gateway/2_voice/2_rust_voice_bridge.py` | |
| `voice/listener.py` | `p2_gateway/2_voice/2a_voice_listener.py` | |
| `voice/processor.py` | `p2_gateway/2_voice/3_audio_processor.py` | |
| `voice/transcriber.py` | `p2_gateway/2_voice/3a_whisper_transcriber.py` | |
| `voice/output.py` | `p2_gateway/2_voice/3b_voice_output_manager.py` | |
| `tts_voice_manager.py` | `p2_gateway/2_voice/1b_voice_file_manager.py` | |
| `models/lm_studio.py` | `p2_gateway/5_adapter/1_lm_studio_connector.py` | |
| `models/sglang.py` | `p2_gateway/5_adapter/2_sglang_connector.py` | |
| `models/vllm.py` | `p2_gateway/5_adapter/3_vllm_connector.py` | |

### Phase 3 — Branch `p1_pipeline/` (fourth, depends on state + gateway)
| Source | Target | Notes |
|---|---|---|
| `serin/messaging/pipeline.py` | `p1_pipeline/0_spine/1_pipeline_runner.py` | |
| `serin/messaging/stages/__init__.py` | `p1_pipeline/0_spine/2_pipeline_stage_base.py` | |
| `serin/messaging/manager.py` | `p1_pipeline/1_ingest/1_message_manager.py` | Split: extract PerceptionResult |
| `serin/messaging/correction_handler.py` | `p1_pipeline/1_ingest/2_corrections.py` | |
| `serin/messaging/long_message.py` | `p1_pipeline/1_ingest/3_length_analyzer.py` | |
| `serin/personality/conversation_analyzer.py` | `p1_pipeline/2_perceive/1_conversation_analyzer.py` | |
| `serin/personality/topic_fatigue.py` | `p1_pipeline/2_perceive/2_topic_fatigue.py` | |
| `serin/active_search.py` | `p1_pipeline/3_think/1_active_search.py` | |
| `models/factory.py` | `p1_pipeline/3_think/2_model_factory.py` | |
| `models/model_adapter.py` | `p1_pipeline/3_think/2a_model_adapter.py` | |
| `serin/messaging/response_controller.py` | `p1_pipeline/3_think/3_response_controller.py` | |
| `serin/messaging/stages/decision.py` | `p1_pipeline/3_think/3a_decision_stage.py` | |
| `serin/messaging/stages/response_planner.py` | `p1_pipeline/3_think/3b_response_planner.py` | |
| `voice/behavior.py` | `p1_pipeline/3_think/4_voice_behavior.py` | |
| `voice/decider.py` | `p1_pipeline/3_think/4a_voice_action_decider.py` | |
| `serin/memory/temporal.py` | `p1_pipeline/4_remember/1_temporal_parser.py` | |
| `serin/messaging/stages/temporal.py` | `p1_pipeline/4_remember/1a_temporal_stage.py` | |
| `serin/utils/background.py` | `p1_pipeline/4_remember/2_background_processor.py` | |
| `voice/pipeline.py` | `p1_pipeline/4_remember/2a_voice_memory_pipeline.py` | |
| `serin/memory/store.py` | `p1_pipeline/4_remember/3_qdrant_store.py` | Split: extract sub-concerns |
| `serin/messaging/stages/memory_write.py` | `p1_pipeline/4_remember/3a_memory_write_stage.py` | |
| `serin/memory/evidence.py` | `p1_pipeline/4_remember/4_evidence_store.py` | |
| `serin/memory/beliefs.py` | `p1_pipeline/4_remember/4a_belief_store.py` | |
| `serin/personality/bot_personality.py` | `p1_pipeline/4_remember/4b_bot_personality.py` | |
| `serin/memory/context.py` | `p1_pipeline/4_remember/5_context_history.py` | |
| `serin/messaging/context_builder.py` | `p1_pipeline/4_remember/5a_context_builder.py` | |
| `serin/memory/retrieval.py` | `p1_pipeline/4_remember/6_human_like_retriever.py` | |
| `serin/messaging/stages/memory_retrieval.py` | `p1_pipeline/4_remember/6a_retrieval_stage.py` | |
| `serin/messaging/fillers.py` | `p1_pipeline/5_act/1_fillers.py` | |
| `serin/messaging/typos.py` | `p1_pipeline/5_act/1a_typos.py` | |
| `serin/messaging/response_generator.py` | `p1_pipeline/5_act/2_response_generator.py` | |
| `serin/messaging/stages/llm_call.py` | `p1_pipeline/5_act/2a_llm_call_stage.py` | |
| `serin/messaging/stages/prompt_assembly.py` | `p1_pipeline/5_act/2b_prompt_assembly.py` | |
| `serin/messaging/stages/personality.py` | `p1_pipeline/5_act/3_personality_stage.py` | |
| `serin/messaging/stages/send.py` | `p1_pipeline/5_act/4_send_stage.py` | |
| `serin/messaging/stages/response_cleaning.py` | `p1_pipeline/5_act/4a_response_cleaning.py` | |

### Phase 3 — Branch `p5_ops/` (fifth)
| Source | Target | Notes |
|---|---|---|
| `serin/control_panel/routes.py` | `p5_ops/1_control_panel/1_routes.py` | |
| `serin/control_panel/server.py` | `p5_ops/1_control_panel/2_server.py` | |
| `hot_reloader.py` | `p5_ops/2_hot_reloader.py` | |
| `scripts/find_duplicate_files.py` | `p5_ops/3_duplicate_finder.py` | |
| `serin/utils/database_protector.py` | `p5_ops/4_database_protector.py` | |
| `serin/memory/sync_monitor.py` | `p5_ops/5_sync_monitor.py` | |

---

## UNRESOLVED

None — all files have been assigned a target location.

## File Count Verification

- Source files mapped: 63 (excluding test files, init files to delete, and duplicates to delete)
- Test files mapped: 22
- Total Python files in repo: 100 (excluding .venv)
- Files to delete: 13 (dead code, shims, duplicates, unnecessary inits)
