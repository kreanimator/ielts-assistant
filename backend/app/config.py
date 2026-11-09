"""Settings, read from environment variables with sensible defaults."""
import os

# Any OpenAI-compatible server works: llama.cpp (default, see docker-compose.yml), Ollama, vLLM.
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8081/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.5-9b")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
DEVICE = os.environ.get("DEVICE", "cuda")

# Kokoro voices: bf_/bm_ are British, af_/am_ are American.
DEFAULT_VOICE = os.environ.get("VOICE", "bf_emma")

# How long you must be silent before your answer counts as finished.
# IELTS candidates pause to think, so this is longer than in a chat assistant.
END_OF_TURN_SILENCE_MS = int(os.environ.get("END_OF_TURN_SILENCE_MS", "1500"))

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
