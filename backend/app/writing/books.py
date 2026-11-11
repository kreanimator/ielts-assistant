"""Imports the Writing tests from your own IELTS books, with the books' model and sample
answers, and loads them for practice.

    python -m app.writing.books "path/to/Cambridge IELTS 11 GT.pdf" ...   (make books does Speaking and Writing)
    python -m app.writing.books --cached       every book already read once (no PDFs needed)

1. The page texts come from core/pages.py (cached by any earlier import).
2. Task pages ("You should spend about 20 minutes on this task") are copied by the LLM into a
   fixed structure: the task's kind (a letter, an essay, or an Academic chart), its prompt
   word for word with the bullet points, how the letter begins, the time and the word count.
3. Tests: each Task 1 starts a new test and a Task 2 belongs to the test before it. General
   Training tests have a letter as Task 1, Academic tests a chart. The General Training books
   number their tests 1, 2, ...; the Academic books number their Academic tests 1, 2, ... and
   call their General Training tests A, B, ..., as the books' answer sections do. Academic
   tests keep only Task 2 (Task 1 needs its chart, which is a picture).
4. Answer pages: the LLM gives each answer's test, task, kind (an examiner's model answer, or
   a candidate's sample answer with its band), the examiner's comment and the first words of
   the answer. The answer itself is cut from the page text, never written by the LLM.
   Candidates' answers are often printed in handwriting with no readable text layer: then
   those pages are read with OCR (when the PDF is there), and if the answer is still not
   readable it is left out (answer: null) and only its band and comment are kept. (Model answers
   are kept only with their text: some books print them as pictures.)

Everything is written to data/private/books/<book>.writing.json (git-ignored). Never commit
or share these files: the books are copyrighted.
"""
import asyncio
import json
import logging
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

from ..core import llm, pages

log = logging.getLogger("ielts.writing.books")

# A task page: a "WRITING TASK 1" heading with "You should spend about 20 minutes on this task"
# or "Write at least 150 words" (OCR slips included). Reading pages also say "You should spend
# about 20 minutes", so the heading is needed too.
WRITING_HEADING = re.compile(r"W\W{0,2}\w?ITING\s*TASK", re.I)
TASK_LINES = re.compile(r"pend\W*(about|no\W*more\W*than)\W*\S{0,2}\W*[24]\s*0\s*minute"
                        r"|at\s*least\s*\S{0,2}\s*[12]\s*5\s*0\s*words", re.I)
# The books' introduction describes the tasks too: not a test.
INTRODUCTION = re.compile(r"introdu|test\s*format|task\s*types", re.I)
# A page of the answer section: model answers, or candidates' sample answers with their band.
ANSWER_PAGE = re.compile(r"(model|sample)\W*answer|answer\W*written\W*by|achieved\W*\S{0,3}\W*band|answer\W*keys", re.I)
# Where one answer in the answer section starts: "TEST 2, WRITING TASK 1 (GENERAL TRAINING)".
ANSWER_HEADING = re.compile(r"TEST\s*(\w{1,2})\s*[,.]?\s*W\W{0,2}\w?ITING\s*TASK\s*(\w)", re.I)
BAND = re.compile(r"achieved\W*\S{0,3}\W*band\W*(\d(?:\s*[.,]\s*5)?)", re.I)
READABLE = 0.85  # the share of an answer's words that must be English words
# Below this, an answer may be garbled handwriting rather than a weak candidate's spelling (both
# score 0.85-0.9): with the PDF, OCR reads it too and the more readable version is kept.
DOUBTFUL = 0.95
MIN_WORDS = 80  # shorter is not an answer (the books' answers have 120 words or more)
# The books' standard notes before an answer: not part of the answer or the comment.
NOTES = re.compile(r"This\s*model\s*has\s*been\s*prepared.{0,200}?approach\w*\.?"
                   r"|This\s*is\s*an\s*an\S{0,6}\s*written\s*by\s*a\s*candidate.{0,80}?score\.?(\s*Here\s*is\s*the\s*examiner\S{0,3}\s*comment\s*:)?",
                   re.I | re.S)

