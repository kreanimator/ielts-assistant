"""Practice for one type of mistake: a short lesson, then exercises.

  GET  /api/practice                      the types you can practise, the ones you make most first,
                                          each with your mistakes' count and your last result
  POST /api/practice/units {"type"}       writes a unit (about half a minute): the lesson and the
                                          exercises, without their answers
  GET  /api/practice/units/{id}           a unit again; with the answers once it is checked
  POST /api/practice/units/{id}/answers   {"answers": {"1": 2, "7": "She goes to school."}}
                                          checks them: what was right, the answers, the score

A unit is written by the LLM for the type (mistakes.TYPES): the rules learners break most often,
and exercises on them. Your own mistakes of that type are shown in the lesson, as they are
stored; they are not given to the LLM (it copied their sentences, slips and all, into its
examples).

Exercises:
- "choice": a sentence with a gap and three ways to fill it (shuffled here). Checked by the code.
- "fix": a sentence with one mistake, to write correctly. An answer that is the expected
  sentence is right by the code; any other is judged by the LLM (there is often more than one
  right way), and the same sentence again is wrong.

The LLM writes more exercises than a unit needs, and each is checked before it is kept (see
checked): every sentence an exercise can make is judged on its own, correct English or not,
without saying which it should be. A gap-fill stays only if its answer makes a correct sentence
and each other option a wrong one (so a gap that two options fit is dropped); a "fix" stays only
if its sentence is judged wrong and its answer correct (so one written the wrong way round is
dropped). Then each is asked whether it is about this type of mistake at all. The lesson's
example sentences are judged the same way, and a rule whose "wrong" sentence is right is left
out. When too few exercises or rules pass, more are written, once (ROUNDS).
"""
import asyncio
import json
import logging
import random
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import llm, mistakes, storage

log = logging.getLogger("ielts.practice")
router = APIRouter()

NOT_PRACTISED = ("spelling", "other")  # spelling is a list of words; "other" is no one thing
CHOICES, FIXES = 6, 4  # exercises in a unit
CHOICE_CANDIDATES, FIX_CANDIDATES = 12, 8  # written by the LLM; the checked ones are kept
OWN_EXAMPLES = 5  # of your mistakes, shown in the lesson
MIN_EXERCISES = 6  # fewer passed the check: no unit, try again
ROUNDS = 2  # times exercises are written for a unit, until enough have passed
POINTS, MIN_POINTS = 4, 2  # rules in a lesson, at most and at least
PASSED = 0.8  # of the exercises right: the type counts as practised well

LESSON_SCHEMA = {
    "type": "object",
    "properties": {
        "intro": {"type": "string"},
        "points": {"type": "array", "minItems": 5, "maxItems": 5, "items": {
            "type": "object",
            "properties": {"rule": {"type": "string"}, "right": {"type": "string"}, "wrong": {"type": "string"}},
            "required": ["rule", "wrong", "right"],
        }},
    },
    "required": ["intro", "points"],
}
LESSON_PROMPT = """You are an English teacher preparing a learner for IELTS. Write a short lesson on one
type of mistake: {title} ({covers}).
- intro: two sentences, at most 40 words: what this is about and why it matters. Speak to the
  learner ("you").
- points: the five rules that learners break most often. Each has
  - rule: one rule in plain words, at most 25 words, no grammar terms a learner would not know;
  - right: a short, natural sentence that follows this rule;
  - wrong: the same sentence breaking the rule, as a learner would. It must be wrong English.
"""

