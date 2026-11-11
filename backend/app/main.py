"""The backend: one FastAPI app that mounts each module's routes.

  /api/speaking/..., /ws/speaking   the Speaking module (see speaking/router.py)
  /api/sessions/...                 past sessions and reports, for every module (see core/history.py)
  GET /                             the Flutter app (after `make frontend`)
  GET /dev                          a plain developer test page (Speaking)

A new module (Writing, later Listening and Reading) lives in its own package with its own
router, included below.
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .core import history
from .speaking.router import router as speaking

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

DEV_PAGE = Path(__file__).parent / "static" / "index.html"
FRONTEND = Path(__file__).parents[2] / "frontend" / "build" / "web"

app = FastAPI(title="IELTS Assistant")
# Lets `flutter run` (another localhost port) call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST", "DELETE"],
)
app.include_router(history.router)
app.include_router(speaking)


@app.get("/dev")
def dev_page():
    return FileResponse(DEV_PAGE)


# Last, so the routes above take priority over the static files.
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
else:
    @app.get("/")
    def no_frontend():
        return RedirectResponse("/dev")
