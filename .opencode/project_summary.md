# Serin Bot — Project State (Jul 23 2026)

## Objective
Iteratively fix all runtime errors from stale paths/names after the rename migration — voice join, TTS playback, voice transcription, startup noise — until the bot runs cleanly end-to-end.

## Important Details
- `.env`: `LLM_MODEL=gemmafable12b`, `LLM_SUPPORTS_AUDIO=true`, `LLM_SUPPORTS_VISION=true`
- Rust voice bridge binary: `<config_dir>/Serin/voice/rust_receiver/target/release/voice_receiver`
- Hot-reloader auto-restarts on file changes (may not catch `__init__.py` changes)
- `process_voice_input()` in `d4_5_message_process.py` is a standalone function with `self: Any` — called with `EnhancedMessageManagerV3` as `self`
- `VoiceMemoryPipeline` created before `EnhancedMessageManagerV3` in init order (voice → TTS → message manager)

## Completed Fixes (chronological)

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `d4_2_bridge_commands.py` | `bridge.send_tts_audio()` / `.interrupt()` called as methods | Import and call as standalone functions |
| 2 | `d3_2_voice_decider.py` | LLM output missing commas between JSON key-value pairs | Join lines with commas in `_parse_decision` |
| 3 | `d3_2_voice_decider.py` | Raw JSON parse failures | Switch to `chat_completion` with `response_format={"type": "json_object"}` |
| 4 | `d4_4_core_manager.py` (via `d3_3_transcribe_pipeline.py`) | Voice decider used `smolvlm256m` instead of `gemmafable12b` | Passed `config.LLM_MODEL` to `get_model_connector()` |
| 5 | `d3_3_transcribe_pipeline.py` | `VoiceMemoryPipeline` got `message_manager` before `EnhancedMessageManagerV3` created | Use `get_message_manager()` from DI container |
| 6 | `d4_5_message_process.py` | `process_voice_input` accessed `self.voice_pipeline` directly (missing attribute) | Use `getattr(self, 'voice_pipeline', None)` |
| 7 | `d2_2_tooling_background.py` | Naive vs aware datetime comparison crash in `_group_by_conversation()` | Strip `tzinfo` from all timestamps via `.replace(tzinfo=None)` |
| 8 | `d3_2_system_connector.py:86` | LLM reconnect spammed `logger.exception` every cycle | Downgraded to `logger.error` |
| 9 | `d3_3_transcribe_pipeline.py` | `_check_voice_action()` never called after `pipeline.process()` | Wired into pipeline result handling |
| 10 | Bot entry point | Voice callback failed when no active channel found | Added `_find_active_channel()` fallback |
| 11 | Bot shutdown | Shutdown disconnects from voice after database backup | Voice disconnect before db shutdown |
| 12 | `d5_1_search_store.py` | BM25 index failures at import time | Downgraded to `logger.warning` |
| 13 | SQLite schema | Duplicate-column errors during migration | Made silent |
| 14 | `d4_5_message_process.py` | `process_voice_input` used `get_message_manager()` from DI | (same as #5, chain fix) |
| — | — | Graphify knowledge graph | Built: 4524 nodes, 8807 edges, 264 communities |
| 15 | `tests/test_attr_contracts.py` | New test file | Catches `'NoneType' object has no attribute` errors at test time by scanning standalone `self: Any` functions for attribute existence on target class |

## Active / Remaining
- Voice end-to-end: VAD → transcribe → store → `process_voice_input` → LLM → TTS playback — last error (context_builder None) fixed by DI container change; needs restart to confirm

## Test Suite Status
- `tests/test_attr_contracts.py`: 2 tests, pass
- `tests/test_runtime_contracts.py`: 111 tests, pass (2 skipped — `test_string_var_defined` + `test_self_attrs_exist_on_target` when no issues)
- `tests/test_di_contracts.py`: 6 tests, pass
- **Total (contract tests)**: 113 passed, 2 skipped
- **Pre-existing failures** (not from this work): `tests/bot_pipeline_init/test_main.py` (event_handlers rename), `tests/integration/` (2 failures)

## Relevant Files
- `serin/d1_1_pipeline_flow/d2_2_flow_ingest/d3_2_ingest_core/d4_5_message_process.py`: `process_voice_input()` standalone function
- `serin/d1_1_pipeline_flow/d2_2_flow_ingest/d3_2_ingest_core/d4_4_core_manager.py`: `EnhancedMessageManagerV3` class
- `serin/d1_2_gateway_io/d2_2_voice_system/d3_2_bridge_io/d4_2_bridge_commands.py`: `send_tts_audio()`, `interrupt()` standalone functions
- `serin/d1_2_gateway_io/d2_3_voice_transcribe/d3_3_transcribe_pipeline.py`: `VoiceMemoryPipeline`
- `serin/d1_1_serin_di.py`: DI container with `get_message_manager()`
- `serin/d1_3_state_core/d2_4_core_voice/d3_2_voice_decider.py`: `VoiceActionDecider`
- `tests/test_attr_contracts.py`: Attribute contract enforcement
- `.env`: LLM config
