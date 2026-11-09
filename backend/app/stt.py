"""Speech to text with faster-whisper."""
from dataclasses import dataclass, field

import numpy as np
from faster_whisper import WhisperModel

# Whisper drops fillers and repetitions unless the prompt shows them.
# IELTS fluency scoring needs them, so we prime it with a disfluent example.
FILLER_PROMPT = "Umm, let me think, like, hmm... Okay, uh, I- I think that, you know, it's, er, quite good."


@dataclass
class Word:
    text: str
    start: float  # seconds from the start of the answer
    end: float


@dataclass
class Transcript:
    text: str
    words: list[Word] = field(default_factory=list)  # only when asked for (slower)


class Transcriber:
    def __init__(self, model_name: str, device: str):
        compute_type = "int8_float16" if device == "cuda" else "int8"
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe(self, audio: np.ndarray, with_words: bool = False) -> Transcript:
        """audio: float32 mono at 16 kHz. with_words adds word timings for fluency metrics."""
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            initial_prompt=FILLER_PROMPT,
            condition_on_previous_text=False,
            beam_size=5,
            word_timestamps=with_words,
        )
        segments = list(segments)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        words = [Word(w.word.strip(), w.start, w.end) for s in segments for w in (s.words or [])]
        return Transcript(text, words)
