# Serin — AI Discord Bot with Voice & Memory

Advanced Discord AI bot featuring real-time voice conversation, Qdrant vector memory, multi-modal LLM support (text, vision, audio), and a Web control panel.

## Features

- **Voice Chat** — Real-time speech detection with DAVE-compatible Rust receiver, VAD-based silence detection (configurable threshold), noise burst filtering, Whisper transcription, and Edge-TTS speech synthesis
- **Memory System** — Qdrant vector database for long-term conversational memory with BM25 + semantic hybrid search, topic fatigue tracking, and temporal context
- **Multi-Modal** — Vision support (image analysis via smolvlm or similar), direct audio input to Gemma 12B (skip STT, `input_audio` field)
- **Control Panel** — Web dashboard (Flask on port 8081) for monitoring, configuration, and manual interaction
- **Hot Reloader** — Auto-detects Python, Rust (serin_core), and Rust voice receiver changes; rebuilds and restarts automatically
- **Conversation Management** — Enhanced message manager, context builder, natural response generation, thinking filter, correction handler, mention translator

## Quick Start

### Prerequisites

- Python 3.11+
- Rust toolchain (for building the voice receiver and optional PyO3 module)
- A Discord bot token with voice intents enabled
- An OpenAI-compatible LLM endpoint (llama-swap, vLLM, Ollama, etc.)
- Qdrant vector database (optional for memory features)

### Setup

```bash
# 1. Clone and configure
git clone <repo-url> Serin
cd Serin
cp .env.example .env
# Edit .env: fill in DISCORD_TOKEN, model URL, etc.

# 2. Create virtualenv and install dependencies
pip install uv
uv sync
# or: pip install -r requirements.txt

# 3. Build the Rust voice receiver (required for voice features)
cd voice/rust_receiver
cargo build --release
cd ../..

# 4. Build the serin_core PyO3 module (optional — Python fallbacks exist)
cd serin_core
maturin develop --release
cd ..

# 5. Start the bot
python3 hot_reloader.py
```

The bot runs in a tmux-compatible hot-reload loop. Changes to `.py` files, `serin_core/src/lib.rs`, or `voice/rust_receiver/src/*.rs` trigger automatic rebuild + restart.

### Environment Variables

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Discord bot token (required) |
| `VLLM_BASE_URL` | OpenAI-compatible LLM API endpoint |
| `LLM_MODEL` | Model name (e.g. gemma12b) |
| `LLM_PROVIDER` | Backend type (vllm, etc.) |
| `QDRANT_HOST` / `QDRANT_PORT` | Qdrant vector database connection |
| `ENABLE_VOICE` | Voice features (`true`/`false`) |
| `ENABLE_TTS` | Text-to-speech (`true`/`false`) |
| `VOICE_RECEIVER_MODE` | `"rust"` (DAVE-compatible) or `"pycord"` |
| `LLM_SUPPORTS_VISION` | Enable vision/image inputs |
| `LLM_SUPPORTS_AUDIO` | Enable direct audio input to Gemma |
| `CONTROL_PANEL_PORT` | Web dashboard port (default 8081) |
| `DEBUG_MODE` | Enable debug logging |
| `TRACE_MESSAGES` | Trace raw messages |
| `ALLOWED_CHANNEL_IDS` | Restrict bot to specific channels |

## Architecture

Serin is organized as a message pipeline:

```
Discord Event
     │
     ▼
MessagePipeline (serin/messaging/pipeline.py)
     │
     ├── ResponseDecisionStage   — should Serin respond?
     ├── MemoryRetrievalStage    — fetch relevant memories from Qdrant
     ├── TemporalStage           — resolve time references
     ├── PersonalityStage        — inject tone + traits
     ├── PromptAssemblyStage     — build LLM prompt
     ├── LLMCallStage            — call the model
     ├── ResponseCleaningStage   — filter + naturalize response
     ├── SendStage               — type + send to Discord
     └── MemoryWriteStage        — store interaction in Qdrant
```

Each stage is independently testable in `serin/messaging/stages/`. Adding behavior = adding one stage.

## Project Structure

