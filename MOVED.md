# Module Locations

These root-level files have moved to the `serin/` package or been renamed:

| Old location | New location |
|---|---|
| config.py | serin/core/config.py |
| logger_config.py | serin/core/logger.py (kept as shim at root) |
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
| voice/rust_voice_bridge.py | voice/bridge.py |
| voice/audio_stream_processor.py | voice/processor.py |
| voice/voice_memory_pipeline.py | voice/pipeline.py |
| voice/voice_output_manager.py | voice/output.py |
| voice/whisper_transcriber.py | voice/transcriber.py |
| voice/voice_listener.py | voice/listener.py |
| voice/voice_behavior_manager.py | voice/behavior.py |
| voice/voice_tracker.py | voice/tracker.py |
| voice/voice_action_decider.py | voice/decider.py |
| voice/voice_profiles.py | voice/profiles.py |
| models/model_factory.py | models/factory.py |
| models/model_interface.py | models/interface.py |
| models/model_adapter.py | models/adapter.py |
| models/vllm_connector.py | models/vllm.py |
| models/lm_studio_connector.py | models/lm_studio.py |
| models/sglang_connector.py | models/sglang.py |
