"""The Reading and Listening tests of your own books, as text from a web page that prints them.

OCR of a scanned book loses lines, tables and diagrams. A site that publishes the same tests as
web pages has all of it as clean text: the passages, every question, the Listening transcripts
and the answers. This module reads those pages for the books you imported (and only those), so
their tests are shown complete.

    python -m app.core.web_tests <the site's list of tests>      (make web-tests URL=...)
    python -m app.core.web_tests --cached                         parse again the pages saved before

It is never run for you: no address is built in, `make install` does not call it, and the app
does not fetch anything while it runs. Read the site's terms before you use it; most forbid
automated copying, and the tests are the publisher's. It asks for one page every few seconds
(WEB_TESTS_DELAY) and each page only once: the pages are kept in data/private/web/.

The pages it understands are laid out like ieltsvault.com/resources (parse_reading and
parse_listening say how). What it finds is written, git-ignored, next to the books:

    data/private/books/<book>.reading-web.json    {"source", "tests": [{"test", "kind", "slug",
                                                   "key", "any_order", "sections", "content"}]}
    data/private/books/<book>.listening-web.json  the same, each part with its "transcript"

reading/books.py shows a test with this text in place of the OCR text (the printed pages stay
one click away), and adds the tests of your books that OCR could not import.
"""
import json
import logging
import os
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

from . import pages
from .config import DATA_DIR

log = logging.getLogger("ielts.web_tests")

DELAY = float(os.environ.get("WEB_TESTS_DELAY", "3"))  # seconds between two requests
AGENT = "ielts-assistant (personal study import; one page every few seconds)"
SLUG = re.compile(r"\b([a-z0-9-]+?)-(\d{1,2})-(academic-reading|general-training-reading|listening)-test-(\d{1,2})\b")
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def cache_dir() -> Path:
    return DATA_DIR / "private" / "web"


# ---------------------------------------------------------------- which tests

def my_books() -> dict[int, list[str]]:
    """The books imported from your PDFs, by their number: {10: ["cambridge-ielts-10"],
    11: ["cambridge-ielts-11-ac", "cambridge-ielts-11-gt"]}."""
    found: dict[int, list[str]] = {}
    for path in sorted(pages.books_dir().glob("*.pages.json")):
        book_id = path.name.removesuffix(".pages.json")
        m = re.search(r"\d{1,2}", book_id)
        if m:
            found.setdefault(int(m.group(0)), []).append(book_id)
    return found


def book_for(ids: list[str], skill: str) -> str | None:
    """The book a test belongs to, when a number has two (Academic and General Training); None
    when you have only the other one (an Academic book has no General Training Reading). A book
    that says neither has both (the older ones), and every book has the Listening tests."""
    general = [i for i in ids if re.search(r"(^|-)(gt|general)(-|$)", i)]
    academic = [i for i in ids if re.search(r"(^|-)(ac|academic)(-|$)", i)]
    both = [i for i in ids if i not in general and i not in academic]
    if skill == "general-training-reading":
        return (general or both or [None])[0]
    if skill == "academic-reading":
        return (academic or both or [None])[0]
    return (both or academic or general)[0]


def wanted(index_html: str) -> list[dict]:
    """The tests on the site's list that belong to your books: [{"slug", "book", "skill",
    "test", "kind"}]. A book with two General Training tests calls them A and B."""
    books = my_books()
    found = {}
    for m in SLUG.finditer(index_html):
        series, number, skill, n = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        if series != "cambridge-ielts" or number not in books:
            continue
        book = book_for(books[number], skill)
        if book:
            found[m.group(0)] = {"slug": m.group(0), "book": book, "skill": skill, "n": n}
    per_book: dict[tuple, int] = {}
    for t in found.values():
        per_book[t["book"], t["skill"]] = max(per_book.get((t["book"], t["skill"]), 0), t["n"])
    for t in found.values():
        lettered = t["skill"] == "general-training-reading" and per_book[t["book"], t["skill"]] <= 2
        t["test"] = "AB"[t["n"] - 1] if lettered else str(t["n"])
        t["kind"] = {"academic-reading": "academic", "general-training-reading": "general"}.get(t["skill"], "")
    return sorted(found.values(), key=lambda t: (t["book"], t["skill"], t["n"]))


# ---------------------------------------------------------------- fetching

