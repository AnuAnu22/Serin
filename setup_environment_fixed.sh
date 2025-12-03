#!/bin/bash
# Set up environment without PATH export

# Install CUDA-compatible PyTorch using full uv path
echo "Installing CUDA-compatible PyTorch..."
/home/user1/.local/bin/uv pip install --system torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130

# Install other dependencies
echo "Installing other dependencies..."
/home/user1/.local/bin/uv pip install --system chromadb python-dotenv fastapi openai py-cord[voice] faster-whisper librosa numpy scipy sentence-transformers pydub webrtcvad websockets uvicorn jinja2 requests

echo "Environment setup complete!"
echo "Test installation:"
/home/user1/.local/bin/uv pip list | grep torch