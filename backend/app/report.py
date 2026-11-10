"""The end-of-session report: an estimated band for each IELTS Speaking criterion.

- Fluency and Coherence, Lexical Resource, Grammatical Range and Accuracy: the LLM
  judges the transcript against the band descriptors, given the measured numbers,
  and must quote evidence before it gives each band.
- Pronunciation: from the measured pronunciation score (the LLM cannot hear).
- Overall: the average of the four, rounded like IELTS does (to the nearest half band,
  with .25 and .75 rounded up).

These are practice estimates, not official scores. Both kinds of band are checked
against human ratings: scripts/calibrate_pronunciation.py and scripts/calibrate_bands.py.
"""
import asyncio
import math
import re

import numpy as np

from . import llm, prosody

FILLERS = {"um", "umm", "uh", "er", "erm", "ah", "hmm", "mm"}
# The LLM's bands, corrected to match human examiners: band = slope * llm_band + offset.
# Fitted with scripts/calibrate_bands.py --fit on 60 Speak & Improve dev tests and checked
# on held-out tests (see the README). Uncorrected, the LLM is too low by about a
# third of a band for Fluency and a whole band for the others, at every level. Only that
# shift is corrected: a steeper slope fitted the tests a little better but would inflate
# strong speakers beyond the range the tests cover.
CORRECTION = {"fluency_coherence": (1.0, 0.3), "lexical_resource": (1.0, 1.0), "grammar": (1.0, 1.1)}
MIN_ANSWERS, MIN_WORDS = 3, 80
# The LLM can judge the session several times at once, and the bands are then averaged.
# On the Speak & Improve dev set, 3 passes followed the examiners no better than one
# (correlation 0.64 against 0.59 and 0.65 for two single runs) and took twice as long.
PASSES, PASS_TEMPERATURE = 1, 0.2
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
PROMPT = """You are an experienced IELTS Speaking examiner. Estimate the candidate's bands
for three criteria from the session transcript and the measured numbers. Be fair: neither
generous nor harsh. Pick the band whose description fits best, and judge each criterion on
its own (they often differ by half a band or more).

Fluency and Coherence
- 9: fluent with only rare, content-related hesitation; fully coherent, well developed.
- 8: fluent; hesitation mostly to find ideas, not words; develops topics coherently.
- 7: speaks at length without noticeable effort; some hesitation or self-correction;
  uses a range of linking words and discourse markers flexibly.
- 6: willing to speak at length, though sometimes loses coherence through repetition,
  self-correction or hesitation; uses a range of linking words, not always well.
- 5: keeps going but relies on repetition, self-correction or slow speech; overuses a
  few linking words; simple speech is fluent, complex ideas cause problems.
- 4: cannot respond without noticeable pauses; may speak slowly; links simple sentences
  with repeated simple connectives; coherence breaks down at times.
- 3: long pauses; limited ability to link simple sentences; gives only simple answers.
Lexical Resource
- 9: full flexibility and precision on all topics; idiomatic language used naturally.
- 8: wide, flexible vocabulary that conveys precise meaning; less common and idiomatic
  words used skilfully, with only occasional slips.
- 7: flexible vocabulary on a range of topics; some less common and idiomatic words and
  collocations; some wrong choices; paraphrases well.
- 6: wide enough vocabulary to discuss topics at length and make meaning clear despite
  some inappropriate choices; generally paraphrases successfully.
- 5: manages familiar and unfamiliar topics but with limited flexibility; paraphrases
  with mixed success.
- 4: enough vocabulary for familiar topics, only basic meaning on unfamiliar ones;
  frequent wrong word choices; rarely paraphrases.
- 3: simple vocabulary for personal information; not enough for less familiar topics.
Grammatical Range and Accuracy
- 9: full range of structures, natural and accurate apart from native-like slips.
- 8: wide range of structures used flexibly; most sentences error-free; only occasional
  errors.
- 7: a range of complex structures with some flexibility; frequent error-free sentences,
  though some errors remain.
- 6: a mix of simple and complex structures, with limited flexibility; frequent errors
  in complex structures, which rarely make the meaning unclear.
- 5: basic sentence forms with reasonable accuracy; a limited range of complex
  structures, which usually contain errors.
- 4: basic sentence forms and some correct simple sentences; subordinate structures are
  rare; errors are frequent.
- 3: attempts basic forms with limited success; relies on memorised phrases.

Rules:
- The transcript comes from speech recognition. "um", restarts and missing punctuation
  are normal in speech: count them only for Fluency, never as grammar or word errors.
- A fluent speaker usually says 110-170 words per minute.
- Judge what the candidate shows. Short answers show less range, so judge the range
  shown in the longer answers.
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
    """Measured accuracy → band, calibrated against expert ratings of 1,340 adult learner
    sentences (speechocean762, see scripts/calibrate_pronunciation.py): each point is the
    median app score at one expert level. Below 0.45 the experts' levels 3 to 5 score
    alike, so the band stays at 4. Capped at 8.5: word stress and intonation are part of
    the IELTS band, and our measures of them did not predict the experts' scores (see the
    README), so they cannot raise it."""
    points = [(0.45, 4.0), (0.535, 5.375), (0.67, 6.125), (0.84, 7.0), (0.93, 8.0), (0.98, 8.5)]
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
        "long_pauses_per_minute": round(sum(f["pauses"] for f in fluency) / seconds * 60, 1)
        if seconds and all("pauses" in f for f in fluency) else None,
        "fillers_per_100_words": round(sum(f["fillers"] for f in fluency) / words * 100, 1) if words else None,
        "repetitions_per_100_words": round(sum(f["repetitions"] for f in fluency) / words * 100, 1) if words else None,
        "grammar_errors_per_100_words": round(sum(c["category"] == "grammar" for c in corrections) / words * 100, 1) if words else None,
        "vocabulary_errors": sum(c["category"] == "vocabulary" for c in corrections),
        "vocabulary_variety": round(moving_type_token_ratio(tokens), 2),
        "pronunciation": round(sum(p["score"] * w for p, w in scored) / max(1, sum(w for _, w in scored)), 2) if scored else None,
        "pitch_range": round(float(np.median(ranges)), 1) if (ranges := [a["delivery"]["intonation"]["range"] for a in answers
                                                               if a["delivery"] and a["delivery"].get("intonation")]) else None,
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
    if session.get("mode") == "drill":
        return {"stats": stats, "enough": False,
                "note": "Drills practise one thing, so they get no band estimate. Your answers and their checks are below."}
    report = {"stats": stats, "enough": len(answers) >= MIN_ANSWERS and stats["words"] >= MIN_WORDS}
    if not report["enough"]:
        report["note"] = (f"Speak at least {MIN_ANSWERS} answers and {MIN_WORDS} words for band estimates. "
                          f"This session has {len(answers)} answers and {stats['words']} words.")
        return report

    transcript = "\n".join(
        f"{'Examiner' if m['role'] == 'examiner' else 'Candidate'}: {m['text']}" for m in session["messages"]
    )
    numbers = "\n".join(f"- {label}: {stats[key]}" for key, label in LABELS.items() if stats[key] is not None)
    messages = [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": f"Measured numbers:\n{numbers}\n\nTranscript:\n{transcript}"},
    ]
    passes = await asyncio.gather(*(llm.complete_json(messages, SCHEMA, PASS_TEMPERATURE, max_tokens=1500)
                                  for _ in range(PASSES)))  # a normal judgement is about 650 tokens
    judged = passes[0]  # its quotes, strengths and priorities are shown
    for key in ("fluency_coherence", "lexical_resource", "grammar"):
        judged[key]["band"] = sum(p[key]["band"] for p in passes) / len(passes)

    criteria = [
        {"id": "fluency_coherence", "name": "Fluency and Coherence", **judged["fluency_coherence"]},
        {"id": "lexical_resource", "name": "Lexical Resource", **judged["lexical_resource"]},
        {"id": "grammar", "name": "Grammatical Range and Accuracy", **judged["grammar"]},
    ]
    if stats["pronunciation"] is not None:
        criteria.append(pronunciation_criterion(stats))
    for c in criteria:
        if c["id"] in CORRECTION:
            slope, offset = CORRECTION[c["id"]]
            c["llm_band"] = c["band"]
            c["band"] = min(9.0, max(1.0, slope * c["band"] + offset))
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
    if (spread := stats.get("pitch_range")) is not None:
        evidence.append(f"Your voice rose and fell over {spread:.0f} semitones (lively speech: 5 or more).")
        if spread < prosody.FLAT_SEMITONES:
            summary += (" Your voice stays quite flat: let it rise and fall more, and stress the"
                        " important word in each phrase.")
    return {
        "id": "pronunciation",
        "name": "Pronunciation",
        "evidence": evidence,
        "summary": summary + " (The band comes from individual sounds; word stress and intonation do not change it.)",
        "band": pronunciation_band(accuracy),
    }
