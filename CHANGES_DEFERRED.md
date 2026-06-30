# Deferred Changes (logic changes found during refactor — do not implement now)

## Format: [file] — [what was found] — [recommended fix later]

## Control Panel — Unexposed Backend Routes
- `serin/control_panel/routes.py` (6 routes: `GET /api/enhanced/status`, `POST /api/enhanced/search`, `POST /api/enhanced/memories`, `GET /api/enhanced/users/{user_id}`, `POST /api/enhanced/cleanup`, `POST /api/enhanced/test-connection`) — not wired into `index.html` because these are internal batch-processing endpoints that operate on the Qdrant backend directly. A human operator should use the standard `/api/memory/search` instead. If a dedicated "Advanced Memory" tab is desired later, wire these into a new UI panel.
- `GET /api/settings`, `POST /api/settings/update` — superseded by `/api/config` and `/api/config` (POST). The frontend already uses `/api/config` for all settings.
- `POST /api/voice/load`, `POST /api/voice/clear` — voice cloning file management (TIER 8 in server.py). The frontend has equivalent TTS voice management via `/api/tts/voice/load` and `/api/tts/voice/clear`. The voice cloning routes are a separate feature for loading speaker reference audio files into `voice_manager`. If a dedicated "Voice Cloning" panel is desired in the future, wire these routes into a new section in the voice tab.
- `GET /api/memory/user/{user_id}` — single-user profile detail. The frontend lists all known users via `/api/memory/users` but has no drill-down to see a specific user's full profile. Adding a user detail modal would be future work.
- `POST /api/brain/abort` — superseded by `POST /api/emergency-stop` which delegates to the same handler. The frontend already uses `/api/emergency-stop`.

## Code Quality

- `models/model_interface.py:111,125` — `NotImplementedError` for `chat_completion_blocking()` and `send_input_blocking()`. Every concrete connector (vllm, lm_studio, sglang) overrides `chat_completion()` and `send_input()` (async variants). The blocking methods are never called in production. If a sync caller is added, implement stubs that call `asyncio.run()` on the async variants.
- `models/factory.py:70` — "Safetensors connector not implemented yet" log message. This is future-proofing for local model loading; no user config option triggers it today. If a `provider=safetensors` config value is ever added, implement a safetensors connector.
- `voice/transcriber.py:214` — "Whisper API fallback not implemented". The code path `WhisperTranscriberFallback.transcribe()` is only reachable if `WhisperTranscriber._transcribe_local()` raises an exception AND `config.USE_WHISPER_API` is set. In production, `_transcribe_local` uses the local Whisper model (always available if whisper is installed). The fallback exists only for future cloud-API support.
- `serin/visual_memory_system.py:103` — raises `NotImplementedError`. Confirmed: this class is never imported by any production code (last caller was the root `visual_memory_system.py` which was deleted in Phase 7). The file exists in `serin/` but is dead code. Safe to delete in a future cleanup pass.
- `serin/utils/database_protector.py` — `atexit`-registered `cleanup_on_exit()` writes to `logger` after `sys.stdout` is closed during interpreter shutdown, causing `ValueError: I/O operation on closed file` on every graceful exit. This is a Python `atexit` ordering problem, not a functional bug. Fix: replace `atexit.register` with a `ContextManager` or use `sys.excepthook` for the cleanup path.
