"""The answer keys of your own IELTS books (Listening and Reading), and marking answers with them.

The keys are printed in two or three columns ("1 FALSE", "2 TRUE", ...), which a page's plain
text mixes up, and most books are scanned. So:

1. The key pages are found in the page texts (core/pages.py) and read again with OCR with
   positions, three times at different sizes (cached in data/private/books/<book>.keys-ocr.json,
   so a second import needs no PDF).
2. lines() puts each page back in reading order: page-wide headings, then the columns one
   after the other, each line with its question number and answer.
3. parse() reads those lines in turn: the headings (TEST 2, LISTENING, ACADEMIC READING,
   Section 1, Questions 1-10), each question's answer as printed, and which questions may be
   answered in any order. OCR sometimes runs a column of numbers ("2345") or of letters
   ("CABF") together, or misses a number: those answers are numbered in order. (No LLM: a 9B
   model mislabelled tests and skipped whole sections.)
4. agreed() keeps each answer that two of the three readings agree on: OCR's slips differ from
   one size to another. A question without one is missing, and its test is left out.
5. accepted() turns a printed answer into the answers that count as correct: "4/four sides",
   "(musical) instruments", "talk // give a talk", "NOT Africa" and the books' notes.

Everything is written to data/private/books/<book>.keys.json (git-ignored):
{"tests": {"1": {"listening": {...}, "reading": {...}}}}, each {"kind": "academic" | "general" | "",
"answers": {"1": "FALSE", ...}, "any_order": [[11, 12]], "sections": [[1, 13], [14, 26], [27, 40]],
"guessed": [questions numbered by their order, as OCR missed the number], "doubtful": true when
a question has two answers printed over several lines (hard to number: such tests are left out)}.
"""
import asyncio
import itertools
import json
import logging
import re
import statistics
import unicodedata
from pathlib import Path

from . import pages

log = logging.getLogger("ielts.keys")

KEY_PAGE = re.compile(r"answer\s*key", re.I)
# A key page without its title: Reading answers in a column of numbers.
KEY_LIKE = re.compile(r"\b(TRUE|FALSE|NOT\s*GIVEN|YES|NO)\b")
# The Writing answers that follow the keys in the books.
AFTER_KEYS = re.compile(r"(model|sample)\W*answer", re.I)
MAX_KEY_PAGES = 26
# A question number (or "11&12", "11-13") at the start of a line, or a section's heading: where a column starts.
COLUMN_START = re.compile(r"^\d{1,2}(\s*(&|and|-|–)\s*\d{1,2})?\b|^(Section|Reading\s*Passage|Questions|Part)\b", re.I)
WATERMARK = re.compile(r"www\.|\.com\b", re.I)

# Headings of the key: "TEST 2" ("PRACTICE TEST 2"), "ACADEMIC READING", "LISTENING KEYS", and a
# section's "Section 2, Questions 11-20" / "Reading Passage 1, Questions 1-13".
TEST_HEADING = re.compile(r"^(?:PRACTICE\s*|GENERAL\s*TRAINING\s*)?TEST\s*(\d{1,2}|[A-D])\s*$", re.I)
SKILL_HEADING = re.compile(r"^(ACADEMIC\s*|GENERAL\s*TRAINING\s*)?:?\s*(LISTENING|READING)(\s*KEYS?)?\s*$", re.I)
SECTION_HEADING = re.compile(r"^(Section|Reading\s*Passage|Passage|Part)\b(.*?Questions?\s*(\d{1,2})\s*\W{1,3}\s*(\d{1,2}))?",
                             re.I)
SCORES = re.compile(r"^If\s*you\s*score", re.I)  # the advice after each key: not answers
RANGE = re.compile(r"^\d{1,2}\s*[-–]\s*\d{1,2}(\s+\d{1,2}\s*[-–]\s*\d{1,2})*$")  # "0-11  12-26"
GROUP = re.compile(r"^(\d{1,2})\s*(?:&|and|,|-|–)\s*(\d{1,2})\b\s*(.*)$", re.I)
NUMBERED = re.compile(r"^(\d{1,2})\b(?![/:])\s*(.*)$")  # not "10/ten times", an answer
EITHER = re.compile(r"\b(in\s*)?(either|any)\s*order\b", re.I)
# The advice printed under each key ("you may get an acceptable score under examination conditions").
ADVICE = re.compile(r"\b(you|score|scores|examination|conditions|recommend|acceptable|institutions|different|"
                    r"practice|lessons|improving|unlikely|likely|before|remember)\b", re.I)
