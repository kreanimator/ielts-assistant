"""The end-of-session report: an estimated band for each IELTS Speaking criterion.

- Fluency and Coherence, Lexical Resource, Grammatical Range and Accuracy: the LLM
  judges the transcript against the band descriptors, given the measured numbers,
  and must quote evidence before it gives each band.
- Pronunciation: from the measured pronunciation score (the LLM cannot hear).
- Overall: the average of the four, rounded like IELTS does (to the nearest half band,
  with .25 and .75 rounded up).

These are practice estimates, not official scores. The pronunciation mapping is a
first guess, to be calibrated with sample answers that have examiner bands.
"""
import math
import re

import numpy as np

from . import llm

FILLERS = {"um", "umm", "uh", "er", "erm", "ah", "hmm", "mm"}
MIN_ANSWERS, MIN_WORDS = 3, 80
BANDS = [b / 2 for b in range(2, 19)]  # 1.0 .. 9.0

CRITERION = {
    "type": "object",
    "properties": {  # evidence first, so the band follows from it
        "evidence": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
        "summary": {"type": "string"},
        "band": {"type": "number", "enum": BANDS},
    },
    "required": ["evidence", "summary", "band"],
}
SCHEMA = {
    "type": "object",
    "properties": {
        "fluency_coherence": CRITERION,
        "lexical_resource": CRITERION,
        "grammar": CRITERION,
        "strengths": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
        "priorities": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
    },
    "required": ["fluency_coherence", "lexical_resource", "grammar", "strengths", "priorities"],
}

# The band descriptors in brief, in our own words.
PROMPT = """You are a strict, experienced IELTS Speaking examiner. Estimate the candidate's
bands for three criteria from the session transcript and the measured numbers.

Fluency and Coherence
- 8-9: speaks at length with only rare hesitation; ideas fully developed and linked.
- 7: speaks at length without noticeable effort; some hesitation; flexible linking words.
- 6: willing to speak at length but loses coherence at times through repetition,
  self-correction or hesitation; uses a range of linking words, not always well.
- 5: keeps going but relies on repetition, self-correction and slow speech; overuses
  simple linking words.
- 4: cannot respond without noticeable pauses; simple sentences, repetitive linking.
Lexical Resource
- 8-9: wide, precise vocabulary, natural idioms and collocations.
- 7: flexible vocabulary on many topics, some less common words and collocations,
  some errors of word choice.
- 6: enough vocabulary to discuss topics at length and make meaning clear despite
  some wrong choices; can paraphrase.
- 5: manages familiar topics with limited flexibility; paraphrases with mixed success.
- 4: basic vocabulary for familiar topics; frequent errors of word choice.
Grammatical Range and Accuracy
- 8-9: wide range of structures, mostly error-free sentences.
- 7: range of complex structures with some flexibility; frequent error-free sentences.
- 6: mix of simple and complex structures with limited flexibility; frequent errors
  in complex structures that rarely reduce understanding.
- 5: basic sentence forms reasonably accurate; few complex structures, usually with errors.
- 4: basic forms with frequent errors; rare subordinate clauses.

Rules:
- Most learners are between 5 and 7. Do not inflate. Give 8 or more only for near-native speech.
- A fluent speaker usually says 110-170 words per minute with few long pauses.
- Very short answers cannot show range: they limit Fluency, Lexical Resource and Grammar.
- evidence: up to 3 short quotes of the candidate's own words that justify the band
  (a measured number only when no quote fits).
- summary: one or two sentences, addressed to the candidate ("You ...").
- strengths: up to 3 specific things the candidate does well.
- priorities: up to 3 concrete practice actions for the next session, most important first."""


# What each measured number means, so the LLM reads it correctly.
LABELS = {
    "answers": "answers given",
    "words": "words spoken, without fillers",
    "wpm": "speaking speed in words per minute",
    "words_per_answer": "average words per answer",
    "long_pauses_per_minute": "silences longer than 0.7 s inside answers, per minute",
    "fillers_per_100_words": "fillers (um, uh) per 100 words",
    "repetitions_per_100_words": "repeated words or restarts per 100 words",
    "grammar_errors_per_100_words": "grammar mistakes found per 100 words",
    "vocabulary_errors": "wrong word choices found",
    "vocabulary_variety": "share of different words in each 40-word stretch, 0 to 1 (higher means more varied)",
}


def round_band(value: float) -> float:
    """IELTS rounding: to the nearest half band, .25 and .75 round up."""
    return math.floor(value * 2 + 0.5) / 2


def pronunciation_band(score: float) -> float:
    """First guess, not yet calibrated: measured accuracy → band. Capped at 8.5,
    because stress and intonation are not measured."""
    points = [(0.70, 4.0), (0.80, 5.5), (0.90, 6.5), (0.95, 7.5), (0.98, 8.5)]
    band = np.interp(score, [p[0] for p in points], [p[1] for p in points])
    return round_band(float(band))


