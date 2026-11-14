"""The Listening test: four recordings played once and 40 questions, marked with the answer key.

As in the computer-delivered test, the recordings cannot be paused or played again, and there
are two minutes at the end to check the answers. So the clock is the recording's:

- start() chooses a test and stores it in the session's details: {"book", "test", "title",
  "audio": [{"part", "file", "seconds"}], "sections", "minutes", "deadline", "started_at",
  "answers", "saved_at", "finished"}. Nothing runs yet: the app shows "Play" first.
- play() starts the clock (once): the deadline is the recordings' length plus CHECK_SECONDS.
  From then on state() says how many seconds have gone ("elapsed"), and the app plays the
  recording from there, also after a reload: time that passed is not played again.
- The app saves the answers every few seconds (save()); none are accepted after the deadline.
- finish() turns the last saved answers into the session's answer; build() writes the report:
  each answer marked, the raw score (out of 40) and its band from the official table.

The key and the transcripts stay on the server until the test is finished; then state() gives
the transcripts too, to read what was said.
"""
import os
import random

from fastapi import HTTPException

from ..core import answer_keys, storage, timed
from ..core.bands import raw_band
from ..core.timed import TimeUp  # noqa: F401 (the router catches it)
from . import books

CHECK_SECONDS = float(os.environ.get("LISTENING_CHECK_SECONDS", "120"))  # to check the answers at the end
# For trying the app: stop each test after this many seconds of recording (0: the whole of it).
TRIAL_SECONDS = float(os.environ.get("LISTENING_TEST_SECONDS", "0"))


def choose(book: str | None, test: str | None) -> dict:
    """That test, or a random one (of that book, if given)."""
    if book and test:
        found = books.find_test(book, test)
        if found is None:
            raise LookupError("No such Listening test in your books")
        return found
    tests = [{**t, "book": b["id"], "book_title": b["title"]} for b in books.load_books() for t in b["tests"]
             if not book or b["id"] == book]
    if not tests:
        raise LookupError("No Listening tests yet: import your books' recordings with make listening-books")
    return random.choice(tests)


def start(book: str | None = None, test: str | None = None) -> dict:
    chosen = choose(book, test)
    title = f"{chosen['book_title']}, Test {chosen['test']} (Listening)"
    session = storage.create_session("listening", "test", title, "", "answer key")
    storage.add_message(session, "examiner", title)
    length = sum(a["seconds"] for a in chosen["audio"])
    if TRIAL_SECONDS:
        length = min(length, TRIAL_SECONDS)
    storage.set_details(session, {
        "book": chosen["book"], "test": chosen["test"], "title": title, "audio": chosen["audio"],
        "sections": chosen["sections"], "minutes": (length + CHECK_SECONDS) / 60, "recording_seconds": length,
        "deadline": None, "started_at": None, "answers": {}, "saved_at": None, "finished": False,
    })
    return state(session)


def play(session_id: str) -> dict:
    """Starts the recording's clock, the first time; later calls change nothing."""
    details = storage.get_session(session_id)["details"]
    if details["started_at"] is None and not details["finished"]:
        details["started_at"] = timed.now().isoformat()
        details["deadline"] = timed.deadline(details["minutes"])
        storage.set_details(session_id, details)
    return state(session_id)


def _running(details: dict) -> bool:
    return details["started_at"] is not None


def state(session_id: str) -> dict | None:
    """The test as the app shows it; a test whose time ran out is finished first."""
    session = storage.get_session(session_id)
    if session is None or session["module"] != "listening" or not session["details"]:
        return None
    details = session["details"]
    if _running(details) and timed.expired(details):
        details = finish(session_id)
    found = books.find_test(details["book"], details["test"])
    content = found and found.get("content")
    if content and not details["finished"]:  # what is said: only after the test
        content = {**content, "parts": [{k: v for k, v in p.items() if k != "transcript"} for p in content["parts"]]}
    total = details["minutes"] * 60
    left = timed.seconds_left(details) if _running(details) else total
    return {
        "session": session_id,
        "title": details["title"],
        "book": details["book"],
        "test": details["test"],
        "audio": details["audio"],
        "recording_seconds": details["recording_seconds"],
        "check_seconds": CHECK_SECONDS,
        "sections": details["sections"],
        "questions": 40,
        "content": content,
        "started": _running(details),
        "elapsed": round(max(0.0, total - left), 1),
        "answers": details["answers"],
        "seconds_left": max(0, round(left)),
        "finished": details["finished"],
    }


def save(session_id: str, answers: dict[str, str]) -> dict:
    """Stores the answers ({"1": "...", ...}, any of them). Raises TimeUp after the deadline."""
    details = storage.get_session(session_id)["details"]
    if details["finished"] or _running(details) and not timed.in_time(details):
        raise TimeUp()
    details["answers"].update({q: a.strip()[:200] for q, a in answers.items() if q.isdigit() and 1 <= int(q) <= 40})
    details["saved_at"] = timed.now().isoformat()
    storage.set_details(session_id, details)
    left = timed.seconds_left(details) if _running(details) else details["minutes"] * 60
    return {"seconds_left": max(0, round(left)), "saved": True}


def finish(session_id: str) -> dict:
    """Ends the test: the last saved answers become the session's answer. Safe to call twice."""
    details = storage.get_session(session_id)["details"]
    if details["finished"]:
        return details
    answers = {q: a for q, a in details["answers"].items() if a}
    text = "\n".join(f"{q}. {answers.get(str(q), '')}" for q in range(1, 41))
    storage.add_message(session_id, "candidate", text, answer=0)
    taken = timed.seconds_taken(details) if _running(details) else 0
    storage.set_answer_field(session_id, 0, "delivery", {"answers": answers, "test_seconds": taken})
    details["finished"] = True
    storage.set_details(session_id, details)
    return details


async def build(session: dict) -> dict:
    """The report: each answer marked with the key, the raw score and the band."""
    details = session["details"]
    if details and _running(details) and timed.expired(details):
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
    band = raw_band("listening", raw)
    questions = [{"q": int(q), "given": answers.get(q, ""), "key": found["key"][q], "right": right[q]}
                 for q in sorted(found["key"], key=int)]
    return {
        "enough": True,
        "overall": band,
        "raw": raw,
        "of": len(questions),
        "questions": questions,
        "any_order": found["any_order"],
        "parts": [{"first": first, "last": last, "right": sum(right[str(q)] for q in range(first, last + 1)),
                   "of": last - first + 1} for first, last in found["sections"]],
        "note": f"{raw} of {len(questions)} answers right: band {band:g} on the official Listening table.",
        "criteria": [],
        "strengths": [],
        "priorities": [],
    }
