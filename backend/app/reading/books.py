"""Imports the Reading tests from your own IELTS books, and loads them.

    python -m app.reading.books "path/to/Cambridge IELTS 10.pdf" ...   (make books does every module)
    python -m app.reading.books --cached     the books imported before (no PDFs needed if their
                                             pages were saved as pictures once)

A Reading test is shown as text, like the computer-delivered test (content.py): each passage
beside its questions, each question with its own control. A group of questions that could not be
read for sure (a table, a diagram, OCR trouble) is shown as its printed picture, and a test whose
text could not be read at all as its printed pages. The answers are marked with the book's
answer key.

1. The page texts come from core/pages.py (cached by any earlier import). The Writing import
   (writing/books.py) must have run: each test's Reading pages are the ones before its Writing
   task, from "READING PASSAGE 1" (Academic) or "SECTION 1" (General Training) on.
2. Those pages are saved as pictures in data/private/books/<book>/reading/<page>.jpg, and read
   with OCR (positions kept, cached in <book>.reading-ocr.json) for their text. A line the OCR
   found but could not read is read again on its own (reread_lines).
3. The answer key comes from core/answer_keys.py. A test is kept only when its key has all 40
   answers read for sure (each agreed by two of three OCR readings, and no two-answer question
   printed over several lines): a wrong key would mark you wrongly.

A test whose text was also saved from a web page (core/web_tests.py, make web-tests) shows that
text, which is complete, in place of the OCR text: see with_web_text().

Everything is written to data/private/books/<book>.reading.json (git-ignored). Never commit or
share these files: the books are copyrighted.
"""
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

from ..core import answer_keys, pages, web_tests
from . import content

log = logging.getLogger("ielts.reading.books")

ACADEMIC_START = re.compile(r"READING\s*PASSAGE\s*[1Il]\b", re.I)
GENERAL_START = re.compile(r"(SECTION|PART)\s*(1|ONE)\b", re.I)
GENERAL_QUESTIONS = re.compile(r"Questions?\s*1\s*\W{1,2}\s*1[0-9]\b|spend\s*\d0\s*minutes\s*on\s*Questions\s*1\s*\W", re.I)
LISTENING = re.compile(r"listen|recording|you\s*will\s*hear", re.I)
# Where each passage (Academic) or section (General Training) starts.
PART_START = re.compile(r"(READING\s*PASSAGE|SECTION|PART)\s*([1-3Il]|ONE|TWO|THREE)\b", re.I)
PART_NUMBER = {"1": 1, "I": 1, "L": 1, "ONE": 1, "2": 2, "TWO": 2, "3": 3, "THREE": 3}


def folder(book_id: str) -> Path:
    return pages.books_dir() / book_id / "reading"


def general_start(text: str) -> bool:
    if not GENERAL_START.search(text):
        return False
    top = "\n".join(text.splitlines()[:3])
    return bool(GENERAL_QUESTIONS.search(text) and not LISTENING.search(text)
                or re.search(r"\bREADING\b", top)
                or re.search(r"Reading\s*and\s*Writ", text, re.I) and re.search(r"Test\s*[AB]\b", text))


def reading_pages(texts: list[str], writing_tests: list[dict]) -> dict[str, list[int]]:
    """Each test's Reading pages (0-based): from its first passage to the page before its Writing
    task (writing.json numbers pages from 1)."""
    found, after = {}, 0
    for test in writing_tests:
        end = test["page"] - 1
        starts = ([i for i in range(after, end) if ACADEMIC_START.search(texts[i])]
                  or [i for i in range(after, end) if general_start(texts[i])])
        if starts and 4 <= end - starts[0] <= 20:
            found[test["test"]] = list(range(starts[0], end))
        after = end + 1
    return found


