# SUBSYSTEM: config_base (d1_4)

Lowest architectural layer: configuration singleton + logging. Everything else imports it.
`d1_4_config_base/` holds 4 files; `core_logger` alone is imported by 76 files (highest
inbound in the whole graph).

## Files

### `d1_4_config_base/__init__.py`
Empty package marker (0 lines of code). No re-exports.

### `d1_4_config_base/d2_1_base_config.py` — BotConfig singleton
- `load_dotenv()` at module import (line 26): reads `.env` from cwd into os.environ.
- `class BotConfig` (line 28): singleton via `__new__` (line 31) with `_instance` +
  `_initialized` guard. `__init__` runs once; all settings are read from env with
  defaults. Module-level global instance `config = BotConfig()` (line 182) — this is the
  import everyone uses (`from serin.d1_4_config_base.d2_1_base_config import config`).
- Key attributes (all from env, default shown):
  - Core: `DISCORD_TOKEN`, `DEBUG_MODE`, `TRACE_MESSAGES`, `MAINTENANCE_INTERVAL_HOURS=24`,
    `CONTROL_PANEL_PORT=8081`, `CONTROL_PANEL_KEY`, `CONTROL_PANEL_ALLOWED_ORIGINS` (CORS).
  - Feature flags: `ENABLE_VOICE=true`, `ENABLE_TTS=true`.
  - Voice: `VOICE_RECEIVER_MODE='rust'` (alt `'pycord'`), **`RUST_VOICE_RECEIVER_PATH`** —
    default `os.path.join(os.path.dirname(__file__), 'voice', 'rust_receiver', 'target',
    'release', 'voice_receiver')` = `serin/d1_4_config_base/voice/...` (line 66-69).
    ⚠️ STALE: the real Rust binary lives at repo-root `voice/rust_receiver/target/...`.
    Default only works if overridden via env `RUST_VOICE_RECEIVER_PATH`. Flag for Phase 4.
  - Qdrant: `QDRANT_HOST=localhost`, `QDRANT_PORT=6333`, `QDRANT_USE_DOCKER=false`,
    container/image names for docker auto-start.
  - Model (llama-swap/OpenAI-compatible): `LLM_MODEL='Qwen/Qwen2.5-7B-Instruct'`,
    `LLM_BASE_URL='http://localhost:8080/v1'`, `LLM_API_KEY='unused'`,  # pragma: allowlist secret — doc placeholder, not a real key
    `LLM_SUPPORTS_VISION=false`, `VISION_MODEL='smolvlm256m'`, `LLM_SUPPORTS_AUDIO=false`,
    generation params `LLM_TEMPERATURE=0.75`, `LLM_TOP_P=0.9`, `LLM_MAX_TOKENS=400`,
    `LLM_ENABLE_THINKING=false`.
  - Debug/logging: `DEBUG_MEMORY`, `DEBUG_LLM`, `LOG_LEVEL='DEBUG'`, `LOG_FORMAT='text'`.
  - Channels: `ALLOWED_CHANNEL_IDS` → `set[int]` (parsed, ValueError→warning).
  - Creator: `CREATOR_IDS` → `frozenset[str]`; digits-only entries kept, others warned;
    **falls back to a hardcoded Discord user id `{'1378682870876340395'}`** (line 121) when
    unset — this is the developer's own ID for deterministic live replies.
  - `PERSONALITY` dict (runtime-only; not persisted).
- Methods:
  - `to_dict()` (line 132): projection for the control-panel API (no secrets — token/key
    deliberately excluded).
  - `update_from_dict(data)` (line 156): runtime override of simple keys (bool/int/str cast
    by existing type), plus `ALLOWED_CHANNEL_IDS` and `PERSONALITY` merge. Used by control
    panel ops routes to hot-adjust config. Side effect: logs "BotConfig updated".
- Invariants: singleton; `_initialized` prevents re-read of env after first construct.
- Who consumes: effectively every layer. `config` is imported by core_logger/debug_logger
  (this dir), all state_core modules, pipeline, gateway, ops. `to_dict`/`update_from_dict`
  are used by `d1_5` control panel routes (see CONNECTIONS).

### `d1_4_config_base/d2_3_core_logger.py` — logging bootstrap (the 76-inbound hub)
- Module-level import side effect: `logger = setup_logging()` runs at import (lines 195, 204).
  Importing this file configures the root `"serin"` logger — this is WHY 76 files import it.
