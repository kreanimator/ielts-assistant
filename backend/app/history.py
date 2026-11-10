"""Past sessions: list, details, reports, recordings, delete.

  GET    /api/sessions                       all sessions, newest first (with reports, without messages)
  GET    /api/sessions/{id}                  one session with every message, its feedback and numbers
  POST   /api/sessions/{id}/report           writes the band report if there is none yet (or ?again=true), returns it
  GET    /api/sessions/{id}/answers/{n}.wav  your recorded answer
  DELETE /api/sessions/{id}                  removes the session and its recordings
"""
import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from . import report, storage

router = APIRouter(prefix="/api/sessions")
report_lock = asyncio.Lock()  # one report at a time: they share the LLM


@router.get("")
def list_sessions():
    return storage.list_sessions()


@router.get("/{session_id}")
def get_session(session_id: str):
    return _session_or_404(session_id)


@router.post("/{session_id}/report")
async def write_report(session_id: str, again: bool = False):
    """again=true writes a new report even if there is one."""
    async with report_lock:
        session = _session_or_404(session_id)
        if session["report"] is None or again:
            session["report"] = await report.build(session)
            storage.set_report(session_id, session["report"])
    return session["report"]


@router.get("/{session_id}/answers/{answer}.wav")
def answer_audio(session_id: str, answer: int):
    path = storage.audio_path(session_id, answer)
    if not path.exists():
        raise HTTPException(404, "No recording for this answer")
    return FileResponse(path, media_type="audio/wav")


@router.delete("/{session_id}")
def delete_session(session_id: str):
    _session_or_404(session_id)
    storage.delete_session(session_id)
    return {"deleted": session_id}


def _session_or_404(session_id: str) -> dict:
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    return session