CHOICE_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "minItems": CHOICE_CANDIDATES, "maxItems": CHOICE_CANDIDATES, "items": {
        "type": "object",
        "properties": {
            "sentence": {"type": "string"},
            "correct": {"type": "string"},
            "wrong": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string"}},
            "why": {"type": "string"},
        },
        "required": ["sentence", "correct", "wrong", "why"],
    }}},
    "required": ["items"],
}
CHOICE_PROMPT = """You are an English teacher. Write {n} gap-fill exercises that practise one type of
mistake: {title} ({covers}).
Each exercise:
- sentence: one natural sentence of 8 to 16 words about everyday life, work, study or travel, with
  exactly one gap written as ___ where the tested words go.
- correct: the only words that fill the gap correctly. Write "(nothing)" if the gap must stay empty.
- wrong: two other ways to fill it that a learner might choose and that are clearly wrong in this
  sentence. Never a second correct answer: if two answers could both be right, write another sentence.
- why: why the correct answer is right, at most 20 words.
No hints: never put the answer, a base form or anything else in brackets in the sentence.
Make the exercises different from each other: different rules of this type, different words."""

FIX_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "minItems": FIX_CANDIDATES, "maxItems": FIX_CANDIDATES, "items": {
        "type": "object",  # the correct sentence first: the LLM then breaks it, and mixes the two up less
        "properties": {"correct_sentence": {"type": "string"}, "sentence_with_mistake": {"type": "string"},
                       "why": {"type": "string"}},
        "required": ["correct_sentence", "sentence_with_mistake", "why"],
    }}},
    "required": ["items"],
}
FIX_PROMPT = """You are an English teacher. Write {n} "correct the sentence" exercises that practise one
type of mistake: {title} ({covers}).
For each exercise:
- correct_sentence: first write one natural, fully correct sentence of 8 to 16 words about
  everyday life, work, study or travel.
- sentence_with_mistake: then the same sentence with one mistake of this type put into it, the kind
  a learner really makes. Change as little as possible; it must now be wrong English.
- why: what is wrong in the sentence with the mistake, at most 20 words.
Make the exercises different from each other: different rules of this type, different words."""

VERDICTS = {
    "type": "object",
    "properties": {"answers": {"type": "array", "items": {
        "type": "object",
        "properties": {"n": {"type": "integer"}, "yes": {"type": "boolean"}},
        "required": ["n", "yes"],
    }}},
    "required": ["answers"],
}
CORRECT_PROMPT = """You are a careful English teacher marking sentences. Judge each numbered sentence on
its own: yes = it is fully correct, natural standard English; no = it has a mistake of grammar,
a wrong, missing or extra word, or a wording no native speaker would use. About half of these
sentences have a mistake, so read each word. Return every sentence once, with its number."""
ABOUT_PROMPT = """Each numbered line shows a sentence with a mistake and the same sentence corrected.
For each: yes = the correction is an example of this type of mistake: {title} ({covers});
no = it corrects something else. Return every line once, with its number."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"answers": {"type": "array", "items": {
        "type": "object",
        "properties": {"n": {"type": "integer"}, "correct": {"type": "boolean"}},
        "required": ["n", "correct"],
    }}},
    "required": ["answers"],
}
JUDGE_PROMPT = """A learner was given sentences with one mistake each and asked to write them correctly.
For each numbered item you get the sentence with the mistake, one correct version, and the
learner's sentence. Answer correct: true only if the learner's sentence is fully correct English,
keeps the meaning, and no longer has the mistake. Another correct wording than the given one is
fine; small differences of punctuation and capital letters do not matter."""


class Start(BaseModel):
    type: str


class Answers(BaseModel):
    answers: dict[str, int | str]


@router.get("/api/practice")
def overview():
    """The types to practise: those you make mistakes in first, the most frequent first."""
    mistakes.sync()
    counts = {t["id"]: t for t in mistakes.summary()["types"]}
    results = last_results()
    types = [{"id": key, "title": title, "covers": covers,
              "mistakes": counts[key]["count"] if key in counts else 0,
              "improving": counts[key]["improving"] if key in counts else False,
              **results.get(key, {"units": 0, "last": None})}
             for key, (title, covers) in mistakes.TYPES.items() if key not in NOT_PRACTISED]
    types.sort(key=lambda t: -t["mistakes"])  # stable: the others stay in the list's order
    return {"types": types, "passed": PASSED}


@router.post("/api/practice/units")
async def start(body: Start):
    if body.type not in mistakes.TYPES or body.type in NOT_PRACTISED:
        raise HTTPException(404, "No practice for this type")
    content = await write_unit(body.type)
    unit_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    with storage.connect() as db:
        db.execute("INSERT INTO practice_units (id, type, created_at, content) VALUES (?, ?, ?, ?)",
                   (unit_id, body.type, datetime.now(timezone.utc).isoformat(), json.dumps(content)))
    return shown(_unit_or_404(unit_id))


@router.get("/api/practice/units/{unit_id}")
def get_unit(unit_id: str):
    return shown(_unit_or_404(unit_id))


@router.post("/api/practice/units/{unit_id}/answers")
async def check(unit_id: str, body: Answers):
    unit = _unit_or_404(unit_id)
    if unit["result"] is None:
        unit["result"] = await mark(unit["content"]["exercises"], body.answers)
        with storage.connect() as db:
            db.execute("UPDATE practice_units SET result = ? WHERE id = ?", (json.dumps(unit["result"]), unit_id))
    return shown(unit)


def _unit_or_404(unit_id: str) -> dict:
    with storage.connect() as db:
        row = db.execute("SELECT * FROM practice_units WHERE id = ?", (unit_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "No such unit")
    return {"id": row["id"], "type": row["type"], "created_at": row["created_at"],
            "content": json.loads(row["content"]), "result": json.loads(row["result"]) if row["result"] else None}


def last_results() -> dict[str, dict]:
    """type → how many units you finished, and the last one's score."""
    with storage.connect() as db:
        rows = db.execute("SELECT * FROM practice_units WHERE result IS NOT NULL ORDER BY created_at").fetchall()
    results = {}
    for row in rows:
        result = json.loads(row["result"])
        entry = results.setdefault(row["type"], {"units": 0})
        entry["units"] += 1
        entry["last"] = {"unit": row["id"], "score": result["score"], "of": result["of"], "date": row["created_at"],
                         "passed": result["score"] >= PASSED * result["of"]}
    return results


