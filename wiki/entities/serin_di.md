---
type: entity
tags: [di, wiring, composition-root]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/SUBSYSTEM_wiring_entry_di.md, docs/CONNECTIONS.md]
status: seed
---

# serin_di (the Rule-5 composition root)

## What it is

The ONE module allowed to import pipeline/state classes. Gateway code gets objects via
`create_*`/`get_*` factories, never by importing the classes directly — this is what makes
[[gateway_isolation]] / THE_LAW Rule 5 mechanically enforceable.

## Where it lives

`serin/d1_1_pipeline_flow/d1_1_serin_di.py`

## What it owns

- **Singletons** created at startup: `_logger`, `_mention_translator`, `_message_manager`,
  `_crawler`, `_qdrant` behind `init_root()`/`set_*(obj)`/`get_*()` — getters raise
  RuntimeError if uninitialized (the pattern `test_di_contracts.py` scans whole-tree for
  read-but-never-written slots).
- **Lazy factory functions** that function-body-import pipeline/state classes:
  `create_mention_translator`, `create_qdrant_memory_system`, `create_message_crawler`,
  `create_sync_monitor`, `create_message_manager`, `build_message_pipeline` (→
  `MessagePipeline.build`), `get_thinking_filter_instance`.
- **response_generator wrappers** that poke module globals (`rg.discord_client`, `rg.llama`)
  so gateway never imports that module: `set_response_generator_client`,
  `initialize_llama_connector`, `get_llama_connector`, `get_response_generator_fn`,
  `build_voice_system_prompt`.
- **db_protect bridging** (`get_database_validation_error_type`, `create_database_protector`,
  …) and a voice→pipeline pass-through `process_voice_input`.

## Contract (from the module docstring)

"Gateway code knows how to call a factory" is fine; "gateway code imports and directly
instantiates pipeline classes" is what Rule 5 forbids.

## See also

[[gateway_isolation]] · [[the_law_rule5]] · [[message_pipeline]] · [[architecture]] · [[index]]
