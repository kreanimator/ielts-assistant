"""A Reading test as text, the way the computer-delivered test shows it: each part's passage
on the left, its questions on the right, each with its own control (TRUE / FALSE / NOT GIVEN
buttons, the options of a multiple-choice question, a list of letters to match, a gap to type
in).

build() reads the OCR lines of a test's pages (core/layout.py) and its answer key:

    {"parts": [{"part": 1, "first": 1, "last": 13, "pages": [88, 89, 90, 91],
                "intro": "You should spend about 20 minutes on ...",
                "passage": [{"kind": "title" | "text" | "note", "text": "...", "letter": "A" | None}],
                "groups": [GROUP, ...]}]}

    GROUP = {"first": 1, "last": 6, "type": TYPE, "instructions": ["Complete the notes below.", ...],
             "options": [{"letter": "A", "text": "..."}],   # the choices, for every type with letters
             "questions": [{"q": 7, "text": "...", "options": [...]}],
             "notes": [[" text ", 3, " more text"], ...],  # "notes": lines of text and gaps
             "stem": "Which TWO ...?",                      # "multi"
             "printed": False,                              # True: show the pictures instead
             "pictures": [{"page": 90, "box": [x0, y0, x1, y1]}]}  # the printed group (fractions of the page)

    TYPE, the control of each question: "tfng" | "ynng" (buttons), "choice" (each question its
    options), "multi" (choose TWO or more letters for several questions), "match" (a letter from
    the options for each question), "gaps" (a word or two for each question), "notes" (gaps
    inside notes or a summary).

A group's text is shown only when it checks out: every question number found once, in order,
and every option letter in sequence. Otherwise ("printed": True) the group is shown as its
picture, with the same controls (tables and diagrams always are), so nothing is ever missing.
"""
import logging
import re

from ..core.layout import reading_order

log = logging.getLogger("ielts.reading.content")

GLUED_HEADING = re.compile(r"^Questions?\s*(\d{2,4})\b\s*(Reading)?$", re.I)  # "Questions 1418": the dash lost
SINGLE_HEADING = re.compile(r"^Question\s*(\d{1,2})\s*(Reading)?$", re.I)
PART_RANGE = re.compile(r"Questions?\s*(\d{1,2})\s*(?:[-–—~]|and|to)\s*(\d{1,2})\b", re.I)
GROUP_HEADING = re.compile(r"^Questions?\s*(\d{1,2})\s*(?:[-–—~]|and|to)\s*(\d{1,2})\b(?!\s*(?:,|which|are))", re.I)
# "READING PASSAGE 2" or "SECTION 1  Questions 1-14" as a line of its own
PART_HEADING = re.compile(r"^(READING\s*PASSAGE|SECTION|PART)\s*([1-3Il]|ONE|TWO|THREE)\s*(Questions?\s*\d.*)?$", re.I)
SPEND = re.compile(r"^You\s*should\s*spend", re.I)
READ_TEXT = re.compile(r"^Read\s*the\s*(text|texts|information|advertisement|article|passage|extract|notice)", re.I)
INSTRUCTION = re.compile(
    r"^(Complete|Choose|Write|Answer|Do\s*the\s*following|In\s*boxes|Look\s*at|Match|Classify|Label|Use\s*the|"
    r"Questions?\b|NB\b|N\.B|You\s*may|Reading\s*Passage\s*\d|The\s*(reading\s*)?passage\s*has|"
    r"Which\s*(paragraph|section|part)|TRUE\b|FALSE\b|NOT\s*GIVEN|YES\b|NO\b|if\s*(the|there|it)|"
    r"Each|Example|from\s*the|Write\s*the|Select|List\s*of\s*(Headings|People|Researchers|Theories))", re.I)