def shown(unit: dict) -> dict:
    """The unit for the app: the answers only once it has been checked."""
    title, covers = mistakes.TYPES[unit["type"]]
    content, result = unit["content"], unit["result"]
    exercises = []
    for e in content["exercises"]:
        item = {"n": e["n"], "kind": e["kind"], "sentence": e["sentence"]}
        if e["kind"] == "choice":
            item["options"] = e["options"]
        if result:
            item.update(result["exercises"][str(e["n"])])
        exercises.append(item)
    return {"id": unit["id"], "type": unit["type"], "title": title, "covers": covers, "date": unit["created_at"],
            "lesson": content["lesson"], "exercises": exercises,
            "result": {"score": result["score"], "of": result["of"],
                       "passed": result["score"] >= PASSED * result["of"]} if result else None}


# ---- writing a unit ----

def own_examples(kind: str) -> list[dict]:
    """Your latest mistakes of this type."""
    found = next((t for t in mistakes.summary()["types"] if t["id"] == kind), None)
    return [{k: e[k] for k in ("original", "better", "why", "module", "session")}
            for e in (found["examples"][:OWN_EXAMPLES] if found else [])]


async def write_unit(kind: str) -> dict:
    title, covers = mistakes.TYPES[kind]
    mistakes.sync()
    own = own_examples(kind)
    about = {"title": title, "covers": covers}

    async def ask(prompt: str, schema: dict, **more) -> dict:
        return await llm.complete_json([{"role": "system", "content": prompt.format(**about, **more)},
                                        {"role": "user", "content": f"Write it for: {title}."}],
                                       schema, temperature=0.7, max_tokens=3000)

    async def exercises_round() -> list[dict]:
        choices, fixes = await asyncio.gather(ask(CHOICE_PROMPT, CHOICE_SCHEMA, n=CHOICE_CANDIDATES),
                                              ask(FIX_PROMPT, FIX_SCHEMA, n=FIX_CANDIDATES))
        formed = [e for e in [*map(as_choice, choices["items"]), *map(as_fix, fixes["items"])] if e]
        good = await checked(formed, title, covers)
        log.info("%s: %d exercises written, %d well formed, %d passed the check",
                 kind, len(choices["items"]) + len(fixes["items"]), len(formed), len(good))
        return good

    async def lesson() -> dict:
        for _ in range(ROUNDS):
            written = await ask(LESSON_PROMPT, LESSON_SCHEMA)
            # A rule stays when its "wrong" sentence is judged wrong and its "right" one right.
            points = [p for p in written["points"] if normalise(p["wrong"]) != normalise(p["right"])]
            judged = await verdicts(CORRECT_PROMPT, [x for p in points for x in (p["wrong"], p["right"])])
            points = [p for i, p in enumerate(points) if judged[2 * i] is False and judged[2 * i + 1] is True]
            log.info("%s: %d of %d rules of the lesson passed the check", kind, len(points), len(written["points"]))
            if len(points) >= MIN_POINTS:
                break
        return {"intro": written["intro"], "points": points[:POINTS]}

    lesson_task = asyncio.create_task(lesson())
    good = []
    for _ in range(ROUNDS):
        seen = {normalise(e["sentence"]) for e in good}
        good += [e for e in await exercises_round() if normalise(e["sentence"]) not in seen]
        choices, fixes = ([e for e in good if e["kind"] == k] for k in ("choice", "fix"))
        if len(good) >= CHOICES + FIXES:
            break
    rules = await lesson_task
    # A unit has CHOICES + FIXES exercises when enough passed the check; one kind fills in for the other.
    exercises = choices[:CHOICES] + fixes[:FIXES]
    spare = choices[CHOICES:] + fixes[FIXES:]
    exercises += spare[:CHOICES + FIXES - len(exercises)]
    exercises.sort(key=lambda e: e["kind"] != "choice")
    if len(exercises) < MIN_EXERCISES or len(rules["points"]) < MIN_POINTS:
        raise HTTPException(503, "The exercises did not come out well enough this time. Please try again.")
    for n, e in enumerate(exercises, 1):
        e["n"] = n
    return {"lesson": {**rules, "yours": own}, "exercises": exercises}