```
├── discord_bot.py              # Main bot entry point
├── hot_reloader.py             # Auto-reload on file changes
├── pyproject.toml              # Python dependencies
├── .env.example                # Config template
│
├── serin/                      # Main package
│   ├── core/                   # Config, logging — imported by everything
│   │   ├── config.py
│   │   └── logger.py
│   ├── memory/                 # Qdrant vector store, BM25 index, hybrid search
│   │   ├── qdrant.py
│   │   ├── retrieval.py
│   │   ├── context.py
│   │   ├── sync_monitor.py
│   │   └── temporal.py
│   ├── messaging/              # Message pipeline — all text response logic
│   │   ├── pipeline.py         # MessagePipeline: runs 9 stages in order
│   │   ├── context.py          # MessageContext: data envelope for stages
│   │   ├── manager.py          # Pre-processing wrapper for backwards compat
│   │   ├── stages/             # 9 pipeline stage files
│   │   │   ├── decision.py, memory_retrieval.py, temporal.py,
│   │   │   ├── personality.py, prompt_assembly.py, llm_call.py,
│   │   │   ├── response_cleaning.py, send.py, memory_write.py
│   │   ├── response_generator.py
│   │   ├── response_controller.py
│   │   ├── mention_translator.py
│   │   ├── fillers.py, typos.py
│   │   ├── correction_handler.py
│   │   ├── long_message.py, crawler.py
│   │   └── context_builder.py
│   ├── personality/            # Personality traits, conversation mood
│   │   ├── bot_personality.py
│   │   ├── conversation_analyzer.py
│   │   └── topic_fatigue.py
│   ├── utils/                  # Support utilities
│   │   ├── background.py, passive_monitor.py
│   │   ├── thinking_filter.py, debug_logger.py
│   │   └── database_protector.py
│   └── control_panel/          # Web dashboard (Flask)
│       ├── server.py
│       └── routes.py
│
├── voice/                      # Voice pipeline
│   ├── bridge.py               # stdin/stdout bridge to Rust binary
│   ├── processor.py            # VAD, silence detection, burst filter, lock
│   ├── pipeline.py             # Voice message processing
│   ├── output.py               # TTS synthesis and queuing
│   ├── transcriber.py          # Speech-to-text via faster-whisper
│   ├── listener.py             # Voice connection listener
│   ├── behavior.py             # Voice behavior rules
│   ├── tracker.py, decider.py, profiles.py
│   └── rust_receiver/src/main.rs  # DAVE-compatible Rust voice receiver
│
├── models/                     # LLM connectors
│   ├── factory.py, interface.py, adapter.py
│   ├── vllm.py, lm_studio.py, sglang.py
│
├── serin_core/                 # PyO3 Rust module (optional)
│   └── src/lib.rs              # FTS, thinking filter, contractions, etc.
│
├── tts/                        # Text-to-speech engine
│   └── tts_engine.py
│
├── tests/                      # Test suite (run with pytest)
│   ├── messaging/stages/       # Pipeline stage unit tests
│   ├── voice/                  # Voice processor smoke tests
│   └── memory/                 # Memory system tests
│
└── docs/                       # Reference documentation
    ├── LOGGING.md              # Structured logging convention
    └── ARCHITECTURE.md         # Detailed architecture reference
```

## Data Flow

### Text Message
1. `discord_bot.py:on_message()` receives Discord event
2. `MessagePipeline.process(ctx)` runs 9 stages in sequence
3. Response sent to Discord; interaction stored in Qdrant

### Voice Message
1. User speaks → Discord sends encrypted Opus frames
2. Rust receiver decrypts + decodes to PCM → stdout
3. `voice/processor.py` reads PCM chunks, runs VAD, buffers speech
4. After 1.5s of consecutive silence (bursts <0.5s ignored), audio queued
5. If Gemma (supports `input_audio`), raw PCM sent to LLM directly — skips STT
6. Otherwise Whisper transcribes to text
7. LLM generates → Edge-TTS synthesizes → Rust plays in voice channel
8. Processing lock released on `TTS_DONE` from Rust

## Development

```bash
# Run tests (excludes integration tests requiring live services)
pytest tests/ -m "not integration"

# Build Rust components manually
cd voice/rust_receiver && cargo build --release
cd serin_core && maturin develop --release

# Debug voice pipeline
LOG_LEVEL=DEBUG python3 hot_reloader.py
```

## Troubleshooting

- **DAVE `opus_decode` errors** — mitigated by lowered VAD threshold (150), always-buffer mode. If persistent, check `vendor/songbird/src/driver/tasks/udp_rx/mod.rs:229-232` for the DAVE `adjusted_tail` fix.
- **Processing lock stuck** — 30-second safety net auto-releases if TTS_DONE signal isn't received.
- **Fresh clone issues** — ensure `voice/rust_receiver` and `serin_core` are fully built (steps 3–4 above).
