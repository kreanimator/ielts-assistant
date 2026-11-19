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
6. mark() also takes what an examiner takes though the key does not print it: a number in
   words or figures ("two weeks" for "2 weeks"), and words more than the key's that do not make
   the answer wrong, within the word limit ("in small groups" for "groups", when that is what
   the recording says): see right_answer() and more_words().

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
GROUP = re.compile(r"^(\d{1,2})\s*(?:&|and|,|-|–)\s*(\d{1,2})(?!\d)\s*(.*)$", re.I)  # "26&27IN EITHER ORDER" too
NUMBERED = re.compile(r"^(\d{1,2})\b(?![/:])\s*(.*)$")  # not "10/ten times", an answer
EITHER = re.compile(r"\b(in\s*)?(either|any)\s*order\b", re.I)
# The same note beside an answer, maybe cut short or after a mark of the bracket: "snakes § in either".
NOTE_BESIDE = re.compile(r"\s+[^\w\s()]?\s*(?:(?:in\s*)?(either|any)\s*order|in\s+(either|any))\s*$", re.I)
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
    a = re.sub(r"\s+(a\s+)?lot\s+of\s+time\b.*$", "", a)  # "plants lot of time improving your": the advice beside
    a = re.sub(r"\bBOTH\s*(REQUIRED\s*)?FOR\s*ONE\s*M\s*A\s*R\s*K\b,?", "", a, flags=re.I)
    a = re.sub(r"\b(IN\s+)?\w*TH\w*\s+ORDER\b", "", a, flags=re.I)  # "either order", OCR slips included
    a = re.sub(r"(?<=\w)\s*[\]}]$", "", a)  # "walking boots]": the bracket round answers in any order
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
        self.bracketed: list[tuple[int, str]] = []  # (17, "any"): "in any order" beside one answer of a bracket
        self.unsure: set[int] = set()  # questions read, but not to be trusted: the web page's answer is used

    def brackets(self):
        """The groups that "in any order" / "in either order" beside one answer stand for. The
        note is printed beside the middle of a bracket: of three answers ("any") beside the
        middle one; of two ("either") beside the first or the second, so the one next to it that
        is in the same part and in no other group."""
        grouped = {q for g in self.any_order for q in g}

        def free(q: int, near: int) -> bool:
            part = lambda n: next((i for i, (a, b) in enumerate(self.sections) if a <= n <= b), (n - 1) // 10)  # noqa: E731
            return near in self.answers and near not in grouped and part(near) == part(q)

        for q, kind in self.bracketed:
            if q in grouped:
                continue
            if kind == "any" and free(q, q - 1) and free(q, q + 1):
                group = [q - 1, q, q + 1]
            elif kind == "either" and (free(q, q + 1) or free(q, q - 1)):
                group = [q, q + 1] if free(q, q + 1) else [q - 1, q]
            else:
                continue
            self.any_order.append(group)
            grouped |= set(group)

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
    """The keys in a book's key pages (each page's lines, see lines()), by test and skill.

    Some older books print no "TEST n" over their keys: a page is one test, its
    Listening key beside its Reading key. Then each LISTENING heading starts the next test, and
    only the Listening keys are read: the Reading columns run into each other on those pages."""
    tests: dict[str, dict[str, _Key]] = {}
    test, key, skipping = "", None, False
    untitled = not any(TEST_HEADING.match(line.strip()) for page in page_lines for line in page)
    for line in (line.strip() for page in page_lines for line in page):
        line = re.sub(r"^\S*order\s+(?=\d)", "", line, flags=re.I)  # "Iorder  39  B": a note of the next column
        if untitled and (m := SKILL_HEADING.match(line)):
            skipping = False
            key = None
            if m.group(2).upper() == "LISTENING":
                test = str(len(tests) + 1)
                key = tests.setdefault(test, {}).setdefault("listening", _Key())
            continue
        if untitled and re.match(r"(Reading\s*)?Passage\b", line, re.I):
            key = None  # a Reading key: left out, see above
            continue
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
                if EITHER.fullmatch(rest.strip(" ;,.")):
                    # "32  IN EITHER ORDER", then "metal" and "leather": two answers for one mark,
                    # on lines of their own. They are read as one answer, but not trusted.
                    key.close_note()
                    key.unsure.add(q)
                    key.queue.append(q)
                    continue
                if (note := NOTE_BESIDE.search(rest)) and rest[:note.start()].strip() and not re.search(r"REQUIRED|MARK", rest, re.I):
                    # "17 socks  in any order": the note beside a bracket round 16 to 18
                    key.close_note()
                    key.bracketed.append((q, (note.group(1) or note.group(2)).lower()))
                    rest = rest[:note.start()].strip()
                elif TRAILING_NOTE.search(rest) and len(rest.split()) > 1:
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
            k.brackets()
            for q, a in k.answers.items():
                near = [k.answers.get(q - 1, ""), k.answers.get(q + 1, "")]
                if a in ("1", "l", "|") and any(re.fullmatch(r"[A-L]", n) for n in near):
                    k.answers[q] = "I"  # OCR reads the letter I as 1
                elif a in ("1", "l", "|") and any(re.fullmatch(r"[ivx]+", n) for n in near):
                    k.answers[q] = "i"
    return {t: {s: {"kind": k.kind, "answers": {str(q): a for q, a in sorted(k.answers.items())},
                    "any_order": k.any_order, "guessed": sorted(k.guessed),
                    "sections": sorted(k.sections), "doubtful": k.doubtful, "unsure": sorted(map(str, k.unsure))}
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
            key["unsure"] = sorted({q for k in keys for q in k.get("unsure", [])}, key=int)
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
                  r"|\b(in\s+(either|any)\s+order)\b|\bor\s+(any\s+)?acceptable\s+alternatives?\b", re.I)
# The same in capitals, before or after the answer: "MUST BE IN ORDER 20 (cm) 50 (cm)",
# "1 July ALTERNATIVE FORMS ACCEPTED", "MUST STATE ALL THREE white, grey, brown".
SHOUTED = re.compile(r"\b(MUST|ALTERNATIVE)\b(\s+[^\sa-z0-9(£$/]+)*")
ABBREVIATIONS = {"true": "t", "false": "f", "notgiven": "ng", "yes": "y", "no": "n"}


def accepted(printed: str) -> set[str]:
    """Every answer that counts as correct for a printed answer, squeezed (see squeezed()).

    "talk // give a talk" (or " / " with spaces, or "OR") lists whole answers; "4/four sides" a
    choice of words; brackets are optional: "(musical) instruments", "record(s)"; "NOT x" is a
    wrong answer the key warns about; "ACCEPT x" adds one. TRUE/FALSE/NOT GIVEN and YES/NO may be
    written as T/F/NG and Y/N, as on the answer sheet. "A (and) B" (two letters for one mark) takes
    both letters, in either order."""
    text = SHOUTED.sub(" ", NOTE.sub(" ", printed))
    if both := re.fullmatch(r"\s*([A-L])\s*(?:\(and\)|and|&|,)?\s*([A-L])\s*", text):
        a, b = both.group(1).lower(), both.group(2).lower()  # two letters for one mark, either order
        return {a + b, b + a, f"{a}and{b}", f"{b}and{a}"}
    found = {squeezed(phrase) for phrase in phrases(printed)}
    found.discard("")
    for long, short in ABBREVIATIONS.items():
        if long in found:
            found.add(short)
    return found


def phrases(printed: str) -> set[str]:
    """The answers a printed answer stands for, as words: "(in) groups" is "groups" and "in groups"."""
    text = re.sub(r"\bACCEPT\b", "//", SHOUTED.sub(" ", NOTE.sub(" ", printed)))
    found = set()
    for whole in re.split(r"//|\s/\s|\bOR\b", text):
        whole = re.sub(r"\bNOT\b(?!\s*GIVEN).*", "", whole).strip(" ,;.")
        if whole:
            found |= _variants(whole)
        sides = whole.split("/")
        if len(sides) > 1 and all(len(re.sub(r"\([^)]*\)", " ", s).split()) >= 2 for s in sides):
            for side in sides:  # "half hour/30 minutes": whole answers, as "//"
                found |= _variants(side.strip())
    return found


def _variants(text: str) -> set[str]:
    """The answers one alternative stands for: brackets optional, word/word a choice."""
    while (inner := re.sub(r"\(([^()]*)\(([^()]*)\)([^()]*)\)", r"(\1) (\2) (\3)", text)) != text:
        text = inner  # "((the) year) 2000": every word of it optional
    text = text.replace("()", "")
    choices = []
    for part in re.findall(r"\([^)]*\)|[^\s()]+", text):
        if part.startswith("("):
            choices.append(["", *part.strip("()").split("/")])
            continue
        options = part.split("/")
        # "1/one-year": the "-year" belongs to every choice ("$25/twenty-five": "-five" does not)
        suffix = next((o[o.index("-"):] for o in options if "-" in o), "")
        if suffix[1:] in UNITS:
            suffix = ""
        choices.append([o if "-" in o or not suffix else o + suffix for o in options])
    combos = itertools.islice(itertools.product(*choices), 256)
    return {" ".join(filter(None, c)) for c in combos}


UNITS = {w: n for n, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * n for n, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), start=2)}
ARTICLES = {"a", "an", "the"}
# A word before the answer that an examiner lets pass: "in groups" for "groups".
BEFORE = {"in", "at", "on", "for", "by", "with"}
# Words that turn an answer round: "not confident" is not "confident" with a word more.
TURNING = {"not", "no", "never", "less", "without", "nor", "neither", "hardly", "non", "except", "few", "little"}


