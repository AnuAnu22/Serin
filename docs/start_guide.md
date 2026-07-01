# Project Startup Guide

## 1. Quick Start
```bash
cp .env.example .env
# Edit .env with your Discord bot token
bash setup.sh setup
```

## 2. What `bash setup.sh setup` Does

The unified setup wizard:
- Detects GPU / VRAM / CPU and recommends a safe LLM model
- Installs Python dependencies via `uv`
- Configures your Discord token and LLM settings interactively
- Offers to install llama-swap (LLM backend) via Docker or binary
- Offers to configure Qdrant (vector database) via Docker

All choices are saved to `.setup_state` — rerun anytime to change anything.

## 3. Managing Services

```bash
bash setup.sh start      # Start all configured services
bash setup.sh stop       # Stop all services
bash setup.sh status     # Show service status
bash setup.sh qdrant logs   # Tail Qdrant logs
```

## 4. Starting the Bot
```bash
uv run python -m serin
```
