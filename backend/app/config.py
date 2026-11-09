"""Settings, read from environment variables with sensible defaults."""
import os
from pathlib import Path

# Your sessions, recordings and the database (git-ignored, never leaves this computer).
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parents[2] / "data"))

# Any OpenAI-compatible server works: llama.cpp (default, see docker-compose.yml), Ollama, vLLM.
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8081/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.5-9b")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
DEVICE = os.environ.get("DEVICE", "cuda")

# Kokoro voices offered in the app. The prefix is accent and gender:
# bf_ British female, bm_ British male, af_ American female, am_ American male.
VOICES = ["bf_emma", "bf_isabella", "bm_george", "bm_fable", "af_heart", "af_bella", "am_michael", "am_fenrir"]
DEFAULT_VOICE = os.environ.get("VOICE", "bf_emma")

# While you speak, the live transcript is refreshed this often.
PARTIAL_TRANSCRIPT_EVERY_S = float(os.environ.get("PARTIAL_TRANSCRIPT_EVERY_S", "1.0"))

# How long you must be silent before your answer counts as finished.
# IELTS candidates pause to think, so this is longer than in a chat assistant.
END_OF_TURN_SILENCE_MS = int(os.environ.get("END_OF_TURN_SILENCE_MS", "1500"))

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