def words(text: str) -> list[str]:
    """An answer as its words, as they are compared: lower case, no marks, and a number written
    in words as its figures ("two weeks" is "2 weeks", "twenty-five" is "25"). "every second
    day" and "every other day" are "every 2 days". "$25" is "25 dollars" and "£50" "50 pounds";
    "11.00" and "11 o'clock" are "11"; a date is "27 june" (dated())."""
    text = re.sub(r"\$\s*([\d.,]+)(\s*(thousand|million))?", r"\1\2 dollars", text)
    text = re.sub(r"£\s*([\d.,]+)(\s*(thousand|million))?", r"\1\2 pounds", text)
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    plain = re.sub(r"\b(\d{1,2})[.:]00\b", r"\1", plain.replace("'", ""))  # "11.00" is "11"
    plain = re.sub(r"\b(dollars|pounds)\s+(dollars?|pounds?)\b", r"\1", plain)  # "$25 dollars"
    plain = re.sub(r"\s*\boclock\b", "", plain)
    plain = re.sub(r"(?<=\d)[,.:](?=\d)", "", plain)  # "1,500" and "4.30" stay one number
    found, number = [], None  # number: [thousands done, the rest so far] while a number is read
    for word in re.findall(r"[a-z]+|\d+", plain) + [""]:
        value = UNITS.get(word, TENS.get(word))
        if value is not None:
            rest = number[1] if number else None
            fits = rest is not None and (rest % 100 == 0 and rest > 0 or rest % 100 >= 20 and rest % 10 == 0 and value < 10)
            if number and (fits or rest == 0 and number[0]):
                number[1] += value  # "twenty" + "five", "two hundred" + "ten", "one thousand" + "five"
            else:
                if number:
                    found.append(str(sum(number)))
                number = [0, value]
            continue
        if word == "hundred" and number and 0 < number[1] < 10:
            number[1] *= 100
            continue
        if word == "thousand" and number and not number[0] and 0 < number[1] < 1000:
            number = [number[1] * 1000, 0]
            continue
        if word == "and" and number and (number[1] >= 100 and number[1] % 100 == 0 or number[0] and not number[1]):
            continue  # "two hundred and ten"
        if number:
            found.append(str(sum(number)))
            number = None
        if word:
            found.append(word)
    for i in range(len(found) - 2):
        if found[i] == "every" and found[i + 1] in ("second", "other") and found[i + 2].isalpha():
            found[i + 1:i + 3] = ["2", found[i + 2].rstrip("s") + "s"]
    return dated(found)