def parts(texts: list[str], numbers: list[int]) -> list[dict]:
    """The page where each passage or section starts: [{"part": 1, "page": 17}, ...]."""
    found = {}
    for i in numbers:
        for m in PART_START.finditer(texts[i][:400]):
            n = PART_NUMBER.get(m.group(2).upper())
            if n and n not in found and (not found or n == max(found) + 1):
                found[n] = i
    return [{"part": n, "page": i} for n, i in sorted(found.items())]


def sections(found: list[list[int]], texts: list[str], part_pages: list[dict]) -> list[list[int]]:
    """The questions of each part, [[1, 13], [14, 26], [27, 40]]: from the key's headings (when
    they chain from 1 to 40), else from the first "Questions 1-13" on each part's first page."""
    def chain(start: int, left: list[list[int]]) -> list[list[int]] | None:
        if start == 41:
            return []
        for s in left:
            if s[0] == start and (rest := chain(s[1] + 1, left)) is not None:
                return [s, *rest]
        return None

    if (found_chain := chain(1, found)) and len(found_chain) == 3:
        return found_chain
    ranges = []
    for part in part_pages:
        m = re.search(r"Questions?\s*(\d{1,2})\s*\W{1,3}\s*(\d{1,2})", texts[part["page"]])
        ranges.append([int(m.group(1)), int(m.group(2))] if m else None)
    return ranges if None not in ranges and (chain(1, ranges) or []) == ranges and len(ranges) == 3 else []


OCR_WIDTH = 1600  # the passages' small print needs more pixels than the answer keys


def page_ocr(path: Path, book_id: str, numbers: list[int]) -> dict[int, dict]:
    """The pages' OCR with positions (pages.ocr_boxes), cached in <book>.reading-ocr.json."""
    cache = pages.books_dir() / f"{book_id}.reading-ocr.json"
    found = json.loads(cache.read_text()) if cache.exists() else {}
    missing = [i for i in numbers if str(i) not in found]
    if missing and path.exists():
        found.update({str(i): v for i, v in pages.ocr_boxes(path, missing, OCR_WIDTH).items()})
    unchecked = [i for i in numbers if str(i) in found and found[str(i)].get("reread") != REREAD]
    if unchecked:
        reread_lines(book_id, {i: found[str(i)] for i in unchecked})
    if missing and path.exists() or unchecked:
        cache.write_text(json.dumps(found, ensure_ascii=False))
    return {i: found[str(i)] for i in numbers if str(i) in found}


SPACED_OUT = re.compile(r"\S\s{3,}\S")
SHORT_WORDS = set("a i of to in is it on as at by an or be we he if so no do up my us am me".split())
REREAD = 2  # the version of the check below (a page checked by an older one is checked again)


def garbled(text: str) -> bool:
    """Not a line of print: letters scattered with spaces between ("b d    a tg      nn")."""
    words = text.split()
    odd = [w for w in words if len(w.strip(".,;:'\"()-")) <= 2 and not w.isdigit()
           and w.lower().strip(".,;:'\"()") not in SHORT_WORDS and not re.fullmatch(r"[A-Z][.,]?", w)]
    return bool(SPACED_OUT.search(text)) or len(words) >= 5 and len(odd) >= 0.4 * len(words)


def unread(page: dict) -> list[list]:
    """The page's lines the OCR found but could not read: a long line that is garbled, or holds
    a fraction of the letters its length does."""
    import statistics
    boxes = page["boxes"]
    if len(boxes) < 5:
        return []
    line = statistics.median(b[3] - b[1] for b in boxes)

    def density(b) -> float:  # letters per line-height of width: the same for small and large print
        return len(b[4].replace(" ", "")) * (b[3] - b[1]) / (b[2] - b[0])

    long = [b for b in boxes if b[2] - b[0] > 8 * line]
    if len(long) < 3:
        return []
    usual = statistics.median(map(density, long))
    return [b for b in long if density(b) < 0.5 * usual or garbled(b[4])]


