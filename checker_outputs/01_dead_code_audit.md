# Dead Code Audit Report

**Generated:** 2026-07-24
**Tool:** vulture serin/ --min-confidence 60
**Total Findings:** 272

---

## Executive Summary

| Category | Count | Description |
|---|---|---|
| **A — Unwired** | ~145 | Complete functions/methods never invoked anywhere |
| **B — Dead** | ~55 | Old routing/IO code, debug infrastructure, superseded modules |
| **C — Unused Import** | ~4 | Leftover imports from removed functionality |
| **D — Unused Variables** | ~8 | Assigned but never read (potential bugs) |
| **Duplicates** | ~60 | Same function/method defined in two parallel modules |

**Goal:** Drop vulture findings from ~270 to < 50 by removing Category B and C, fixing Category D, and consolidating duplicates.

---

## Category A — Unwired (complete functions, never called)

These are full, working functions never invoked. Most are in the control panel routing layer.

| File | Function | Confidence | Notes |
|---|---|---|---|
| `d4_1_panel_control.py:15` | `register_control_routes` | 60% | Route registration, never called |
| `d4_1_panel_control.py:18` | `list_tts_voices` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:42` | `get_current_tts` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:65` | `load_tts_voice` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:83` | `clear_tts_voice` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:100` | `test_tts_voice` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:121` | `update_tts_settings` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:142` | `get_audio_settings` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:170` | `update_audio_settings` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:206` | `get_audio_stats` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:251` | `list_voice_profiles` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:299` | `set_active_voice_profile` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:333` | `get_background_queue` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:350` | `clear_background_queue` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:382` | `get_voice_behavior_settings` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:403` | `update_voice_behavior_settings` | 60% | API endpoint, never called |
| `d4_1_panel_control.py:418` | `get_voice_behavior_stats` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_1_voice_channels.py:18` | `register_voice_channel_routes` | 60% | Never called |
| `d4_2_voice_routes/d5_1_voice_channels.py:20` | `get_voice_channels` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_1_voice_channels.py:40` | `join_voice_channel` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_1_voice_channels.py:59` | `leave_voice_channel` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_1_voice_channels.py:72` | `get_voice_status` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_2_voice_tts.py:14` | `register_voice_tts_routes` | 60% | Never called |
| `d4_2_voice_routes/d5_2_voice_tts.py:16` | `get_tts_status` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_2_voice_tts.py:29` | `test_tts` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_2_voice_tts.py:42` | `list_tts_voices` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_3_voice_memory.py:14` | `register_voice_memory_routes` | 60% | Never called |
| `d4_2_voice_routes/d5_3_voice_memory.py:16` | `get_voice_memory` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_3_voice_memory.py:33` | `get_voice_memory_stats` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_4_voice_brain.py:21` | `register_voice_brain_routes` | 60% | Never called |
| `d4_2_voice_routes/d5_4_voice_brain.py:23` | `get_brain_state` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_4_voice_brain.py:42` | `emergency_stop` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_4_voice_brain.py:46` | `get_system_prompt` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_4_voice_brain.py:53` | `update_system_prompt` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_4_voice_brain.py:81` | `sever_context` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_5_voice_ops.py:20` | `register_voice_ops_routes` | 60% | Never called |
| `d4_2_voice_routes/d5_5_voice_ops.py:22` | `trigger_manual_sync` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_5_voice_ops.py:35` | `get_recent_logs` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_5_voice_ops.py:48` | `restart_bot` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_5_voice_ops.py:58` | `get_audio_settings` | 60% | API endpoint, never called |
| `d4_2_voice_routes/d5_5_voice_ops.py:70` | `update_audio_settings` | 60% | API endpoint, never called |
| `d3_2_panel_server/d4_9_missing_routes.py:22` | `get_current_mood` | 60% | **WIRED** — registered via register_missing_routes |
| `d3_2_panel_server/d4_9_missing_routes.py:54` | `set_mood` | 60% | **WIRED** — registered via register_missing_routes |
| `d3_2_panel_server/d4_9_missing_routes.py:85` | `get_mood_history` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:102` | `join_voice` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:120` | `leave_voice` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:137` | `get_voice_status` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:157` | `get_voice_files` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:171` | `load_voice_file` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:205` | `get_voice_channels` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:228` | `leave_all_voice_channels` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:242` | `test_tts_voice` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:255` | `load_tts_voice` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:269` | `clear_tts_voice` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:282` | `test_tts` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:295` | `get_tts_voices` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:315` | `get_current_tts` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:334` | `update_tts_settings` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:350` | `get_tts_status` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:371` | `get_audio_settings` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:389` | `update_audio_settings` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:406` | `get_audio_speakers` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:419` | `get_audio_stats` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:433` | `get_voice_behavior_settings` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:446` | `update_voice_behavior_settings` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:465` | `get_voice_behavior_stats` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:479` | `list_voice_profiles` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:496` | `set_active_voice_profile` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:565` | `test_qdrant_connection` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:588` | `run_background_maintenance` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:602` | `start_crawler` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:615` | `stop_crawler` | 60% | **WIRED** |
| `d3_2_panel_server/d4_9_missing_routes.py:654` | `rebuild_bm25_index` | 60% | **WIRED** |
| `d3_3_panel_lifecycle.py:115` | `register_lifecycle_routes` | 60% | Never called |
| `d3_4_panel_routes.py:43` | `ConfigUpdateRequest` | 60% | Unused class |
| `d3_4_panel_routes.py:44` | `use_qdrant` | 60% | Unused variable |
| `d3_4_panel_routes.py:49` | `register_enhanced_routes` | 60% | Never called |
| `d3_4_panel_routes.py:60` | `get_enhanced_status` | 60% | API endpoint, never called |
| `d3_4_panel_routes.py:84` | `search_memories_enhanced` | 60% | API endpoint, never called |
| `d3_4_panel_routes.py:153` | `get_user_profile_enhanced` | 60% | API endpoint, never called |
| `d3_4_panel_routes.py:170` | `cleanup_memories_enhanced` | 60% | API endpoint, never called |
| `d3_4_panel_routes.py:194` | `test_connection_enhanced` | 60% | API endpoint, never called |