ANSWER_SHEET = re.compile(r"answer\s*sheet", re.I)
LIST_HEADING = re.compile(r"^List\s*of\b", re.I)
RANGE = re.compile(r"\b\d{1,2}\s*(?:[-–—~]|and|to)\s*\d{1,2}\b|\(Questions?[^)]*\)", re.I)
LETTER_RANGE = re.compile(r"\b([A-Z])\s*[-–—~]\s*([A-Z])\b|\b([A-Z]),\s*(?:[A-Z],\s*)*(?:[A-Z]\s*)?or\s*([A-Z])\b")
LEADER = re.compile(r"\s*(?:[.…·_]\s*){2,}")
# a page number or running header left inside the text ("64", "Reading")
RUNNING_LINE = re.compile(r"^(\d{1,3}|Reading|READING|Test\s*\d+|(General\s*Training|Academic)\s*Reading(\s*and\s*Writing)?)$", re.I)
EXAMPLE = re.compile(r"^Example\b", re.I)
EXAMPLE_ROW = re.compile(r"^(Paragraph|Section)\s+[A-Z]\s+[ivxl]+$", re.I)
# Questions' furniture that ended up in a passage: the part's layout was not understood.
NOT_PASSAGE = re.compile(r"^(List\s*of\s*Headings|Answer\s+[ivxl]+|Example(\s+Answer)?)$", re.I)
ROMAN_AT = re.compile(r"^\(?(xv|xiv|xiii|xii|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i)\)?(?=\s|[A-Z])\s*(.*)$", re.I)
ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv"]
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TFNG = {"TRUE", "FALSE", "NOT GIVEN"}
YNNG = {"YES", "NO", "NOT GIVEN"}
TABLE_LIKE = re.compile(r"\b(table|flow\s*-?\s*chart|diagram|chart|map|plan|form)\b", re.I)
NOTES_LIKE = re.compile(r"\b(notes|summary|paragraph\s*below|text\s*below)\b", re.I)


def _answers_kind(answers: list[str], instructions: str = "") -> str:
    # "v // Early research ...": the numeral; "FALSE/F", "TRUE///T": the word
    answers = [re.split(r"/+", a)[0].strip() for a in answers]
    up = [a.upper() for a in answers]
    if all(a in TFNG for a in up) and any(a in ("TRUE", "FALSE") for a in up):
        return "tfng"
    if all(a in YNNG for a in up) and any(a in ("YES", "NO") for a in up):
        return "ynng"
    if all(a == "NOT GIVEN" for a in up):
        return "ng"
    if all(a.lower() in ROMAN for a in answers) and (re.search(r"heading", instructions, re.I)
                                                      or not all(re.fullmatch(r"[A-Z]", a) for a in up)):
        return "roman"
    if all(re.fullmatch(r"[A-Z]", a) for a in up):
        return "letter"
    return "words"


def _number_at(text: str, q: int, start: int = 0) -> re.Match | None:
    """The question number q standing alone in the text (not part of 1890, 2.5 or 10%)."""
    return re.compile(rf"(?<![\d.,£$/]){q}(?![\d%]|\.\d|,\d)").search(text, start)


def _masked(text: str) -> str:
    """Ranges ("19–22", "(Questions 1-5)") blanked out, so their numbers are not questions."""
    return RANGE.sub(lambda m: " " * len(m.group(0)), text)


def _split_lines(lines: list[dict], first: int, last: int) -> list[tuple[int, str]] | None:
    """Questions printed one a line, a number lost here and there: a line without a number
    between two questions that lack exactly that many is theirs."""
    found: list[tuple[int | None, str]] = []
    for line in lines:
        m = re.match(r"^(\d{1,2})(?!\d)\s*(.*)$", line["text"])
        found.append((int(m.group(1)), m.group(2)) if m and first <= int(m.group(1)) <= last else (None, line["text"]))
    numbered = [i for i, (q, _) in enumerate(found) if q is not None]
    if not numbered:
        return None
    out, previous_q, previous_i = [], first - 1, -1
    for i in [*numbered, len(found)]:
        q = found[i][0] if i < len(found) else last + 1
        between = [t for _, t in found[previous_i + 1:i]] if previous_i >= 0 or q > first else []
        missing = q - previous_q - 1
        if missing == len(between):
            out += [(previous_q + 1 + k, t) for k, t in enumerate(between)]
        elif missing == 0 and out:
            out[-1] = (out[-1][0], " ".join([out[-1][1], *between]))  # a question on two lines
        else:
            return None
        if i < len(found):
            out.append((q, found[i][1]))
        previous_q, previous_i = q, i
    return out if [q for q, _ in out] == list(range(first, last + 1)) else None


