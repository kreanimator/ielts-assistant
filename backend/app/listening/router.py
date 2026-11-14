"""The Listening module's routes.

  GET  /api/listening/books   the Listening tests that can be taken (see books.py): each test's
                              length in minutes (their keys stay on the server)
  GET  /api/listening/audio/<book>/<file>
                              a recording of a test (the browser asks for the part it plays)

The test (see test.py):
  POST /api/listening/tests   {"book": "<id>", "test": "2"}, or {"book": "<id>"} or nothing for a
                              random test; returns its state, not yet playing:
                              {"session", "title", "book", "test", "audio": [{"part", "file", "seconds"}],
                               "recording_seconds", "check_seconds", "sections", "questions",
                               "content" (the questions as text, reading/content.py; after the test
                               each part has its "transcript" too), "started", "elapsed",
                               "answers": {"1": "..."}, "seconds_left", "finished"}
  POST /api/listening/tests/<id>/play     starts the recording's clock (once); returns the state
  GET  /api/listening/tests/<id>          its state (to continue after a reload: play from "elapsed")
  PUT  /api/listening/tests/<id>/answers  {"1": "A", "14": "tent", ...} saves the answers so far; 409
                                          after the deadline (the app saves every few seconds)
  POST /api/listening/tests/<id>/finish   {...} (optional, saved first if still in time) ends the test;
                                          then POST /api/sessions/<id>/report marks it

A group's pictures (maps, plans) are served by /api/reading/pictures/<name>.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core import modules
from . import books, test

router = APIRouter()
MODES = {"test": "Full test"}
modules.register("listening", MODES, test.build)


@router.get("/api/listening/books")
def list_books():
    return [
        {"id": b["id"], "title": b["title"],
         "tests": [{"test": t["test"], "minutes": round(sum(a["seconds"] for a in t["audio"]) / 60)} for t in b["tests"]]}
        for b in books.load_books()
    ]


@router.get("/api/listening/audio/{book_id}/{name}")
def recording(book_id: str, name: str):
    found = books.audio_file(book_id, name)
    if found is None:
        raise HTTPException(404, "No such recording")
    return FileResponse(found[0], media_type=found[1], headers={"Cache-Control": "private, max-age=86400"})


class TestStart(BaseModel):
    book: str | None = None
    test: str | None = None


@router.post("/api/listening/tests")
def start_test(body: TestStart):
    try:
        return test.start(body.book, body.test)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/api/listening/tests/{session_id}/play")
def play_test(session_id: str):
    _state_or_404(session_id)
    return test.play(session_id)


@router.get("/api/listening/tests/{session_id}")
def test_state(session_id: str):
    return _state_or_404(session_id)


@router.put("/api/listening/tests/{session_id}/answers")
def save_answers(session_id: str, answers: dict[str, str]):
    _state_or_404(session_id)
    try:
        return test.save(session_id, answers)
    except test.TimeUp as e:
        raise HTTPException(409, "Time is up: the answers saved before the end are kept") from e


@router.post("/api/listening/tests/{session_id}/finish")
def finish_test(session_id: str, answers: dict[str, str] | None = None):
    _state_or_404(session_id)
    if answers:
        try:
            test.save(session_id, answers)
        except test.TimeUp:
            pass  # too late: the answers saved in time count
    test.finish(session_id)
    return test.state(session_id)


def _state_or_404(session_id: str) -> dict:
    state = test.state(session_id)
    if state is None:
        raise HTTPException(404, "No such test")
    return state
