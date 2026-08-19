---
type: entity
tags: [config, env, singleton]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/SUBSYSTEM_config_base.md, docs/README.md]
status: seed
---

# BotConfig (config singleton)

## What it is

The env-driven configuration singleton. `load_dotenv()` at module import; `class BotConfig`
is a `__new__`-based singleton with an `_initialized` guard so env is read exactly once.
Module-level instance `config = BotConfig()` is the import everyone uses
(`from serin.d1_4_config_base.d2_1_base_config import config`) — imported by ~76 files via the
logger, the highest-inbound module in the graph.

## Where it lives

`serin/d1_4_config_base/d2_1_base_config.py`

## Key attributes (env → default)

- Core: `DISCORD_TOKEN`, `DEBUG_MODE`, `TRACE_MESSAGES`, `MAINTENANCE_INTERVAL_HOURS=24`,
  `CONTROL_PANEL_PORT=8081`, `CONTROL_PANEL_KEY`, `CONTROL_PANEL_ALLOWED_ORIGINS`.
- Voice: `ENABLE_VOICE=true`, `ENABLE_TTS=true`, `VOICE_RECEIVER_MODE='rust'` | `'pycord'`,
  and ⚠️ `RUST_VOICE_RECEIVER_PATH` (STALE — wrong default, no code reads it; the bridge
  resolves its own path — see [[known_debt]]).
- Qdrant: `QDRANT_HOST/Port`, `QDRANT_USE_DOCKER`, container/image names.
- Model: `LLM_MODEL='Qwen/Qwen2.5-7B-Instruct'`, `LLM_BASE_URL`, `LLM_API_KEY`,
  `LLM_SUPPORTS_VISION`/audio, temperature/top_p/max_tokens, `LLM_ENABLE_THINKING`.
- Channels/creator: `ALLOWED_CHANNEL_IDS` (set[int]), `CREATOR_IDS` (frozenset — **falls
  back to a hardcoded Discord user id** when unset, for deterministic live replies).
- `PERSONALITY` dict (runtime-only).

## Key methods

- `to_dict()` — control-panel projection, **secrets deliberately excluded**.
- `update_from_dict(data)` — runtime override of simple keys + channel/personality merge;
  used by panel ops routes to hot-adjust config.

## See also

[[architecture]] · [[known_debt]] · [[index]]