MONTHS = {m[:3]: m for m in "january february march april may june july august september october november december".split()}


def dated(tokens: list[str]) -> list[str]:
    """A date as "27 june", however it is written: "27th June", "the 27th of June", "June 27th",
    "Jun 27". Other words are left as they are."""
    month = lambda t: MONTHS.get(t[:3]) if t[:3] in MONTHS and (t in MONTHS.values() or t in MONTHS or t == "sept") else None  # noqa: E731
    out = list(tokens)
    i = 0
    while i < len(out):
        day = out[i].isdigit() and 1 <= int(out[i]) <= 31
        if day and i + 1 < len(out) and out[i + 1] in ("st", "nd", "rd", "th"):
            del out[i + 1]  # "27th" is read as "27", "th"
        if day and i + 2 < len(out) and out[i + 1] == "of" and month(out[i + 2]):
            del out[i + 1]  # "27 of june"
        if day and i + 1 < len(out) and month(out[i + 1]):
            out[i + 1] = month(out[i + 1])
            if i > 0 and out[i - 1] == "the":
                del out[i - 1]
                i -= 1
        elif day and i > 0 and month(out[i - 1]):
            out[i - 1:i + 1] = [out[i], month(out[i - 1])]  # "june 27" is "27 june"
        i += 1
    return out


def word_limit(instructions: str) -> tuple[int, bool] | None:
    """How much may be written, from a group's instructions: "NO MORE THAN TWO WORDS AND/OR A
    NUMBER" is (2, True), "ONE WORD ONLY" (1, False); None when they set no limit."""
    m = re.search(r"\b(ONE|TWO|THREE|FOUR|FIVE)\s+WORDS?\b", instructions)
    if m is None:
        return None
    return ["ONE", "TWO", "THREE", "FOUR", "FIVE"].index(m.group(1)) + 1, bool(re.search(r"\bNUMBERS?\b", instructions))


