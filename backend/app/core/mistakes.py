"""Your mistakes from every session in one place, each named by its type.

  GET /api/mistakes    the types of mistake you make, most frequent first, each with your own
                       examples; the words you misspell; the sounds you get wrong

Where they come from:
- Speaking: the analyst's corrections of each answer (see speaking/analyst.py), and the sounds
  the pronunciation check heard as another sound.
- Writing: the errors marked in your answers (grammar, spelling, precision; see
  writing/assessor.py). Optional style suggestions and task notes are not mistakes.

A correction says only "grammar" or "vocabulary": too wide to practise. So each one is given a
type from TYPES (two, when it mends two things) by the LLM, once, and the type is kept in the `mistakes` table (see storage.py).
The table is filled from the sessions (sync) whenever the page is asked for, so a session that
was deleted, or a report that was written again, takes its mistakes with it. Types are given in
the background: the reply says how many are still "pending", and the app asks again.
"""
import asyncio
import json
import logging
from collections import Counter

from fastapi import APIRouter

from . import llm, storage

log = logging.getLogger("ielts.mistakes")
router = APIRouter()

# id → (title, what it covers: for the LLM and shown under the title).
TYPES = {
    "articles": ("Articles", "a, an or the is missing, extra or the wrong one"),
    "tense_past": ("Past tenses", "a finished past event needs the past simple, past continuous or past perfect"),
    "tense_perfect": ("Present perfect", "have done / have been doing is needed, or is used where the past simple belongs"),
    "tense_other": ("Present and future forms", "present simple or continuous, will, going to: the wrong one of these"),
    "agreement": ("Subject–verb agreement", "the verb does not match its subject: he go, people is, there is many"),
    "prepositions": ("Prepositions", "the wrong, a missing or an extra preposition: in, on, at, to, for, of, with"),
    "plurals": ("Plurals and countable nouns", "singular or plural, much or many, few or little, nouns that have no plural"),
    "word_order": ("Word order", "the right words in the wrong order, also in questions and with adverbs"),
    "word_form": ("Word form", "the right word in the wrong form: noun, verb, adjective or adverb (success, successful)"),
    "verb_patterns": ("Verb patterns", "to do or doing after a verb, the verb after a modal, passive or active"),
    "conditionals": ("Conditionals", "if sentences, wish, and would in the wrong place"),
    "comparisons": ("Comparisons", "more, most, -er, -est, than, as ... as"),
    "pronouns": ("Pronouns and relative clauses", "he, it, they, this, which, who, that: wrong, missing or unclear"),
    "linking": ("Linking words", "however, although, because, so, and: missing, wrong or used too often"),
    "sentences": ("Sentence structure", "an unfinished sentence, two joined without a link, or a missing subject or verb"),
    "word_choice": ("Word choice", "a word that does not mean this or does not go with its neighbours (collocation)"),
    "clarity": ("Clear meaning", "the words are vague, exaggerated or say something that was not meant"),
    "punctuation": ("Punctuation", "commas, full stops, apostrophes and capital letters"),
    "spelling": ("Spelling", "a spelling or typing mistake"),
    "other": ("Other", "none of the other types"),
}
BATCH = 8  # corrections the LLM names in one request
EXAMPLES = 30  # shown per type, newest first
RECENT = 3  # a type not seen in your last RECENT checked sessions is "improving"

MAX_TYPES = 2  # a correction often mends two things at once ("he go at school" → "he goes to school")