TASK = {
    "type": "object",
    "properties": {
        "task": {"type": "integer", "enum": [1, 2]},
        "kind": {"type": "string", "enum": ["letter", "chart", "essay"]},
        "prompt": {"type": "string"},
        "bullets": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
        "begin": {"type": "string"},
        "minutes": {"type": "integer"},
        "words": {"type": "integer"},
    },
    "required": ["task", "kind", "prompt", "bullets", "begin", "minutes", "words"],
}
TASKS_SCHEMA = {
    "type": "object",
    "properties": {"test": {"type": "string"}, "tasks": {"type": "array", "maxItems": 2, "items": TASK}},
    "required": ["test", "tasks"],
}
TASKS_PROMPT = """You copy the IELTS Writing tasks on one book page. The text may contain OCR slips.
test: the test's number or letter if the page has a heading like "Test 6" (gives "6") or "Test B"
(gives "B"), else "". Never the page number.
For each task on the page (WRITING TASK 1 and/or WRITING TASK 2):
- task: 1 or 2.
- kind: "letter" (Task 1 that asks you to write a letter), "chart" (Task 1 about a graph, chart,
  table, map, diagram or process), or "essay" (Task 2).
- prompt: the situation or topic and what to write, word for word, without the bullet points and
  without the standard lines ("You should spend about ...", "Write at least ... words.", "You do
  NOT need to write any addresses.", "Begin your letter as follows:").
- bullets: for a letter, the points to cover, word for word, without the bullet signs. Else [].
- begin: for a letter, how it must begin, e.g. "Dear Sir or Madam," or "Dear ...,". Else "".
- minutes: the time to spend (20 or 40). words: the minimum number of words (150 or 250).
Fix only clear OCR slips (like "hobbles" for "hobbies" or "ta::;k"). Never invent text.
Only tasks under a WRITING TASK heading count. A page can also hold Reading questions or a Speaking
role-play card ("Task: The candidate is to find out ...", "Ask the examiner about"): copy the
Writing tasks and leave those out. If the page has no Writing task, return no tasks."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"comment": {"type": "string"}, "first_words": {"type": "string"}},
    "required": ["comment", "first_words"],
}
ANSWER_PROMPT = """You read one answer from the answer section of an IELTS book: a heading, a note
on who wrote it, maybe the examiner's comment, then the answer itself. The text may contain OCR
slips, and the answer may be garbled.
- comment: the examiner's comment, word for word, or "" if there is none. The note "This model has
  been prepared by an examiner ..." or "This is an answer written by a candidate ..." is not part
  of the comment.
- first_words: the first eight words of the answer itself (after the note and the comment),
  copied exactly as they appear in the text, even if they are garbled.