def as_choice(item: dict) -> dict | None:
    """A gap-fill exercise with its options shuffled, or None if it is not well formed."""
    options = [item["correct"].strip(), *(w.strip() for w in item["wrong"])]
    sentence = item["sentence"].strip()
    # The LLM sometimes writes the whole sentence, without the gap: the gap is where the answer stands.
    if "___" not in sentence and options[0] and len(re.findall(rf"\b{re.escape(options[0])}\b", sentence)) == 1:
        sentence = re.sub(rf"\b{re.escape(options[0])}\b", "___", sentence)
    if sentence.count("___") != 1 or len({o.lower() for o in options}) != 3 or not all(options) \
            or "(" in sentence:  # a hint in brackets gives the answer away
        return None
    if sentence.startswith("___"):  # a capital letter must not give the answer away
        options = [o[0].upper() + o[1:] for o in options]
    correct = options[0]
    random.shuffle(options)
    return {"kind": "choice", "sentence": sentence, "options": options,
            "answer": options.index(correct), "why": first_line(item["why"])}


def as_fix(item: dict) -> dict | None:
    wrong, right = item["sentence_with_mistake"].strip(), item["correct_sentence"].strip()
    if normalise(wrong) == normalise(right) or not 4 <= len(right.split()) <= 30:
        return None
    return {"kind": "fix", "sentence": wrong, "answer": right, "why": first_line(item["why"])}


def first_line(text: str) -> str:
    """The reason without what the LLM sometimes adds after it ("(Note: ...)")."""
    return text.strip().splitlines()[0].strip() if text.strip() else ""


def filled(sentence: str, words: str) -> str:
    """The gap-fill sentence with these words in its gap."""
    words = "" if words.strip().lower() in ("(nothing)", "nothing", "-", "") else words.strip()
    return re.sub(r"\s+([,.!?;:])", r"\1", re.sub(r"\s+", " ", sentence.replace("___", words))).strip()


