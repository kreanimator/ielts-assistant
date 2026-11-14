"""Imports the recordings of your own IELTS books (their CDs, as audio files), and loads their
Listening tests.

    python -m app.listening.books "path/to/the folder with your books' recordings"
                                              (make listening-books AUDIO=...)

A Listening test needs three things:

1. Its recordings. The folder given is searched for a folder of each imported book (its
   number in the name: "Cambridge IELTS 10"), and that one for audio files. tracks() works out
   which file is which test and part, from the names ("Test 3 Section 2", "test1_audio4") or,
   for CD tracks without names, from their order (four parts a test, four tests). They are
   copied to data/private/books/<book>/listening/ and listed in <book>.listening.json with
   their lengths, so the app needs neither the disk nor the CDs again. A browser plays MP3 and
   M4A (AAC) files; WMA files are named and left out (convert them to MP3 first).
2. Its questions as text. They come from core/web_tests.py (make web-tests): OCR does not read
   the forms, tables and maps of the Listening pages. A test without them is left out.
3. Its answer key: the book's own (core/answer_keys.py) when all 40 answers were read for
   sure, else the web page's answers (see web_tests.choosable).

Never commit or share these files: the books and their recordings are copyrighted.
"""
import json
import logging
import re
import shutil
import struct
import sys
from pathlib import Path

from ..core import answer_keys, pages, web_tests

log = logging.getLogger("ielts.listening.books")

PLAYABLE = {".mp3", ".m4a", ".aac", ".ogg", ".wav"}
OTHER_AUDIO = {".wma", ".flac", ".ape", ".ra"}
NAMED = re.compile(r"test\s*[_ -]?\s*(\d{1,2})\D{0,3}?(?:section|part|audio|sec|s|p)\s*[_ -]?\s*(\d)(?!\d)", re.I)
WHOLE = re.compile(r"test\s*[_ -]?\s*(\d{1,2})(?!\d)", re.I)
MEDIA = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg", ".wav": "audio/wav"}


def folder(book_id: str) -> Path:
    return pages.books_dir() / book_id / "listening"