def measured(answers: list[dict]) -> dict:
    """Totals over the whole session from each answer's delivery numbers."""
    fluency = [a["delivery"]["fluency"] for a in answers if a["delivery"] and a["delivery"]["fluency"]]
    seconds = sum(f["seconds"] for f in fluency)
    words = sum(f["words"] for f in fluency)
    scored = [(a["delivery"]["pronunciation"], a["delivery"]["fluency"].get("words", 0))
              for a in answers if a["delivery"] and a["delivery"]["pronunciation"]["score"] is not None]
    sounds = {}
    for a in answers:
        for s in (a["delivery"] or {}).get("pronunciation", {}).get("sounds", []):
            key = (s["expected"], s["heard"])
            sounds[key] = sounds.get(key, 0) + s["count"]
    corrections = [c for a in answers if a["feedback"] for c in a["feedback"]["corrections"]]
    text = " ".join(a["text"] for a in answers).lower()
    tokens = [t for t in re.findall(r"[a-z']+", text) if t not in FILLERS]
    return {
        "answers": len(answers),
        "words": words,
        "minutes": round(seconds / 60, 1),
        "wpm": round(words / seconds * 60) if seconds else None,
        "words_per_answer": round(words / len(fluency)) if fluency else None,
        "long_pauses_per_minute": round(sum(f["pauses"] for f in fluency) / seconds * 60, 1) if seconds else None,
        "fillers_per_100_words": round(sum(f["fillers"] for f in fluency) / words * 100, 1) if words else None,
        "repetitions_per_100_words": round(sum(f["repetitions"] for f in fluency) / words * 100, 1) if words else None,
        "grammar_errors_per_100_words": round(sum(c["category"] == "grammar" for c in corrections) / words * 100, 1) if words else None,
        "vocabulary_errors": sum(c["category"] == "vocabulary" for c in corrections),
        "vocabulary_variety": round(moving_type_token_ratio(tokens), 2),
        "pronunciation": round(sum(p["score"] * w for p, w in scored) / max(1, sum(w for _, w in scored)), 2) if scored else None,
        "sounds": [{"expected": e, "heard": h, "count": n} for (e, h), n in sorted(sounds.items(), key=lambda kv: -kv[1])][:4],
    }


def moving_type_token_ratio(tokens: list[str], window: int = 40) -> float:
    """Share of different words, averaged over 40-word windows (fair across answer lengths)."""
    if len(tokens) < window:
        return len(set(tokens)) / max(1, len(tokens))
    return float(np.mean([len(set(tokens[i:i + window])) / window for i in range(len(tokens) - window + 1)]))


async def build(session: dict) -> dict:
    answers = [m for m in session["messages"] if m["role"] == "candidate"]
    stats = measured(answers)
    report = {"stats": stats, "enough": len(answers) >= MIN_ANSWERS and stats["words"] >= MIN_WORDS}
    if not report["enough"]:
        report["note"] = (f"Speak at least {MIN_ANSWERS} answers and {MIN_WORDS} words for band estimates. "
                          f"This session has {len(answers)} answers and {stats['words']} words.")
        return report

    transcript = "\n".join(
        f"{'Examiner' if m['role'] == 'examiner' else 'Candidate'}: {m['text']}" for m in session["messages"]
    )
    numbers = "\n".join(f"- {label}: {stats[key]}" for key, label in LABELS.items() if stats[key] is not None)
    judged = await llm.complete_json(
        [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": f"Measured numbers:\n{numbers}\n\nTranscript:\n{transcript}"},
        ],
        SCHEMA,
    )

    criteria = [
        {"id": "fluency_coherence", "name": "Fluency and Coherence", **judged["fluency_coherence"]},
        {"id": "lexical_resource", "name": "Lexical Resource", **judged["lexical_resource"]},
        {"id": "grammar", "name": "Grammatical Range and Accuracy", **judged["grammar"]},
    ]
    if stats["pronunciation"] is not None:
        criteria.append(pronunciation_criterion(stats))
    for c in criteria:
        c["band"] = round_band(c["band"])
    report.update(
        criteria=criteria,
        overall=round_band(sum(c["band"] for c in criteria) / len(criteria)),
        strengths=judged["strengths"],
        priorities=judged["priorities"],
    )
    return report


def pronunciation_criterion(stats: dict) -> dict:
    accuracy = stats["pronunciation"]
    evidence = [f"Sounds matched the expected English sounds {round(accuracy * 100)}% of the time."]
    evidence += [
        f"/{s['expected']}/ left out {s['count']}×" if not s["heard"] else f"/{s['expected']}/ said as /{s['heard']}/ {s['count']}×"
        for s in stats["sounds"]
    ]
    if not stats["sounds"]:
        summary = "Your individual sounds are clear."
    elif max(s["count"] for s in stats["sounds"]) >= 2:
        summary = "Work on the sounds listed: they repeat across your answers."
    else:
        summary = "Your sounds are mostly clear, with a few one-off slips."
    return {
        "id": "pronunciation",
        "name": "Pronunciation",
        "evidence": evidence,
        "summary": summary + " (Measured from individual sounds only; stress and intonation are not checked yet.)",
        "band": pronunciation_band(accuracy),
    }