def _choices_from_lines(lines: list[dict], first: int, last: int, letters: str) -> list[dict] | None:
    """Multiple-choice questions read line by line: a question's number starts its stem, its
    options follow (A, B, C, D, the letter sometimes stuck to the text, "Bwe experience ...");
    an option A that lost its letter is the line just before B."""
    questions: list[dict] = []
    for line in lines:
        text = line["text"]
        m = re.match(r"^(\d{1,2})(?!\d)\s*(.*)$", text)
        expected = questions[-1]["q"] + 1 if questions else first
        if m and int(m.group(1)) == expected and not line.get("letter"):
            questions.append({"q": expected, "stem": [m.group(2)], "options": []})
            continue
        if not questions:
            if first == last:
                questions.append({"q": first, "stem": [text], "options": []})
            continue
        current = questions[-1]
        want = letters[len(current["options"])] if len(current["options"]) < len(letters) else None
        letter, rest = line.get("letter"), text
        if not letter and want:
            o = re.match(rf"^{want}(?:\s+|(?=[a-z]))(.+)$", text)
            if o:
                letter, rest = want, o.group(1)
        if letter and letter == want:
            current["options"].append({"letter": letter, "text": rest.strip()})
        elif letter == "B" and not current["options"] and len(current["stem"]) > 1:
            current["options"] += [{"letter": "A", "text": current["stem"].pop()}, {"letter": "B", "text": rest.strip()}]
        elif current["options"]:
            current["options"][-1]["text"] += " " + text
        else:
            current["stem"].append(text)
    if [q["q"] for q in questions] != list(range(first, last + 1)) or any(len(q["options"]) < 3 for q in questions):
        return None
    return [{"q": q["q"], "text": " ".join(q["stem"]).strip(), "options": q["options"]} for q in questions]


def _split_numbered(text: str, first: int, last: int) -> list[tuple[int, str]] | None:
    """The text cut at the question numbers first..last, in order: [(q, its text)]. A group of
    one question may have no number before it (its heading has it)."""
    masked = _masked(text)
    if first == last and _number_at(masked, first) is None:
        return [(first, text.strip())] if text.strip() else None
    marks, at = [], 0
    for q in range(first, last + 1):
        m = _number_at(masked, q, at)
        if m is None:
            return None
        marks.append((q, m.start(), m.end()))
        at = m.end()
    out = []
    for i, (q, _, end) in enumerate(marks):
        stop = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        out.append((q, text[end:stop].strip(" .:")))
    return out


def _split_options(text: str, letters: str) -> tuple[str, list[dict]] | None:
    """'stem A one B two C three' → ("stem", [{"letter": "A", "text": "one"}, ...]), the letters
    found in order; None when fewer than three are."""
    marks, at = [], 0
    for letter in letters:
        m = re.compile(rf"(?:^|(?<=[\s.?:]))\[?{letter}\]?(?=\s)").search(text, at)
        if m is None:
            break
        marks.append((letter, m.start(), m.end()))
        at = m.end()
    if len(marks) < 3:
        return None
    options = []
    for i, (letter, _, end) in enumerate(marks):
        stop = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        options.append({"letter": letter, "text": text[end:stop].strip()})
    if any(not o["text"] for o in options):
        return None
    return text[:marks[0][1]].strip(), options


def _line_text(line: dict) -> str:
    return f"{line['letter']} {line['text']}" if line.get("letter") else line["text"]


def _joined(lines: list[dict]) -> str:
    text = ""
    for line in lines:
        piece = _line_text(line)
        if text.endswith("-") and piece[:1].islower():
            text = text + piece
        else:
            text = f"{text} {piece}" if text else piece
    return re.sub(r"\s+", " ", text).strip()


def _letter_range(instructions: list[str]) -> str:
    for line in instructions:
        m = LETTER_RANGE.search(line)
        if m:
            a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            if a == "A" and b > a:
                return LETTERS[:LETTERS.index(b) + 1]
    return ""


def _pictures(lines: list[dict], line_height: float = 40) -> list[dict]:
    """The printed area of these lines, one box per page."""
    pictures = []
    for page in dict.fromkeys(l["page"] for l in lines):
        boxes = [l["box"] for l in lines if l["page"] == page]
        pad = line_height * 0.6
        pictures.append({"page": page, "box": [round(min(b[0] for b in boxes) - pad), round(min(b[1] for b in boxes) - pad),
                                                round(max(b[2] for b in boxes) + pad), round(max(b[3] for b in boxes) + pad)]})
    return pictures


