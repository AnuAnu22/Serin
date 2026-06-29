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

## Project Structure

```
├── discord_bot.py              # Main bot entry point
├── hot_reloader.py             # Auto-reload on file changes
├── web_server.py               # Control panel Flask app
├── config.py                   # Configuration from env
├── pyproject.toml              # Python dependencies
├── .env.example                # Config template
├── voice/                      # Voice pipeline
│   ├── audio_stream_processor.py  # VAD, silence detection, burst filter, processing lock
│   ├── rust_voice_bridge.py       # stdin/stdout bridge to Rust binary
│   ├── rust_receiver/src/main.rs  # DAVE-compatible Rust voice receiver
│   ├── voice_output_manager.py    # TTS synthesis and queuing
│   ├── voice_memory_pipeline.py   # Voice message processing
│   ├── whisper_transcriber.py     # Speech-to-text via faster-whisper
│   └── ...                      # Profiles, behavior, tracker, etc.
├── serin_core/                 # PyO3 Rust module (optional)
│   └── src/lib.rs              # FTS, thinking filter, contractions, etc.
├── memory_system.py            # Qdrant vector memory
├── enhanced_memory_retrieval.py # Hybrid search (BM25 + semantic)
├── conversation_context_builder.py  # Context assembly
├── natural_response_generator.py    # Response formatting
└── tests/                      # Test suite
```

## Voice Pipeline

1. User speaks → Discord sends encrypted Opus frames
2. Rust receiver (DAVE-compatible) decrypts + decodes to PCM → stdout
3. `audio_stream_processor.py` reads PCM chunks, runs VAD, buffers speech
4. After 1.5s of consecutive silence (with burst filter: noises <0.5s ignored), audio is queued
5. If model supports audio (Gemma), raw PCM is sent via `input_audio` field — skips STT
6. Otherwise, Whisper transcribes audio to text
7. LLM generates response → Edge-TTS synthesizes → Rust plays in voice channel
8. Processing lock blocks new audio until `TTS_DONE` signal from Rust (track end event)

## Development

```bash
# Run tests
pytest tests/

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
