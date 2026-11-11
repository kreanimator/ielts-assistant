"""Imports the Speaking tests from your own IELTS books (PDF) and loads them for practice.

    python -m app.speaking.books "path/to/Cambridge IELTS 8.pdf" ...      (or: make books BOOKS="...")

1. Reads each page's text (see core/pages.py: the text layer, or OCR for scanned pages).
2. Finds the pages with a Speaking test: "Speaking", "Part 2" and a cue card.
3. The LLM copies each test into a fixed structure (Part 1 topics and questions, the
   Part 2 cue card, Part 3 discussion topics and questions), fixing obvious OCR slips.

Everything is written to data/private/books/ (git-ignored): <book>.json with the tests,
and <book>.pages.json with the page texts, so a second import skips the slow reading.
(Other modules write <book>.<module>.json there, so <book>.json alone is Speaking's.)
Never commit or share these files: the books are copyrighted.
"""
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

from ..core import llm, pages

log = logging.getLogger("ielts.speaking.books")

QUESTIONS = {"type": "array", "minItems": 1, "items": {"type": "string"}}
TOPIC = {
    "type": "object",
    "properties": {"topic": {"type": "string"}, "questions": QUESTIONS},
    "required": ["topic", "questions"],
}
SCHEMA = {
    "type": "object",
    "properties": {
        "part1": {"type": "array", "minItems": 1, "items": TOPIC},
        "part2": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "points": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
            },
            "required": ["task", "points"],
        },
        "part3": {"type": "array", "minItems": 1, "items": TOPIC},
    },
    "required": ["part1", "part2", "part3"],
}
PROMPT = """You copy one IELTS Speaking test from text extracted from a book page.
The text may contain OCR slips and parts of other pages: copy only the Speaking test.
- part1: each Part 1 topic with its questions, copied word for word. Drop bracketed
  prompts like [Why/Why not?] and the bullet signs.
- part2: task is the cue card's first line ("Describe ..."); points are the lines after
  "You should say:", with the last one starting "and explain ...".
- part3: each discussion topic with its questions, word for word.
Fix only clear OCR slips (like "Yo'u" or "p.Nhy"). Never invent questions."""


def speaking_pages(texts: list[str]) -> list[int]:
    """Pages where a Speaking test starts, found by its structure: Part 2 and Part 3, with
    a cue card or discussion topics. (Headings are often garbled in scanned books.)"""
    return [
        i for i, text in enumerate(texts)
        if re.search(r"part\s*2", text, re.I) and re.search(r"part\s*3", text, re.I)
        and re.search(r"you should say|describe|discussion topics", text, re.I)
    ]


def has_cue_card(text: str) -> bool:
    return bool(re.search(r"you should say", text, re.I))


async def read_test(texts: list[str], page: int) -> dict:
    # The next page too, in case Part 3 continues there.
    text = texts[page] + "\n\n(next page)\n" + texts[page + 1] if page + 1 < len(texts) else texts[page]
    test = await llm.complete_json(
        [{"role": "system", "content": PROMPT}, {"role": "user", "content": text[:6000]}], SCHEMA
    )
    test["page"] = page + 1
    return test


async def import_book(path: Path) -> dict:
    texts = pages.read(path)
    found = speaking_pages(texts)
    # Some books have the cue card as a picture, or a garbled text layer: read those pages with OCR.
    missing = [i for i in found if not has_cue_card(texts[i])]
    if missing:
        log.info("%s: reading %d Speaking pages with OCR", path.name, len(missing))
        for i, text in zip(missing, pages.ocr(path, missing)):
            if has_cue_card(text):
                texts[i] = text
        pages.save(path, texts)

    tests, seen = [], set()
    for page in found:
        test = await read_test(texts, page)
        task = test["part2"]["task"].strip().lower()
        if task.startswith("describe") and task not in seen:  # skips repeats, e.g. in sample answers
            seen.add(task)
            tests.append({"test": len(tests) + 1, **test})  # numbered in book order
    book = {"id": pages.slug(path), "title": pages.title(path), "file": path.name, "tests": tests}
    (pages.books_dir() / f"{book['id']}.json").write_text(json.dumps(book, indent=1, ensure_ascii=False))
    return book


def load_books() -> list[dict]:
    if not pages.books_dir().exists():
        return []
    paths = [p for p in pages.books_dir().glob("*.json") if p.name.count(".") == 1]  # not <book>.pages.json
    return sorted((json.loads(p.read_text()) for p in paths), key=lambda b: b["title"])


def find_test(book_id: str, number: int) -> dict | None:
    """One test, with its book's title under "book"."""
    for book in load_books():
        if book["id"] == book_id:
            test = next((t for t in book["tests"] if t["test"] == number), None)
            return test and {**test, "book": book["title"]}
    return None


async def main(paths: list[str]):
    for p in paths:
        path = Path(p)
        try:
            book = await import_book(path)
        except Exception as e:  # one broken file should not stop the others
            print(f"{path.name}: failed ({type(e).__name__}: {e})")
            continue
        found = ", ".join(str(t["test"]) for t in book["tests"]) or "none"
        print(f"{book['title']}: Speaking tests {found}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1:]))