TRAILING_NOTE = re.compile(r"\s+(in|any|either|order)$", re.I)  # "11 E in" / "12 F any" / "13 H order"


def tidied(answer: str) -> str | None:
    """An answer as printed, without what OCR ran into it: a page header ("C Reading"), the advice
    under the key, the books' notes ("BOTH REQUIRED FOR ONE MARK", "in either order"); "∥" is
    "//", and "!" in a numeral is "i" ("vi!"). None when what is left does not look like an answer:
    then the key misses that question, and its test is left out rather than marked wrongly."""
    a = answer.replace("∥", "//")
    a = re.sub(r"\s+(Reading|Listening)$", "", a)
    a = re.sub(r"\s+(that\s+)?you\b.*$", "", a)
    a = re.sub(r"\bBOTH\s*(REQUIRED\s*)?FOR\s*ONE\s*M\s*A\s*R\s*K\b,?", "", a, flags=re.I)
    a = re.sub(r"\b(IN\s+)?\w*TH\w*\s+ORDER\b", "", a, flags=re.I)  # "either order", OCR slips included
    a = a.strip(" ;,.")
    if re.fullmatch(r"[ivx!|]+", a):
        a = a.replace("!", "i").replace("|", "i")
    plain = unicodedata.normalize("NFKD", a).encode("ascii", "ignore").decode()
    if plain != a and re.fullmatch(r"[ivxn]+", plain):
        return None  # a numeral OCR misread ("viñ")
    if not a or plain != a and not re.fullmatch(r"[\w\s()/.,'£$%-]+", plain) or re.search(r"[!|\[\]{}]|//\s*$", a):
        return None
    return a


def key_pages(texts: list[str]) -> list[int]:
    """The answer key's pages: in the second half of the book, from the first page titled "Answer
    key" (or looking like one) up to the model and sample answers for Writing that follow."""
    n = len(texts)
    found = [i for i in range(n // 2, n)
             if KEY_PAGE.search(texts[i]) or (re.search(r"READING", texts[i]) and KEY_LIKE.search(texts[i])
                                              and len(re.findall(r"\n\s*\d{1,2}\s*\n", texts[i])) > 5)]
    if not found:
        return []
    run = []
    for i in range(found[0], min(n, found[0] + MAX_KEY_PAGES)):
        if AFTER_KEYS.search(texts[i]) and not KEY_PAGE.search(texts[i]):
            break
        run.append(i)
    return run


def clean(text: str) -> str:
    """OCR text without full-width forms and the Chinese watermarks of some scans."""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"[　-鿿가-힯]+", "", text).strip()


def lines(page: dict) -> list[str]:
    """A key page in reading order: page-wide lines (headings), then each column top to bottom,
    one line per row ("1  FALSE"). A box taller than a line (OCR read a column of numbers or
    letters as one) is its own line, placed where it starts."""
    width, height = page["size"]
    boxes = [[*b[:4], clean(b[4])] for b in page["boxes"]]
    boxes = [b for b in boxes if b[4] and not WATERMARK.search(b[4]) and height * 0.03 < b[1] and b[3] < height * 0.96]
    if not boxes:
        return []
    line_height = statistics.median(b[3] - b[1] for b in boxes)
    # a big slanted watermark: taller and much wider than a line (a column OCR ran together is narrow)
    boxes = [b for b in boxes if not (b[3] - b[1] > 2.5 * line_height and b[2] - b[0] > 4 * line_height)]

    def tall(box) -> bool:
        return box[3] - box[1] > 1.7 * line_height

    columns, previous = [], None
    for x in sorted(b[0] for b in boxes if COLUMN_START.match(b[4])):
        if previous is None or x - previous > width * 0.08:  # a gap: the next column
            columns.append(x)
        previous = x
    columns = columns or [0]

    def column(box) -> int:
        return max([i for i, x in enumerate(columns) if box[0] >= x - width * 0.02], default=0)

    wide = [b for b in boxes if b[2] - b[0] > width * 0.5 or TEST_HEADING.match(b[4]) or SKILL_HEADING.match(b[4])]
    cuts = [0, *sorted(b[1] for b in wide), height + 1]
    out = []
    for top, bottom in itertools.pairwise(cuts):
        out += [b[4] for b in wide if b[1] == top]
        for c in range(len(columns)):
            rows: list[list] = []
            inside = (b for b in boxes if b not in wide and column(b) == c and top <= b[1] < bottom)
            for b in sorted(inside, key=lambda b: b[1] if tall(b) else (b[1] + b[3]) / 2):
                first = rows[-1][0] if rows else None
                if first and not tall(b) and not tall(first) and first[1] <= (b[1] + b[3]) / 2 <= first[3]:
                    rows[-1].append(b)
                else:
                    rows.append([b])
            out += ["  ".join(b[4] for b in sorted(row, key=lambda b: b[0])) for row in rows]
    return out


