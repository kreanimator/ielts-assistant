"""The Reading test: three passages (Academic) or three sections (General Training) and 40
questions in 60 minutes, timed on the server (core/timed.py), marked with the book's answer key.

- start() chooses a test from your books and stores it with the deadline in the session's
  details: {"book", "test", "kind", "title", "pages", "parts", "sections", "minutes", "deadline",
  "answers": {"1": "...", ...}, "saved_at", "finished"}. The key stays on the server.
- The app saves your answers every few seconds (save()); none are accepted after the deadline.
- finish() turns the last saved answers into the session's answer; build() writes the report:
  each answer marked, the raw score (out of 40) and its band from the official table.
"""
import os
import random

from fastapi import HTTPException

from ..core import answer_keys, storage, timed
from ..core.bands import raw_band
from ..core.timed import TimeUp  # noqa: F401 (the router catches it)
from . import books

MINUTES = int(os.environ.get("READING_TEST_MINUTES", "60"))  # shorter for testing the app
KINDS = {"academic": "Academic", "general": "General Training"}


def choose(book: str | None, test: str | None, kind: str | None) -> dict:
    """That test, or a random one (of that kind, if given)."""
    if book and test:
        found = books.find_test(book, test)
        if found is None:
            raise LookupError("No such Reading test in your books")
        return found
    tests = [{**t, "book": b["id"], "book_title": b["title"]} for b in books.load_books() for t in b["tests"]
             if (not book or b["id"] == book) and (not kind or t["kind"] == kind)]
    if not tests:
        raise LookupError("No Reading tests in your books yet: import them with make books")
    return random.choice(tests)


def start(book: str | None = None, test: str | None = None, kind: str | None = None) -> dict:
    chosen = choose(book, test, kind)
    title = f"{chosen['book_title']}, Test {chosen['test']} ({KINDS[chosen['kind']]} Reading)"
    session = storage.create_session("reading", "test", title, "", "answer key")
    storage.add_message(session, "examiner", title)
    storage.set_details(session, {
        "book": chosen["book"], "test": chosen["test"], "kind": chosen["kind"], "title": title,
        "pages": chosen["pages"], "parts": chosen["parts"], "sections": chosen.get("sections") or [],
        "minutes": MINUTES, "deadline": timed.deadline(MINUTES),
        "answers": {}, "saved_at": None, "finished": False,
    })
    return state(session)


def state(session_id: str) -> dict | None:
    """The test as the app shows it; a test whose time ran out is finished first."""
    session = storage.get_session(session_id)
    if session is None or session["module"] != "reading" or not session["details"]:
        return None
    details = session["details"]
    if timed.expired(details):
        details = finish(session_id)
    found = books.find_test(details["book"], details["test"])
    return {
        "session": session_id,
        "title": details["title"],
        "book": details["book"],
        "test": details["test"],
        "kind": details["kind"],
        "pages": details["pages"],
        "parts": details["parts"],
        "sections": details.get("sections") or [],
        "questions": 40,
        "content": found and found.get("content"),  # the text: from the book, never the key
        "minutes": details["minutes"],
        "answers": details["answers"],
        "seconds_left": max(0, round(timed.seconds_left(details))),
        "finished": details["finished"],
    }


def save(session_id: str, answers: dict[str, str]) -> dict:
    """Stores the answers ({"1": "...", ...}, any of them). Raises TimeUp after the deadline."""
    details = storage.get_session(session_id)["details"]
    if not timed.in_time(details):
        raise TimeUp()
    details["answers"].update({q: a.strip()[:200] for q, a in answers.items() if q.isdigit() and 1 <= int(q) <= 40})
    details["saved_at"] = timed.now().isoformat()
    storage.set_details(session_id, details)
    return {"seconds_left": max(0, round(timed.seconds_left(details))), "saved": True}


def finish(session_id: str) -> dict:
    """Ends the test: the last saved answers become the session's answer. Safe to call twice."""
    details = storage.get_session(session_id)["details"]
    if details["finished"]:
        return details
    answers = {q: a for q, a in details["answers"].items() if a}
    text = "\n".join(f"{q}. {answers.get(str(q), '')}" for q in range(1, 41))
    storage.add_message(session_id, "candidate", text, answer=0)
    storage.set_answer_field(session_id, 0, "delivery", {"answers": answers, "test_seconds": timed.seconds_taken(details)})
    details["finished"] = True
    storage.set_details(session_id, details)
    return details


async def build(session: dict) -> dict:
    """The report: each answer marked with the key, the raw score and the band."""
    details = session["details"]
    if details and timed.expired(details):
        finish(session["id"])
        session = storage.get_session(session["id"])
        details = session["details"]
    if not details or not details["finished"]:
        raise HTTPException(409, "This test is still in progress: finish it first")
    found = books.find_test(details["book"], details["test"])
    if found is None:
        raise HTTPException(404, "This test's answer key is gone: import your books again")
    answers = details["answers"]
    right = answer_keys.mark({"answers": found["key"], "any_order": found["any_order"]}, answers)
    raw = sum(right.values())
    table = "reading-academic" if details["kind"] == "academic" else "reading-general"
    band = raw_band(table, raw)
    sections = found.get("sections") or []  # empty when the parts' questions were not found
    questions = [{"q": int(q), "given": answers.get(q, ""), "key": found["key"][q], "right": right[q]}
                 for q in sorted(found["key"], key=int)]
    return {
        "enough": True,
        "overall": band,
        "raw": raw,
        "of": len(questions),
        "kind": details["kind"],
        "questions": questions,
        "any_order": found["any_order"],
        "parts": [{"first": first, "last": last, "right": sum(right[str(q)] for q in range(first, last + 1)),
                   "of": last - first + 1} for first, last in sections],
        "note": (f"{raw} of {len(questions)} answers right: band {band:g} on the official "
                 f"{KINDS[details['kind']]} Reading table."),
        "criteria": [],
        "strengths": [],
        "priorities": [],
    }