def fetch(index_url: str) -> list[dict]:
    """Saves the page of each wanted test (once) and returns the tests."""
    import httpx
    folder = cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": AGENT}, follow_redirects=True, timeout=30) as client:
        index = client.get(index_url)
        index.raise_for_status()
        (folder / "index.html").write_text(index.text)
        (folder / "source.txt").write_text(index_url)
        tests = wanted(index.text)
        missing = [t for t in tests if not (folder / f"{t['slug']}.html").exists()]
        print(f"{len(tests)} tests of your books on the list; {len(missing)} pages to fetch "
              f"(about {round(len(missing) * DELAY / 60) or 1} min)", flush=True)
        for t in missing:
            time.sleep(DELAY)
            skill = "listening" if t["skill"] == "listening" else "reading"
            url = urljoin(str(index.url), f"{urlsplit(str(index.url)).path.rstrip('/')}/{skill}/tests/{t['slug']}")
            try:
                page = client.get(url)
                page.raise_for_status()
            except httpx.HTTPError as e:
                print(f"{t['slug']}: not fetched ({e})", flush=True)
                continue
            (folder / f"{t['slug']}.html").write_text(page.text)
        fetch_images(client, str(index.url), tests)
    return tests


def image_path(src: str) -> str:
    """The picture's own address on the site ("/_next/image?url=%2Fimages%2Fa.png&w=..." is a
    resized copy of /images/a.png)."""
    query = parse_qs(urlsplit(src).query)
    return unquote(query["url"][0]) if query.get("url") else src


def image_name(src: str) -> str:
    """The file a picture is saved as in data/private/web/images/."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", urlsplit(image_path(src)).path.rsplit("/", 1)[-1])[-120:]


def image_file(name: str) -> Path | None:
    """A saved picture (a map, a plan or a diagram of a group of questions)."""
    path = cache_dir() / "images" / name
    return path if re.fullmatch(r"[A-Za-z0-9._-]+", name) and not name.startswith(".") and path.is_file() else None


def fetch_images(client, base: str, tests: list[dict]) -> None:
    """Saves the pictures the tests' questions need (maps, plans, diagrams), once."""
    folder = cache_dir() / "images"
    folder.mkdir(parents=True, exist_ok=True)
    for t in tests:
        page = cache_dir() / f"{t['slug']}.html"
        if not page.exists():
            continue
        sections = [s for s in tree(page.read_text()).find("section") if (s.attrs.get("id") or "").startswith("section-")]
        for src in dict.fromkeys(i.attrs.get("src") or "" for s in sections for i in s.find("img")):
            if not src or (folder / image_name(src)).exists():
                continue
            time.sleep(DELAY)
            try:
                picture = client.get(urljoin(base, image_path(src)))
                picture.raise_for_status()
            except Exception as e:  # a missing picture: its group says so
                print(f"{t['slug']}: picture {image_name(src)} not fetched ({e})", flush=True)
                continue
            (folder / image_name(src)).write_bytes(picture.content)


# ---------------------------------------------------------------- the page as a tree

VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr"}
SKIPPED = {"script", "style", "svg", "button"}


class Node:
    def __init__(self, tag: str, attrs: dict, parent: "Node | None" = None):
        self.tag, self.attrs, self.parent, self.kids = tag, attrs, parent, []

    @property
    def elements(self) -> list["Node"]:
        return [k for k in self.kids if isinstance(k, Node)]

    def text(self) -> str:
        """Its text, the spaces tidied ("( 9 ) …" stays as the page has it)."""
        return re.sub(r"[ \t\r\f\v]+", " ", self.raw()).strip()

    def raw(self) -> str:
        return "".join(k if isinstance(k, str) else ("\n" if k.tag == "br" else k.raw()) for k in self.kids)

    def find(self, tag: str | None = None, **attrs):
        for k in self.elements:
            if (tag is None or k.tag == tag) and all(k.attrs.get(a) == v for a, v in attrs.items()):
                yield k
            yield from k.find(tag, **attrs)

    def first(self, tag: str | None = None, **attrs) -> "Node | None":
        return next(self.find(tag, **attrs), None)

    def has_class(self, name: str) -> bool:
        return name in (self.attrs.get("class") or "").split()


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.at = self.root
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIPPED:
            self.skip += 1
        if self.skip:
            return
        node = Node(tag, dict(attrs), self.at)
        self.at.kids.append(node)
        if tag not in VOID:
            self.at = node

    def handle_endtag(self, tag):
        if tag in SKIPPED:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        node = self.at
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.at = node.parent

    def handle_data(self, data):
        if not self.skip:
            self.at.kids.append(data)