Never invent text."""


async def read_tasks(text: str) -> tuple[str, list[dict]]:
    """The test's name printed on the page ("" if none) and the page's tasks."""
    messages = [{"role": "system", "content": TASKS_PROMPT}, {"role": "user", "content": text[:6000]}]
    reply = await llm.complete_json(messages, TASKS_SCHEMA, temperature=0, max_tokens=2048)
    if not reply["tasks"]:  # the page has a Writing heading: one more try
        reply = await llm.complete_json(messages, TASKS_SCHEMA, temperature=0.3, max_tokens=2048)
    label = test_label(reply["test"])
    if label and not re.search(rf"test\s*{re.escape(label)}\b", text, re.I):
        label = ""  # not printed as "Test 6" (the LLM sometimes takes the page number)
    return label, reply["tasks"]


async def read_answer(segment: str) -> dict:
    """The examiner's comment and the answer's first words."""
    return await llm.complete_json(
        [{"role": "system", "content": ANSWER_PROMPT}, {"role": "user", "content": segment[:6000]}], ANSWER_SCHEMA,
        max_tokens=1536,
    )


def answer_segments(texts: list[str], i: int) -> list[dict]:
    """The answers that start on page i: test, task, General Training or not, and the text
    from the heading to the next heading (on the next page too, for a long answer)."""
    text = with_next_page(texts, i)
    headings = list(ANSWER_HEADING.finditer(text))
    found = []
    for n, heading in enumerate(headings):
        if heading.start() >= len(texts[i]):
            break  # starts on the next page: read with that page
        end = headings[n + 1].start() if n + 1 < len(headings) else len(text)
        segment = text[heading.start():end]
        band = BAND.search(segment[:800])  # before the notes go: "who achieved a Band 7 score"
        segment = NOTES.sub(" ", segment, count=1)
        task = test_label(heading.group(2))
        if task not in ("1", "2"):
            continue
        found.append({
            "test": test_label(heading.group(1)), "task": int(task),
            "general_training": bool(re.search(r"general", text[heading.end():heading.end() + 40], re.I)),
            "band": float(re.sub(r"\s*[.,]\s*", ".", band.group(1))) if band else None,
            "segment": segment,
        })
    return found


def clean(text: str) -> str:
    """Decodes the "/G57/G72" glyph codes some PDFs have instead of letters."""
    return re.sub(r"/G([0-9A-F]{2})", lambda m: chr(int(m.group(1), 16)), text)


def is_task_page(text: str) -> bool:
    return (bool(WRITING_HEADING.search(text)) and bool(TASK_LINES.search(text))
            and not ANSWER_PAGE.search(text) and not INTRODUCTION.search(text[:300]))


def is_answer_page(text: str) -> bool:
    return bool(ANSWER_PAGE.search(text)) and bool(ANSWER_HEADING.search(text))


def build_tests(found: list[dict], general_book: bool) -> list[dict]:
    """Groups the tasks (in page order) into tests and names them as the book does: by the name
    printed on the page, else counting on from the test before."""
    tests = []
    for task in found:
        current = tests[-1] if tests else None
        new = (current is None or task["task"] == 1 or current["seen2"]
               or (task["label"] and current["label"] and task["label"] != current["label"])
               # A test's two tasks are on the same page or the next: further on, a Task 2 whose
               # Task 1 page was not found starts the next test.
               or task["page"] - current["page"] > 2)
        if new:
            current = {"label": task["label"], "kind1": None, "seen2": False, "page": task["page"],
                       "task1": None, "task2": None}
            tests.append(current)
        current["label"] = current["label"] or task["label"]
        if task["task"] == 1:
            current["kind1"] = task["kind"]
            if task["kind"] == "letter":
                current["task1"] = {k: task[k] for k in ("prompt", "bullets", "begin", "minutes", "words")}
                current["task1"]["begin"] = letter_start(task["begin"])
        else:
            current["seen2"] = True
            current["task2"] = {k: task[k] for k in ("prompt", "minutes", "words")}
    named, number, letter = [], 0, 0
    for test in tests:
        general = general_book or test["kind1"] == "letter"
        label = test["label"]
        if label.isdigit():
            number = int(label)
        elif label.isalpha():
            letter = ord(label[0]) - ord("A") + 1
        elif general and not general_book:  # the Academic books call their General Training tests A, B, ...
            letter += 1
            label = chr(ord("A") + letter - 1)
        else:
            number += 1
            label = str(number)
        if test["task1"] is None and test["task2"] is None:
            continue
        named.append({"test": label, "type": "general" if general else "academic", "page": test["page"],
                      "task1": test["task1"], "task2": test["task2"], "answers": []})
    return named


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def cut_answer(text: str, first_words: str) -> str | None:
    """The answer's text in its segment: from its first words on."""
    words = first_words.split()[:5]
    if len(words) < 2:
        return None
    start = None
    # Exact first, then the closest stretch of the page (for slips in first_words).
    for match in re.finditer(re.escape(words[0]), text):
        if normalise(text[match.start():match.start() + 200]).startswith(normalise(" ".join(words))):
            start = match.start()
            break
    if start is None:
        target = normalise(" ".join(words))
        best = (0.0, None)
        for match in re.finditer(r"\S+", text):
            ratio = SequenceMatcher(None, target, normalise(text[match.start():match.start() + len(target) + 20])[:len(target)]).ratio()
            if ratio > best[0]:
                best = (ratio, match.start())
        if best[0] < 0.8:
            return None
        start = best[1]
    answer = text[start:]
    lines = [line for line in answer.splitlines() if not re.fullmatch(r"\s*\d{1,3}\s*", line)  # page numbers
             and not re.search(r"(model and )?sample (writing )?answers? (for writing|sheets)", line, re.I)]
    answer = re.sub(r"[ \t]+", " ", "\n".join(lines)).strip()
    return answer if len(answer.split()) >= MIN_WORDS else None