def reread_lines(book_id: str, found: dict[int, dict]) -> None:
    """Reads again, each on its own from the page's picture, the lines the OCR could not read
    (see unread()); on its own a line usually reads well, if not at the first try then with more
    of the page around it or enlarged. Marks the pages as checked."""
    engine = None
    for number, page in found.items():
        picture = folder(book_id) / f"{number}.jpg"
        lines = unread(page) if picture.exists() else []
        if lines:
            import numpy as np
            from PIL import Image
            from rapidocr import RapidOCR
            engine = engine or RapidOCR(params={"Global.log_level": "warning"})
            with Image.open(picture) as opened:
                image = opened.convert("RGB")
            k = image.width / page["size"][0]
            for b in lines:
                for pad, scale in ((6, 1), (14, 1), (6, 1.6), (14, 2.2)):
                    part = image.crop((int((b[0] - 12) * k), int((b[1] - pad) * k),
                                       int((b[2] + 12) * k), int((b[3] + pad) * k)))
                    if scale != 1:
                        part = part.resize((int(part.width * scale), int(part.height * scale)), Image.LANCZOS)
                    result = engine(np.array(part))
                    # the line itself, not a slice of the one above or below it
                    middle = part.height / 2
                    row = sorted((float(r[0][0]), t) for r, t in zip(result.boxes, result.txts)
                                 if float(r[0][1]) < middle < float(r[2][1])) if result.txts else []
                    text = " ".join(t for _, t in row)
                    if len(text.replace(" ", "")) > 1.3 * len(b[4].replace(" ", "")) and not garbled(text):
                        log.info("%s page %d: read again %r as %r", book_id, number, b[4], text)
                        b[4] = text
                        break
        page["reread"] = REREAD


async def import_book(path: Path) -> dict:
    book_id = pages.slug(path)
    writing = pages.books_dir() / f"{book_id}.writing.json"
    if not writing.exists():
        raise FileNotFoundError(f"{book_id}: import the book's Writing first (make books)")
    texts = pages.read(path)
    writing_tests = json.loads(writing.read_text())["tests"]
    keys = await answer_keys.import_keys(path, texts)
    tests = []
    for test, numbers in reading_pages(texts, writing_tests).items():
        key = keys["tests"].get(test, {}).get("reading")
        if key is None or len(key["answers"]) < 40 or key.get("doubtful"):
            log.info("%s test %s: %s", book_id, test, "no answer key" if key is None
                     else "a two-answer question that could not be read for sure" if len(key["answers"]) == 40
                     else f"the answer key misses questions {sorted(set(map(str, range(1, 41))) - set(key['answers']), key=int)}")
            continue
        missing = [i for i in numbers if not (folder(book_id) / f"{i}.jpg").exists()]
        if missing:
            if not path.exists():
                log.info("%s test %s: its pages need the PDF once", book_id, test)
                continue
            await asyncio.to_thread(pages.render, path, missing, folder(book_id))
        kind = next(t["type"] for t in writing_tests if t["test"] == test)
        part_pages = parts(texts, numbers)
        part_questions = sections(key["sections"], texts, part_pages)
        ocr = await asyncio.to_thread(page_ocr, path, book_id, numbers)
        text = (content.build(ocr, part_pages, part_questions, key["answers"], key["any_order"])
                if len(ocr) == len(numbers) else None)
        if text and text.get("doubtful"):
            log.info("%s test %s: a key's letter is not one of its question's choices", book_id, test)
            continue
        if text and text["sections"] != part_questions:
            log.info("%s test %s: the parts' questions are %s (the key said %s)", book_id, test, text["sections"], part_questions)
            part_questions = text["sections"]
        if text is None:
            log.info("%s test %s: its text could not be read for sure: shown as printed pages", book_id, test)
        tests.append({"test": test, "kind": kind, "pages": numbers, "parts": part_pages,
                      "sections": part_questions, "key": key["answers"], "any_order": key["any_order"],
                      "content": text})
    speaking = pages.books_dir() / f"{book_id}.json"
    title = json.loads(speaking.read_text())["title"] if speaking.exists() else pages.title(path)
    book = {"id": book_id, "title": title, "file": path.name, "tests": tests}
    (pages.books_dir() / f"{book_id}.reading.json").write_text(json.dumps(book, ensure_ascii=False, indent=1))
    return book


