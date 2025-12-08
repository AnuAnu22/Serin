#!/bin/bash

# Configuration
# This matches the model currently running on your localhost:8000
MODEL_PATH="cpatonn/Qwen3-VL-4B-Instruct-AWQ-4bit"
HOST="0.0.0.0"
PORT="8000"

# Check if vllm is installed
if ! command -v vllm &> /dev/null; then
    echo "❌ vLLM is not installed or not in PATH."
    echo "Please install it using: pip install vllm"
    exit 1
fi

echo "🚀 Starting vLLM server..."
echo "   Model: $MODEL_PATH"
echo "   Address: http://$HOST:$PORT"

# Run vLLM serving
# --dtype auto: Automatically detect precision
# --gpu-memory-utilization: Adjust based on your GPU (0.9 is standard)
# --max-model-len: Context window size
vllm serve "$MODEL_PATH" \
    --gpu-memory-utilization 0.90 \
    --max-model-len 4096 \
    --trust-remote-code
