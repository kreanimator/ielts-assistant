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