def load_books() -> list[dict]:
    if not pages.books_dir().exists():
        return []
    found = [with_web_text(json.loads(p.read_text())) for p in pages.books_dir().glob("*.reading.json")]
    return sorted((b for b in found if b["tests"]), key=lambda b: b["title"])


def with_web_text(book: dict) -> dict:
    """The book's tests with the text saved from the web (core/web_tests.py), if any: it takes
    the place of the OCR text (the test keeps its printed pages, and its key from the book), and
    the tests OCR could not import are added, marked with the book's key if it was read for
    sure, else with the web page's answers."""
    web = web_tests.load(book["id"], "reading")
    if not web:
        return book
    keys = (answer_keys.load_keys(book["id"]) or {"tests": {}})["tests"]
    for found in web:
        content = found["content"]
        mine = next((t for t in book["tests"] if t["test"] == found["test"]), None)
        if mine is None:
            key = keys.get(found["test"], {}).get("reading")
            sure = key is not None and len(key["answers"]) == 40 and not key.get("doubtful")
            book["tests"].append({"test": found["test"], "kind": found["kind"], "pages": [], "parts": [],
                                  "sections": found["sections"],
                                  "key": web_tests.choosable(key["answers"], found) if sure else found["key"],
                                  "any_order": web_tests.merged(key["any_order"] if sure else [], found["any_order"]),
                                  "content": content})
            continue
        starts = [p["page"] for p in mine["parts"]] + [10 ** 9]
        if len(mine["parts"]) == len(content["parts"]):
            for i, part in enumerate(content["parts"]):
                part["pages"] = [n for n in mine["pages"] if starts[i] <= n < starts[i + 1]]
        mine.update(content=content, sections=found["sections"], key=web_tests.choosable(mine["key"], found),
                    any_order=web_tests.merged(mine["any_order"], found["any_order"]))
    book["tests"].sort(key=lambda t: (t["kind"], t["test"]))
    return book


def find_test(book_id: str, test: str) -> dict | None:
    """One test, with its book's id and title."""
    for book in load_books():
        if book["id"] == book_id:
            found = next((t for t in book["tests"] if t["test"] == test), None)
            return found and {**found, "book": book["id"], "book_title": book["title"]}
    return None


def crop(book_id: str, page: int, box: list[float]) -> bytes | None:
    """A part of a page's picture (a group of questions as printed); `box` in fractions of the page."""
    picture = page_picture(book_id, page)
    if picture is None or len(box) != 4 or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        return None
    from io import BytesIO

    from PIL import Image
    with Image.open(picture) as image:
        w, h = image.size
        part = image.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)))
        out = BytesIO()
        part.save(out, "JPEG", quality=85)
    return out.getvalue()


def page_picture(book_id: str, page: int) -> Path | None:
    """A Reading page's picture, if it belongs to an imported test."""
    for book in load_books():
        if book["id"] == book_id and any(page in t["pages"] for t in book["tests"]):
            picture = folder(book_id) / f"{page}.jpg"
            return picture if picture.exists() else None
    return None


async def main(args: list[str]):
    if args == ["--cached"]:
        from ..writing.books import cached_books
        paths = cached_books()
    else:
        paths = [Path(p).expanduser() for p in args]
    for path in paths:
        try:
            book = await import_book(path)
        except Exception as e:  # one broken file should not stop the others
            print(f"{path.name}: failed ({type(e).__name__}: {e})")
            continue
        kinds = [t["kind"] for t in book["tests"]]
        print(f"{book['title']}: {kinds.count('academic')} Academic and {kinds.count('general')} "
              f"General Training Reading tests", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1:]))
