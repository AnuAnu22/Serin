#!/bin/bash



# Check if docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed or not in PATH"
    exit 1
fi

# Run SGLang container
# --gpus all: Access to all GPUs
# --ipc=host: Required for PyTorch shared memory
# -v ...: Mount HuggingFace cache so models don't redownload
# --quantization awq: Required for this specific model format
# --context-length 16384: Safe starting point for 12GB VRAM (can likely go higher)
docker run --gpus all \
    --name sglang-hermes \
    --shm-size 4g \
    -p 30000:30000 \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    --ipc=host \
    lmsysorg/sglang:latest \
    python3 -m sglang.launch_server \
    --model-path solidrust/Hermes-3-Llama-3.1-8B-AWQ \
    --port 30000 \
    --host 0.0.0.0 \
    --quantization awq \
    --context-length 8192 \
    --mem-fraction-static 0.5