def _notes(lines: list[dict], first: int, last: int) -> list[list] | None:
    """Notes or a summary: each line as text and gaps ([" text ", 3, " more"]), every number
    first..last found once, in order."""
    out, q = [], first
    for line in lines:
        text, pieces, masked = _line_text(line), [], _masked(_line_text(line))
        at = 0
        while q <= last:
            m = _number_at(masked, q, at)
            if m is None:
                break
            before = LEADER.sub(" ", text[at:m.start()])
            pieces += [before, q] if before.strip() else [q]
            at, q = m.end(), q + 1
            # the dots of the gap after its number
            lead = LEADER.match(text, at)
            if lead:
                at = lead.end()
        rest = LEADER.sub(" ", text[at:])
        if rest.strip():
            pieces.append(rest)
        if pieces:
            out.append(pieces)
    return out if q > last else None


def _group(lines: list[dict], first: int, last: int, key: dict, any_order: list[list[int]]) -> dict:
    answers = [key.get(str(q), "") for q in range(first, last + 1)]
    lines = [l for l in lines if not RUNNING_LINE.match(l["text"].strip())]
    instructions, at = [], 0
    while at < len(lines) and INSTRUCTION.match(_line_text(lines[at])) and not LIST_HEADING.match(lines[at]["text"]):
        instructions.append(lines[at]["text"])
        at += 1
    sheet = [j for j, l in enumerate(lines[:8]) if ANSWER_SHEET.search(l["text"])]
    if sheet and sheet[-1] >= at and not any(re.match(r"^\d{1,2}(?!\d)", l["text"]) for l in lines[at:sheet[-1]]):
        instructions += [l["text"] for l in lines[at:sheet[-1] + 1]]
        at = sheet[-1] + 1
        while at < len(lines) and re.match(r"^(NB|N\.B|You\s*may)", lines[at]["text"]):
            instructions.append(lines[at]["text"])
            at += 1
    content = lines[at:]
    kind = _answers_kind(answers, " ".join(instructions))
    shown = [re.sub(r"\s+", " ", i) for i in instructions if not ANSWER_SHEET.search(i)]
    numbers = range(first, last + 1)
    group = {"first": first, "last": last, "type": "gaps", "printed": True, "instructions": shown,
             "options": [], "questions": [{"q": q, "text": ""} for q in numbers]}
    text = _joined(content)
    all_text = " ".join(instructions)

    def shown_as_text(**fields):
        group.update(printed=False, **fields)
        return group

    if kind in ("tfng", "ynng", "ng"):
        group["type"] = kind if kind != "ng" else ("ynng" if re.search(r"\bYES\b", all_text) else "tfng")
        items = _split_numbered(text, first, last) or _split_lines(content, first, last)
        if items and all(0 < len(t) < 400 for _, t in items):
            return shown_as_text(questions=[{"q": q, "text": t} for q, t in items])
        return group

    if kind == "letter":
        letters = _letter_range(instructions) or _letter_range([text])
        if letters and any(a.split("//")[0].strip().upper() not in letters for a in answers):
            group["doubtful"] = True  # the key's letter is not one of the choices: misread
        items = _split_numbered(text, first, last)
        together = any(set(g) <= set(numbers) for g in any_order) or re.search(r"\b(TWO|THREE|FOUR|FIVE)\b", all_text + " " + text[:200])
        if together and not items:
            group["type"] = "multi"
            found = _split_options(text, letters or LETTERS)
            if found and len(found[1]) > len(numbers):
                return shown_as_text(stem=found[0], options=found[1])
            group["options"] = [{"letter": c, "text": ""} for c in letters or "ABCDE"]
            return group
        # each question with its own options: multiple choice
        if items:
            choices = [_split_options(t, letters or "ABCDE") for _, t in items]
            if all(choices) and all(len(c[1]) >= 3 for c in choices):
                group["type"] = "choice"
                return shown_as_text(questions=[{"q": q, "text": c[0], "options": c[1]} for (q, _), c in zip(items, choices)])
        by_lines = _choices_from_lines(content, first, last, letters or "ABCDE")
        if by_lines:
            group["type"] = "choice"
            return shown_as_text(questions=by_lines)
        if re.search(r"Choose\s*the\s*correct\s*letter", all_text, re.I) and not LIST_HEADING.search(text):
            group.update(type="choice", questions=[{"q": q, "text": "", "options": [{"letter": c, "text": ""} for c in letters or "ABCD"]}
                                                   for q in numbers])
            return group
        # a list of options (people, endings, features) somewhere in the group, and the questions
        group["type"] = "match"
        option_lines = [l for l in content if l.get("letter") or re.match(r"^[A-L]\s", l["text"])]
        found = _split_options(" ".join(_line_text(l) for l in option_lines), letters or LETTERS) if option_lines else None
        rest = [l for l in content if l not in option_lines and not LIST_HEADING.match(l["text"])]
        items = _split_numbered(_joined(rest), first, last) or _split_lines(rest, first, last)
        options = found[1] if found else [{"letter": c, "text": ""} for c in letters]
        if items and options and all(0 < len(t) < 400 for _, t in items):
            return shown_as_text(options=options, questions=[{"q": q, "text": t} for q, t in items])
        group["options"] = [{"letter": o["letter"], "text": ""} for o in options] or [{"letter": c, "text": ""} for c in LETTERS[:8]]
        return group

    if kind == "roman":
        group["type"] = "match"
        # the worked example: "Example  Answer" and under it "Paragraph C  iv"
        content = [l for i, l in enumerate(content) if not EXAMPLE.match(l["text"])
                   and not (i and EXAMPLE.match(content[i - 1]["text"]) and EXAMPLE_ROW.match(l["text"]))]
        headings = _headings(content, instructions)
        rest = [l for l in content if not any(l is h for h in headings[1])] if headings else content
        rest = [l for l in rest if not LIST_HEADING.match(l["text"])]
        items = _split_numbered(_joined(rest), first, last) or _split_lines(rest, first, last)
        if headings and items and all(0 < len(t) < 120 for _, t in items):
            items = [(q, re.sub(r"\s*\b(Example|Answer)\b.*$", "", t)) for q, t in items]
            return shown_as_text(options=headings[0], questions=[{"q": q, "text": t} for q, t in items])
        count = len(headings[0]) if headings else 0
        group["options"] = [{"letter": r, "text": ""} for r in ROMAN[:max(count, _roman_count(instructions), len(numbers) + 3)]]
        return group

    # words: gaps
    if TABLE_LIKE.search(all_text):
        return group  # a table or a diagram: as printed
    if NOTES_LIKE.search(all_text):
        notes = _notes(content, first, last)
        if notes:
            group["type"] = "notes"
            return shown_as_text(notes=notes)
        return group
    items = _split_numbered(text, first, last) or _split_lines(content, first, last)
    if items and all(0 < len(t) < 300 for _, t in items):
        return shown_as_text(questions=[{"q": q, "text": LEADER.sub(" … ", t).strip()} for q, t in items])
    return group