SCHEMA = {
    "type": "object",
    "properties": {"mistakes": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "n": {"type": "integer"},
            "changed": {"type": "string"},  # written first, so the types follow from it
            "types": {"type": "array", "minItems": 1, "maxItems": MAX_TYPES,
                      "items": {"type": "string", "enum": list(TYPES)}},
        },
        "required": ["n", "changed", "types"],
    }}},
    "required": ["mistakes"],
}
PROMPT = """You sort an English learner's mistakes into types, for a teacher who will choose exercises.
Each numbered mistake has the learner's words, the corrected words and the reason given.
For each one:
- changed: compare the learner's words with the corrected words and say, in at most 15 words,
  exactly what was changed, word by word ("go → goes; at → to").
- types: the type of each change, the most important first; two types only when two different
  things were mended, otherwise one. The types:
{types}
Rules:
- Go by what was changed, not by the reason's wording. Ignore changes of style.
- A verb changed in tense only: a tense type. Changed only to match its subject: "agreement".
  Active to passive or passive to active, to do or doing, or the verb after a modal: "verb_patterns".
- The same word in another form (success, successful) is "word_form"; "word_choice" is only for
  a different word, when the grammar of the learner's words was already right.
- A word that was only spelled wrong is "spelling", never "word_form" or "word_choice".
- Words that cannot be read at all (broken letters): "other".
- "other" only when no type fits.
Return every mistake once, with its number."""

tagging = asyncio.Lock()  # one background run at a time
_task = None


@router.get("/api/mistakes")
async def mistakes():
    global _task
    sync()
    result = summary()
    if result["pending"] and not tagging.locked():
        _task = asyncio.create_task(tag_pending())  # kept, so it is not collected while it runs
    return result


# ---- collecting ----

def collect() -> dict[tuple[str, str], dict]:
    """Every correction in the stored sessions: (session, key) → the correction."""
    found = {}
    with storage.connect() as db:
        answers = db.execute(
            """SELECT m.session_id, m.answer, m.feedback FROM messages m JOIN sessions s ON s.id = m.session_id
               WHERE s.module = 'speaking' AND m.feedback IS NOT NULL""").fetchall()
        reports = db.execute("SELECT id, report FROM sessions WHERE module = 'writing' AND report IS NOT NULL").fetchall()
    for row in answers:
        for i, c in enumerate(json.loads(row["feedback"]).get("corrections", [])):
            found[row["session_id"], f"{row['answer']}.{i}"] = {**_fields(c), "module": "speaking"}
    for row in reports:
        for task in json.loads(row["report"]).get("tasks", []):
            for i, c in enumerate(task.get("corrections", [])):
                found[row["id"], f"task{task['task']}.{i}"] = {**_fields(c), "module": "writing"}
    return found


def _fields(correction: dict) -> dict:
    return {k: str(correction.get(k) or "") for k in ("category", "original", "better", "why")}


