# Serin — AI Discord Bot with Voice, Memory & Personality

> *"It's not a bot. It's Serin."*

[![CI](https://github.com/AnuAnu22/Serin/actions/workflows/test.yml/badge.svg)](https://github.com/AnuAnu22/Serin/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Rust](https://img.shields.io/badge/rust-required-F74C00?logo=rust&logoColor=white)](https://www.rust-lang.org)

Serin is an advanced Discord AI companion that processes **text and voice** through a
10-stage message pipeline, backed by **Qdrant vector memory + SQLite**, a **Bayesian
belief/evidence system**, an **affect & conversation-dynamics engine**, and an
OpenAI-compatible LLM backend (llama-swap / vLLM / Ollama / LM Studio / …). Voice transport
uses a **Rust subprocess** for DAVE-compatible Discord voice decryption + playback, and an
**optional Rust PyO3 module** (`serin_core`) that accelerates hot loops but degrades
gracefully to pure Python when absent. A **FastAPI control panel** exposes live pipeline
telemetry over WebSockets.

See [`docs/SERIN_VISION.md`](docs/SERIN_VISION.md) for the full design philosophy.

## Why Serin is different

Most Discord bots are command-line tools wearing a costume: they reply instantly, to
everything, with no memory of who you are. Serin is built around the opposite bet — that a bot
earns its place in a community the same way a person does, through *accumulated, persistent
state* rather than a fresh performance each turn.

- **Causality, not performance.** Serin's warmth, bias, and silences are *downstream of real
  history with you* — not rolled from a die or pasted in by a prompt. Push on it and the state
  holds.
- **It decides, like a person.** Reply, react, or stay quiet — chosen by a
  conversation-dynamics engine, not a keyword trigger. And it never replies *instantly* unless
  a human would.
- **Relationships that drift.** Familiarity, mood, and affect change how it talks to you over
  weeks, not within a single message. It forms opinions and can grow to like — or dislike — you.
- **Imperfect, human memory.** It remembers fuzzily — emotional impressions and key facts, not
  database dumps — and forgets the way people do.
- **The "BOT" tag stops mattering.** Serin never denies what it is, but the tag shouldn't be the
  reason it feels present. That's the whole goal.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
  - [See it come alive (2 minutes)](#see-it-come-alive-2-minutes)
- [Architecture](#architecture)
- [Data Flow](#data-flow)
- [Development](#development)
- [Documentation](#documentation)
- [Contributing](#contributing)

## Features

- **Natural presence, not a command tool** — replies are *caused* by accumulated relational
  state (familiarity, mood, affect, standing) rather than rolled fresh each turn. Serin decides
  to reply / react / ignore, and times its responses like a person.
- **10-stage message pipeline** — Decision → Retrieval → Plan (belief-constrained) → Temporal →
  Personality → Prompt Assembly → LLM → Cleaning → Send → Memory Write. Each stage is an
  independently testable unit (see [`docs/SUBSYSTEM_pipeline_act.md`](docs/SUBSYSTEM_pipeline_act.md)).
- **Voice conversation** — Rust `voice_receiver` subprocess decrypts/decodes Discord Opus to PCM,
  Python runs VAD + silence detection + noise-burst filtering, Whisper transcribes, and Edge-TTS /
  Coqui synthesizes the reply played back into the voice channel.
- **Memory & beliefs** — Qdrant vector store with BM25 + semantic hybrid search, a Bayesian
  belief/evidence engine (`PENDING → SUPPORTED → CONTESTED → SUPERSEDED`), fact extraction,
  and a SQLite backing store. Per-user relationships, evidence, and episodic memories.
- **Multi-modal LLM** — vision inputs (e.g. `smolvlm`) and direct audio input (`input_audio` to
  Gemma-class models, skipping STT) when the configured model supports them.
- **Affect & conversation dynamics** — a `ConversationDynamicsEngine` (Boltzmann-style
  energy model) drives the reply/react/ignore decision and natural typing delays; an
  `AffectEngine` tracks per-user sentiment over time.
- **FastAPI control panel** — web dashboard with WebSocket live updates: pipeline stage events,
  prompt-debug snapshots, personality mood history, and bot state.
- **Hot reloader** — watches `*.py`, `cargo build`s the voice receiver / `maturin develop`s
  `serin_core` automatically, and restarts the bot on change.
- **Lawful architecture** — the codebase is governed by a strict, enforced architecture
  ([`docs/THE_LAW.md`](docs/THE_LAW.md)): depth-sequence naming, a 5/5 directory horizon,
  a 500-line ceiling, and a depth-DAG import rule (Rule 5).

## Quick Start

### Option A — Setup wizard (recommended)

`setup.sh` detects your GPU/VRAM/CPU, recommends a model, installs dependencies via `uv`,
configures your Discord token + LLM settings interactively, and can spin up llama-swap and
Qdrant via Docker.

```bash
cp .env.example .env          # baseline config; the wizard edits it interactively
bash setup.sh setup           # interactive: deps + Discord token + LLM + Qdrant
bash setup.sh start           # start configured services (llama-swap + Qdrant)
uv run python -m serin        # run the bot
```

Manage services any time:

```bash
bash setup.sh status          # service status
bash setup.sh stop            # stop all services
bash setup.sh qdrant logs     # tail Qdrant logs
```

### Option B — Manual setup

```bash
# 1. Configure
cp .env.example .env
# Edit .env: set DISCORD_TOKEN, LLM_BASE_URL, LLM_MODEL, etc.

# 2. Dependencies (uv is required)
pip install uv
uv sync                       # installs everything in pyproject.toml

# 3. Rust voice receiver (required for voice features)
cargo build --release --manifest-path voice/rust_receiver/Cargo.toml
#   → produces target/release/voice_receiver

# 4. serin_core PyO3 module (optional — Python fallbacks exist)
cd serin_core && maturin develop --release && cd ..

# 5. Run
uv run python -m serin
```

> **Entry points (both canonical):** `uv run python -m serin` runs the bot directly
> (retry + clean-shutdown). `python discord_bot.py` (repo root) launches it under the
> hot reloader — a watched subprocess that auto-restarts on code/Rust changes. Use the
> reloader during development: `uv run python hot_reloader.py`.

### See it come alive (2 minutes)

Once the bot is running in a channel (text is enough — voice is optional):

1. **Talk to it like a person.** Say something, or `@mention` it. Watch it *not* always reply
   instantly — it decides whether to respond, react, or stay quiet, and paces itself like a
   human.
2. **Open the control panel** at `http://localhost:8081` (port set by `CONTROL_PANEL_PORT`).
   It streams the pipeline **live**: every stage the message flows through, the prompt snapshot,
   personality mood, and bot state — over WebSockets.
3. **Build a relationship.** Mention it over a few sessions and watch familiarity, mood, and
   affect shift how it talks to you. Ask it what it thinks of someone and see the standing
   (friend / stranger / enemy) surface in its voice.

That feedback loop — *state in, behavior out* — is the whole point, and it's visible the moment
the panel lights up.

### Prerequisites

- **Python 3.11+**
- **Rust toolchain** (for the voice receiver and the optional `serin_core` module)
- A **Discord bot token** with the *Message Content* and *Server Members* intents, plus
  voice intent (Privileged Gateway Intents) enabled
- An **OpenAI-compatible LLM endpoint** (llama-swap, vLLM, Ollama, LM Studio, SGLang, …)
- **Qdrant** (optional for memory — Docker-managed via `QDRANT_USE_DOCKER=true`, or bring your own)

### Environment Variables

Based on [` .env.example`](.env.example). All settings are env-driven (loaded by
`serin/d1_4_config_base/d2_1_base_config.py` → `BotConfig`).

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Discord bot token (**required**) |
| `LLM_BASE_URL` | OpenAI-compatible API endpoint (e.g. `http://localhost:8080/v1`) |
| `LLM_API_KEY` | API key (ignored by most local backends) |
| `LLM_MODEL` | Model identifier (e.g. `Qwen/Qwen2.5-7B-Instruct`, `gemma12b`) |
| `LLM_TEMPERATURE` / `LLM_TOP_P` / `LLM_MAX_TOKENS` | Generation parameters |
| `LLM_ENABLE_THINKING` | Enable reasoning/thinking tokens (`true`/`false`) |
| `LLM_SUPPORTS_VISION` | Enable vision/image inputs |
| `VISION_MODEL` | Vision model (e.g. `smolvlm256m`) |
| `LLM_SUPPORTS_AUDIO` | Enable direct audio input to the LLM (`true`/`false`) |
| `QDRANT_HOST` / `QDRANT_PORT` | Qdrant connection (`localhost:6333` default) |
| `QDRANT_USE_DOCKER` | Auto-manage Qdrant via Docker (`true`/`false`) |
| `ENABLE_VOICE` / `ENABLE_TTS` | Voice + text-to-speech features |
| `VOICE_RECEIVER_MODE` | `"rust"` (DAVE-compatible, default) or `"pycord"` |
| `CREATOR_IDS` | Comma-separated user IDs that always get an instant reply |
| `ALLOWED_CHANNEL_IDS` | Restrict the bot to specific channel IDs |
| `CONTROL_PANEL_PORT` | Web dashboard port (default `8081`) |
| `CONTROL_PANEL_KEY` | Sets panel auth; empty = no auth (dev only) |
| `DEBUG_MODE` / `TRACE_MESSAGES` / `DEBUG_MEMORY` / `DEBUG_LLM` | Debug logging toggles |
| `LOG_LEVEL` | `DEBUG`/`INFO`/… |
| `LOG_FORMAT` | `text` (default) or `json` |
| `MAINTENANCE_INTERVAL_HOURS` | Periodic maintenance cadence |

## Architecture

Serin follows a **layered, dependency-ordered architecture** enforced by
[`docs/THE_LAW.md`](docs/THE_LAW.md) (Rule 5 — the Depth DAG). A single composition root
(`serin/d1_1_serin_di.py`) owns all pipeline/state class imports; the
gateway consumes them through `create_*`/`get_*` factories, so a file may only import from
strictly shallower depth.

Five numbered layers (`d1_1` … `d1_5`) hold the system in dependency order
(low-numbered = higher in the graph):

| Layer | Role |
|---|---|
| `d1_1_pipeline_flow` | The message lifecycle: ingest → perceive → think → remember → act (the 10-stage DAG + dispatch) |
| `d1_2_gateway_io` | I/O boundaries: Discord gateway, voice system, STT transcribe |
| `d1_3_state_core` | Shared state (lowest layer): logger, core memory, model system, voice, conversation state |
| `d1_4_config_base` | `BotConfig` singleton + debug logging |
| `d1_5_ops_tooling` | Operational machinery: FastAPI control panel, background processor, hot reloader, passive monitor |

### The 10-stage message pipeline

```
Discord Event (on_message)
      │
      ▼
EnhancedMessageManagerV3  ── builds a MessageContext envelope + MessagePipeline
      │
      ▼
┌─────────────────────────── MessagePipeline (10 stages) ───────────────────────────┐
│  1. ResponseDecisionStage   — reply / react / ignore? (ConversationDynamicsEngine) │
│  2. MemoryRetrievalStage    — hybrid BM25+vector search from Qdrant               │
│  3. ResponsePlannerStage    — belief-constrained plan (Bayesian beliefs)           │
│  4. TemporalStage           — resolve date/time references                         │
│  5. PersonalityStage        — inject persona + per-relationship tone              │
│  6. PromptAssemblyStage     — build the full prompt (8 context sections)          │
│  7. LLMCallStage            — call the model                                      │
│  8. ResponseCleaningStage   — strip thinking tags, humanize, truncate             │
│  9. SendStage               — type + send to Discord (natural delay)              │
│ 10. MemoryWriteStage        — ALWAYS runs: perceive + store + affect feedback     │
└────────────────────────────────────────────────────────────────────────────────────┘
```

Stages broadcast live events to the control panel (WebSocket) as they run. The pipeline
breaks early when the decision stage sets `halt_reason`, but **`MemoryWriteStage` always runs**
— so perception, memory, personality, and affect update for *every* message even when Serin
stays silent.

### Project layout (top level)

```
Serin/
├── discord_bot.py            # Root entry → hot reloader (auto-restart)
├── hot_reloader.py           # Root entry → runs the reloader
├── pyproject.toml           # Python deps + tool config (ruff/mypy/pyright/…)
├── setup.sh                 # Unified setup/start/stop/status wizard
├── .env.example             # Config template
├── README.md                # This file
│
├── serin/                   # All source (5 depth-1 layers, d1_1 … d1_5)
│   ├── d1_1_pipeline_flow/  # ingest, perceive, think, remember, act
│   ├── d1_2_gateway_io/     # discord (incl. main_entry + initializer), voice, transcribe
│   ├── d1_3_state_core/     # logger, core memory (Qdrant/SQLite/BM25), model, voice, conversation
│   ├── d1_4_config_base/    # BotConfig singleton
│   └── d1_5_ops_tooling/    # control panel (FastAPI), background, hot reloader, monitors
│
├── serin_core/              # Optional Rust PyO3 accelerator (FTS, thinking filter, contractions)
├── voice/rust_receiver/     # Rust voice binary (DAVE-compatible) + vendored songbird
├── control_panel/static/    # Dashboard HTML/JS
├── tts/                     # Text-to-speech voice assets
├── scripts/                 # Automation: law checkers, undef-var scanner, deploy helpers
├── bot_data/                # Runtime data: bot_data.db (SQLite), memory_fts.db (FTS5), Qdrant
├── tests/                   # pytest suite (mirrors serin/)
└── docs/                    # Reference documentation (see below)
```

The full subsystem map (14 subsystems) and per-file verification live in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); cross-cutting edges (panel observability,
affect→store, PyO3 seams, voice seam, DI/entry duality) are enumerated in
[`docs/CONNECTIONS.md`](docs/CONNECTIONS.md).

## Data Flow

### Text message → reply
1. `discord_bot.on_message` runs the intake funnel (skips own/non-text/DM/empty messages,
   routes allowed vs passive channels, short-circuits command handlers), then calls
   `message_manager.process_message`.
2. `EnhancedMessageManagerV3` builds a `MessageContext` envelope and a fresh `MessagePipeline`
   (wired with the retrieval/context builder, dynamics engine, and affect engine).
3. The **10-stage DAG** runs: the decision stage consults the `ConversationDynamicsEngine`
   (reply/react/ignore) and `AffectEngine`; retrieval searches Qdrant/BM25; the planner writes a
   belief-constrained plan; personality + temporal context are injected; the prompt is assembled;
   the LLM is called; output is cleaned; the reply is sent.
4. **`MemoryWriteStage`** perceives the exchange, stores facts/beliefs/evidence, updates
   relationships and per-user affect, then writes the reply — for every message, even on halt.

### Voice message → response
1. Gateway `on_voice_state_update` feeds the `VoiceTracker`.
2. The Rust `voice_receiver` subprocess decodes Discord voice UDP (via songbird — no second
   gateway client, avoiding dual-gateway conflict) and streams `AUDIO:{uid}:{len}` PCM lines.
3. `AudioStreamProcessor` buffers per-user PCM with VAD (RMS-150) under a per-guild lock;
   `VoiceMemoryPipeline` transcribes (Whisper) and routes to the response path.
4. The reply is queued to `VoiceOutputManager`, TTS'd (edge-tts→ffmpeg or Coqui), and sent to
   Rust as `SPEAK:{len}`+WAV; on playback end Rust emits `TTS_DONE`, which releases the Python
   per-guild lock.

### Control panel
Routes read live `ConversationDynamicsEngine` state, `PersonalityState` mood history, and the
`bot_state` dict. `/api/bot/restart` writes a gate-confirmed `.restart.signal` that the hot
reloader picks up. The `BackgroundProcessor` summarizes message batches via the extractor LLM
and runs impression/affect batches.

## Development

```bash
# Install + hooks
pip install uv && uv sync
cp scripts/hooks/pre-commit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

# Run non-integration tests (requires no live services)
uv run pytest tests/ -m "not integration" -q

# Build Rust components
cargo build --release --manifest-path voice/rust_receiver/Cargo.toml
maturin develop            # serin_core (optional accelerator; bot runs without it)

# Debug the voice pipeline
LOG_LEVEL=DEBUG uv run python hot_reloader.py
```

### Static-analysis & architecture gates (CI)

These must pass clean before merge (see [`AGENTS.md`](AGENTS.md) and
[`CONTRIBUTING.md`](CONTRIBUTING.md)):

```bash
uv run ruff check serin/                 # lint + imports + format gate
uv run mypy serin/                       # strict type checking
uv run pyright serin/                    # Pyright (LSP) gate
uv run semgrep --config .semgrep/rules/  # custom patterns (no bare except, no os.environ, …)
.venv/bin/import-linter lint             # THE_LAW Rule 5 layer boundaries
uv run bandit -r serin/ -q               # security scan
uv run detect-secrets scan --baseline .secrets.baseline
```

`serin_core` uses a Rust dev/CI CLI (`scripts/undef-var-scanner`) exercised by the test suite:
build it with `cargo build --release --manifest-path scripts/undef-var-scanner/Cargo.toml`.

### THE_LAW (architectural invariants)

Every contribution must comply with [`docs/THE_LAW.md`](docs/THE_LAW.md):

- **5/5 Horizon** — no directory exceeds 5 files + 5 subdirectories.
- **500-Line Ceiling** — no `.py` file exceeds 500 lines (a file becomes a folder at 501).
- **Depth-Sequence Naming** — `d{depth}_{seq}_{word}_{word}.py` (the name *is* the address).
- **Import DAG (Rule 5)** — a file may only import from strictly shallower depth digits.
- **Required Sections** — every file has Imports / Types / Constants / Entry / Core / Helpers / Errors.

Validate locally:

```bash
uv run python scripts/law/check_structure.py
uv run python scripts/law/check_imports.py
```

## Documentation

| Doc | What it covers |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Living, per-file architecture map (14 subsystems) |
| [`docs/CONNECTIONS.md`](docs/CONNECTIONS.md) | Cross-subsystem edge list + shared state |
| [`docs/THE_LAW.md`](docs/THE_LAW.md) | The enforced architectural law |
| [`docs/SERIN_VISION.md`](docs/SERIN_VISION.md) | Design philosophy & prime directive |
| [`docs/ENGINEERING_STANDARDS.md`](docs/ENGINEERING_STANDARDS.md) | Code-organization standards |
| [`docs/CODING_GUIDELINES.md`](docs/CODING_GUIDELINES.md) | Behavior guidelines |
| [`docs/start_guide.md`](docs/start_guide.md) | Setup/service walkthrough |
| `docs/SUBSYSTEM_*.md` | One deep doc per subsystem (act, ingest, remember, think, gateway_*, rust_accel, tests, …) |
| [`docs/troubleshooting_guide.md`](docs/troubleshooting_guide.md) | Qdrant / memory / integration troubleshooting |
| [`docs/deployment_checklist.md`](docs/deployment_checklist.md) | Deployment checklist |
| [`SECURITY.md`](SECURITY.md) | Security policy |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution workflow |

## Contributing

1. Fork & clone, install deps with `uv sync`, install the pre-commit hook.
2. Branch: `git checkout -b feat/my-feature`.
3. Make changes following THE_LAW; run `pytest` + the structure/import/lint gates locally.
4. Commit with conventional prefixes (`feat:`, `fix:`, `refactor:`, `docs:` …).
5. Push and open a PR; CI gates + a code-owner approval are required.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for full details.

## License

See repository license file.
