# Project Startup Guide

## 1. Environment Setup
Ensure your `.env` file is configured. See `.env.example` (if available) or the configuration section below.

## 2. Starting the LLM Server (vLLM)
Run the following command to start the vLLM server. This uses environment variables from your `.env` file (or defaults if not set).

```bash
# Load environment variables from .env
export $(grep -v '^#' .env | xargs)

# Run vLLM Server
python3 -m vllm.entrypoints.openai.api_server \
    --model ${VLLM_MODEL_PATH:-solidrust/Hermes-3-Llama-3.1-8B-AWQ} \
    --quantization ${VLLM_QUANTIZATION:-awq} \
    --dtype half \
    --max-model-len ${VLLM_MAX_MODEL_LEN:-8192} \
    --gpu-memory-utilization ${VLLM_GPU_MEMORY_UTILIZATION:-0.95} \
    --port ${VLLM_PORT:-8000}
```

### Configuration Variables (in `.env`)
| Variable | Default | Description |
| :--- | :--- | :--- |
| `VLLM_MODEL_PATH` | `solidrust/Hermes-3-Llama-3.1-8B-AWQ` | HuggingFace model ID |
| `VLLM_QUANTIZATION` | `awq` | Quantization method (awq, gptq, etc.) |
| `VLLM_MAX_MODEL_LEN` | `8192` | Context window size |
| `VLLM_GPU_MEMORY_UTILIZATION` | `0.95` | Fraction of GPU memory to use |
| `VLLM_PORT` | `8000` | Server port |

## 3. Starting the Bot
```bash
python3 main.py
```
