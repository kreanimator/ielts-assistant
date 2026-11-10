"""Imports the Speaking tests from your own IELTS books (PDF) and loads them for practice.

    python -m app.books "path/to/Cambridge IELTS 8.pdf" ...      (or: make books BOOKS="...")

1. Reads each page's text. Scanned pages have no text, so they are read with OCR
   (the page is rendered with PDFium and read by RapidOCR), about 1 s per page.
2. Finds the pages with a Speaking test: "Speaking", "Part 2" and a cue card.
3. The LLM copies each test into a fixed structure (Part 1 topics and questions, the
   Part 2 cue card, Part 3 discussion topics and questions), fixing obvious OCR slips.

Everything is written to data/private/books/ (git-ignored): <book>.json with the tests,
and <book>.pages.json with the page texts, so a second import skips the slow reading.
Never commit or share these files: the books are copyrighted.
"""
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

from . import config, llm

log = logging.getLogger("ielts.books")

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


def books_dir() -> Path:
    return config.DATA_DIR / "private" / "books"


def slug(path: Path) -> str:
    name = re.sub(r"\[.*?\]", "", path.stem)  # drop "[www.site.com]" tags
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def title(path: Path) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\[.*?\]", "", path.stem)).strip(" -")


def page_texts(path: Path) -> list[str]:
    """The text of every page: from the PDF's text layer, or by OCR for scanned pages."""
    from pypdf import PdfReader  # imported here: the backend only needs them when importing

    reader = PdfReader(path)
    texts = [page.extract_text() or "" for page in reader.pages]
    scanned = [i for i, text in enumerate(texts) if len(text.strip()) < 200]
    if scanned:
        log.info("%s: reading %d scanned pages with OCR", path.name, len(scanned))
        for i, text in zip(scanned, ocr(path, scanned)):
            texts[i] = text
    return texts


def ocr(path: Path, pages: list[int]):
    import numpy as np
    import pypdfium2
    from rapidocr import RapidOCR

    engine = RapidOCR(params={"Global.log_level": "warning"})
    pdf = pypdfium2.PdfDocument(path)
    for n, i in enumerate(pages):
        image = np.array(pdf[i].render(scale=2).to_pil().convert("RGB"))
        yield "\n".join(engine(image).txts or [])
        if n % 20 == 19:
            log.info("  OCR %d/%d pages", n + 1, len(pages))


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
    books_dir().mkdir(parents=True, exist_ok=True)
    cache = books_dir() / f"{slug(path)}.pages.json"
    if cache.exists():
        texts = json.loads(cache.read_text())
    else:
        texts = page_texts(path)
    pages = speaking_pages(texts)
    # Some books have the cue card as a picture, or a garbled text layer: read those pages with OCR.
    missing = [i for i in pages if not has_cue_card(texts[i])]
    if missing:
        log.info("%s: reading %d Speaking pages with OCR", path.name, len(missing))
        for i, text in zip(missing, ocr(path, missing)):
            if has_cue_card(text):
                texts[i] = text
    cache.write_text(json.dumps(texts, ensure_ascii=False))

    tests, seen = [], set()
    for page in pages:
        test = await read_test(texts, page)
        task = test["part2"]["task"].strip().lower()
        if task.startswith("describe") and task not in seen:  # skips repeats, e.g. in sample answers
            seen.add(task)
            tests.append({"test": len(tests) + 1, **test})  # numbered in book order
    book = {"id": slug(path), "title": title(path), "file": path.name, "tests": tests}
    (books_dir() / f"{book['id']}.json").write_text(json.dumps(book, indent=1, ensure_ascii=False))
    return book


def load_books() -> list[dict]:
    if not books_dir().exists():
        return []
    paths = [p for p in books_dir().glob("*.json") if not p.name.endswith(".pages.json")]
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
