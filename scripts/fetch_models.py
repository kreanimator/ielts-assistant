"""Downloads Whisper, Kokoro and the pronunciation model, and checks that each one loads.

    make app-models      (part of make install)

The models are saved in the Hugging Face cache (~/.cache/huggingface), as on a normal start.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))

from app import config  # noqa: E402


def main():
    print(f"Device: {config.DEVICE} (Whisper: {config.WHISPER_MODEL} on {config.WHISPER_DEVICE})", flush=True)
    from app.stt import Transcriber
    Transcriber(config.WHISPER_MODEL, config.WHISPER_DEVICE)
    print("  Whisper ready", flush=True)
    from app.tts import Speaker
    speaker = Speaker(config.DEVICE)
    for voice in config.VOICES:
        speaker.voice(voice)
    speaker.speak("Hello.", config.DEFAULT_VOICE)
    print("  Kokoro and its voices ready", flush=True)
    from app.pronunciation import PronunciationScorer
    PronunciationScorer(config.DEVICE)
    print("  Pronunciation model ready", flush=True)
    from silero_vad import load_silero_vad
    load_silero_vad()
    print("  Voice detection ready", flush=True)


if __name__ == "__main__":
    main()
