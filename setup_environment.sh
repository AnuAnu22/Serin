#!/bin/bash
# Add uv to PATH
export PATH="$PATH:/home/user1/.local/bin"

# Install CUDA-compatible PyTorch
echo "Installing CUDA-compatible PyTorch..."
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130

# Install other dependencies
echo "Installing other dependencies..."
uv pip install chromadb python-dotenv fastapi openai py-cord[voice] faster-whisper librosa numpy scipy sentence-transformers pydub webrtcvad websockets uvicorn jinja2 requests

echo "Environment setup complete!"
echo "Test installation:"
uv pip list | grep torch