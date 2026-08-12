# SUBSYSTEM: gateway_discord — the Discord gateway + composition root (d1_2 d2_1)

Checklist: 7/7 files read. Status: DRAFT (wip). Finalize name: `SUBSYSTEM_gateway_discord.md`.

Root: `serin/d1_2_gateway_io/d2_1_io_discord/`

## Scope & role in the system

**The Discord-facing gateway — and the system's real wiring/composition hub.** This is where Serin
connects to Discord and where *all subsystems get assembled at startup*. It decides what actually
runs: the entry point, the single `discord.Client`, the event handlers, and — critically — the
`PipelineInitializer` that composes the message pipeline, memory, background processors, voice
system, crawler, sync monitor, and control panel via the `serin_di` factories (CONNECTIONS I).

Four physical pieces plus a local DI-lite couple:
1. **`d3_2_discord_bot.py`** — module-level **global state hub**: the single `client`, the
   `stats` dict, `db_protector`, and the module `None`-initialized globals (`message_manager`,
   `background_processor`, `passive_monitor`, `message_crawler`, all voice components). Nearly every
   gateway file imports `client`/`stats`/`db_protector` from here.
2. **`d3_1_pipeline_init/`** — the bottle neck: `__init__.py` holds `on_ready` + `on_message`
   (the two `@client.event` hooks that matter), the module globals re-bound after init, and re-exports
   `main`. `d4_1_main_entry.py` = `main()` (the async entry). `d4_1_pipeline_initializer.py` =
   `PipelineInitializer` (the big orchestration class).
3. **`d3_3_command_handlers.py`** — `!profile` / `!stats` / `!help`.
4. **`d3_4_event_handlers.py`** — `on_voice_state_update`, `on_error`, `run_maintenance`.

## Files

### d3_2_discord_bot.py — global state hub + DB protection  ⭐
The module that *holds the world*:
- Builds intents (`message_content`, `members`, `guilds`, `presences`, `voice_states`) and creates the
  **single `client = discord.Client(intents=intents)`**.
- **Global holders** (imported across the gateway): `mention_translator`, `message_manager`,
  `background_processor`, `passive_monitor`, `message_crawler`, `voice_listener`, `audio_processor`,
  `voice_pipeline`, `tts_engine`, `voice_output_manager`, `voice_manager`, `voice_behavior_manager` —
  all `None` until `on_ready`. `voice_available` computed by try/except importing voice components.
- `stats: dict` — messages_received/processed/ignored/passive, commands, corrections, voice_events,
  voice_messages, errors, start_time.
- `db_protector = create_database_protector("./bot_data")`; `init_database_protection()` validates all
  DBs (critical→raise `database_validation_error`, recoverable→`recover_from_corruption`), wires graceful
  shutdown, and overrides SIGINT/SIGTERM with a **voice-first** handler (disconnects RustVoiceBridge
  `_protocol` before DB backup).
- Gateway DI bootstrapping: calls `get_logger()`/`init_gateway(_default_logger)` at import so module-level
  logging works (CONNECTIONS I / io_di).
- Validates token; falls back to default `ALLOWED_CHANNEL_IDS` if none set.

### d3_1_pipeline_init/__init__.py — the hooks that run the bot  ⭐
Folder form of the former `bot_pipeline_init.py` (Rule 2). Defines:
- **`on_ready()`** (`@client.event`) → constructs `PipelineInitializer(client, bot_state)`,
  `await initialize()`, then re-binds module globals `message_manager` / `voice_behavior_manager` /
  `voice_listener`.
- **`on_message(message)`** (`@client.event`) — the intake funnel: counts stats; filters bot messages /
  non-text / empty; classifies channel allowed vs passive; **passive_monitor.process_message** for ALL
  channels; in allowed channels runs command handlers then
  **`message_manager.process_message(message)`** (→ Subsystem 8 → Subsystem 7 pipeline). This is the top
  of the canonical entry chain.
- Module globals `message_manager`/`voice_behavior_manager`/`voice_listener` (None until on_ready),
  `_initializer`; `__all__`; re-exports `main`; `if __name__ == "__main__"` → `asyncio.run(main())`.

### d3_1_pipeline_init/d4_1_main_entry.py — main() (the async entry)
`main()` — extracted from `bot_pipeline_init.py`. Sets the response-generator's discord client
(`set_response_generator_client(client)` via serin_di), logs config, then a **retry loop (max 5, backoff
`min(30, 2^n)`)** around `async with client: asyncio.create_task(run_maintenance()); await
client.start(DISCORD_TOKEN)`. Catches aiohttp/Discord connection errors; outer try/except maps the serin_di
`database_validation_error`/`database_recovery_error` types + closes client in `finally`.
**This is the single convergent entry for BOTH `python -m serin` and the hot-reloader subprocess**
(CONNECTIONS I entry duality).

### d3_1_pipeline_init/d4_1_pipeline_initializer.py — PipelineInitializer (the wiring hub, outbound 33)  ⭐
`initialize()` orchestrates the whole startup, delegating to `self._init_*`:
1. `_init_mention_translator` → `create_mention_translator(client)` (serin_di) + `set_mention_translator`,
   `init_root(logger)`, `init_database_protection()`, caches guild members.
2. `_init_database_and_memory` → `initialize_llama_connector()` + `create_qdrant_memory_system` +
   `set_qdrant`.
