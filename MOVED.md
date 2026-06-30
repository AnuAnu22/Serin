# Module Locations & Deletions

## Root → `serin/` Package (Phase 2)

| Old root file | Moved to |
|---|---|
| config.py | serin/core/config.py |
| logger_config.py | serin/core/logger.py |
| qdrant_memory_system.py | serin/memory/qdrant.py |
| enhanced_memory_retrieval.py | serin/memory/retrieval.py |
| enhanced_memory_context.py | serin/memory/context.py |
| memory_sync_monitor.py | serin/memory/sync_monitor.py |
| temporal_context.py | serin/memory/temporal.py |
| enhanced_message_manager.py | serin/messaging/manager.py |
| conversation_context_builder.py | serin/messaging/context_builder.py |
| natural_response_generator.py | serin/messaging/response_generator.py |
| response_controller.py | serin/messaging/response_controller.py |
| mention_translator.py | serin/messaging/mention_translator.py |
| correction_handler.py | serin/messaging/correction_handler.py |
| conversational_fillers.py | serin/messaging/fillers.py |
| realistic_typos.py | serin/messaging/typos.py |
| long_message_handler.py | serin/messaging/long_message.py |
| message_crawler.py | serin/messaging/crawler.py |
| bot_personality.py | serin/personality/bot_personality.py |
| conversation_analyzer.py | serin/personality/conversation_analyzer.py |
| topic_fatigue.py | serin/personality/topic_fatigue.py |
| background_processor.py | serin/utils/background.py |
| passive_monitor.py | serin/utils/passive_monitor.py |
| thinking_filter.py | serin/utils/thinking_filter.py |
| debug_logger.py | serin/utils/debug_logger.py |
| database_protector.py | serin/utils/database_protector.py |
| web_server.py | serin/control_panel/server.py |
| enhanced_api_routes.py | serin/control_panel/routes.py |

## Voice/ Renames (Phase 2)

| Old name | New name |
|---|---|
| voice/rust_voice_bridge.py | voice/bridge.py |
| voice/audio_stream_processor.py | voice/processor.py |
| voice/voice_output_manager.py | voice/output.py |
| voice/voice_listener.py | voice/listener.py |
| voice/voice_behavior_manager.py | voice/behavior.py |
| voice/voice_tracker.py | voice/tracker.py |
| voice/voice_action_decider.py | voice/decider.py |
| voice/voice_profiles.py | voice/profiles.py |

## Deleted Dead Duplicates (Phase 7 + cleanup pass)

These were byte-identical duplicate files left over from
incomplete renaming. The canonical file (listed second) was kept.

| Deleted | Canonical kept |
|---|---|
| models/model_factory.py | models/factory.py |
| models/interface.py | models/model_interface.py |
| models/adapter.py | models/model_adapter.py |
| models/vllm_connector.py | models/vllm.py |
| models/lm_studio_connector.py | models/lm_studio.py |
| models/sglang_connector.py | models/sglang.py |
| voice/whisper_transcriber.py | voice/transcriber.py |
| voice/voice_memory_pipeline.py | voice/pipeline.py |
| dev.py | (no replacement — use hot_reloader.py) |

## Deleted Root Originals (Phase 7, confirmed no production imports)

- `active_search.py`
- `background_processor.py`
- `bot_personality.py`
- `conversation_analyzer.py`
- `conversation_context_builder.py`
- `conversational_fillers.py`
- `correction_handler.py`
- `database_protector.py`
- `debug_logger.py`
- `enhanced_api_routes.py`
- `enhanced_memory_context.py`
- `enhanced_memory_retrieval.py`
- `logger_config.py`
- `long_message_handler.py`
- `memory_diagnostic_tool.py`
- `memory_sync_monitor.py`
- `memory_system.py`
- `memory_system_enhancer.py`
- `mention_translator.py`
- `message_crawler.py`
- `natural_response_generator.py`
- `passive_monitor.py`
- `pipeline_stages.py`
- `realistic_typos.py`
- `response_controller.py`
- `self_healing_database.py`
- `temporal_context.py`
- `thinking_filter.py`
- `topic_fatigue.py`
- `visual_memory_system.py` (moved to serin/ later, root copy deleted)
- `web_server.py`

## Remaining at Root

- `discord_bot.py` — **single production entry point**
- `hot_reloader.py` — development hot-reload launcher (calls discord_bot.py as subprocess)
- `tts_voice_manager.py` — TTS voice file management (utility script)