def limits(content: dict | None) -> dict[str, tuple[int, bool]]:
    """Each question's word limit, {"26": (3, True)}, from a test's groups of questions."""
    found = {}
    for part in (content or {}).get("parts", []):
        for group in part["groups"]:
            limit = word_limit(" ".join(group.get("instructions") or []))
            if limit:
                found.update({str(q): limit for q in range(group["first"], group["last"] + 1)})
    return found


def _inside(short: list[str], long: list[str]) -> bool:
    return any(long[i:i + len(short)] == short for i in range(len(long) - len(short) + 1))


def _bare(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in ARTICLES]


def more_words(given: str, printed: str, limit: tuple[int, bool] | None, said: list[str] | None) -> bool:
    """True when an answer is a key's answer with words more that do not make it wrong, as an
    examiner accepts it: it holds the key's answer whole, stays within the word limit, turns
    nothing round ("not ..."), and what was added is an article or a word like "in" before it
    ("in groups"), or the answer is word for word what the recording says (or the passage): "in small groups" for "groups" when the speaker
    said "We did these in small groups". `said`: words() of the recording or passage."""
    answer = words(given)
    if limit is None or not answer:
        return False
    for phrase in phrases(printed):
        key = words(phrase)
        if len("".join(key)) < 3 or not _inside(_bare(key), _bare(answer)):
            continue  # a letter or a numeral is never part of a longer answer
        if any(w in TURNING or w.startswith("un") and w[2:] in key for w in answer if w not in key):
            continue
        count = lambda tokens, digits: sum(t.isdigit() == digits for t in tokens)  # noqa: E731
        numbers = max(1 if limit[1] else 0, count(key, True))
        free = min(count(answer, True), numbers) if limit[1] else 0  # "AND/OR A NUMBER": it is not a word
        if count(answer, True) > numbers or len(answer) - free > max(limit[0], len(key) - min(count(key, True), free)):
            continue
        led = _bare(answer)[1:] if _bare(answer)[0] in BEFORE and _bare(key)[0] not in BEFORE else None
        if _bare(key) in (_bare(answer), led) or said and (_inside(answer, said) or _inside(_bare(answer), _bare(said))):
            return True
    return False


def right_answer(given: str, printed: str, limit: tuple[int, bool] | None = None, said: list[str] | None = None) -> bool:
    """Is this answer right for the printed one? As printed (accepted()); or the same with its
    numbers in words or figures; or with words more that an examiner accepts (more_words())."""
    if not squeezed(given):
        return False
    if squeezed(given) in accepted(printed):
        return True
    if (len(squeezed(given)) > 2 or re.search(r"\d", given)) and words(given) in [words(p) for p in phrases(printed)]:
        return True
    return more_words(given, printed, limit, said)


def mark(key: dict, answers: dict[str, str]) -> dict[str, bool]:
    """Which answers are right, {"1": True, ...} for every question of the key. Questions that may
    be answered in any order share their answers: each right answer counts once.

    The key may bring "limits" (limits() of the test) and "said" (the words() of what each
    question's part says or prints, {"26": [...]}); with them an answer with words more than the
    key's is judged as in more_words()."""
    limit, said = key.get("limits", {}), key.get("said", {})

    def ok(q: str, printed: str) -> bool:
        return right_answer(answers.get(q, ""), printed, limit.get(q), said.get(q))

    right = {q: ok(q, printed) for q, printed in key["answers"].items()}
    for group in key.get("any_order", []):
        qs = [str(q) for q in group if str(q) in key["answers"]]
        pool = [key["answers"][q] for q in qs]
        for q in qs:
            match = next((i for i, printed in enumerate(pool) if ok(q, printed)), None)
            right[q] = match is not None
            if match is not None:
                pool.pop(match)
    return right


def said(content: dict | None) -> dict[str, list[str]]:
    """For each question, the words() of its part's recording (the transcript) and passage."""
    found = {}
    for part in (content or {}).get("parts", []):
        text = "\n".join([*part.get("transcript", []), *(b["text"] for b in part.get("passage", []))])
        if text.strip():
            tokens = words(text)
            found.update({str(q): tokens for q in range(part["first"], part["last"] + 1)})
    return found


def marking_key(found: dict) -> dict:
    """A test (its "key", "any_order" and, when it has its text, "content") as mark() takes it."""
    content = found.get("content")
    return {"answers": found["key"], "any_order": found["any_order"], "limits": limits(content), "said": said(content)}