**Recommendation Category A:**
- The `d4_1_panel_control.py` route functions are all dead — they define FastAPI routes but are never registered via `include_router` or `register_*`. Delete the entire file or move its routes into `d4_9_missing_routes.py`.
- The `d4_2_voice_routes/` files contain route registration functions that are never called. These are dead.
- `d3_3_panel_lifecycle.py:register_lifecycle_routes` is dead.
- `d3_4_panel_routes.py` is dead (entire file).
- The `d4_9_missing_routes.py` functions ARE wired (confirmed via `__init__.py:82`). Keep them.

---

## Category B — Dead (old/debug code, safe to remove)

| File | Function/Class | Confidence | Reason |
|---|---|---|---|
| `d4_1_models_profiles.py:175` | `get_profile_for_mood` | 60% | Duplicate of `d3_3_voice_profiles.py` version |
| `d4_2_models_tracker.py:216` | `get_all_in_voice` | 60% | Duplicate of `d3_4_voice_tracker.py` version |
| `d4_2_models_tracker.py:228` | `get_voice_duration` | 60% | Duplicate |
| `d4_2_models_tracker.py:274` | `get_voice_join_reaction` | 60% | Duplicate |
| `d4_2_models_tracker.py:284` | `get_voice_duration_reaction` | 60% | Duplicate |
| `d4_4_core_manager.py:156` | `active_search` attribute | 60% | Leftover state, never updated |
| `d1_1_serin_di.py:46` | `get_mention_translator` | 60% | Unused DI entry point |
| `d1_1_serin_di.py:68` | `get_crawler` | 60% | Unused DI entry point |
| `d1_1_serin_di.py:79` | `get_qdrant` | 60% | Unused DI entry point |
| `d3_1_ingest_context/d4_1_context_builder.py:153` | `_search_with_time_range` | 60% | Dead search method |
| `d2_3_flow_perceive/d3_2_bot_personality.py:122` | `express_preference` | 60% | Dead personality method |
| `d2_3_flow_perceive/d3_2_bot_personality.py:225` | `set_preference` | 60% | Dead personality method |
| `d2_3_flow_perceive/d3_2_bot_personality.py:254` | `express_opinion` | 60% | Dead personality method |
| `d2_3_flow_perceive/d3_2_bot_personality.py:284` | `set_opinion` | 60% | Dead personality method |
| `d2_3_flow_perceive/d3_2_bot_personality.py:396` | `detect_topic_in_message` | 60% | Dead topic detection |
| `d2_3_flow_perceive/d3_3_conversation_analyzer.py:19` | `analyze_conversation_flow` | 60% | Dead analyzer |
| `d2_3_flow_perceive/d3_3_conversation_analyzer.py:203` | `should_acknowledge_topic_change` | 60% | Dead topic change handler |
| `d2_3_flow_perceive/d3_4_topic_fatigue.py:124` | `get_most_discussed_topics` | 60% | Dead fatigue method |
| `d2_3_flow_perceive/d3_4_topic_fatigue.py:147` | `apply_fatigue_to_personality` | 60% | Dead fatigue method |
| `d2_3_flow_perceive/d3_4_topic_fatigue.py:188` | `get_fatigue_context_note` | 60% | Dead fatigue method |
| `d2_3_flow_perceive/d3_4_topic_fatigue.py:220` | `get_topic_fatigue` | 60% | Dead standalone function |
| `d2_4_flow_remember/d3_1_remember_core/d4_1_knowledge_belief/d5_1_belief_beliefs.py:42` | `add_or_update_belief` | 60% | Duplicate — active version is in `d3_1_belief_store.py` |
| `d2_4_flow_remember/d3_1_remember_core/d4_1_knowledge_belief/d5_1_belief_beliefs.py:147` | `infer_beliefs_from_facts` | 60% | Duplicate |
| `d2_4_flow_remember/d3_1_remember_core/d4_4_core_store.py:165` | `background_jobs` attribute | 60% | Dead attribute |
| `d2_4_flow_remember/d3_1_remember_core/d4_4_core_store.py:176` | `_find_qdrant_container` | 60% | Dead Docker helper |
| `d2_4_flow_remember/d3_1_remember_core/d4_4_core_store.py:183` | `_ensure_qdrant_docker` | 60% | Dead Docker helper |
| `d2_4_flow_remember/d3_1_remember_core/d4_4_core_store.py:203` | `row_factory` attribute | 60% | Dead SQLite attribute |
| `d2_4_flow_remember/d3_2_remember_knowledge/d4_1_knowledge_belief/d5_2_belief_evidence.py:49` | `add_fact` | 60% | Duplicate of `d3_2_evidence_store.py` version |
| `d2_4_flow_remember/d3_2_remember_knowledge/d4_1_knowledge_belief/d5_2_belief_evidence.py:87` | `get_active_facts` | 60% | Duplicate |
| `d2_4_flow_remember/d3_2_remember_knowledge/d4_1_knowledge_belief/d5_2_belief_evidence.py:137` | `supersede_fact` | 60% | Duplicate |
| `d2_4_flow_remember/d3_2_remember_knowledge/d4_1_knowledge_belief/d5_2_belief_evidence.py:147` | `deactivate_facts_by_message` | 60% | Duplicate |
| `d2_4_flow_remember/d3_2_remember_knowledge/d4_2_memory_context.py:18` | `memory_weights` attribute | 60% | Dead attribute |
| `d2_4_flow_remember/d3_2_remember_knowledge/d4_2_memory_context.py:21` | `add_context` | 60% | Dead method |
| `d2_4_flow_remember/d3_2_remember_knowledge/d4_2_memory_context.py:29` | `get_relevant_context` | 60% | Dead method |
| `d2_4_flow_remember/d3_2_remember_knowledge/d4_2_memory_context.py:53` | `get_personality_traits` | 60% | Dead method |
| `d2_4_flow_remember/d3_2_remember_knowledge/d4_3_memory_quality.py:184` | `create_enhanced_memory_retriever` | 60% | Dead factory |
| `d2_4_flow_remember/d3_2_remember_knowledge/d4_3_memory_quality.py:188` | `create_memory_quality_assessor` | 60% | Dead factory |
| `d1_2_gateway_io/d2_2_voice_system/d3_2_bridge_io/d4_3_bridge_recovery.py:146` | `set_reconnect_callback` | 60% | Dead callback setter |
| `d1_2_gateway_io/d2_2_voice_system/d3_2_bridge_io/d4_3_bridge_recovery.py:202` | `set_username` | 60% | Dead username setter |
| `d1_2_gateway_io/d2_3_voice_transcribe/d3_4_transcribe_transcriber.py:200` | `WhisperTranscriberFallback` class | 60% | Dead fallback class |
| `d1_4_config_base/d2_2_debug_logger.py:199` | `log_context` | 60% | Dead debug logger |
| `d1_4_config_base/d2_2_debug_logger.py:204` | `log_llm_io` | 60% | Dead debug logger |
| `d1_4_config_base/d2_2_debug_logger.py:231` | `log_response` | 60% | Dead debug logger |
| `d1_4_config_base/d2_2_debug_logger.py:241` | `log_api_request` | 60% | Dead debug logger |