_dictionary = None


def readability(text: str) -> float:
    """The share of the words that are English words (the CMU dictionary)."""
    global _dictionary
    if _dictionary is None:
        from nltk.corpus import cmudict  # installed with the pronunciation model (g2p_en)
        _dictionary = set(cmudict.words())
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return 0.0
    return sum(w.lower().strip("'") in _dictionary for w in words) / len(words)


def letter_start(begin: str) -> str:
    """How the letter must begin. The books use three: "Dear Sir or Madam,", "Dear Sir," and
    "Dear ...," for a name you choose (printed as dots, which OCR turns into "Dear." or "Deu,")."""
    if re.search(r"m\W*\w{0,2}\W*d\W*\w{0,2}\W*m", begin, re.I):  # Madam, with OCR slips ("MGtdA.m")
        return "Dear Sir or Madam,"
    if re.search(r"\bsir\b", begin, re.I):
        return "Dear Sir,"
    return "Dear ...,"


def readable_task(task: dict) -> bool:
    return readability(task["prompt"] + " " + " ".join(task["bullets"])) >= READABLE


async def import_book(path: Path) -> dict:
    texts = [clean(t) for t in pages.read(path)]
    general_book = is_general_book(pages.title(path))

    found = []
    for i, text in enumerate(texts):
        if not is_task_page(text):
            continue
        label, tasks = await read_tasks(text)
        # A garbled scan (nothing found, or a task that is not readable): try OCR.
        if (not tasks or any(not readable_task(t) for t in tasks)) and path.exists():
            label, tasks = await read_tasks(clean(next(pages.ocr(path, [i]))))
        for task in tasks:
            task["task"] = 2 if task["kind"] == "essay" else 1  # OCR can garble the heading, not the kind
            if task["kind"] == "letter" and not re.search(r"letter|dear", text, re.I):
                continue  # not a letter task (one book has a Speaking role-play card on a Writing page)
            if readable_task(task):
                found.append({**task, "label": label, "page": i + 1})
            else:
                log.info("  page %d: Task %d is not readable", i + 1, task["task"])
    tests = build_tests(found, general_book)

    doubtful = {}  # page → its answers whose text could not be read, or not well
    for i, text in enumerate(texts):
        if not is_answer_page(text):
            continue
        for a in answer_segments(texts, i):
            test = find_in(tests, a, general_book)
            if test is None:
                continue
            read = await read_answer(a["segment"])
            answer = cut_answer(a["segment"], read["first_words"])
            # A band means a candidate wrote it (one book heads such an answer "MODEL ANSWER").
            entry = {"task": a["task"], "kind": "sample" if a["band"] is not None else "model", "band": a["band"],
                     "comment": read["comment"].strip(), "answer": answer, "page": i + 1}
            if answer is None or readability(answer) < READABLE:
                entry["answer"] = None
            if entry["answer"] is None or readability(answer) < DOUBTFUL:
                doubtful.setdefault(i, []).append((a, entry))
            test["answers"].append(entry)

    # Answers printed in handwriting: OCR reads them better than their text layer.
    if doubtful and path.exists():
        read_pages = sorted({j for i in doubtful for j in (i, i + 1) if j < len(texts)})
        log.info("%s: reading %d answer pages with OCR", path.name, len(read_pages))
        ocr = dict(zip(read_pages, (clean(t) for t in pages.ocr(path, read_pages))))
        ocr_texts = [ocr.get(j, "") for j in range(len(texts))]
        for i, waiting in doubtful.items():
            found = answer_segments(ocr_texts, i)
            for a, entry in waiting:
                again = next((x for x in found if x["task"] == a["task"] and x["test"] == a["test"]), None)
                if again is None:
                    continue
                answer = cut_answer(again["segment"], (await read_answer(again["segment"]))["first_words"])
                before = readability(entry["answer"]) if entry["answer"] else 0.0
                if answer and readability(answer) >= READABLE and readability(answer) > before:
                    entry["answer"] = answer
    # A model answer is only useful with its text (it has no band or comment).
    for test in tests:
        test["answers"] = [a for a in test["answers"] if a["kind"] == "sample" or a["answer"]]

    book = {"id": pages.slug(path), "title": pages.title(path), "file": path.name, "tests": tests}
    pages.books_dir().mkdir(parents=True, exist_ok=True)
    (pages.books_dir() / f"{book['id']}.writing.json").write_text(json.dumps(book, indent=1, ensure_ascii=False))
    return book