class _Key:
    """One test's key for one skill, filled line by line."""

    def __init__(self):
        self.kind = ""
        self.answers: dict[int, str] = {}
        self.guessed: set[int] = set()  # numbered by order: OCR missed the number, or it wraps
        self.any_order: list[list[int]] = []
        self.queue: list[int] = []  # numbers read before their answers
        self.last = 0
        self.noted: list[int] = []  # "11 E in" / "12 F any" / "13 H order": one group
        self.sections: list[list[int]] = []  # [[1, 13], [14, 26], [27, 40]]: the questions of each part
        self.doubtful = False  # a question with two answers for one mark, printed over several lines

    def give(self, q: int, answer: str, guessed: bool = False):
        if q in self.guessed and not guessed:
            # the number was there after all: the guess was the rest of the answer before
            if q - 1 in self.answers:
                self.answers[q - 1] += " " + self.answers[q]
            del self.answers[q]
            self.guessed.discard(q)
        if q in self.answers or not 1 <= q <= 40:
            return
        answer = re.sub(r"\s*\b(Questions?|Section|Reading\s*Passage)\s*\d.*$", "", answer).strip()
        if not answer:
            return
        self.answers[q] = answer
        if guessed:
            self.guessed.add(q)
        self.last = q

    def continues(self, text: str) -> bool:
        """The line is the rest of the last answer (a long answer wraps)."""
        before = self.answers.get(self.last, "")
        return bool(before) and (before.count("(") > before.count(")") or text.startswith(("/", ")"))
                                 or re.search(r"(/|\band|\bor|,)$", before) is not None)

    def text(self, line: str):
        """An answer line without its number."""
        line = re.sub(r"\s*\b(Questions?|Section|Reading\s*Passage)\s*\d.*$", "", line).strip()
        if not line or len(ADVICE.findall(line)) >= 2 or (len(line.split()) > 6 and not self.continues(line)):
            return  # a heading run into the line, or a sentence of advice: not an answer
        if self.queue:
            if len(self.queue) > 1 and re.fullmatch(r"[A-L]{2,}", line) and len(line) <= len(self.queue):
                for letter in line:  # OCR ran a column of letters together
                    self.give(self.queue.pop(0), letter)
                return
            self.give(self.queue.pop(0), line)
        elif self.continues(line):
            self.answers[self.last] += " " + line
        elif 0 < self.last < 40:  # never before the first number: a note under the heading
            self.give(self.last + 1, line, guessed=True)

    def numbers(self, digits: str):
        """A column of numbers OCR ran together: "2345" after 1 is 2, 3, 4, 5."""
        n, rest, found = self.last + 1, digits, []
        while rest.startswith(str(n)):
            found.append(n)
            rest = rest[len(str(n)):]
            n += 1
        self.queue = found if found and not rest else []

    def close_note(self):
        if len(self.noted) > 1:
            self.any_order.append(self.noted)
        self.noted = []


