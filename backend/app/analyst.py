"""Checks each answer and suggests fixes: grammar, vocabulary, fluency and coherence.

Pronunciation needs the audio, not the transcript; it comes with the phoneme model.
"""
import re

from . import llm

CATEGORIES = ["grammar", "vocabulary", "fluency", "coherence"]

SCHEMA = {
    "type": "object",
    "properties": {
        "corrections": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": CATEGORIES},
                    "original": {"type": "string"},
                    "better": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["category", "original", "better", "why"],
            },
        },
        "good": {"type": "string"},
        "tip": {"type": "string"},
    },
    "required": ["corrections", "good", "tip"],
}

PROMPT = """You are an experienced IELTS Speaking examiner and English teacher.
Give feedback on one spoken answer from a candidate. The answer is a speech-to-text
transcript, so ignore punctuation, capital letters and spelling.

Return:
- corrections: up to 4 real mistakes or clearly weak choices, most important first.
  - category: "grammar" (tense, agreement, articles, prepositions, word order),
    "vocabulary" (wrong word, collocation, or a basic word where a better one fits),
    "fluency" (unfinished sentences or confusing restarts),
    "coherence" (unclear ideas or missing linking words).
  - original: the exact words from the answer, copied without changes.
  - better: the corrected or improved version of those words.
  - why: the rule in at most 12 simple words.
  Only correct what a native speaker would not say. If a native speaker could say it
  the same way, it is not a mistake: do not suggest changes of style or taste.
  Never comment on fillers ("um", "uh"), speed or pronunciation: they are measured
  separately. List each mistake once. If the answer has no real mistakes, return an
  empty list.
- good: one specific thing the candidate did well, at most 20 words.
- tip: one practical way to reach a higher IELTS band with this answer, at most 20
  words, for example adding a reason or an example, or a better linking word."""

FILLERS = {"um", "umm", "uh", "er", "erm", "ah", "hmm"}


async def analyse(question: str, answer: str) -> dict:
    messages = [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": f"Examiner's question: {question}\n\nCandidate's answer: {answer}"},
    ]
    feedback = await llm.complete_json(messages, SCHEMA)
    feedback["corrections"] = _useful(feedback["corrections"], answer)
    return feedback


def _useful(corrections: list[dict], answer: str) -> list[dict]:
    """Drops corrections that don't quote the answer, change nothing but fillers, or repeat."""
    kept, seen = [], set()
    for c in corrections:
        original, better = _words(c["original"]), _words(c["better"])
        if not original or original not in _words(answer):
            continue
        if _words(c["original"], drop_fillers=True) == better or better in seen:
            continue
        seen.add(better)
        kept.append(c)
    return kept


def _words(text: str, drop_fillers: bool = False) -> str:
    """Lowercase words only, so punctuation from the transcript does not matter."""
    words = re.findall(r"[a-z0-9']+", text.lower())
    return " ".join(w for w in words if not (drop_fillers and w in FILLERS))