def _natural(path: Path) -> list:
    """Sorts "Track 2" before "Track 10", a CD's folder before its files."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", str(path))]


def tracks(files: list[Path]) -> dict[str, list[tuple[int, Path]]]:
    """Which file is which: {"1": [(1, path), (2, path), (3, path), (4, path)], ...}, the test
    and its parts; a test recorded as one file is {"1": [(0, path)]}. {} when it cannot be told.

    - Names that say it: "IELTS 10 Test 3 Section 2", "Test1,Part4", "ielts15_test2_audio3".
      A set numbered 5 to 8 (the second book of a pair) is tests 1 to 4.
    - "ielts 2 Test 3": one file a test.
    - Tracks without names: in order, four parts a test. Short tracks (a CD's introduction)
      are not parts."""
    files = sorted(files, key=_natural)
    named = [(NAMED.search(f.stem), f) for f in files]
    if files and all(m for m, _ in named):
        found: dict[int, list[tuple[int, Path]]] = {}
        for m, f in named:
            found.setdefault(int(m.group(1)), []).append((int(m.group(2)), f))
        shift = min(found) - 1 if min(found) > 4 else 0
        if all(sorted(p for p, _ in parts) == [1, 2, 3, 4] for parts in found.values()):
            return {str(t - shift): sorted(parts) for t, parts in sorted(found.items())}
        return {}
    whole = [(WHOLE.search(f.stem), f) for f in files]
    if files and all(m for m, _ in whole) and len({m.group(1) for m, _ in whole}) == len(files):
        return {m.group(1): [(0, f)] for m, f in whole}
    sizes = sorted(f.stat().st_size for f in files)
    usual = sizes[len(sizes) // 2] if sizes else 0
    parts = [f for f in files if f.stat().st_size >= 0.3 * usual]
    if parts and len(parts) % 4 == 0 and len(parts) <= 16:
        return {str(i // 4 + 1): [(n + 1, f) for n, f in enumerate(parts[i:i + 4])] for i in range(0, len(parts), 4)}
    return {}


# ---------------------------------------------------------------- how long a recording is

MP3_BITRATES = {  # kbit/s by the header's index: MPEG-1 Layer III, and MPEG-2/2.5 Layer III
    3: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
}
MP3_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def seconds(path: Path) -> float:
    """The length of an MP3 or M4A recording, read from the file itself (0 if it cannot be)."""
    try:
        return _m4a_seconds(path) if path.suffix.lower() in (".m4a", ".aac") else _mp3_seconds(path)
    except (OSError, struct.error, ValueError, IndexError, ZeroDivisionError):
        return 0.0


def _mp3_seconds(path: Path) -> float:
    """Every frame's length added up (the files are small, and a variable bit rate has no
    other honest answer); a "Xing"/"Info" header with the number of frames is used if there."""
    data = path.read_bytes()
    at = 0
    if data[:3] == b"ID3":  # the tag before the sound: its size is 4 bytes of 7 bits
        at = 10 + (data[6] << 21 | data[7] << 14 | data[8] << 7 | data[9])
    total, frames, end = 0.0, 0, len(data) - 4
    while at < end:
        if data[at] != 0xFF or data[at + 1] & 0xE0 != 0xE0:
            at += 1
            continue
        version, layer = data[at + 1] >> 3 & 3, data[at + 1] >> 1 & 3
        bitrate_index, rate_index, padding = data[at + 2] >> 4, data[at + 2] >> 2 & 3, data[at + 2] >> 1 & 1
        if version == 1 or layer != 1 or bitrate_index in (0, 15) or rate_index == 3:
            at += 1
            continue
        bitrate = MP3_BITRATES[3 if version == 3 else 2][bitrate_index] * 1000
        rate = MP3_RATES[version][rate_index]
        samples = 1152 if version == 3 else 576
        length = samples // 8 * bitrate // rate + padding
        if frames == 0:
            head = data[at:at + 200]
            for tag in (b"Xing", b"Info"):
                i = head.find(tag)
                if i >= 0 and head[i + 7] & 1:
                    return struct.unpack(">I", head[i + 8:i + 12])[0] * samples / rate
        total += samples / rate
        frames += 1
        at += max(length, 1)
    return total


def _m4a_seconds(path: Path) -> float:
    """The movie header's duration ("moov" > "mvhd")."""
    with path.open("rb") as f:
        def boxes(stop: int):
            while f.tell() < stop:
                start = f.tell()
                size, kind = struct.unpack(">I4s", f.read(8))
                if size == 1:
                    size = struct.unpack(">Q", f.read(8))[0]
                elif size == 0:
                    size = stop - start
                yield kind, start + size
                f.seek(start + size)

        end = path.stat().st_size
        for kind, stop in boxes(end):
            if kind == b"moov":
                for inner, _ in boxes(stop):
                    if inner == b"mvhd":
                        version = f.read(4)[0]
                        if version == 1:
                            f.read(16)
                            scale, length = struct.unpack(">IQ", f.read(12))
                        else:
                            f.read(8)
                            scale, length = struct.unpack(">II", f.read(8))
                        return length / scale
    return 0.0


# ---------------------------------------------------------------- importing

def book_folders(root: Path) -> dict[int, Path]:
    """The folders under `root` (or `root` itself) named with a book's number, by that number:
    "Cambridge IELTS 10" → 10. The last number in the name counts ("IELTS 7 CD" has one)."""
    found = {}
    for path in [root, *sorted(p for p in root.iterdir() if p.is_dir())]:
        numbers = re.findall(r"(?<!\d)\d{1,2}(?!\d)", path.name)
        if numbers and re.search(r"ielts", path.name, re.I):
            found.setdefault(int(numbers[-1]), path)
    return found