def parse(page_lines: list[list[str]]) -> dict[str, dict]:
    """The keys in a book's key pages (each page's lines, see lines()), by test and skill."""
    tests: dict[str, dict[str, _Key]] = {}
    test, key, skipping = "", None, False
    for line in (line.strip() for page in page_lines for line in page):
        if m := TEST_HEADING.match(line):
            test, key, skipping = m.group(1).upper(), None, False
            if re.match(r"GENERAL", line, re.I):  # "GENERAL TRAINING TEST A": a Reading test only
                key = tests.setdefault(test, {}).setdefault("reading", _Key())
                key.kind = "general"
            continue
        if m := SKILL_HEADING.match(line):
            skipping = False
            if test:
                key = tests.setdefault(test, {}).setdefault(m.group(2).lower(), _Key())
                if m.group(1):
                    key.kind = "general" if m.group(1).strip().upper().startswith("G") else "academic"
            continue
        if key is None:
            continue
        if m := SECTION_HEADING.match(line):
            skipping = False
            key.close_note()
            if m.group(3):
                key.last, key.queue = int(m.group(3)) - 1, []
                section = [int(m.group(3)), int(m.group(4))]
                if section[0] < section[1] <= 40 and section not in key.sections:
                    key.sections.append(section)
            continue
        if SCORES.match(line):
            skipping = True
            continue
        if re.search(r"REQUIRED|FOR\s*ONE\s*MARK", line, re.I) and not re.search(r"\b[A-L]\b.*\b[A-L]\b", line):
            key.doubtful = True  # "BOTH REQUIRED FOR ONE MARK" on its own line: the answers follow, hard to number
        if RANGE.match(line):
            continue
        if m := GROUP.match(line):
            first, last = int(m.group(1)), int(m.group(2))
            if first < last <= 40 and last - first < 5:
                skipping = False
                group = list(range(first, last + 1)) if re.search(r"[-–]", line[:8]) else [first, last]
                key.any_order.append(group)
                key.last, key.queue = first - 1, list(group)
                rest = EITHER.sub("", m.group(3)).strip()
                if rest:
                    key.text(rest)
                continue
        if m := NUMBERED.match(line):
            q, rest = int(m.group(1)), m.group(2).strip()
            if 1 <= q <= 40 and not (q <= key.last and q not in key.guessed and not rest):
                skipping = False
                if TRAILING_NOTE.search(rest) and len(rest.split()) > 1:
                    key.noted.append(q)
                    rest = TRAILING_NOTE.sub("", rest)
                else:
                    key.close_note()
                rest = EITHER.sub("", rest).strip()
                if rest:
                    key.queue = [n for n in key.queue if n > q]
                    key.give(q, rest)
                else:
                    key.queue.append(q)
                continue
        if m := re.fullmatch(r"(\d{3,})\s*(.*)", line):
            if not m.group(2) or EITHER.fullmatch(m.group(2).strip()):
                key.numbers(m.group(1))  # "3435  IN EITHER ORDER": 34 and 35, either order
                if m.group(2) and len(key.queue) > 1:
                    key.any_order.append(list(key.queue))
                continue
        if skipping or re.fullmatch(r"\d+", line) or len(EITHER.sub("", line).strip()) < 1:
            continue
        key.text(line)
    for skills in tests.values():
        for k in skills.values():
            k.answers = {q: tidy for q, a in k.answers.items() if (tidy := tidied(a))}
            for q, a in k.answers.items():
                near = [k.answers.get(q - 1, ""), k.answers.get(q + 1, "")]
                if a in ("1", "l", "|") and any(re.fullmatch(r"[A-L]", n) for n in near):
                    k.answers[q] = "I"  # OCR reads the letter I as 1
                elif a in ("1", "l", "|") and any(re.fullmatch(r"[ivx]+", n) for n in near):
                    k.answers[q] = "i"
    return {t: {s: {"kind": k.kind, "answers": {str(q): a for q, a in sorted(k.answers.items())},
                    "any_order": k.any_order, "guessed": sorted(k.guessed),
                    "sections": sorted(k.sections), "doubtful": k.doubtful}
                for s, k in skills.items()}
            for t, skills in tests.items()}


# OCR misreads differently at each size ("A" for "V", "iii" for "viii", a missed number that
# shifts the answers after it): each key page is read at three widths (pixels), and an answer
# counts only when two readings agree.
READINGS = (1000, 1600, 2400)


# Most letter answers are A to L (paragraphs, options); a few lists go further.
EARLY = re.compile(r"[A-L]")
LATE = re.compile(r"[M-Z]")


def agreed(readings: list[dict]) -> dict:
    """The keys of several readings of the same pages: each answer two readings agree on. A test
    one reading missed (its heading misread) still counts from the others; its any-order groups and
    parts' questions come from the first reading that has it."""
    found: dict[str, dict] = {}
    for test in dict.fromkeys(t for r in readings for t in r):
        for skill in dict.fromkeys(s for r in readings for s in r.get(test, {})):
            keys = [k for r in readings if (k := r.get(test, {}).get(skill))]
            key = dict(keys[0])
            votes = {}
            for q in map(str, range(1, 41)):
                said = [a for k in keys if (a := k["answers"].get(q))]
                if answer := next((a for a in said if sum(squeezed(b) == squeezed(a) for b in said) >= 2), None):
                    # "A" against "V", "V": a big serif A read as V by two readings. Letters after
                    # L are rare (a long list of words) and then every reading sees them.
                    early = {a for a in said if EARLY.fullmatch(a)}
                    if LATE.fullmatch(answer) and len(early) == 1:
                        answer = early.pop()
                    votes[q] = answer
            key["answers"] = votes
            key["doubtful"] = any(k.get("doubtful") for k in keys)
            found.setdefault(test, {})[skill] = key
    return found


