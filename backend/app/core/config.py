"""Settings every module shares, read from environment variables with sensible defaults.
Each module keeps its own settings next to it (for example speaking/config.py)."""
import os
import sys
from pathlib import Path

if sys.platform == "darwin":  # a few PyTorch operations have no Apple GPU version yet: run them on the CPU
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


def best_device() -> str:
    """cuda (NVIDIA), mps (Apple Silicon) or cpu."""
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# Your sessions, recordings and the database (git-ignored, never leaves this computer).
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parents[3] / "data"))

# Any OpenAI-compatible server works: llama.cpp (default, started by make llm), Ollama, vLLM.
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8081/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.5-9b")

# The device for the local models (Kokoro, the pronunciation model): cuda, mps or cpu
# (default: the best found).
DEVICE = os.environ.get("DEVICE") or best_device()

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
