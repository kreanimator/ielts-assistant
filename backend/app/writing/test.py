"""The full Writing test: Task 1 and Task 2 in one sitting, timed on the server.

As in IELTS, you have 60 minutes for both tasks and decide how to share them (about 20 minutes for
Task 1 and 40 for Task 2 is advised). The clock is kept here, not in the browser:

- start() stores both tasks and the deadline in the session's details (the clock: core/timed.py).
- The app saves your answers every few seconds (save()). The server accepts them until the
  deadline, plus a grace period for a save already on its way; later saves are refused, so a
  slow or paused browser cannot add time.
- finish() turns the last saved answers into the session's answers (candidate messages), then the
  report can be written. A test whose time ran out is finished with what was saved, the next time
  it is opened (state()) or its report is asked for (see assessor.build).

details: {"tasks": [task 1, task 2], "deadline": ISO time, "minutes": 60,
          "answers": {"1": "...", "2": "..."}, "saved_at": ISO time, "finished": false}
"""
import asyncio
import os

from fastapi import HTTPException

from ..core import llm, storage, timed
from ..core.text import word_count
from ..core.timed import TimeUp  # noqa: F401 (the router catches it)
from . import tasks

MINUTES = int(os.environ.get("WRITING_TEST_MINUTES", "60"))  # shorter for testing the app


async def choose_tasks(source: str, book: str | None, test: str | None, topic: str | None) -> tuple[list[dict], str]:
    """Task 1 and Task 2, and the test's title. From your books: both tasks of one General Training
    test (that test, or a random one). New: two tasks written by the LLM."""
    if source == "book":
        letter = tasks.from_book(1, book, test, with_task2=True)
        if letter is None:
            raise LookupError("No General Training test with both tasks in your books")
        essay = tasks.from_book(2, letter["book"], letter["test"])
        return [letter, essay], letter["title"]
    letter, essay = await asyncio.gather(tasks.new_task(1, topic), tasks.new_task(2, topic))
    return [letter, essay], f"New test: {letter['title']}; {essay['title']}"


async def start(source: str, book: str | None = None, test: str | None = None, topic: str | None = None) -> dict:
    chosen, title = await choose_tasks(source, book, test, topic)
    session = storage.create_session("writing", "test", title, "", await llm.model_name())
    for task in chosen:
        storage.add_message(session, "examiner", tasks.as_text(task))
    storage.set_details(session, {
        "tasks": chosen,
        "minutes": MINUTES,
        "deadline": timed.deadline(MINUTES),
        "answers": {"1": "", "2": ""},
        "saved_at": None,
        "finished": False,
    })
    return state(session)


def state(session_id: str) -> dict | None:
    """The test as the app shows it; a test whose time ran out is finished first."""
    session = storage.get_session(session_id)
    if session is None or session["mode"] != "test" or not session["details"]:
        return None
    details = session["details"]
    if timed.expired(details):
        details = finish(session_id)
    left = timed.seconds_left(details)
    return {
        "session": session_id,
        "title": session["topic"],
        "tasks": details["tasks"],
        "minutes": details["minutes"],
        "answers": details["answers"],
        "seconds_left": max(0, round(left)),
        "finished": details["finished"],
    }


def save(session_id: str, answers: dict[str, str]) -> dict:
    """Stores the answers ({"1": ..., "2": ...}, either or both). Raises TimeUp after the deadline."""
    session = storage.get_session(session_id)
    details = session["details"]
    if not timed.in_time(details):
        raise TimeUp()
    details["answers"].update({k: v for k, v in answers.items() if k in ("1", "2")})
    details["saved_at"] = timed.now().isoformat()
    storage.set_details(session_id, details)
    return {"seconds_left": max(0, round(timed.seconds_left(details))), "saved": True}


def finish(session_id: str) -> dict:
    """Ends the test: the last saved answers become the session's answers. Safe to call twice."""
    session = storage.get_session(session_id)
    details = session["details"]
    if details["finished"]:
        return details
    taken = timed.seconds_taken(details)
    for n, task in enumerate(details["tasks"]):
        text = details["answers"].get(str(task["task"]), "").strip()
        storage.add_message(session_id, "candidate", text, answer=n)
        storage.set_answer_field(session_id, n, "delivery", {
            "task": task, "words": word_count(text), "seconds": None, "test_seconds": taken,
        })
    details["finished"] = True
    storage.set_details(session_id, details)
    return details


def finish_if_needed(session: dict) -> dict:
    """The session, finished if it is a test whose time ran out (for the report). A test still in
    progress has no report yet: finish it first."""
    details = session["details"]
    if session["mode"] != "test" or not details or details["finished"]:
        return session
    if not timed.expired(details):
        raise HTTPException(409, "This test is still in progress: finish it first")
    finish(session["id"])
    return storage.get_session(session["id"])