**Recommendation Category B:**
- Delete `d4_1_models_profiles.py`, `d4_2_models_tracker.py` (duplicates of state core modules).
- Delete `d1_1_serin_di.py` entirely (all 3 functions are DI entry points that are unused).
- Delete `d3_4_panel_routes.py` entirely (unused route definitions).
- Delete `d3_3_panel_lifecycle.py:register_lifecycle_routes` function.
- Remove dead attributes (`active_search`, `background_jobs`, `row_factory`, `memory_weights`, `temporal_refs`).
- Remove dead Docker helpers (`_find_qdrant_container`, `_ensure_qdrant_docker`).
- Remove `d2_3_flow_perceive/d3_2_bot_personality.py` methods: `express_preference`, `set_preference`, `express_opinion`, `set_opinion`, `detect_topic_in_message`. These are the personality module methods that seem to have been superseded by the dynamics engine in `d5_1_dynamics_engine.py`.

---

## Category C — Unused Imports

| File | Symbol | Confidence |
|---|---|---|
| `d3_3_system_factory.py:12` | `provider` | 100% |
| `d3_3_system_factory.py:17` | `_analyzer` | 60% (likely) |
| `d4_3_mention_translator.py` (state_core) | duplicate methods | — |

**Recommendation Category C:** Remove the `provider` variable from `d3_3_system_factory.py`. Investigate whether `d3_3_system_factory.py` is itself dead (all its functions are unused too — `get_available_providers`, `get_loaded_models`, `load_model_if_needed`, `unload_all_models` are all unused at 60% confidence).