- `_PROJECT_ROOT = Path(__file__).parent` (line 22) → resolves to `serin/d1_4_config_base/`,
  so `_LOG_DIR = serin/d1_4_config_base/logs/` (confirmed on disk). ⚠️ The docstring claims
  "relative paths resolved from project root" but it is file-relative. Log file:
  `logs/serin_ai.log`, `RotatingFileHandler` 5MB × 5 backups (line 160-162).
- `SUCCESS_LEVEL = 25` custom level, registered via `logging.addLevelName`; a `.success()`
  method is monkey-patched onto `logging.Logger` (line 34). Note: other modules use
  `logging.getLogger(__name__)` which returns a logger under `serin.*` inheriting these
  handlers + level.
- `LoggerProtocol` (line 38): `@runtime_checkable` Protocol listing debug/info/warning/error/
  exception/critical/success — the structural type for logger injection across subsystems.
- `ContextFilter` (line 48): injects empty `correlation_id` onto every record.
- Formatters: `JSONFormatter` (line 58, emits ISO-8601 UTC `datetime`, level, logger,
  filename:lineno, message, optional exception + all extra= dict fields), `TextFormatter`
  (line 90), `ColoredFormatter` (line 99, ANSI per-level, only colors ≥WARNING and SUCCESS).
- `setup_logging()` (line 122): **idempotent** — returns early if `root_logger.handlers`
  exist (line 127). Reads `LOG_LEVEL` (default DEBUG) and `LOG_FORMAT` (text|json). Console
  handler at INFO (utf-8 TextIOWrapper over sys.stdout.buffer), file handler at DEBUG,
  `ContextFilter` on root. Silences noisy third-party loggers to WARNING: discord.*,
  llama_cpp, asyncio, urllib3, PIL, matplotlib, huggingface_hub, sentence_transformers,
  torch, httpx, httpcore.
- `get_correlation_id()` (line 198): `uuid4().hex[:8]`.

### `d1_4_config_base/d2_2_debug_logger.py` — DebugLogger
- `class DebugLogger` (line 13): verbose, opt-in debug logging. Reads
  `config.DEBUG_MODE` / `DEBUG_MEMORY` / `DEBUG_LLM` at construction (lines 17-19).
  Uses stdlib `logging.getLogger(__name__)` — inherits serin root handlers but NOT the
  custom `success` level usage. Methods (each early-returns unless the relevant flag):
  `log_message_received`, `log_context_built` (recent conversation/memories/profiles),
  `log_llm_input` (truncates >500 chars), `log_llm_output` (raw vs cleaned),
  `log_memory_stored`, `log_background_summary`, `log_correction_detected`,
  `log_response_decision`, `log_voice_event`. All wrap logger.info with `====` banners.
- Module globals + convenience funcs: `debug = DebugLogger()` (line 190) and module-level
  `log_message`, `log_memory`, `log_summary`, `log_correction`, `log_voice` (lines 194-216).
- Consumers (confirmed by grep):
  - `d5_3_write_store.py:24` imports `log_memory` → called at :239 on every memory write.
  - `d4_5_message_process.py:18` imports `log_correction, log_message` → :129, :239.
  - `d4_2_models_tracker.py:12` imports `log_voice` → :103 JOIN, :127 LEAVE.
  - `d3_4_voice_tracker.py` and `d5_2_tooling_background_summary.py` also import this module.

## Cross-cutting notes
- Importing `core_logger` is the de-facto logging bootstrap for the whole process — no
  explicit `setup_logging()` call is needed elsewhere.
- config `CONTROL_PANEL_ALLOWED_ORIGINS` feeds the panel CORS allow-list (see
  control_panel state module) — a config value shared across layers 1 and 5.
- `RUST_VOICE_RECEIVER_PATH` and `VOICE_RECEIVER_MODE` are the config-side half of the
  Python↔Rust subprocess seam (CONNECTIONS.md section E).
- `CREATOR_IDS` fallback embeds a real Discord user id — a hardcoded identity, not a secret.

## Verification / tests
- No dedicated tests in tests/ for config or logger (checked tests/ tree). Behavior
  verified by reading + on-disk check of the log dir.
