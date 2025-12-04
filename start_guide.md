# Project Startup Guide

## 1. Environment Setup
Ensure your `.env` file is configured. See `.env.example` (if available) or the configuration section below.

## 2. Starting the LLM Server (vLLM)
Choose one of the options below depending on your needs.

### 🚀 Option 1: Production Mode (Best Quality)
Use this for the actual bot.
**Model:** `hugging-quants/Meta-Llama-3.1-8B-Instruct-GPTQ-INT4`
**VRAM Usage:** ~7.5GB

```bash
vllm serve hugging-quants/Meta-Llama-3.1-8B-Instruct-GPTQ-INT4 \
  --host 0.0.0.0 \
  --port 8000 \
  --gpu-memory-utilization 0.65 \
  --max-model-len 8192 \
  --dtype half
```

### 🚀 Option 2: Testing Mode (Low VRAM)
Use this for development or if you are running other heavy apps (TTS, Games).
**Model:** `ModelCloud/Llama-3.2-3B-Instruct-gptqmodel-4bit-vortex-v3`
**VRAM Usage:** ~2.5GB (Ultra Efficient)

```bash
vllm serve ModelCloud/Llama-3.2-3B-Instruct-gptqmodel-4bit-vortex-v3 \
  --host 0.0.0.0 \
  --port 8000 \
  --gpu-memory-utilization 0.3 \
  --max-model-len 8192 \
  --dtype half
```

### 🚀 Option 3: Vision Testing Mode (Experimental)
Use this if you want to test Image + Thinking capabilities.
**Model:** `pramjana/Qwen3-VL-4B-Thinking-4bit-GPTQ`
**VRAM Usage:** ~3-4GB (Estimated)

```bash
vllm serve pramjana/Qwen3-VL-4B-Thinking-4bit-GPTQ \
  --host 0.0.0.0 \
  --port 8000 \
  --gpu-memory-utilization 0.4 \
  --max-model-len 8192 \
  --dtype half \
  --trust-remote-code
```
*Note: This model has no reviews. If it crashes, go back to Option 2.*

## 3. Starting the Bot
```bash
python3 main.py
```