def import_book(book_id: str, source: Path) -> dict | None:
    """Copies a book's recordings from `source` and writes <book>.listening.json; None (and
    why) when its files cannot be told apart."""
    every = [p for p in source.rglob("*") if p.is_file()]
    other = [p for p in every if p.suffix.lower() in OTHER_AUDIO]
    files = [p for p in every if p.suffix.lower() in PLAYABLE]
    if not files:
        kinds = ", ".join(sorted({p.suffix.lower().lstrip(".").upper() for p in other}))
        print(f"{book_id}: " + (f"its recordings are {kinds} files, which a browser cannot play: "
                                "convert them to MP3 and import again" if other else "no recordings found"))
        return None
    found = tracks(files)
    if not found:
        print(f"{book_id}: {len(files)} recordings, but which test and part each is cannot be told from "
              "their names or their order")
        return None
    target = folder(book_id)
    target.mkdir(parents=True, exist_ok=True)
    tests = []
    for test, parts in found.items():
        audio = []
        for part, path in parts:
            name = f"{test}-{part}{path.suffix.lower()}" if part else f"{test}{path.suffix.lower()}"
            if not (target / name).exists() or (target / name).stat().st_size != path.stat().st_size:
                shutil.copyfile(path, target / name)
            audio.append({"part": part, "file": name, "seconds": round(seconds(target / name), 1)})
        if any(a["seconds"] < 60 for a in audio):
            print(f"{book_id} test {test}: a recording's length could not be read: left out")
            continue
        tests.append({"test": test, "audio": audio})
    book = {"id": book_id, "title": _title(book_id), "tests": tests}
    (pages.books_dir() / f"{book_id}.listening.json").write_text(json.dumps(book, ensure_ascii=False, indent=1))
    return book


def _title(book_id: str) -> str:
    speaking = pages.books_dir() / f"{book_id}.json"
    return json.loads(speaking.read_text())["title"] if speaking.exists() else book_id


# ---------------------------------------------------------------- the tests

def load_books() -> list[dict]:
    """The books' Listening tests that can be taken: with their recordings, their questions as
    text and their key. Each test: {"test", "audio": [{"part", "file", "seconds"}], "sections",
    "key", "any_order", "content"} (content: as reading/content.py, each part with its
    "transcript")."""
    if not pages.books_dir().exists():
        return []
    books = []
    for path in sorted(pages.books_dir().glob("*.listening.json")):
        book = json.loads(path.read_text())
        web = {t["test"]: t for t in web_tests.load(book["id"], "listening")}
        keys = (answer_keys.load_keys(book["id"]) or {"tests": {}})["tests"]
        tests = []
        for test in book["tests"]:
            found = web.get(test["test"])
            if found is None:
                continue
            key = keys.get(test["test"], {}).get("listening")
            sure = key is not None and len(key["answers"]) == 40 and not key.get("doubtful")
            tests.append({**test, "sections": found["sections"], "content": found["content"],
                          "key": web_tests.choosable(key["answers"], found) if sure else found["key"],
                          "any_order": web_tests.merged(key["any_order"] if sure else [], found["any_order"])})
        if tests:
            books.append({**book, "tests": tests})
    return sorted(books, key=lambda b: b["title"])


def find_test(book_id: str, test: str) -> dict | None:
    """One test, with its book's id and title."""
    for book in load_books():
        if book["id"] == book_id:
            found = next((t for t in book["tests"] if t["test"] == test), None)
            return found and {**found, "book": book["id"], "book_title": book["title"]}
    return None


def audio_file(book_id: str, name: str) -> tuple[Path, str] | None:
    """A recording of an imported test and its media type."""
    for book in load_books():
        if book["id"] == book_id and any(a["file"] == name for t in book["tests"] for a in t["audio"]):
            path = folder(book_id) / name
            return (path, MEDIA.get(path.suffix, "application/octet-stream")) if path.is_file() else None
    return None


def main(args: list[str]) -> None:
    if len(args) != 1 or not Path(args[0]).expanduser().is_dir():
        sys.exit(__doc__)
    folders = book_folders(Path(args[0]).expanduser())
    mine = web_tests.my_books()
    if not mine:
        sys.exit("Import your books first (make books)")
    for number, ids in sorted(mine.items()):
        book_id = web_tests.book_for(ids, "listening")
        if number not in folders:
            print(f"{book_id}: no folder with its number under {args[0]}")
            continue
        book = import_book(book_id, folders[number])
        if book:
            ready = next((len(b["tests"]) for b in load_books() if b["id"] == book_id), 0)
            minutes = sum(a["seconds"] for t in book["tests"] for a in t["audio"]) / 60
            print(f"{book['title']}: recordings of {len(book['tests'])} tests ({minutes:.0f} minutes); "
                  f"{ready} can be taken" + ("" if ready == len(book["tests"]) else
                                             " (the others have no questions as text: make web-tests)"), flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main(sys.argv[1:])