def _roman_count(instructions: list[str]) -> int:
    """"Write the correct number, i-xi, ...": 11."""
    for line in instructions:
        m = re.search(r"\bi\s*[-–—~]\s*(x{0,1}(?:ix|iv|v?i{0,3}))\b", line)
        if m and m.group(1).lower() in ROMAN:
            return ROMAN.index(m.group(1).lower()) + 1
    return 0


def _headings(content: list[dict], instructions: list[str]) -> tuple[list[dict], list[dict]] | None:
    """The list of headings (i, ii, ...): ([{"letter": "iv", "text": ...}], the lines used).
    A line without a numeral is the line above going on, or a heading whose numeral OCR lost,
    when exactly that many numerals are missing there."""
    lines = []
    for l in content:
        if re.match(r"^\d{1,2}(?!\d)", l["text"]) or EXAMPLE.match(l["text"]):
            if lines:
                break  # the questions
            continue
        if LIST_HEADING.match(l["text"]):
            continue
        lines.append(l)
    entries = []  # (index of the numeral or None, text, line)
    for l in lines:
        text = _line_text(l)
        m = ROMAN_AT.match(text)
        index = ROMAN.index(m.group(1).lower()) if m and m.group(1).lower() in ROMAN else None
        entries.append((index, m.group(2).strip() if index is not None else text, l))
    total = max(_roman_count(instructions), max((i + 1 for i, _, _ in entries if i is not None), default=0))
    if total < 2:
        return None
    out: list[dict] = []
    known = [k for k, (i, _, _) in enumerate(entries) if i is not None]
    previous_index, previous_k = -1, -1
    for k in [*known, len(entries)]:
        index = entries[k][0] if k < len(entries) else total
        between = entries[previous_k + 1:k]
        if index <= previous_index:
            return None
        missing = index - previous_index - 1
        if missing == len(between):
            out += [{"letter": ROMAN[previous_index + 1 + n], "text": t} for n, (_, t, _) in enumerate(between)]
        elif missing == 0 and out:
            out[-1]["text"] += " " + " ".join(t for _, t, _ in between)  # wrapped lines
        else:
            return None
        if k < len(entries):
            out.append({"letter": ROMAN[index], "text": entries[k][1]})
        previous_index, previous_k = index, k
    if len(out) != total or any(not o["text"] for o in out):
        return None
    for o in out:
        o["text"] = re.sub(r"\s+", " ", o["text"]).strip()
    return out, [l for _, _, l in entries]


