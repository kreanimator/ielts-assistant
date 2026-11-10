"""Drills: short practice of one weak area.

- Sound drills: the examiner says a sentence full of one sound, you repeat it, and the
  pronunciation check counts how many of those sounds came out right.
- Language drills: the examiner asks questions that need one structure (past tenses,
  linking words, ...) and the analyst checks that structure first.

Your past sessions suggest which sounds to drill: the ones you got wrong most often.
"""
from . import llm, storage

SENTENCES = 6  # per sound drill
CANDIDATES = 10  # sentences the LLM writes; the richest in the sound are kept
MIN_SOUNDS = 2  # a kept sentence has the sound at least this often
QUESTIONS = 6  # per language drill

SOUNDS = {
    "θ": ("/θ/ as in \"think\"", "th as in think, three, health, month"),
    "ð": ("/ð/ as in \"this\"", "th as in this, mother, they, weather"),
    "v": ("/v/ as in \"very\"", "v as in very, vivid, travel, never"),
    "w": ("/w/ as in \"water\"", "w as in water, window, always, quick"),
    "ɹ": ("/r/ as in \"right\"", "r as in right, road, story, carry"),
    "l": ("/l/ as in \"light\"", "l as in light, little, hello, believe"),
    "ɪ": ("/ɪ/ as in \"ship\"", "the short i as in ship, sit, live, busy"),
    "æ": ("/æ/ as in \"cat\"", "the a as in cat, black, happy, family"),
}
LANGUAGE = {
    "past": ("Past tenses", "past tenses (past simple, past continuous, present perfect)",
             "Ask about past experiences, memories and changes in their life."),
    "future": ("Talking about the future", "future forms (will, going to, present continuous for plans)",
               "Ask about plans, predictions and hopes."),
    "conditionals": ("Conditionals", "conditional sentences (if ... would, if ... will, if ... would have)",
                     "Ask hypothetical questions: what would they do if ..., what if ... had happened."),
    "linking": ("Linking words", "linking words (however, although, as a result, on the other hand)",
                "Ask for opinions that need reasons, contrasts and consequences."),
    "comparisons": ("Comparisons", "comparatives and superlatives (more ... than, the most, as ... as)",
                    "Ask them to compare places, times, people and things."),
    "opinions": ("Opinions with reasons", "giving an opinion and supporting it with a reason and an example",
                 "Ask for their opinion on everyday social questions and ask why."),
}

SENTENCES_SCHEMA = {
    "type": "object",
    "properties": {"sentences": {"type": "array", "minItems": CANDIDATES, "maxItems": CANDIDATES,
                                 "items": {"type": "string"}}},
    "required": ["sentences"],
}
SENTENCES_PROMPT = """Write {n} different practice sentences for an English learner to repeat aloud.
Each sentence: natural everyday English, 7 to 12 words, with at least four words that
contain the sound {sound}. Use common words. No names, no numbers, no tongue twisters."""


def catalogue() -> dict:
    """The drills, and the sounds your past sessions suggest."""
    drills = [{"id": f"sound:{s}", "kind": "sound", "title": t, "description": f"Repeat sentences full of {d}."}
              for s, (t, d) in SOUNDS.items()]
    drills += [{"id": f"language:{k}", "kind": "language", "title": t, "description": f"Practise {d}."}
               for k, (t, d, _) in LANGUAGE.items()]
    return {"drills": drills, "suggested": suggested()}


def suggested(limit: int = 3) -> list[dict]:
    """The drill sounds you got wrong most often in your last 20 sessions."""
    counts = {}
    for s in storage.list_sessions()[:20]:
        session = storage.get_session(s["id"])
        for m in session["messages"]:
            for sound in ((m["delivery"] or {}).get("pronunciation") or {}).get("sounds", []):
                if sound["expected"] in SOUNDS:
                    counts[sound["expected"]] = counts.get(sound["expected"], 0) + sound["count"]
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return [{"id": f"sound:{s}", "reason": f"missed {n}× in your recent sessions"} for s, n in top if n >= 2]


def parse(drill_id: str | None) -> tuple[str, str] | None:
    """("sound", "θ") or ("language", "past"), or None for an unknown id."""
    kind, _, key = (drill_id or "").partition(":")
    if (kind == "sound" and key in SOUNDS) or (kind == "language" and key in LANGUAGE):
        return kind, key
    return None


def title(kind: str, key: str) -> str:
    return SOUNDS[key][0] if kind == "sound" else LANGUAGE[key][0]


async def sentences(sound: str, count) -> list[str]:
    """Sentences to repeat, richest in the sound first. The LLM often mixes up similar
    sounds (the two "th"), so count(text, sound) checks each one with the dictionary."""
    reply = await llm.complete_json(
        [{"role": "system", "content": SENTENCES_PROMPT.format(n=CANDIDATES, sound=SOUNDS[sound][1])},
         {"role": "user", "content": "Write the sentences."}],
        SENTENCES_SCHEMA,
    )
    unique = list(dict.fromkeys(s.strip() for s in reply["sentences"] if s.strip()))
    scored = sorted(((count(s, sound), s) for s in unique), key=lambda x: -x[0])
    good = [s for n, s in scored if n >= MIN_SOUNDS]
    return (good or [s for _, s in scored])[:SENTENCES]


def language_prompt(key: str) -> str:
    _, focus, how = LANGUAGE[key]
    return f"""You are {{name}}, a friendly English speaking coach. The learner is practising {focus}.
{how} Ask one short, natural question per turn that makes them use it, and react briefly
to their answer first. Start by greeting them, saying your name, and saying in one sentence
what you will practise together."""


def analyst_focus(key: str) -> str:
    return LANGUAGE[key][1]
