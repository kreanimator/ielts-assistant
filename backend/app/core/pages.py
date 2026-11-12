"""Reads the pages of your own IELTS books (PDF), for every module's importer.

Each page's text comes from the PDF's text layer, or by OCR for scanned pages (the page
is rendered with PDFium and read by RapidOCR, about 1 s per page). The texts are cached
in data/private/books/<book>.pages.json (git-ignored), so a second import skips the slow
reading. Never commit or share these files: the books are copyrighted.
"""
import json
import logging
import re
from pathlib import Path

from . import config

log = logging.getLogger("ielts.pages")


def books_dir() -> Path:
    return config.DATA_DIR / "private" / "books"


def slug(path: Path) -> str:
    name = re.sub(r"\[.*?\]", "", path.stem)  # drop "[www.site.com]" tags
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def title(path: Path) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\[.*?\]", "", path.stem)).strip(" -")


def cache_path(path: Path) -> Path:
    return books_dir() / f"{slug(path)}.pages.json"


def read(path: Path) -> list[str]:
    """The text of every page: from the cache, or read from the PDF (and then cached)."""
    cache = cache_path(path)
    if cache.exists():
        return json.loads(cache.read_text())
    texts = page_texts(path)
    save(path, texts)
    return texts


def save(path: Path, texts: list[str]) -> None:
    """Caches the page texts, for example after a module has re-read some pages with OCR."""
    books_dir().mkdir(parents=True, exist_ok=True)
    cache_path(path).write_text(json.dumps(texts, ensure_ascii=False))


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
    """The OCR text of the given pages (0-based), one by one."""
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


def ocr_boxes(path: Path, pages: list[int], width: int = 1000) -> dict[int, dict]:
    """OCR with positions, for pages printed in columns (the answer keys), each page rendered
    `width` pixels wide: its image size and its lines of text with their boxes,
    {page: {"size": [w, h], "boxes": [[x0, y0, x1, y1, text]]}}."""
    import numpy as np
    import pypdfium2
    from rapidocr import RapidOCR

    engine = RapidOCR(params={"Global.log_level": "warning"})
    pdf = pypdfium2.PdfDocument(path)
    found = {}
    for i in pages:
        image = pdf[i].render(scale=width / pdf[i].get_width()).to_pil().convert("RGB")
        result = engine(np.array(image))
        boxes = result.boxes if result.boxes is not None else []
        found[i] = {"size": list(image.size),
                    "boxes": [[float(b[0][0]), float(b[0][1]), float(b[2][0]), float(b[2][1]), text]
                              for b, text in zip(boxes, result.txts or [])]}
    return found


def render(path: Path, pages: list[int], folder: Path, width: int = 1400) -> None:
    """Saves the pages as pictures (folder/<page>.jpg, `width` pixels wide), for the modules that
    show the book's own pages (Reading: the passages with their tables and diagrams)."""
    import pypdfium2

    folder.mkdir(parents=True, exist_ok=True)
    pdf = pypdfium2.PdfDocument(path)
    for i in pages:
        page = pdf[i]
        image = page.render(scale=width / page.get_width()).to_pil().convert("RGB")
        image.save(folder / f"{i}.jpg", quality=82, optimize=True)