def _passage(lines: list[dict]) -> tuple[str, list[dict]]:
    """The intro ("You should spend ...") and the passage's titles and paragraphs."""
    intro, blocks = [], []
    for line in lines:
        text = line["text"]
        if PART_HEADING.match(text) or re.fullmatch(r"READING|Reading", text.strip()):
            continue
        if READ_TEXT.match(text) and (blocks or intro):
            # the next text of a General Training section: "Read the text below and answer ..."
            blocks.append({"kind": "note", "text": text, "letter": None})
            continue
        if SPEND.match(text) or READ_TEXT.match(text) or (intro and not blocks and not line["big"] and not intro[-1].rstrip().endswith(".")):
            intro.append(text)
            continue
        kind = "title" if line["big"] else "text"
        last = blocks[-1] if blocks else None
        if last and last["kind"] == "note" and not re.search(r"[.?!]$", last["text"]):
            last["text"] += " " + text  # its second line
            continue
        new = (last is None or last["kind"] != kind or line.get("letter")
               or (kind == "text" and line.get("indent") and (text[:1].isupper() or text[:1] in "'‘\"“"))
               or (kind == "text" and line["gap"] and (re.search(r"[.?!:'\"’”)]$", last["text"]) or text[:1].isupper())))
        if new:
            blocks.append({"kind": kind, "text": text, "letter": line.get("letter")})
        elif last["text"].endswith("-") and text[:1].islower():
            last["text"] += text
        else:
            last["text"] += " " + text
    return re.sub(r"\s+", " ", " ".join(intro)).strip(), blocks


