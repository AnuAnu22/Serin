# Project Startup Guide

## 1. Environment Setup
Ensure your `.env` file is configured. See `.env.example` (if available) or the configuration section below.

## 2. Starting the LLM Server (SGLang)
Instead of using a script, run the following Docker command. This uses environment variables from your `.env` file (or defaults if not set).

```bash
# Load environment variables from .env
export $(grep -v '^#' .env | xargs)

# Run SGLang Docker Container
docker run --gpus all \
    --name sglang-hermes \
    --shm-size 4g \
    -p ${SGLANG_PORT:-30000}:30000 \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    --ipc=host \
    lmsysorg/sglang:latest \
    python3 -m sglang.launch_server \
    --model-path ${SGLANG_MODEL_PATH:-solidrust/Hermes-3-Llama-3.1-8B-AWQ} \
    --port 30000 \
    --host 0.0.0.0 \
    --quantization ${SGLANG_QUANTIZATION:-awq} \
    --context-length ${SGLANG_CONTEXT_LENGTH:-8192} \
    --mem-fraction-static 0.5
```

### Configuration Variables (in `.env`)
| Variable | Default | Description |
| :--- | :--- | :--- |
| `SGLANG_MODEL_PATH` | `solidrust/Hermes-3-Llama-3.1-8B-AWQ` | HuggingFace model ID |
| `SGLANG_CONTEXT_LENGTH` | `8192` | Context window size |
| `SGLANG_QUANTIZATION` | `awq` | Quantization method |
| `SGLANG_PORT` | `30000` | Host port to map |

## 3. Starting the Bot
```bash
python3 main.py
```