---

## Category D — Unused Variables (potential bugs)

| File | Variable | Confidence | Severity |
|---|---|---|---|
| `d4_1_context_builder.py:43` | `query_time_hint` | 100% | MINOR — unused parameter, should be removed from signature |
| `d3_2_bot_personality.py:298` | `user_stance` | 100% | **BUG** — param documented but never read in `can_disagree`; method always falls through to random fallback |
| `d3_3_response_generator.py:80` | `resolved_last_message` | 100% | MINOR — unused parameter |
| `d3_3_system_listener.py:47` | `reconnect` | 100% | MINOR — param accepted but never used in `connect()` body |
| `d3_3_system_factory.py:12` | `provider` | 100% | MINOR — unused parameter |
| `d4_4_knowledge_retrieval.py:29` | `temporal_priority` | 60% | MINOR — possibly leftover from refactor |
| `d4_4_knowledge_retrieval.py:36` | `personality_weights` | 60% | MINOR — dead attribute |
| `d4_4_knowledge_retrieval.py:37` | `conversation_history` | 60% | MINOR — dead attribute |

**Recommendation Category D:**
- Remove `query_time_hint` param from `build_context()` if no longer supported.
- Fix `can_disagree` in `bot_personality.py` — `user_stance` param is documented but ignored; either use it or remove it.
- Remove `resolved_last_message` param from `get_response_natural()`.
- Remove `reconnect` param from `VoiceConnector.connect()` if the caller hardcodes `False` (already happening at call site).

---

## Duplicate Modules

The codebase has **14 pairs of duplicate function/method definitions** across pipeline, gateway_io, and state_core modules. The state_core versions (`d1_3_state_core/`) are the canonical/active ones (confirmed via imports). The gateway_io versions are the dead duplicates.