def _heading(text: str, expected: int) -> tuple[int, int] | None:
    """The questions of a group heading: "Questions 14-18", "Question 13", or "Questions 1418"
    (the dash lost: split where the group that comes next starts)."""
    m = GROUP_HEADING.match(text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = SINGLE_HEADING.match(text)
    if m:
        return int(m.group(1)), int(m.group(1))
    m = GLUED_HEADING.match(text)
    if m:
        digits, start = m.group(1), str(expected)
        if digits.startswith(start) and len(digits) > len(start):
            return expected, int(digits[len(start):])
    return None


def _part_ranges(ocr: dict[int, dict], starts: list[int]) -> list[list[int]]:
    """Each part's questions as its first page says ("You should spend about 20 minutes on
    Questions 14-27", "SECTION 1 Questions 1-14"), when they run from 1 to 40."""
    ranges = []
    for i in range(3):
        found = None
        for line in reading_order(ocr[starts[i]], starts[i]) if starts[i] in ocr else []:
            if SPEND.match(line["text"]) or PART_HEADING.match(line["text"]):
                m = PART_RANGE.search(line["text"])
                if m:
                    found = [int(m.group(1)), int(m.group(2))]
                    break
        ranges.append(found)
    expected = 1
    for r in ranges:
        if r is None or r[0] != expected or r[1] < r[0]:
            return []
        expected = r[1] + 1
    return ranges if expected == 41 else []


def build(ocr: dict[int, dict], part_pages: list[dict], sections: list[list[int]], key: dict,
          any_order: list[list[int]]) -> dict | None:
    """The test as text (see the module's docstring); None when it cannot be read for sure.
    The parts' questions come from the pages when they say (else `sections`, from the key);
    they are returned too ("sections")."""
    numbers = sorted(ocr)
    starts = [p["page"] for p in part_pages] + [numbers[-1] + 1]
    sections = _part_ranges(ocr, starts) or sections
    if len(sections) != 3 or len(part_pages) != 3:
        log.info("the parts' questions are not known")
        return None
    parts = []
    for i, (first, last) in enumerate(sections):
        lines = [l for page in numbers if starts[i] <= page < starts[i + 1] for l in reading_order(ocr[page], page)]
        headings, expected = [], first
        for at, line in enumerate(lines):
            found = _heading(line["text"], expected)
            if found and first <= found[0] <= found[1] <= last:
                # "Questions 1-7" over "Read the text below": the text's heading, not the questions'
                follow = lines[at + 1]["text"] if at + 1 < len(lines) else ""
                if not READ_TEXT.match(follow):
                    headings.append((at, *found))
                    expected = found[1] + 1
        passage_lines, groups = [], []
        cursor = 0
        for n, (at, a, b) in enumerate(headings):
            passage_lines += lines[cursor:at]
            end = headings[n + 1][0] if n + 1 < len(headings) else len(lines)
            body = lines[at + 1:end]
            # the passage goes on after the questions printed before it (a list of headings)
            stop = next((j for j, l in enumerate(body) if PART_HEADING.match(l["text"]) or SPEND.match(l["text"])
                         or READ_TEXT.match(l["text"]) or (l["big"] and j > 0 and _all_numbers(body[:j], a, b))), len(body))
            if len(_joined(passage_lines)) < 400 and a == first:
                # the questions printed before the passage (a list of headings): they end with
                # the line of their last question (and an example after it)
                last_line = next((j for j in range(len(body) - 1, -1, -1)
                                  if re.match(rf"^{b}(?!\d)", body[j]["text"]) and j < stop), None)
                if last_line is not None:
                    stop = last_line + 1
                    while stop < len(body) and (EXAMPLE.match(body[stop]["text"]) or re.match(r"^(Paragraph|Section)\s+[A-Z]\s+[ivx]+$", body[stop]["text"], re.I)):
                        stop += 1
            groups.append(_group(body[:stop], a, b, key, any_order))
            groups[-1]["instructions"] = [t for t in groups[-1]["instructions"]
                                          if not re.fullmatch(r"Example(\s+Answer)?", t.strip(), re.I)]
            groups[-1]["pictures"] = _pictures([lines[at], *body[:stop]])
            passage_lines += body[stop:]
            cursor = end
        passage_lines += lines[cursor:]
        intro, passage = _passage(passage_lines)
        # a list of headings printed before the passage, whose questions come after it: not the
        # passage's text (its group shows it as printed)
        strays = [j for j, block in enumerate(passage[:10]) if NOT_PASSAGE.match(block["text"].strip())]
        if strays:
            start = next((j for j in range(strays[-1] + 1, len(passage))
                          if passage[j]["kind"] == "title" or len(passage[j]["text"]) >= 300), len(passage))
            passage = passage[start:]
        covered = [q for g in groups for q in range(g["first"], g["last"] + 1)]
        if covered != list(range(first, last + 1)):
            log.info("part %d: the questions' headings cover %s, not %d-%d", i + 1,
                     [(g["first"], g["last"]) for g in groups], first, last)
            return None  # a group heading was not read: the text cannot be trusted
        if any(g.get("doubtful") for g in groups):
            return {"doubtful": True}
        for g in groups:
            for picture in g["pictures"]:
                w, h = ocr[picture["page"]]["size"]
                x0, y0, x1, y1 = picture["box"]
                picture["box"] = [round(max(0, x0) / w, 4), round(max(0, y0) / h, 4), round(min(w, x1) / w, 4), round(min(h, y1) / h, 4)]
        parts.append({"part": i + 1, "first": first, "last": last, "pages": [p for p in numbers if starts[i] <= p < starts[i + 1]],
                      "intro": intro, "passage": passage, "groups": groups})
    return {"parts": parts, "sections": sections}


def _all_numbers(lines: list[dict], first: int, last: int) -> bool:
    return _split_numbered(_masked(_joined(lines)), first, last) is not None
