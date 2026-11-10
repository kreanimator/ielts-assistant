"""Settings, read from environment variables with sensible defaults."""
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
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parents[2] / "data"))

# Any OpenAI-compatible server works: llama.cpp (default, started by make llm), Ollama, vLLM.
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8081/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.5-9b")

# The device for Kokoro and the pronunciation model: cuda, mps or cpu (default: the best found).
DEVICE = os.environ.get("DEVICE") or best_device()
# Whisper runs on NVIDIA GPUs or the CPU (it has no Apple GPU version). Without an NVIDIA
# GPU a smaller model keeps the live transcript quick; set WHISPER_MODEL=large-v3-turbo
# for the best accuracy if your computer is fast enough.
WHISPER_DEVICE = "cuda" if DEVICE == "cuda" else "cpu"
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3-turbo" if DEVICE == "cuda" else "small.en")

# Kokoro voices offered in the app. The prefix is accent and gender:
# bf_ British female, bm_ British male, af_ American female, am_ American male.
VOICES = ["bf_emma", "bf_isabella", "bm_george", "bm_fable", "af_heart", "af_bella", "am_michael", "am_fenrir"]
DEFAULT_VOICE = os.environ.get("VOICE", "bf_emma")

# While you speak, the live transcript is refreshed this often.
PARTIAL_TRANSCRIPT_EVERY_S = float(os.environ.get("PARTIAL_TRANSCRIPT_EVERY_S", "1.0" if DEVICE == "cuda" else "2.0"))

# How long you must be silent before your answer counts as finished.
# IELTS candidates pause to think, so this is longer than in a chat assistant.
END_OF_TURN_SILENCE_MS = int(os.environ.get("END_OF_TURN_SILENCE_MS", "1500"))

# Full exam timing, in seconds. Part 1 and Part 3 ask no new question in their last
# WRAP_UP_SECONDS, and cut off an answer still going on at the limit.
PART1_SECONDS = float(os.environ.get("PART1_SECONDS", "300"))
PART3_SECONDS = float(os.environ.get("PART3_SECONDS", "300"))
WRAP_UP_SECONDS = float(os.environ.get("WRAP_UP_SECONDS", "30"))
# Part 2: preparation, the talk's limit, and the pause that ends the talk early.
PREP_SECONDS = float(os.environ.get("PREP_SECONDS", "60"))
LONG_TURN_SECONDS = float(os.environ.get("LONG_TURN_SECONDS", "120"))
LONG_TURN_SILENCE_MS = int(os.environ.get("LONG_TURN_SILENCE_MS", "5000"))

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