async def import_keys(path: Path, texts: list[str]) -> dict:
    """Reads the book's answer keys (OCR from the PDF, or the cached OCR) and saves them."""
    book_id = pages.slug(path)
    cache = pages.books_dir() / f"{book_id}.keys-ocr.json"
    ocr = json.loads(cache.read_text()) if cache.exists() else {}
    numbers = key_pages(texts)
    readings = []
    for width in map(str, READINGS):
        if width not in ocr:
            if not path.exists():
                raise FileNotFoundError(f"{path}: the answer keys need the PDF once (OCR with positions)")
            log.info("%s: reading %d answer key pages with OCR (%s pixels wide)", path.name, len(numbers), width)
            ocr[width] = await asyncio.to_thread(pages.ocr_boxes, path, numbers, int(width))
            cache.write_text(json.dumps(ocr, ensure_ascii=False))
        found = {int(k): v for k, v in ocr[width].items()}
        readings.append(parse([lines(found[i]) for i in sorted(found)]))
    keys = {"id": book_id, "tests": agreed(readings)}
    (pages.books_dir() / f"{book_id}.keys.json").write_text(json.dumps(keys, ensure_ascii=False, indent=1))
    return keys


def load_keys(book_id: str) -> dict | None:
    path = pages.books_dir() / f"{book_id}.keys.json"
    return json.loads(path.read_text()) if path.exists() else None


def squeezed(text: str) -> str:
    """Letters and digits only, lower case: how answers are compared."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()  # "somé" is "some"
    return re.sub(r"[^a-z0-9]", "", plain.lower())


# The books' notes in an answer: not part of it.
NOTE = re.compile(r"\((?=[^)]*\b(must|spelling|capital|accept|order|only|correct)\b)[^)]*\)?"
                  r"|\b(in\s+(either|any)\s+order)\b", re.I)
ABBREVIATIONS = {"true": "t", "false": "f", "notgiven": "ng", "yes": "y", "no": "n"}


def accepted(printed: str) -> set[str]:
    """Every answer that counts as correct for a printed answer, squeezed (see squeezed()).

    "talk // give a talk" (or " / " with spaces, or "OR") lists whole answers; "4/four sides" a
    choice of words; brackets are optional: "(musical) instruments", "record(s)"; "NOT x" is a
    wrong answer the key warns about; "ACCEPT x" adds one. TRUE/FALSE/NOT GIVEN and YES/NO may be
    written as T/F/NG and Y/N, as on the answer sheet. "A (and) B" (two letters for one mark) takes
    both letters, in either order."""
    text = NOTE.sub(" ", printed)
    if both := re.fullmatch(r"\s*([A-L])\s*(?:\(and\)|and|&|,)?\s*([A-L])\s*", text):
        a, b = both.group(1).lower(), both.group(2).lower()  # two letters for one mark, either order
        return {a + b, b + a, f"{a}and{b}", f"{b}and{a}"}
    text = re.sub(r"\bACCEPT\b", "//", text)
    found = set()
    for whole in re.split(r"//|\s/\s|\bOR\b", text):
        whole = re.sub(r"\bNOT\b(?!\s*GIVEN).*", "", whole).strip(" ,;.")
        if whole:
            found |= _variants(whole)
    found.discard("")
    for long, short in ABBREVIATIONS.items():
        if long in found:
            found.add(short)
    return found


def _variants(text: str) -> set[str]:
    """The answers one alternative stands for: brackets optional, word/word a choice."""
    choices = []
    for part in re.findall(r"\([^)]*\)|[^\s()]+", text):
        if part.startswith("("):
            choices.append(["", *part.strip("()").split("/")])
            continue
        options = part.split("/")
        # "1/one-year": the "-year" belongs to every choice
        suffix = next((o[o.index("-"):] for o in options if "-" in o), "")
        choices.append([o if "-" in o or not suffix else o + suffix for o in options])
    combos = itertools.islice(itertools.product(*choices), 256)
    return {squeezed(" ".join(c)) for c in combos}


def mark(key: dict, answers: dict[str, str]) -> dict[str, bool]:
    """Which answers are right, {"1": True, ...} for every question of the key. Questions that may
    be answered in any order share their answers: each right answer counts once."""
    right = {}
    for q, printed in key["answers"].items():
        given = squeezed(answers.get(q, ""))
        right[q] = bool(given) and given in accepted(printed)
    for group in key.get("any_order", []):
        qs = [str(q) for q in group if str(q) in key["answers"]]
        pool = [accepted(key["answers"][q]) for q in qs]
        for q in qs:
            given = squeezed(answers.get(q, ""))
            match = next((i for i, options in enumerate(pool) if given and given in options), None)
            right[q] = match is not None
            if match is not None:
                pool.pop(match)
    return right
