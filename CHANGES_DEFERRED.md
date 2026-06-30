# Changes Deferred — Structural Migration

Items that were identified during the migration but deferred because they
require behavior changes, proper file splitting, or architectural decisions
beyond the scope of this structural migration.

## Rule 1 (5/5) Violations — Files Per Directory
- `serin/pipeline/ingest/` has 6 files (max 5)
- `serin/pipeline/act/` has 11 files (max 5)
- `serin/pipeline/remember/` has 8 files (max 5)
- `serin/state/model_system/` has 6 files (max 5)
- `serin/gateway/voice_system/` has 6 files (max 5)

## Rule 2 (500-Line) Violations — Files Over 500 Lines
- `serin/ops/database_protector.py` — 918 lines (cohesive protection system)
- `serin/ops/control_panel/server.py` — 1397 lines (web API endpoints)
- `serin/pipeline/ingest/manager.py` — 1056 lines (message processing)
- `serin/pipeline/ingest/crawler.py` — 593 lines (message sync)
- `serin/pipeline/remember/store.py` — 1517 lines (memory storage)
- `serin/pipeline/remember/retrieval.py` — 649 lines (memory retrieval)
- `serin/pipeline/think/response_controller.py` — 518 lines (response control)
- `serin/gateway/discord/bot.py` — 822 lines (Discord entry point)
- `serin/gateway/voice_system/bridge.py` — 942 lines (Rust bridge)
- `serin/gateway/voice_system/processor.py` — 826 lines (audio processing)

## Rule 5 (Import) Violations — Cousin Imports
- `serin/gateway/discord/bot.py` imports from pipeline/, ops/ (main entry point)
- `serin/ops/passive_monitor.py` imports from pipeline/ingest/
- `serin/ops/control_panel/server.py` imports from gateway/, pipeline/
- `serin/ops/control_panel/routes.py` imports from pipeline/remember/
- `serin/pipeline/ingest/manager.py` imports from personality/, gateway/

## Deferred During Previous Sessions
- `voice/rust_voice_bridge.py` was a known duplicate of `voice/bridge.py`
- `voice/audio_stream_processor.py` was a known duplicate of `voice/processor.py`
- These were resolved in this migration (deleted, importers consolidated)
