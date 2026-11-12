"""The tasks to practise: a real one from your books, or a new one the LLM writes.

A task is a dict:
  {"task": 1 or 2, "kind": "letter" or "essay", "prompt": "...", "bullets": [...] (letters),
   "begin": "Dear Sir or Madam," (letters), "minutes": 20 or 40, "words": 150 or 250,
   "source": "book" or "new", "book": "<book id>", "book_title": "...", "test": "2",
   "title": "Cambridge IELTS 8 · Test 2"}

Task 1 is the General Training letter: the Academic Task 1 describes a chart, which the books
print as a picture we cannot show, so the Academic tests give only their Task 2 essays.
"""
import random
import re

from ..core import llm
from . import books

LETTER = {"task": 1, "kind": "letter", "minutes": 20, "words": 150}
ESSAY = {"task": 2, "kind": "essay", "minutes": 40, "words": 250}

# The kinds of letters and essays the test uses, for new tasks.
LETTER_TYPES = {
    "formal": "a formal letter to a company, an official or someone you do not know (begin \"Dear Sir or Madam,\")",
    "semi-formal": "a semi-formal letter to someone you know but not well, such as a manager, a neighbour or a "
                   "teacher (begin \"Dear ...,\")",
    "informal": "an informal letter to a friend (begin \"Dear ...,\")",
}
ESSAY_TYPES = {
    "opinion": "To what extent do you agree or disagree?",
    "discussion": "Discuss both these views and give your own opinion.",
    "advantages": "Do the advantages of this outweigh the disadvantages?",
    "problem": "What problems does this cause, and what solutions can you suggest?",
    "two-part": "Two direct questions about the situation.",
}
# Everyday topics of the General Training test, for new tasks without a topic.
TOPICS = ["work", "education", "technology", "health", "the environment", "transport", "housing", "family",
          "travel", "shopping", "food", "free time", "sport", "the media", "money", "neighbours", "cities",
          "crime", "tourism", "advertising", "children", "older people", "culture", "volunteering"]

NEW_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string"},
        "bullets": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
        "title": {"type": "string"},
    },
    "required": ["prompt", "bullets", "title"],
}
NEW_PROMPT = """You write one new IELTS General Training Writing task, like the ones in the official
practice books. Write it in plain, natural British English.
{what}
- title: two to five words naming the topic, e.g. "A broken washing machine" or "Working from home".
Write only the task, never an answer."""
LETTER_PART = """Task 1, {kind}, about {topic}.
- prompt: the situation in one to three sentences ("You recently ...", "A friend of yours ...")
  ending with "Write a letter to ...". Without the standard lines ("You should spend about 20 minutes",
  "Write at least 150 words", "You do NOT need to write any addresses", "Begin your letter as follows").
- bullets: exactly three points the letter must cover, each starting with a verb in lower case
  ("explain ...", "describe ...", "say what you would like ...")."""
ESSAY_ENDING = "Give reasons for your answer and include any relevant examples from your own knowledge or experience."
ESSAY_PART = """Task 2, an essay about {topic}: the question type "{kind}" ({ending}).
- prompt: "Write about the following topic:" left out; one to three sentences that state a view or
  situation, then the question. End with "{ESSAY_ENDING}"
- bullets: []."""


def book_tasks(task: int) -> list[dict]:
    """Every task number `task` in your books."""
    found = []
    for book in books.load_books():
        for t in book["tests"]:
            if task == 1 and t["type"] != "general":
                continue  # the Academic Task 1 is a chart
            item = t[f"task{task}"]
            if not item:
                continue
            item = {"bullets": [], "begin": "", **item}
            if task == 1:
                item = tidy_letter(item)
            found.append({
                **(LETTER if task == 1 else ESSAY), **item,
                "source": "book", "book": book["id"], "book_title": book["title"], "test": t["test"],
                "title": f"{book['title']} · Test {t['test']}",
            })
    return found


def tidy_letter(item: dict) -> dict:
    """The import sometimes copies the bullet points into the prompt too ("... In your letter
    give details ..."): they are cut from the prompt. The oldest books have no bullet points,
    only sentences in the prompt ("Explain what has happened and ..."), which the import also
    gave as bullet points: those are dropped, so they are not printed twice."""
    prompt = re.split(r"\s*In your letter\b", item["prompt"], maxsplit=1, flags=re.I)[0].strip()
    bullets = item["bullets"]
    if prompt == item["prompt"] and bullets and all(b[:20].lower() in prompt.lower() for b in bullets):
        bullets = []
    return {**item, "prompt": prompt, "bullets": bullets}


def from_book(task: int, book_id: str | None = None, test: str | None = None) -> dict | None:
    """The task from that test, or a random one from your books (None if you have none)."""
    found = [t for t in book_tasks(task) if (book_id is None or t["book"] == book_id) and (test is None or t["test"] == test)]
    return random.choice(found) if found else None


async def new_task(task: int, topic: str | None = None, kind: str | None = None) -> dict:
    """A new task written by the LLM, on the topic if given (else a random everyday topic)."""
    topic = (topic or "").strip() or random.choice(TOPICS)
    if task == 1:
        kind = kind if kind in LETTER_TYPES else random.choice(list(LETTER_TYPES))
        what = LETTER_PART.format(kind=LETTER_TYPES[kind], topic=topic)
    else:
        kind = kind if kind in ESSAY_TYPES else random.choice(list(ESSAY_TYPES))
        what = ESSAY_PART.format(kind=kind, ending=ESSAY_TYPES[kind], topic=topic, ESSAY_ENDING=ESSAY_ENDING)
    reply = await llm.complete_json(
        [{"role": "system", "content": NEW_PROMPT.format(what=what)}, {"role": "user", "content": "Write the task."}],
        NEW_SCHEMA, temperature=0.9, max_tokens=800,
    )
    prompt = reply["prompt"].strip()
    if task == 2 and "give reasons" not in prompt.lower():
        prompt += " " + ESSAY_ENDING
    return {
        **(LETTER if task == 1 else ESSAY),
        "prompt": prompt,
        "bullets": [b.strip() for b in reply["bullets"]][:3] if task == 1 else [],
        "begin": ("Dear Sir or Madam," if kind == "formal" else "Dear ...,") if task == 1 else "",
        "source": "new", "type": kind, "title": reply["title"].strip() or topic.capitalize(),
    }


def as_text(task: dict, minimum: bool = True) -> str:
    """The task as the test prints it; without "Write at least ... words." if not minimum (for
    the assessor, which must not judge the length)."""
    lines = [f"WRITING TASK {task['task']}", f"You should spend about {task['minutes']} minutes on this task.", "",
             task["prompt"]]
    if task["bullets"]:
        lines += ["", "In your letter"] + [f"- {b}" for b in task["bullets"]]
    if minimum:
        lines += ["", f"Write at least {task['words']} words."]
    if task["task"] == 1:
        lines += ["You do NOT need to write any addresses.", "", "Begin your letter as follows:", "", task["begin"]]
    return "\n".join(lines)
