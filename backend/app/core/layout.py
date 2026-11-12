"""A scanned page's OCR lines in reading order, for pages printed in columns (the passages and
questions of the Reading test).

The OCR (pages.ocr_boxes) gives a box per line of text in no useful order. reading_order()
splits the page the way it was laid out (a recursive XY-cut): at the widest gutter between
columns first, then at the gaps between paragraphs, and so on inside each piece, so text in two
or three columns under a full-width title reads title, then the first column, then the next.
Letters in the margin (the paragraphs "A", "B", ...) do not make a column of their own: they
join the line beside them.

A line is {"text", "box": [x0, y0, x1, y1], "page", "gap"}; "gap" is True when a space wider
than a line comes before it (a new paragraph).
"""
import re
import statistics
import unicodedata

CJK = re.compile(r"[　-鿿가-힯]+")
MARGIN_LETTER = re.compile(r"^[A-Z]$")


def clean(text: str) -> str:
    return CJK.sub("", unicodedata.normalize("NFKC", text)).strip()


def _gaps(spans: list[tuple[float, float]], low: float, high: float, least: float) -> list[tuple[float, float]]:
    """The empty stretches, at least `least` long, between `low` and `high` that no span covers."""
    found, reach = [], low
    for a, b in sorted(spans):
        if a - reach >= least:
            found.append((reach, a))
        reach = max(reach, b)
    return [g for g in found if g[0] > low]  # a gap at the very start is a margin, not a gutter


