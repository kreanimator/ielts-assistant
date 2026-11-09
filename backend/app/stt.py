"""Speech to text with faster-whisper."""
import numpy as np
from faster_whisper import WhisperModel

# Whisper drops fillers and repetitions unless the prompt shows them.
# IELTS fluency scoring needs them, so we prime it with a disfluent example.
FILLER_PROMPT = "Umm, let me think, like, hmm... Okay, uh, I- I think that, you know, it's, er, quite good."


class Transcriber:
    def __init__(self, model_name: str, device: str):
        compute_type = "int8_float16" if device == "cuda" else "int8"
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32 mono at 16 kHz."""
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            initial_prompt=FILLER_PROMPT,
            condition_on_previous_text=False,
            beam_size=5,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
