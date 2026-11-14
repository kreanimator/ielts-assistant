"""The Reading module's routes.

  GET  /api/reading/books     the Reading tests imported from your books (see books.py): each test's
                              kind (academic or general), pages and parts (their keys stay on the server)
  GET  /api/reading/pages/<book>/<page>.jpg
                              a page of a test, as the book prints it
  GET  /api/reading/crops/<book>/<page>.jpg?box=x0,y0,x1,y1
                              a part of it (fractions of the page): a group of questions as printed
  GET  /api/reading/pictures/<name>
                              a picture of a group of questions saved from the web (a group's "images")

The test (see test.py), timed on the server:
  POST /api/reading/tests     {"book": "<id>", "test": "2"}, or {"kind": "academic"} (or nothing) for a
                              random test; starts it: 60 minutes from now; returns its state:
                              {"session", "title", "book", "test", "kind", "pages", "parts", "sections", "questions",
                               "content" (the passages and questions as text, content.py; null: show the pages),
                               "minutes", "answers": {"1": "..."}, "seconds_left", "finished"}
  GET  /api/reading/tests/<id>          its state (to continue after a reload)
  PUT  /api/reading/tests/<id>/answers  {"1": "TRUE", "14": "iv", ...} saves the answers so far; 409
                                        after the deadline (the app saves every few seconds)
  POST /api/reading/tests/<id>/finish   {...} (optional, saved first if still in time) ends the test;
                                        then POST /api/sessions/<id>/report marks it
"""
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from ..core import modules, web_tests
from . import books, test

router = APIRouter()
MODES = {"test": "Full test"}
modules.register("reading", MODES, test.build)


@router.get("/api/reading/books")
def list_books():
    return [
        {"id": b["id"], "title": b["title"],
         "tests": [{"test": t["test"], "kind": t["kind"], "pages": len(t["pages"])} for t in b["tests"]]}
        for b in books.load_books()
    ]


@router.get("/api/reading/pages/{book_id}/{page}.jpg")
def page_picture(book_id: str, page: int):
    picture = books.page_picture(book_id, page)
    if picture is None:
        raise HTTPException(404, "No such page")
    return FileResponse(picture, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/api/reading/crops/{book_id}/{page}.jpg")
def page_crop(book_id: str, page: int, box: str):
    """A part of a page (box: "x0,y0,x1,y1" in fractions of the page): questions as printed."""
    try:
        numbers = [float(v) for v in box.split(",")]
    except ValueError:
        raise HTTPException(422, "box: four numbers") from None
    picture = books.crop(book_id, page, numbers)
    if picture is None:
        raise HTTPException(404, "No such page")
    return Response(picture, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/api/reading/pictures/{name}")
def group_picture(name: str):
    """A picture of a group of questions saved from the web (a map, a plan, a diagram)."""
    picture = web_tests.image_file(name)
    if picture is None:
        raise HTTPException(404, "No such picture")
    return FileResponse(picture, headers={"Cache-Control": "private, max-age=86400"})


class TestStart(BaseModel):
    book: str | None = None
    test: str | None = None
    kind: Literal["academic", "general"] | None = None


@router.post("/api/reading/tests")
def start_test(body: TestStart):
    try:
        return test.start(body.book, body.test, body.kind)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/api/reading/tests/{session_id}")
def test_state(session_id: str):
    return _state_or_404(session_id)


@router.put("/api/reading/tests/{session_id}/answers")
def save_answers(session_id: str, answers: dict[str, str]):
    _state_or_404(session_id)
    try:
        return test.save(session_id, answers)
    except test.TimeUp as e:
        raise HTTPException(409, "Time is up: the answers saved before the end are kept") from e


@router.post("/api/reading/tests/{session_id}/finish")
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
