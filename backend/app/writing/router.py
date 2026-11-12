"""The Writing module's routes.

  GET  /api/writing/options   the modes, the kinds of new tasks, and how many tasks your books have
  GET  /api/writing/books     the Writing tests imported from your books (see books.py): each test's
                              tasks, and how many model and sample answers it has
  GET  /api/writing/task?task=1&source=book&book=<id>&test=2
                              a task to practise: from that test, or a random one from your books
  GET  /api/writing/task?task=2&source=new&topic=travel&kind=opinion
                              a new task written by the LLM (topic and kind are optional)
  POST /api/writing/answers   {"task": <a task from above>, "answer": "...", "seconds": 1180}
                              saves your answer as a session and returns {"session": "<id>"};
                              then POST /api/sessions/<id>/report writes the report (see assessor.py)

The full test (see test.py), timed on the server:
  POST /api/writing/tests     {"source": "book", "book": "<id>", "test": "2"} or {"source": "new", "topic": "..."}
                              starts a test: both tasks, 60 minutes from now; returns its state:
                              {"session", "title", "tasks": [task 1, task 2], "minutes", "answers": {"1", "2"},
                               "seconds_left", "finished"}
  GET  /api/writing/tests/<id>          its state (to continue after a reload); a test whose time ran
                                        out comes back finished
  PUT  /api/writing/tests/<id>/answers  {"1": "...", "2": "..."} saves the answers so far; 409 after the
                                        deadline (the app saves every few seconds)
  POST /api/writing/tests/<id>/finish   {"1": ..., "2": ...} (optional, saved first if still in time)
                                        ends the test; then POST /api/sessions/<id>/report

A Writing session stores the task as the examiner's message and your answer as the candidate's
message, with the task itself and the time you took in the answer's "delivery".
"""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..core import llm, modules, storage
from ..core.text import word_count
from . import assessor, books, tasks, test

router = APIRouter()
MODES = {"task1": "Task 1 · Letter", "task2": "Task 2 · Essay", "test": "Full test"}
modules.register("writing", MODES, assessor.build)


class Task(BaseModel):
    task: Literal[1, 2]
    kind: Literal["letter", "essay"]
    prompt: str = Field(min_length=10, max_length=3000)
    bullets: list[str] = Field(default=[], max_length=4)
    begin: str = ""
    minutes: int = Field(ge=1, le=120)
    words: int = Field(ge=1, le=1000)
    source: Literal["book", "new"]
    title: str = Field(max_length=200)
    book: str | None = None
    book_title: str | None = None
    test: str | None = None
    type: str | None = None  # a new task's letter or essay type


class Answer(BaseModel):
    task: Task
    answer: str = Field(max_length=20000)
    seconds: int | None = Field(default=None, ge=0)  # the time you took


@router.get("/api/writing/options")
def options():
    return {
        "modes": MODES,
        "letter_types": list(tasks.LETTER_TYPES),
        "essay_types": tasks.ESSAY_TYPES,
        "book_tasks": {1: len(tasks.book_tasks(1)), 2: len(tasks.book_tasks(2))},
    }


@router.get("/api/writing/task")
async def get_task(task: int = Query(ge=1, le=2), source: Literal["book", "new"] = "book", book: str | None = None,
                   test: str | None = None, topic: str | None = None, kind: str | None = None):
    if source == "book":
        found = tasks.from_book(task, book, test)
        if found is None:
            raise HTTPException(404, "No such task in your books. Import your books with make books, or ask for a new task.")
        return found
    return await tasks.new_task(task, topic, kind)


@router.post("/api/writing/answers")
async def save_answer(body: Answer):
    if not word_count(body.answer):
        raise HTTPException(400, "The answer is empty")
    task = body.task.model_dump(exclude_none=True)
    session = storage.create_session("writing", f"task{task['task']}", task["title"], "", await llm.model_name())
    storage.add_message(session, "examiner", tasks.as_text(task))
    storage.add_message(session, "candidate", body.answer.strip(), answer=0)
    storage.set_answer_field(session, 0, "delivery", {"task": task, "seconds": body.seconds,
                                                      "words": word_count(body.answer)})
    return {"session": session}


class TestStart(BaseModel):
    source: Literal["book", "new"]
    book: str | None = None
    test: str | None = None
    topic: str | None = Field(default=None, max_length=200)


@router.post("/api/writing/tests")
async def start_test(body: TestStart):
    try:
        return await test.start(body.source, body.book, body.test, body.topic)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/api/writing/tests/{session_id}")
def test_state(session_id: str):
    state = test.state(session_id)
    if state is None:
        raise HTTPException(404, "No such test")
    return state


@router.put("/api/writing/tests/{session_id}/answers")
def save_test_answers(session_id: str, answers: dict[str, str]):
    _test_or_404(session_id)
    if any(len(v) > 20000 for v in answers.values()):
        raise HTTPException(413, "The answer is too long")
    try:
        return test.save(session_id, answers)
    except test.TimeUp as e:
        raise HTTPException(409, "Time is up: the answers saved before the end are kept") from e


@router.post("/api/writing/tests/{session_id}/finish")
def finish_test(session_id: str, answers: dict[str, str] | None = None):
    _test_or_404(session_id)
    if answers:
        try:
            test.save(session_id, answers)
        except test.TimeUp:
            pass  # too late: the last answers saved in time count
    test.finish(session_id)
    return test.state(session_id)


def _test_or_404(session_id: str):
    if test.state(session_id) is None:
        raise HTTPException(404, "No such test")


@router.get("/api/writing/books")
def list_books():
    """Each book with its tests: the tasks in full, the answers counted (their texts stay on the server)."""
    return [
        {
            "id": b["id"],
            "title": b["title"],
            "tests": [
                {
                    "test": t["test"],
                    "type": t["type"],
                    "task1": t["task1"],
                    "task2": t["task2"],
                    "answers": [
                        {"task": a["task"], "kind": a["kind"], "band": a["band"], "readable": a["answer"] is not None}
                        for a in t["answers"]
                    ],
                }
                for t in b["tests"]
            ],
        }
        for b in books.load_books()
        if b["tests"]
    ]