def sync():
    """Makes the mistakes table match the sessions. A correction that is still there keeps its type."""
    found = collect()
    with storage.connect() as db:
        rows = db.execute("SELECT * FROM mistakes").fetchall()
        known = {(r["session_id"], r["key"]): r for r in rows}
        types = {(r["session_id"], r["original"], r["better"]): r["type"] for r in rows if r["type"]}
        gone = [key for key, row in known.items()  # deleted, or the report was written again
                if key not in found or (found[key]["original"], found[key]["better"]) != (row["original"], row["better"])]
        for key in gone:
            db.execute("DELETE FROM mistakes WHERE session_id = ? AND key = ?", key)
        for (session, key), c in found.items():
            if (session, key) in known and (session, key) not in gone:
                continue
            kind = "spelling" if c["category"] == "spelling" else types.get((session, c["original"], c["better"]))
            db.execute(
                "INSERT INTO mistakes (session_id, key, module, category, original, better, why, type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session, key, c["module"], c["category"], c["original"], c["better"], c["why"], kind))


# ---- naming the types ----

async def name_types(corrections: list[dict]) -> list[list[str]]:
    """The types of each correction, at most MAX_TYPES (["other"] for one the LLM left out)."""
    listed = "\n".join(f"{i + 1}. Learner: \"{c['original']}\"\n   Corrected: \"{c['better']}\"\n   Reason: {c['why']}"
                       for i, c in enumerate(corrections))
    types = "\n".join(f"- {key}: {title}. {covers}." for key, (title, covers) in TYPES.items())
    reply = await llm.complete_json(
        [{"role": "system", "content": PROMPT.format(types=types)}, {"role": "user", "content": listed}],
        SCHEMA, temperature=0, max_tokens=1200)
    named = {m["n"]: list(dict.fromkeys(m["types"])) for m in reply["mistakes"]}  # without repeats
    return [named.get(i + 1, ["other"]) for i in range(len(corrections))]


async def tag_pending():
    """Gives every mistake without a type its type, a few at a time."""
    async with tagging:
        while True:
            with storage.connect() as db:
                rows = db.execute("SELECT * FROM mistakes WHERE type IS NULL LIMIT ?", (BATCH,)).fetchall()
            if not rows:
                return
            try:
                types = await name_types([dict(r) for r in rows])
            except Exception:  # the LLM server is busy or down: the next visit tries again
                log.exception("could not name the mistakes' types")
                return
            with storage.connect() as db:
                for row, kinds in zip(rows, types):
                    db.execute("UPDATE mistakes SET type = ? WHERE session_id = ? AND key = ?",
                               (",".join(kinds), row["session_id"], row["key"]))


# ---- the page ----

def summary() -> dict:
    with storage.connect() as db:
        rows = db.execute(
            """SELECT k.*, s.started_at, s.mode, s.topic FROM mistakes k JOIN sessions s ON s.id = k.session_id
               ORDER BY s.started_at DESC, k.key""").fetchall()
        deliveries = db.execute(
            """SELECT m.delivery, s.started_at FROM messages m JOIN sessions s ON s.id = m.session_id
               WHERE s.module = 'speaking' AND m.delivery IS NOT NULL ORDER BY s.started_at DESC""").fetchall()
    checked = sorted({(r["started_at"], r["session_id"]) for r in rows}, reverse=True)  # sessions with a mistake
    recent = {session for _, session in checked[:RECENT]}
    types = []
    for key, (title, covers) in TYPES.items():
        own = [r for r in rows if key in (r["type"] or "").split(",")]
        if not own or key == "spelling":
            continue
        types.append({
            "id": key,
            "title": title,
            "covers": covers,
            "count": len(own),
            "sessions": len({r["session_id"] for r in own}),
            "last_seen": own[0]["started_at"],
            "by_module": dict(Counter(r["module"] for r in own)),
            # Seen before, more than once, but in none of your latest sessions that had mistakes.
            "improving": len(checked) > RECENT and len(own) > 1 and not any(r["session_id"] in recent for r in own),
            "examples": [_example(r) for r in own[:EXAMPLES]],
        })
    types.sort(key=lambda t: (t["id"] == "other", -t["count"]))
    return {
        "pending": sum(r["type"] is None for r in rows),
        "total": len(rows),
        "sessions": len(checked),
        "types": types,
        "spelling": _spelling([r for r in rows if r["type"] == "spelling"]),  # only spelling: a word, not a phrase
        "sounds": _sounds(deliveries),
    }


def _example(row) -> dict:
    return {"session": row["session_id"], "module": row["module"], "mode": row["mode"], "topic": row["topic"],
            "date": row["started_at"], "original": row["original"], "better": row["better"], "why": row["why"]}


def _spelling(rows: list) -> list[dict]:
    """The words you misspelled, the ones misspelled most often first."""
    words = {}
    for r in rows:
        if len(r["better"].split()) > 3:
            continue  # a phrase with a slip in it, not a word to learn
        word = words.setdefault(r["better"].strip().lower(), {"right": r["better"].strip(), "wrong": [], "count": 0,
                                                              "last_seen": r["started_at"], "session": r["session_id"],
                                                              "module": r["module"]})
        word["count"] += 1
        if r["original"] not in word["wrong"]:
            word["wrong"].append(r["original"])
    return sorted(words.values(), key=lambda w: -w["count"])


def _sounds(deliveries: list) -> list[dict]:
    """The sounds heard as another sound (or not at all), the most frequent first."""
    sounds = {}
    for row in deliveries:
        for s in (json.loads(row["delivery"]).get("pronunciation") or {}).get("sounds", []):
            sound = sounds.setdefault(s["expected"], {"sound": s["expected"], "count": 0, "heard": Counter(),
                                                      "last_seen": row["started_at"]})
            sound["count"] += s["count"]
            sound["heard"][s["heard"]] += s["count"]
    return [{**s, "heard": [{"sound": h, "count": n} for h, n in s["heard"].most_common(3)]}
            for s in sorted(sounds.values(), key=lambda s: -s["count"])]