| Duplicate Function | Active (keep) | Dead (remove) |
|---|---|---|
| `add_or_update_belief` | `d3_1_belief_store.py` | `d5_1_belief_beliefs.py` |
| `infer_beliefs_from_facts` | `d3_1_belief_store.py` | `d5_1_belief_beliefs.py` |
| `add_fact` | `d3_2_evidence_store.py` | `d5_2_belief_evidence.py` |
| `get_active_facts` | `d3_2_evidence_store.py` | `d5_2_belief_evidence.py` |
| `supersede_fact` | `d3_2_evidence_store.py` | `d5_2_belief_evidence.py` |
| `deactivate_facts_by_message` | `d3_2_evidence_store.py` | `d5_2_belief_evidence.py` |
| `restore_for_discord` | `d1_3_state_core/.../d3_1_mention_translator.py` | `d1_1_pipeline_flow/.../d4_3_mention_translator.py` |
| `get_user_info` | `d1_3_state_core/.../d3_1_mention_translator.py` | `d1_1_pipeline_flow/.../d4_3_mention_translator.py` |
| `get_user_id` | `d1_3_state_core/.../d3_1_mention_translator.py` | `d1_1_pipeline_flow/.../d4_3_mention_translator.py` |
| `get_all_in_voice` | `d1_3_state_core/.../d3_4_voice_tracker.py` | `d1_2_gateway_io/.../d4_2_models_tracker.py` |
| `get_voice_duration` | `d1_3_state_core/.../d3_4_voice_tracker.py` | `d1_2_gateway_io/.../d4_2_models_tracker.py` |
| `get_voice_join_reaction` | `d1_3_state_core/.../d3_4_voice_tracker.py` | `d1_2_gateway_io/.../d4_2_models_tracker.py` |
| `get_voice_duration_reaction` | `d1_3_state_core/.../d3_4_voice_tracker.py` | `d1_2_gateway_io/.../d4_2_models_tracker.py` |
| `get_profile_for_mood` | `d1_3_state_core/.../d3_3_voice_profiles.py` | `d1_2_gateway_io/.../d4_1_models_profiles.py` |

**Recommendation:** Delete the entire `d1_2_gateway_io/d2_3_voice_transcribe/d3_1_transcribe_models/` directory (all 4 files) and the dead duplicate methods in `d5_1_belief_beliefs.py` and `d5_2_belief_evidence.py`. The pipeline versions of `mention_translator` should be cleaned up after consolidating with state_core.

---

## Top 20 High-Priority Items Summary

### Immediate fixes (safe, low-risk):
1. **Remove `d3_2_bot_personality.py` personality methods** (`express_preference`, `set_preference`, `express_opinion`, `set_opinion`, `detect_topic_in_message`) — superseded by dynamics engine
2. **Remove `d4_1_models_profiles.py` and `d4_2_models_tracker.py`** — full duplicate modules with no active imports
3. **Remove `d1_1_serin_di.py`** — entire file is 3 unused DI entry points
4. **Remove `d3_4_panel_routes.py`** — entire file is unused route definitions
5. **Remove dead Docker helpers** in `d4_4_core_store.py` (`_find_qdrant_container`, `_ensure_qdrant_docker`)
6. **Remove dead attributes** — `active_search`, `background_jobs`, `row_factory` (from multiple files), `temporal_refs` from message_context
7. **Fix Category D bugs** — remove unused params (`query_time_hint`, `user_stance`, `resolved_last_message`, `reconnect`, `provider`)
8. **Remove debugging log functions** in `d2_2_debug_logger.py` (`log_context`, `log_llm_io`, `log_response`, `log_api_request`)
9. **Remove unused `WhisperTranscriberFallback`** class
10. **Remove unused config attributes** (`CONTROL_PANEL_ALLOWED_ORIGINS`, `RUST_VOICE_RECEIVER_PATH`)

---

## Implementation Notes

1. Do NOT delete `d4_9_missing_routes.py` — these functions are wired via `register_missing_routes(app, bot_state)` at `d3_2_panel_server/__init__.py:82`.
2. Do NOT delete `d5_2_perception_classify.py` — the perception module is active.
3. Do NOT delete the belief/evidence store modules in `d1_3_state_core` — they ARE imported and used.
4. The `d4_3_mention_translator.py` in the pipeline is referenced by `core_manager.py` — do NOT delete it yet; the pipeline version should be consolidated with state_core version separately.
5. All deletions should be verified by running `uv run vulture serin/ --min-confidence 80` after each batch.
