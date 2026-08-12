# SUBSYSTEM: wiring_entry_di — DI containers + entry points

Checklist: 5/5 files read. Status: DRAFT (wip). Finalize name: `SUBSYSTEM_wiring_entry_di.md`.

## Scope & role in the system

This is the COMPOSITION ROOT of the whole bot. It owns:
1. **Entry points** — `serin/__main__.py` (`python -m serin`) and repo-root `discord_bot.py`.
2. **The root DI container** `d1_1_serin_di.py` — the ONE module allowed to import pipeline/state
   code; exposes factory getters/setters so gateway code can build objects without importing them.
3. **The gateway DI container** `d2_4_io_di.py` — a logger holder for the gateway layer.

These files physically sit at different layers (`serin/`, `serin/d1_1_pipeline_flow/`,
`serin/d1_2_gateway_io/`, repo root) but they are one logical unit: the wiring layer.

## Files

### serin/__main__.py
`python -m serin` entry. Imports `main` from
`serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init` (i.e. `d4_1_main_entry.py:main()`)
and runs it under `asyncio.run()`. This is the DIRECT bot path (no hot-reloader).

### discord_bot.py (repo root)
**Unified entry point.** Loads `.env` (dotenv). `main()`:
1. `await auto_start_qdrant()` — optionally starts a Qdrant Docker container
   (`QDRANT_USE_DOCKER=true` env; probes `localhost:{port}/health`; docker-run with
   `--restart unless-stopped`; wait loop up to 60s, continues anyway on timeout).
2. `await hot_reloader_main()` — delegates to `d1_5_ops_tooling/d2_3_hot_reloader.main()`.
   So the ROOT entry launches the **hot-reloader**, which separately spawns the Discord bot as a
   subprocess and auto-restarts it on file changes. Contrast with `__main__.py` running the bot
   directly. Two parallel entry idioms.

### serin/d1_1_pipeline_flow/d1_1_serin_di.py
**Root DI container.** Deliberately engineered as the composition seam enforcing **Gateway
Isolation (Rule 5)**. It holds singletons created at startup (`_logger`, `_mention_translator`,
`_message_manager`, `_crawler`, `_qdrant`) behind `init_root()`/`set_*(obj)`/`get_*()` — each getter
RaiseRuntimeError if uninitialized. It also defines **factory functions** that lazily (function-body)
import pipeline/state classes and construct them, so gateway/PipelineInitializer code calls a
factory instead of importing the class directly. Factories include:
`create_mention_translator`, `create_qdrant_memory_system`, `create_message_crawler`,
`create_sync_monitor`, `create_message_manager`, `build_message_pipeline` (pass-through to
`MessagePipeline.build`), `get_thinking_filter_instance`, and response_generator wrappers
(`set_response_generator_client`, `initialize_llama_connector`, `get_llama_connector`,
`get_response_generator_fn`, `build_voice_system_prompt`) that poke module globals in
`response_generator.py` (`rg.discord_client`, `rg.llama`) — again so gateway never touches the
module directly. Also `db_protect` bridging (`get_database_validation_error_type`,
`get_database_recovery_error_type`, `create_database_protector`,
`get_database_protector_instance`) and a voice→pipeline pass-through `process_voice_input`.
The module DOCSTRING explicitly defenes the contract: "gateway code knows how to call a factory"
is fine; "gateway code imports and directly instantiates pipeline classes" is what Rule 5 forbids.

### serin/d1_2_gateway_io/d2_4_io_di.py
Small gateway-layer DI: `init_gateway(logger)` + `get_logger()` (raises if not initialized). It
hosts a LoggerProtocol holder so gateway modules obtain the logger via this container rather than
re-importing config. (Much lighter than serin_di by design.)

### serin/__init__.py
Empty.

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **Two independent entry paths:**
   - `python -m serin` (`__main__.py`) → `d4_1_main_entry.py:main()` → runs the bot directly.
   - `python discord_bot.py` (`discord_bot.py`) → auto-start Qdrant Docker → hot-reloader
     (`d2_3_hot_reloader.main()`) → spawns bot subprocess with auto-restart.
   This corrects the Phase-1 CONNECTIONS note (entry "moved to d4_1_main_entry.py"): the current
   tree shows the DISCORD_BOT root now goes through the hot-reloader, while __main__ is direct.
   Whichever runs at deploy is an ops decision — flag for Phase-4 to confirm which is canonical.
2. **`serin_di` is the Gateway-Isolation seam** (Rule 5-legal composition root). It's the sole
   importer of pipeline/state classes; everything else in gateway relies on its factories. This is
   the structural backbone that makes `d4_1_pipeline_initializer.py` (gateway, 33 outbound) not
   violate layering — it calls factories here instead of importing pipeline classes.
3. **Factory pattern vs TYPE_CHECKING imports:** type hints reference pipeline/state classes under
   `TYPE_CHECKING` only; the actual imports happen lazily inside factory function bodies.
4. `discord_bot.py` root uses `subprocess`/`urllib`; `d2_3_hot_reloader` (d1_5 ops) owns process
   spawning. `serin_core` rebuild (cargo) is watched there too.

## What's NOT here
- The actual bot `main()` implementation lives in `d1_2_gateway_io/.../d4_1_main_entry.py`
  (Subsystem 9, gateway_discord). PipelineInitializer too.
- The hot-reloader is documented in Subsystem 12 (ops_tooling).