def _gutter(body: list[list], left: float, right: float, width: float, line: float):
    """The best place to split between columns: a vertical stretch at least `least` wide that
    only a few boxes cross (OCR now and then reads two lines across a narrow gutter as one).
    Returns (x, crossing boxes) or None."""
    if len(body) < 4:
        return None
    step = 2
    xs = range(int(left) // step * step, int(right) + 1, step)
    cover = dict.fromkeys(xs, 0)
    for b in body:
        for x in range(int(b[0]) - int(b[0]) % step, int(b[2]) + 1, step):
            if x in cover:
                cover[x] += 1
    allowed = max(2, len(body) // 8)
    least = max(width * 0.005, line * 0.2)
    runs, start = [], None
    for x in [*xs, None]:
        if x is not None and cover[x] <= allowed:
            start = x if start is None else start
        elif start is not None:
            end = (x if x is not None else right) - step
            if end - start >= least and start - left > width * 0.12 and right - end > width * 0.12:
                runs.append((max(cover[v] for v in range(start, end + 1, step)), -(end - start), start, end))
            start = None
    if not runs:
        return None
    _, _, a, b = min(runs)
    return (a + b) / 2, [x for x in body if x[0] < a and x[2] > b]


def _halves(box: list, split: float) -> list[list]:
    """A box OCR read across the gutter, cut at the gutter (at the nearest space)."""
    text = box[4]
    at = round(len(text) * (split - box[0]) / (box[2] - box[0]))
    spaces = [i for i, c in enumerate(text) if c == " "]
    if spaces:
        near = min(spaces, key=lambda i: abs(i - at))
        at = near if abs(near - at) <= 10 else at
    first, second = text[:at].strip(), text[at:].strip()
    return [b for b in ([box[0], box[1], split, box[3], first], [split, box[1], box[2], box[3], second]) if b[4]]


def _cut(boxes: list[list], width: float, line: float, depth: int = 0) -> list[list[list]]:
    """Boxes in reading order, as groups of rows (a row: boxes on one line, left to right)."""
    if len(boxes) <= 1 or depth > 14:
        return _rows(boxes, line)
    left, right = min(b[0] for b in boxes), max(b[2] for b in boxes)
    # columns: the gutter, ignoring the letters in the margin
    body = [b for b in boxes if not MARGIN_LETTER.match(b[4])]
    found = _gutter(body, left, right, width, line)
    if found:
        split, crossing = found
        others = [b for b in body if b not in crossing]

        def merged(box) -> bool:
            """Columns go on above it and below it on both sides: two lines OCR ran together.
            Otherwise it is a title above the columns (or a line under them)."""
            return all(sum(1 for o in others if side(o) and where(o)) >= 2
                       for side in (lambda o: o[2] <= split, lambda o: o[0] >= split)
                       for where in (lambda o: o[3] <= box[1] + line * 0.5, lambda o: o[1] >= box[3] - line * 0.5))

        titles = [b for b in crossing if not merged(b)]
        if titles:  # cut across the page at the first title
            title = min(titles, key=lambda b: b[1])
            above = [b for b in boxes if (b[1] + b[3]) / 2 < title[1]]
            row = [b for b in boxes if b not in above and (b[1] + b[3]) / 2 <= title[3]]
            below = [b for b in boxes if b not in above and b not in row]
            return [*_cut(above, width, line, depth + 1), *_rows(row, line), *_cut(below, width, line, depth + 1)]
        pieces = [h for b in boxes for h in (_halves(b, split) if b in crossing else [b])]
        first = [x for x in pieces if (x[0] + x[2]) / 2 < split]
        second = [x for x in pieces if (x[0] + x[2]) / 2 >= split]
        if first and second:
            return _cut(first, width, line, depth + 1) + _cut(second, width, line, depth + 1)
    # paragraphs: horizontal gaps taller than half a line
    top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
    gaps = _gaps([(b[1], b[3]) for b in boxes], top, bottom, line * 0.5)
    if gaps:
        pieces, cuts = [], [top, *[(a + b) / 2 for a, b in gaps], bottom + 1]
        for a, b in zip(cuts, cuts[1:]):
            piece = [x for x in boxes if a <= (x[1] + x[3]) / 2 < b]
            if piece:
                pieces += _cut(piece, width, line, depth + 1)
        if len(pieces) > 1:
            return pieces
    return _rows(boxes, line)


def _rows(boxes: list[list], line: float) -> list[list[list]]:
    """One group: its boxes as rows, top to bottom; a box joins a row it overlaps by half a line.
    A letter in the margin joins the row nearest to it."""
    letters = [b for b in boxes if MARGIN_LETTER.match(b[4])]
    rows: list[list] = []
    for b in sorted((b for b in boxes if b not in letters), key=lambda b: (b[1] + b[3]) / 2):
        middle = (b[1] + b[3]) / 2
        if rows and rows[-1][0][1] <= middle <= rows[-1][0][3]:
            rows[-1].append(b)
        else:
            rows.append([b])
    for b in letters:
        middle = (b[1] + b[3]) / 2
        near = min(rows, key=lambda r: abs((r[0][1] + r[0][3]) / 2 - middle), default=None)
        if near is not None and abs((near[0][1] + near[0][3]) / 2 - middle) < line:
            near.append(b)
        else:
            rows.append([b])
    rows.sort(key=lambda r: min((x[1] + x[3]) / 2 for x in r))
    return [[sorted(r, key=lambda b: b[0]) for r in rows]] if rows else []


LETTER_FIRST = re.compile(r"^([A-Z])\s+(?=[A-Z\"'(‘“])")


def _margin_letter(box: list, boxes: list[list], line: float) -> list[list]:
    """A paragraph's letter read as part of its first line ("A In 1942 ..."): the letter and the
    line apart. It is one when the line starts with a capital on its own and the next line
    starts further in, where the first line's text does."""
    m = LETTER_FIRST.match(box[4])
    if not m:
        return [box]
    under = [b for b in boxes if 0 < b[1] - box[1] < 2 * line and line * 0.5 < b[0] - box[0] < line * 2.5
             and not LETTER_FIRST.match(b[4])]
    if not under:
        return [box]
    start = min(b[0] for b in under)
    return [[box[0], box[1], box[0] + line * 0.5, box[3], m.group(1)], [start, box[1], box[2], box[3], box[4][m.end():]]]


# Running headers and page numbers ("Test 4", "Reading", "88") at the top or bottom of a page.
RUNNING = re.compile(r"^(Test\s*\d+|Reading|Listening|Writing|Speaking|General\s*Training|Academic|\d{1,3})$", re.I)
WATERMARK = re.compile(r"www\.|\.(com|ir|net|org)\b", re.I)


def reading_order(page: dict, number: int) -> list[dict]:
    """A page's lines in reading order (see the module's docstring); `number` is the page's
    number in the book, kept with each line. A line also says whether it is in larger print than
    most ("big": a title) and the letter in the margin before it, if any ("letter")."""
    width, height = page["size"]
    boxes = [[*b[:4], clean(b[4])] for b in page["boxes"]]
    boxes = [b for b in boxes if b[4] and not WATERMARK.search(b[4])]
    if not boxes:
        return []
    line = statistics.median(b[3] - b[1] for b in boxes)
    # a big slanted watermark: taller and much wider than a line, and tall for its width (a
    # title in large print is not: its box is flat)
    boxes = [b for b in boxes if not (b[3] - b[1] > 2.5 * line and b[2] - b[0] > 4 * line
                                      and b[3] - b[1] > 0.2 * (b[2] - b[0]))]
    # running headers and page numbers: near the page's edge, or its first or last line when
    # the scan has wide margins
    top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
    edge = [b for b in boxes if (b[1] + b[3]) / 2 < height * 0.08 or (b[1] + b[3]) / 2 > height * 0.93
            or b[1] < top + line * 0.6 or b[3] > bottom - line * 0.6]
    boxes = [b for b in boxes if not (b in edge and RUNNING.match(re.sub(r"\s+", " ", b[4])))]
    boxes = [piece for b in boxes for piece in _margin_letter(b, boxes, line)]
    out = []
    for group in _cut(boxes, width, line):
        left = min((b[0] for row in group for b in row if not MARGIN_LETTER.match(b[4])), default=group[0][0][0])
        for i, row in enumerate(group):
            words = [b for b in row if not MARGIN_LETTER.match(b[4])]
            letter = row[0][4] if len(row) > 1 and MARGIN_LETTER.match(row[0][4]) and words else None
            out.append({
                "text": " ".join(b[4] for b in row if not (letter and b is row[0])),
                "box": [min(b[0] for b in row), min(b[1] for b in row), max(b[2] for b in row), max(b[3] for b in row)],
                "page": number,
                "gap": i == 0,
                "big": bool(words) and statistics.median(b[3] - b[1] for b in words) > 1.3 * line,
                "letter": letter,
                # the first line of a paragraph, printed further in than the column
                "indent": min(b[0] for b in (words or row)) > left + 0.8 * line,
            })
    return out
