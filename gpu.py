from llama_cpp import Llama
import torch  # optional: just to check CUDA

print("PyTorch CUDA available:", torch.cuda.is_available())  # if you have torch

# Load a tiny model or your model
llm = Llama(
    model_path="E:\\NewAiNeuro\\lmstudio-community\\deepcogito_cogito-v1-preview-llama-8B-Q6_K_L\\deepcogito_cogito-v1-preview-llama-8B-Q6_K_L.gguf",
    n_gpu_layers=999,
    n_ctx=512,
    verbose=True  # ← MUST see "offloaded X layers to GPU"
)