3. `_init_background_processors` → `BackgroundProcessor`, `PassiveMonitor`, `MessageCrawler`
   (`create_message_crawler`) + `set_crawler`, `create_sync_monitor` + `start_monitoring`.
4. `_init_voice_system` → WhisperTranscriber, VoiceMemoryPipeline, AudioStreamProcessor, VoiceListener,
   TTSEngine, TTSVoiceManager, VoiceOutputManager (Subsystems 10/11 do the work; assembled here).
5. `_init_message_manager` → `create_message_manager` + `set_message_manager`.
6. `_build_pipeline` → **`build_message_pipeline(memory_system, retrieval=context_builder,
   personality=bot_personality, temporal_context=enhanced_context, response_generator,
   thinking_filter, mention_translator, mood_state=personality, client, small_llm=llm,
   dynamics_engine, affect_engine)`** (serin_di) → attaches to `message_manager.pipeline`; also sets
   `background_processor.dynamics_engine` (another CONNECTIONS G touchpoint). CONFIRMS the canonical
   MessagePipeline (Subsystem 7) assembly chain.
7. `_init_voice_behavior`, `_wire_voice_action_callback`, `_wire_pipeline_refs`.
8. `_init_control_panel` → `init_bot_state(...)` + `start_server(CONTROL_PANEL_PORT)` (Subsystem 12).
9. `_update_bot_state` → fills the shared `bot_state` dict with every component.
Also `_backfill_recent_images` (async, semaphore-capped vision descriptions on startup).
The gateway is almost entirely **factory-consumer**: it pulls objects from `serin_di` (CONNECTIONS I
holds, `create_*`/`set_*`/`get_*`/`build_message_pipeline` from `d1_1_serin_di`).

### d3_3_command_handlers.py — !profile / !stats / !help
`handle_profile_command` (traits/interests from `message_manager.get_user_profile`),
`handle_stats_command` (aggregates manager + background + passive + voice_tracker + crawler stats),
`handle_help_command`. All return True if handled. Called from `on_message`.

### d3_4_event_handlers.py — voice + error + maintenance
`on_voice_state_update` (`@client.event`) → feeds `message_manager.voice_tracker.on_voice_update` and
`voice_behavior_manager.on_user_joined_vc`. `on_error` (`@client.event`) → increments errors.
`run_maintenance()` — periodic (config.MAINTENANCE_INTERVAL_HOURS): background_processor maintenance,
scheduled DB backup, memory cleanup (`cleanup_old_memories(90 days, min_importance 0.3)`).

`d2_1_io_discord/__init__.py` — empty (package marker).

## The canonical entry chain (Phase-4 verified)

```
python -m serin ──► __main__ ──► main_entry.main()
discord_bot.py ──► hot_reloader ──(subprocess)──► main_entry.main()
main_entry.main() ──► client.start()
  └─ on_ready @client.event ──► PipelineInitializer.initialize()
       └─ builds: mention_translator, memory, bg_processor, passive_monitor, crawler,
          sync_monitor, voice stack, message_manager, MessagePipeline, control panel
  └─ on_message @client.event ──► passive_monitor.process_message (all channels)
       └─ command handlers ──► message_manager.process_message ──► MessagePipeline.process
```

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **CONNECTIONS I = this subsystem.** The gateway is the *consumer* of the `serin_di` composition root:
   every object arrives via `create_*`/`get_*`/`set_*`/`build_message_pipeline` — gateway code never
   instantiates the pipeline/state classes directly. Confirmed entry duality: both `python -m serin`
   and `discord_bot.py` (→hot_reloader) converge on `main_entry.main()`.
2. **`d3_2_discord_bot` is the shared-state hub** — `client`/`stats`/`db_protector` and all subsystem
   globals live here and are imported across the gateway. This is a real cross-module shared-memory
   pattern (plus the `bot_state` dict filled by `_update_bot_state` for the control panel).
3. **CONNECTIONS G extra touchpoint:** `pipeline_initializer._build_pipeline` sets
   `background_processor.dynamics_engine` — the ops background processor gets the dynamics engine, joining
   the debug_routes/personality_routes/tooling_background reads (confirmed in Subsystems 3/7).
4. **`on_message` is the intake funnel** — passive_monitor sees EVERY message (all channels/cross-server
   passive learning); only allowed channels reach command handlers + the act pipeline.
5. **DB protection is gateway-born:** `init_database_protection` (validate/recover/graceful-shutdown
   w/ voice-first disconnect) runs from on_ready; `run_maintenance` does scheduled backups + cleanup.
6. **Two `main`-style entries reconciled:** `__init__` re-exports `main` from `main_entry.py`; the
   package `__init__` `if __name__=="__main__"` also runs it. Single path of truth.
7. **Voice-first shutdown** is a nice seam: SIGINT/SIGTERM disconnect the RustVoiceBridge before DB
   backup — bridging gateway + voice (Subsystem 10) + db_protect (Subsystem 2).

## What's NOT here
- The pipeline/response/memory/ingest cores (d1_1 subsystems 5-8) — **assembled** here via serin_di,
  not defined here.
- The voice stack implementation (d1_2 d2_2/d2_3, Subsystems 10/11) — instantiated/configured here but
  implemented there.
- The control panel server + state (d1_5, Subsystem 12) — started here via `init_bot_state`/`start_server`.
- The `serin_di` composition root (d1_1_serin_di.py) — consumed here (CONNECTIONS I), defined in Subsystem 4.