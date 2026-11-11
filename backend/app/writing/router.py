"""The Writing module's routes.

  GET /api/writing/books   the Writing tests imported from your books (see books.py): each test's
                           tasks, and how many model and sample answers it has

Practice and assessment come in milestone 18. Until then the module is not registered in
core/modules.py, so the dashboard shows Writing as coming soon.
"""
from fastapi import APIRouter

from . import books

router = APIRouter()


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