async def verdicts(prompt: str, lines: list[str]) -> list[bool | None]:
    """The LLM's yes or no for each line (None for a line it left out)."""
    if not lines:
        return []
    reply = await llm.complete_json(
        [{"role": "system", "content": prompt}, {"role": "user", "content": "\n".join(f"{i + 1}. {x}" for i, x in enumerate(lines))}],
        VERDICTS, temperature=0, max_tokens=900)
    said = {a["n"]: a["yes"] for a in reply["answers"]}
    return [said.get(i + 1) for i in range(len(lines))]


async def checked(exercises: list[dict], title: str, covers: str) -> list[dict]:
    """The exercises that do what they say: see the top of this file."""
    # Every sentence an exercise can make, with whether it should be correct English.
    made = []  # (exercise index, sentence, should be correct)
    for i, e in enumerate(exercises):
        if e["kind"] == "choice":
            made += [(i, filled(e["sentence"], o), j == e["answer"]) for j, o in enumerate(e["options"])]
        else:
            made += [(i, e["sentence"], False), (i, e["answer"], True)]
    order = list(range(len(made)))
    random.shuffle(order)  # so a wrong sentence does not stand next to its correction
    half = len(order) // 2
    parts = await asyncio.gather(*(verdicts(CORRECT_PROMPT, [made[k][1] for k in part])
                                   for part in (order[:half], order[half:])))
    judged = dict(zip(order, [v for part in parts for v in part]))
    sound = [all(judged[k] is should for k, (index, _, should) in enumerate(made) if index == i)
             for i in range(len(exercises))]
    kept = [e for e, ok in zip(exercises, sound) if ok]
    pairs = [f"{filled(e['sentence'], next(o for j, o in enumerate(e['options']) if j != e['answer']))} → "
             f"{filled(e['sentence'], e['options'][e['answer']])}" if e["kind"] == "choice"
             else f"{e['sentence']} → {e['answer']}" for e in kept]
    about = await verdicts(ABOUT_PROMPT.format(title=title, covers=covers), pairs)
    return [e for e, yes in zip(kept, about) if yes]


# ---- checking the answers ----

def normalise(text: str) -> str:
    """Lowercase words only: capitals, punctuation and spaces do not make an answer wrong."""
    return " ".join(re.findall(r"[a-z0-9']+", text.lower().replace("’", "'")))


async def mark(exercises: list[dict], answers: dict[str, int | str]) -> dict:
    marked, to_judge = {}, []
    for e in exercises:
        given = answers.get(str(e["n"]))
        if e["kind"] == "choice":
            right = given == e["answer"]
            marked[str(e["n"])] = {"given": given if isinstance(given, int) else None, "right": right,
                                   "answer": e["answer"], "why": e["why"]}
            continue
        given = given.strip() if isinstance(given, str) else ""
        right = normalise(given) == normalise(e["answer"])
        if not right and normalise(given) and normalise(given) != normalise(e["sentence"]):
            to_judge.append((e, given))  # another wording: it may be right too
        marked[str(e["n"])] = {"given": given, "right": right, "answer": e["answer"], "why": e["why"]}
    if to_judge:
        listed = "\n".join(f"{e['n']}. With the mistake: {e['sentence']}\n   Correct: {e['answer']}\n   Learner: {given}"
                           for e, given in to_judge)
        try:
            reply = await llm.complete_json([{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": listed}],
                                            JUDGE_SCHEMA, temperature=0, max_tokens=400)
            for a in reply["answers"]:
                if str(a["n"]) in marked and any(e["n"] == a["n"] for e, _ in to_judge):
                    marked[str(a["n"])]["right"] = a["correct"]
        except Exception:
            pass  # the LLM is busy: those answers stay as the code marked them
    return {"exercises": marked, "score": sum(m["right"] for m in marked.values()), "of": len(marked)}
