# Serin Refactor Progress

## Status: PHASE 0 — Reconnaissance
## Last completed task: 0.1 — Clone and survey
## Next task: 0.3 — Dead code audit
## Blockers: none
## Notes:

### Key Files (one-sentence descriptions)

| File | Description |
|------|-------------|
| `discord_bot.py` | Entry point — initializes all subsystems, cogs, on_ready/on_message handlers, joins voice |
| `enhanced_message_manager.py` | **God object** — 675 lines, 15+ subsystems: memory, context, response, personality, voice actions, active search, batch flushing |
| `config.py` | Singleton config class reading from env vars — imported by every module |
| `logger_config.py` | Logger setup with rotating file handler, JSON/text formatter, correlation IDs |
| `qdrant_memory_system.py` | **Memory core** — Qdrant vector store, SQLite FTS5 hybrid search, user profiles, relationships |
| `voice/rust_voice_bridge.py` | **Rust IPC** — stdin/stdout protocol to songbird binary, TTS_DONE signal, lock management |
| `voice/audio_stream_processor.py` | **VAD pipeline** — per-user buffering, energy-based VAD, processing lock, silence detection |
| `passive_monitor.py` | Background monitor listening to all channels for passive memory storage |
| `memory_sync_monitor.py` | Sync state tracker — detects memory sync failures, race conditions, performance metrics |
| `pipeline_stages.py` | Already-extracted pipeline stages (8 stages) from earlier work |
| `response_controller.py` | Controls whether the bot should respond (rate limiting, mention detection, cooldowns) |
| `bot_personality.py` | Personality model with traits, moods, tone modifiers |
| `natural_response_generator.py` | LLM connector — builds messages, calls model, applies thinking filter |

### Dead Code Audit Results

| File | Status | Action |
|------|--------|--------|
| `memory_system.py` | DEAD (legacy ChromaDB, only imported by dead scripts) | Keep shim at root, move to `serin/memory/legacy_chromadb.py` or delete |
| `voice/voice_output_queue.py` | DEAD (zero imports, empty file) | Delete |
| `audio_config_manager.py` | DEAD (zero imports) | Delete |
| `check_qdrant_methods.py` | DEAD (zero imports) | Delete |
| `gpu.py` | DEAD (zero imports) | Delete |
| `debug_backfilling_detailed.py` | DEAD (one-time debug script) | Delete |
| `final_backfilling_verification.py` | DEAD (one-time verification) | Delete |
| `reproduce_fts_error.py` | DEAD (one-time debug script) | Delete |
| `memory_system_demo.py` | DEAD (demo script) | Move to tests/ |
| `memory_testing_framework.py` | DEAD (test framework) | Move to tests/ |
| `simple_test.py` | DEAD (test artifact) | Move to tests/ |
| `test_output.txt` | DEAD (test artifact) | Delete |
| `=2.6.1` | DEAD (malformed file, 0 bytes) | Delete |
| `desktop.ini` | DEAD (Windows artifact) | Delete |
| `requirements1.txt` | DEAD (duplicate requirements) | Delete |
| `setup_environment_fixed.sh` | DEAD (one-time setup script) | Delete or archive |
| `visual_memory_system.py` | ALIVE (imported by enhanced_message_manager.py) | Keep |
| `memory_sync_monitor.py` | ALIVE (imported by discord_bot.py) | Keep |
| `passive_monitor.py` | ALIVE (imported by discord_bot.py) | Keep |