def tree(html: str) -> Node:
    parser = _Tree()
    parser.feed(html)
    return parser.root


# ---------------------------------------------------------------- a page's questions

HEADING = re.compile(r"^Questions?\s*(\d{1,2})(?:\s*(?:[-–—]|and|to)\s*(\d{1,2}))?", re.I)
NUMBER = re.compile(r"^(\d{1,2})\s*\.?$")
GAP = re.compile(r"\(\s*(\d{1,2})\s*\)\s*(?:[…_.]\s*){1,}|(?<![\d.,£$/])\b(\d{1,2})\s*(?:…\s*|_{3,}\s*|\.{4,}\s*){1,}")
DOTS = re.compile(r"(?:…\s*|_{3,}\s*|\.{4,}\s*)+")
ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv"]
ROMAN_ITEM = re.compile(r"^\(?(xv|xiv|xiii|xii|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i)\)?[.)]?\s+(\S.*)$", re.I | re.S)
LETTER_ITEM = re.compile(r"^([A-Z])[.)]?\s+(\S.*)$", re.S)
LEGEND = {"TRUE", "FALSE", "NOT GIVEN", "YES", "NO"}
COUNT_WORDS = {"TWO": 2, "THREE": 3, "FOUR": 4}
LETTER_RANGE = re.compile(r"\b([A-Z])\s*[-–—]\s*([A-Z])\b")
PARAGRAPH_LETTER = re.compile(r"^\[([A-Z])\]\s*")


class Unread(Exception):
    """A page that is not laid out as expected: its test is left out."""


