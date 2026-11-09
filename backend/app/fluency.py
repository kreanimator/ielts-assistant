"""Fluency numbers measured from the word timings: speed, pauses, fillers, repetitions."""
import re

from .stt import Word

FILLERS = {"um", "umm", "uh", "er", "erm", "ah", "hmm", "mm"}
LONG_PAUSE_S = 0.7  # a silence inside an answer longer than this breaks the flow


def measure(words: list[Word]) -> dict:
    clean = [re.sub(r"[^a-z'-]", "", w.text.lower()) for w in words]
    spoken = [w for w, c in zip(words, clean) if c and c not in FILLERS]
    if len(spoken) < 3:
        return {}
    seconds = words[-1].end - words[0].start
    gaps = [b.start - a.end for a, b in zip(words, words[1:])]
    pauses = [g for g in gaps if g >= LONG_PAUSE_S]
    return {
        "seconds": round(seconds, 1),
        "words": len(spoken),
        "wpm": round(len(spoken) / seconds * 60) if seconds > 0 else 0,
        "pauses": len(pauses),
        "longest_pause": round(max(pauses, default=0.0), 1),
        "fillers": sum(c in FILLERS for c in clean),
        # "I- I think", "the the": restarts and repeated words
        "repetitions": sum(1 for a, b in zip(clean, clean[1:]) if a and a.rstrip("-") == b.rstrip("-") and a not in FILLERS),
    }
