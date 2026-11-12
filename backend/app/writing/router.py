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

A Writing session stores the task as the examiner's message and your answer as the candidate's
message, with the task itself and the time you took in the answer's "delivery".
"""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..core import llm, modules, storage
from ..core.text import word_count
from . import assessor, books, tasks

router = APIRouter()
MODES = {"task1": "Task 1 · Letter", "task2": "Task 2 · Essay"}
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