def _squeezed(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _number_of(p: Node) -> int | None:
    """The question a paragraph starts with (its number in a span of its own)."""
    first = p.elements[0] if p.elements else None
    if first is None or first.tag != "span" or (p.kids and isinstance(p.kids[0], str) and p.kids[0].strip()):
        return None
    m = NUMBER.match(first.text())
    return int(m.group(1)) if m else None


def _after_first(p: Node) -> str:
    """A paragraph's text after its first element (the number or the letter)."""
    first = p.elements[0]
    rest = Node("p", {})
    rest.kids = p.kids[p.kids.index(first) + 1:]
    return _one_line(rest.text())


def _option(p: Node) -> dict | None:
    """"<strong>A</strong> text": an option."""
    first = p.elements[0] if p.elements else None
    if first is not None and first.tag == "strong" and re.fullmatch(r"[A-Z]", first.text()):
        return {"letter": first.text(), "text": _after_first(p)}
    return None


def _pieces(text: str, first: int, last: int) -> list:
    """Text and gaps: "Restored ( 9 ) ……… of 2001" → ["Restored ", 9, " of 2001"]."""
    out, at = [], 0
    for m in GAP.finditer(text):
        q = int(m.group(1) or m.group(2))
        if not first <= q <= last:
            continue
        before = text[at:m.start()]
        if before:
            out.append(before)
        out.append(q)
        at = m.end()
        if text[at:at + 1].strip() and not text[at:at + 1] in ".,;:)":
            out.append(" ")
    rest = text[at:]
    if rest.strip() or not out:
        out.append(rest)
    return [p if isinstance(p, int) else re.sub(r"[ \t]+", " ", p) for p in out]


def _blocks(node: Node) -> list[Node]:
    """The lines of a block of notes: its innermost paragraphs, list items and headings."""
    line_tags = {"p", "li", "h2", "h3", "h4", "dt", "dd"}
    found = [n for n in node.find() if n.tag in line_tags and not any(k.tag in line_tags for k in n.find())]
    return found or [node]


def _table(table: Node, first: int, last: int) -> list[list[dict]]:
    rows = []
    for tr in table.find("tr"):
        cells = [{"head": c.tag == "th", "span": int(c.attrs.get("colspan") or 1),
                  "pieces": _pieces(_one_line(c.text()), first, last)} for c in tr.elements if c.tag in ("td", "th")]
        if cells:
            rows.append(cells)
    return rows


def _gaps_in(lines: list[list]) -> list[int]:
    return [p for line in lines for p in line if isinstance(p, int)]


BLANK = re.compile(r"(?:…\s*){2,}|_{3,}\s*")


def _repair(lines: list[list], numbers: list[int]) -> None:
    """Mends, in place, the gaps a page numbers wrongly: a number printed twice where the next
    one is missing ("(11) ... (11) ... (13)": the second is 12; with no number missing it is the
    second blank of one question, left as dots), and a blank without its number where one is
    missing."""
    if _gaps_in(lines) == numbers:
        return
    places = [(line, i) for line in lines for i, p in enumerate(line) if isinstance(p, int)]
    expected = numbers[0]
    for k, (line, i) in enumerate(places):
        g = line[i]
        if g == expected - 1 and k:
            following = places[k + 1][0][places[k + 1][1]] if k + 1 < len(places) else numbers[-1] + 1
            if following > expected:
                line[i] = expected
                expected += 1
            else:
                line[i] = " … "
        elif g >= expected:
            expected = g + 1
    if _gaps_in(lines) == numbers:
        return
    # blanks without a number, where the numbers skip one
    for line in lines:
        split = []
        for p in line:
            if isinstance(p, int):
                split.append(p)
                continue
            at = 0
            for m in BLANK.finditer(p):
                split += [p[at:m.start()], None]
                at = m.end()
            split.append(p[at:])
        line[:] = [p for p in split if p != ""]
    flat = [(line, i) for line in lines for i, p in enumerate(line) if p is None or isinstance(p, int)]
    expected = numbers[0]
    for k, (line, i) in enumerate(flat):
        if isinstance(line[i], int):
            expected = line[i] + 1
            continue
        following = next((l[j] for l, j in flat[k + 1:] if isinstance(l[j], int)), numbers[-1] + 1)
        if expected < following:
            line[i] = expected
            expected += 1
        else:
            line[i] = " … "


def parse_group(div: Node, answers: dict[str, str]) -> dict:
    """One group of questions ("Questions 1–5", its instructions, then what the page shows) as
    reading/content.py describes it, the answers of the page turned into the group's letters."""
    els = div.elements
    m = HEADING.match(els[0].text()) if els else None
    if m is None:
        raise Unread("a group without its heading")
    first, last = int(m.group(1)), int(m.group(2) or m.group(1))
    numbers = list(range(first, last + 1))
    instructions, body = [], []
    for e in els[1:]:
        if e.tag == "p" and not body and _number_of(e) is None:
            instructions.append(_one_line(e.text()))
        else:
            body.append(e)
    said = " ".join(instructions)

    questions, listed, extra, images, table, note_blocks = [], [], [], [], None, []
    for block in body:
        if block.tag == "img":
            images.append(block.attrs.get("src") or "")
            continue
        images += [i.attrs.get("src") or "" for i in block.find("img")]
        found_table = block if block.tag == "table" else block.first("table")
        if found_table is not None:
            table = _table(found_table, first, last)
            continue
        numbered = [p for p in ([block] if block.tag == "p" else block.find("p")) if _number_of(p) is not None]
        if numbered:
            for p in numbered:
                siblings = p.parent.elements
                options = []
                for sibling in siblings[siblings.index(p) + 1:]:
                    if sibling.tag == "p" and _number_of(sibling) is not None:
                        break
                    options += [o for o in map(_option, [sibling] if sibling.tag == "p" else sibling.find("p")) if o]
                questions.append({"q": _number_of(p), "text": _after_first(p), "options": options})
            continue
        paragraphs = _blocks(block)
        strongs = [p.elements[0].text().upper() for p in paragraphs if p.elements and p.elements[0].tag == "strong"]
        if strongs and set(strongs) <= LEGEND:
            continue  # "TRUE if the statement agrees ...": the buttons say it
        options = [o for o in map(_option, paragraphs) if o]
        if not options:
            texts = [_one_line(p.text()) for p in paragraphs]
            romans = [ROMAN_ITEM.match(t) for t in texts]
            if sum(map(bool, romans)) >= 3:
                options = [{"letter": r.group(1).lower(), "text": _one_line(r.group(2))} for r in romans if r]
            elif not GAP.search(block.text()):
                letters = [LETTER_ITEM.match(t) for t in texts]
                if sum(map(bool, letters)) >= 3 and [l.group(1) for l in letters if l] == list(LETTERS[:sum(map(bool, letters))]):
                    options = [{"letter": l.group(1), "text": _one_line(l.group(2))} for l in letters if l]
        if options and not listed:
            listed = options
            titles = [_one_line(p.text()) for p in paragraphs if _option(p) is None
                      and not ROMAN_ITEM.match(_one_line(p.text())) and not LETTER_ITEM.match(_one_line(p.text()))]
            extra += [t for t in titles if t]
            continue
        note_blocks.append(block)

    notes = [_pieces(_one_line(p.text()), first, last) for block in note_blocks for p in _blocks(block)]
    notes = [line for line in notes if any(isinstance(p, int) or p.strip() for p in line)]
    group = {"first": first, "last": last, "type": "gaps", "printed": False, "instructions": instructions,
             "options": [], "questions": [], "pictures": []}
    if images:
        group["images"] = [image_name(src) for src in images if src]
    given = [answers.get(str(q), "") for q in numbers]
    upper = {a.upper() for a in given}

    def letters_of(options: list[dict], per_question: dict[int, list[dict]] | None = None) -> None:
        """Turns the page's answers (an option's text, or its letter) into letters."""
        for q in numbers:
            choices = (per_question or {}).get(q) or options
            answer = answers.get(str(q), "")
            hit = [o["letter"] for o in choices if o["text"] and _squeezed(o["text"]) == _squeezed(answer)]
            hit = hit or [o["letter"] for o in choices if o["letter"].lower() == answer.strip().lower()]
            hit = hit or [o["letter"] for o in choices if o["text"] and _squeezed(answer)
                          and (_squeezed(o["text"]).startswith(_squeezed(answer)) or _squeezed(answer).startswith(_squeezed(o["text"])))]
            if len(hit) != 1:
                raise Unread(f"question {q}: its answer is not one of its options")
            answers[str(q)] = hit[0]

    asked = [q["q"] for q in questions]
    if table is not None:
        _repair([c["pieces"] for row in table for c in row], numbers)
        in_table = _gaps_in([c["pieces"] for row in table for c in row])
        if in_table == numbers and not questions:
            return {**group, "type": "table", "table": table}
        if not questions and not in_table and len(table) > 1:
            # questions as rows of a table: the first cell is the number
            rows = [(NUMBER.match(_one_line("".join(p for p in row[0]["pieces"] if isinstance(p, str)))), row) for row in table]
            rows = [(int(n.group(1)), row) for n, row in rows if n]
            if [q for q, _ in rows] == numbers:
                questions = [{"q": q, "text": " ".join(_one_line("".join(p for p in c["pieces"] if isinstance(p, str)))
                                                      for c in row[1:]).strip(), "options": []} for q, row in rows]
                asked = numbers
                table = None
        if table is not None and not questions:
            raise Unread(f"questions {first}-{last}: a table whose gaps are {in_table}")
    if asked and asked != numbers:
        raise Unread(f"questions {first}-{last}: found {asked}")

    if questions:
        own = [q["options"] for q in questions]
        same = all(own) and all([o["letter"] for o in opts] == [o["letter"] for o in own[0]]
                                and [o["text"] for o in opts] == [o["text"] for o in own[0]] for opts in own)
        count = next((n for word, n in COUNT_WORDS.items() if re.search(rf"\b{word}\b", said)), 0)
        if upper <= LEGEND and not all(own):
            kind = "ynng" if upper & {"YES", "NO"} or re.search(r"\bYES\b", said) and not upper & {"TRUE", "FALSE"} else "tfng"
            for q in numbers:
                answers[str(q)] = answers[str(q)].upper()
            return {**group, "type": kind, "questions": [{"q": q["q"], "text": q["text"]} for q in questions]}
        if same and count == len(numbers) and len(own[0]) > count:
            letters_of(own[0])
            stem = next((i for i in reversed(instructions) if i.endswith("?")), "")
            return {**group, "type": "multi", "stem": stem, "options": own[0], "any_order": numbers,
                    "instructions": [i for i in instructions if i != stem]}
        if same and (len(own[0]) > 4 or len(questions) > 1 and re.search(r"\b(match|ending|classify|which\s+(person|group|section|paragraph))", said, re.I)):
            letters_of(own[0])
            return {**group, "type": "match", "options": own[0],
                    "questions": [{"q": q["q"], "text": q["text"]} for q in questions]}
        if all(own):
            letters_of([], {q["q"]: q["options"] for q in questions})
            return {**group, "type": "choice", "questions": questions}
        if any(own):
            raise Unread(f"questions {first}-{last}: some without their options")
        plain = [{"q": q["q"], "text": q["text"]} for q in questions]
        if listed:
            letters_of(listed)
            return {**group, "type": "match", "options": listed, "questions": plain,
                    "instructions": instructions + extra}
        romans = [a.strip().lower() for a in given]
        if all(a in ROMAN for a in romans) and re.search(r"heading", said, re.I):
            raise Unread(f"questions {first}-{last}: the list of headings is missing")
        if all(re.fullmatch(r"[A-Za-z]", a.strip()) for a in given):
            # a letter for each question, the letters being paragraphs or things on a map
            ranges = [LETTER_RANGE.search(i) for i in instructions]
            stop = max([r.group(2) for r in ranges if r and r.group(1) == "A"] + [a.strip().upper() for a in given])
            for q in numbers:
                answers[str(q)] = answers[str(q)].strip().upper()
            return {**group, "type": "match", "questions": plain,
                    "options": [{"letter": c, "text": ""} for c in LETTERS[:LETTERS.index(stop) + 1]]}
        for q in plain:
            q["text"] = DOTS.sub(" … ", GAP.sub(" … ", q["text"])).strip()
        return {**group, "questions": plain}

    _repair(notes, numbers)
    found = _gaps_in(notes)
    if found != numbers:
        raise Unread(f"questions {first}-{last}: the gaps found are {found}")
    if listed:  # a summary completed with words from a box: still typed (the letter or the word)
        group["options"], group["instructions"] = listed, instructions + extra
    return {**group, "type": "notes", "notes": notes}


def parse_answers(root: Node) -> dict[str, str]:
    """The page's answers, {"1": "False", ...}."""
    key = root.first("div", id="answer-key")
    found = {}
    for p in key.find("p") if key is not None else []:
        first = p.elements[0] if p.elements else None
        if first is not None and first.tag == "span" and NUMBER.match(first.text()) and p.parent.tag == "div":
            found.setdefault(NUMBER.match(first.text()).group(1), _after_first(p))
    return found


def _passage(nodes: list[Node]) -> list[dict]:
    """A part's text: its titles and paragraphs ("[B] ..." is paragraph B)."""
    blocks = []
    for node in nodes:
        for p in ([node] if node.tag == "p" else _blocks(node)):
            text = p.text().strip()
            if not text:
                continue
            title = p.has_class("text-center") or p.has_class("font-bold") or (
                len(p.elements) == 1 and p.elements[0].tag == "strong" and p.elements[0].text() == _one_line(text))
            letter = PARAGRAPH_LETTER.match(text)
            if letter:
                text = text[letter.end():]
            # a paragraph's own line breaks are kept (addresses, lists, the lines of a notice)
            text = "\n".join(filter(None, map(_one_line, text.split("\n"))))
            blocks.append({"kind": "title" if title else "text", "text": text, "letter": letter.group(1) if letter else None})
    return blocks


def parse_test(html: str, skill: str) -> dict:
    """A test's page: {"key", "any_order", "sections", "content": {"parts": [...]}} (the parts as
    reading/content.py describes them; a Listening part has its "transcript" too).

    The page is: a <section id="section-N"> for each part, holding its title, its text (Reading)
    and a <div> for each group of questions (parse_group); then <div id="answer-key"> with the
    answers, and for Listening the transcripts ("Part 1" and its paragraphs)."""
    root = tree(html)
    answers = parse_answers(root)
    sections = [s for s in root.find("section") if re.fullmatch(r"section-\d+", s.attrs.get("id") or "")]
    expected = 4 if skill == "listening" else 3
    if len(sections) != expected or sorted(answers, key=int) != [str(q) for q in range(1, 41)]:
        raise Unread(f"{len(sections)} parts and {len(answers)} answers")
    parts, any_order = [], []
    for i, section in enumerate(sections):
        text_nodes, groups = [], []
        for e in section.elements:
            head = e.elements[0] if e.tag == "div" and e.elements else None
            if head is not None and head.tag == "p" and HEADING.match(head.text()):
                group = parse_group(e, answers)
                if "any_order" in group:
                    any_order.append(group.pop("any_order"))
                groups.append(group)
            else:
                text_nodes.append(e)
        if not groups:
            raise Unread(f"part {i + 1} has no questions")
        parts.append({"part": i + 1, "first": groups[0]["first"], "last": groups[-1]["last"], "pages": [],
                      "intro": "", "passage": _passage(text_nodes), "groups": groups})
    covered = [q for part in parts for g in part["groups"] for q in range(g["first"], g["last"] + 1)]
    if covered != list(range(1, 41)):
        raise Unread(f"the groups cover {len(covered)} questions")
    if skill == "listening":
        scripts = {}
        for div in root.find("div"):
            head = div.elements[0] if div.elements else None
            m = re.fullmatch(r"(?:Part|Section)\s*(\d)", head.text()) if head is not None and head.tag == "p" else None
            if m and len(div.elements) > 1:
                scripts.setdefault(int(m.group(1)), [p.text().strip() for p in div.elements[1:] if p.text().strip()])
        for part in parts:
            part["transcript"] = scripts.get(part["part"], [])
    return {"key": answers, "any_order": any_order, "sections": [[p["first"], p["last"]] for p in parts],
            "content": {"parts": parts, "source": "web"}}


# ---------------------------------------------------------------- saving

def save(tests: list[dict]) -> dict[str, dict]:
    """Parses the saved pages and writes <book>.reading-web.json and <book>.listening-web.json;
    returns what was written, by file name. A page that is not understood, or a test without
    exactly 40 questions, is left out (and said)."""
    source_file = cache_dir() / "source.txt"
    source = source_file.read_text().strip() if source_file.exists() else ""
    books: dict[str, dict] = {}
    for t in tests:
        page = cache_dir() / f"{t['slug']}.html"
        if not page.exists():
            continue
        skill = "listening" if t["skill"] == "listening" else "reading"
        try:
            parsed = parse_test(page.read_text(), skill)
        except Unread as e:
            print(f"{t['slug']}: left out ({e})", flush=True)
            continue
        missing = [name for part in parsed["content"]["parts"] for g in part["groups"]
                   for name in g.get("images", []) if image_file(name) is None]
        if missing:
            print(f"{t['slug']}: left out (its picture {missing[0]} is missing)", flush=True)
            continue
        book_key = _book_key(t["book"], t["test"], skill)
        if book_key:
            from .answer_keys import accepted, squeezed
            differs = [q for q, a in parsed["key"].items() if squeezed(a) not in accepted(book_key["answers"].get(q, a))]
            if len(differs) > 8:  # another test, or a page full of slips
                print(f"{t['slug']}: left out ({len(differs)} of its answers are not your book's)", flush=True)
                continue
            parsed["differs"] = differs
        name = f"{t['book']}.{skill}-web.json"
        books.setdefault(name, {"id": t["book"], "source": source, "tests": []})["tests"].append(
            {"test": t["test"], "kind": t["kind"], "slug": t["slug"], **parsed})
    for name, book in books.items():
        (pages.books_dir() / name).write_text(json.dumps(book, ensure_ascii=False, indent=1))
    return books


def _book_key(book_id: str, test: str, skill: str) -> dict | None:
    """The key read from your book for this test, when it has all 40 answers for sure."""
    from .answer_keys import load_keys
    keys = load_keys(book_id)
    key = keys and keys["tests"].get(test, {}).get(skill)
    return key if key and len(key["answers"]) == 40 and not key.get("doubtful") else None


def load(book_id: str, skill: str) -> list[dict]:
    """The tests of a book saved from the web ("reading" or "listening"); [] if none."""
    path = pages.books_dir() / f"{book_id}.{skill}-web.json"
    return json.loads(path.read_text())["tests"] if path.exists() else []


def main(args: list[str]) -> None:
    if args == ["--cached"]:
        index = cache_dir() / "index.html"
        if not index.exists():
            sys.exit("No pages saved yet: run it with the address of the site's list of tests")
        tests = wanted(index.read_text())
    elif len(args) == 1 and args[0].startswith(("http://", "https://")):
        if not my_books():
            sys.exit("Import your books first (make books): only their tests are fetched")
        tests = fetch(args[0])
    else:
        sys.exit(__doc__)
    books = save(tests)
    for skill in ("reading", "listening"):
        found = sum(len(b["tests"]) for name, b in books.items() if name.endswith(f".{skill}-web.json"))
        asked = sum((t["skill"] == "listening") == (skill == "listening") for t in tests)
        print(f"{skill.capitalize()}: {found} of {asked} tests saved as text")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # not a line for every request
    main(sys.argv[1:])