def is_general_book(title: str) -> bool:
    """A General Training book, by its name: "... 11 GT", "IELTS_13_General"."""
    return bool(re.search(r"(^|[^a-z])(gt|general)([^a-z]|$)", title, re.I))


def with_next_page(texts: list[str], i: int) -> str:
    """The page, and the next one when a long answer goes on there (no heading of its own)."""
    text = texts[i]
    if i + 1 < len(texts) and not ANSWER_HEADING.search(texts[i + 1]) and not is_task_page(texts[i + 1]):
        text += "\n" + texts[i + 1]
    return text


def test_label(test: str) -> str:
    """"1", "A", ...: the test's name as printed, with OCR's "I" for 1."""
    label = re.sub(r"[^A-Z0-9]", "", test.upper())
    return "1" if label in ("I", "L") else label


def find_in(tests: list[dict], a: dict, general_book: bool) -> dict | None:
    """The test an answer belongs to (by the test's name, and General Training or not), if we
    keep that task: not an Academic Task 1, whose chart we don't have."""
    general = general_book or a["general_training"]
    for test in tests:
        if test["test"] == a["test"] and (test["type"] == "general") == general:
            if test[f"task{a['task']}"] is not None:
                return test
            return None
    log.info("  no test for the answer to Test %s, Task %d", a["test"], a["task"])
    return None


def load_books() -> list[dict]:
    if not pages.books_dir().exists():
        return []
    paths = pages.books_dir().glob("*.writing.json")
    return sorted((json.loads(p.read_text()) for p in paths), key=lambda b: b["title"])


def find_test(book_id: str, test: str) -> dict | None:
    """One test, with its book's title under "book"."""
    for book in load_books():
        if book["id"] == book_id:
            found = next((t for t in book["tests"] if t["test"] == test), None)
            return found and {**found, "book": book["title"]}
    return None


def cached_books() -> list[Path]:
    """The books whose pages were read before, under their original file names."""
    found = []
    for cache in sorted(pages.books_dir().glob("*.pages.json")):
        book_id = cache.name.removesuffix(".pages.json")
        speaking = pages.books_dir() / f"{book_id}.json"
        name = json.loads(speaking.read_text())["file"] if speaking.exists() else f"{book_id}.pdf"
        found.append(Path(name))
    return found


def summary(book: dict) -> str:
    general = [t for t in book["tests"] if t["type"] == "general"]
    answers = [a for t in book["tests"] for a in t["answers"]]
    scored = [a for a in answers if a["band"] is not None]
    return (f"{len(general)} General Training tests, {len(book['tests']) - len(general)} Academic Task 2s; "
            f"{len(answers)} answers ({len(scored)} with a band, {sum(a['answer'] is None for a in answers)} unreadable)")


async def main(args: list[str]):
    paths = cached_books() if args == ["--cached"] else [Path(p).expanduser() for p in args]
    for path in paths:
        try:
            book = await import_book(path)
        except Exception as e:  # one broken file should not stop the others
            print(f"{path.name}: failed ({type(e).__name__}: {e})")
            continue
        print(f"{book['title']}: {summary(book)}", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1:]))
