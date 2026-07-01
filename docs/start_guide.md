# Project Startup Guide

## 1. Environment Setup
```bash
cp .env.example .env
# Edit .env to match your setup
```

## 2. Starting the LLM Server (llama-swap)

llama-swap is an inference proxy that manages model backends (vLLM, llama.cpp, SGLang, etc.).  
Run the setup script to auto-detect your hardware and install it:

```bash
bash scripts/setup.sh
```

Or start directly with sensible defaults:

```bash
bash start_llama_swap.sh
```

The script will:
- Detect GPU / VRAM / CPU and recommend safe defaults
- Offer to install llama-swap via Docker (recommended) or binary download
- Generate a default config at `~/.config/llama-swap/config.yaml`
- Start the server on `http://localhost:8080/v1`

## 3. Starting the Bot
```bash
uv run discord_bot.py
```
