"""Sessions, answers and reports in a local SQLite database; answer recordings as WAV files.

Everything lives in data/ (git-ignored), on this computer only.
"""
import json
import shutil
import sqlite3
import uuid
import wave
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    module TEXT NOT NULL DEFAULT 'speaking',  -- the skill: speaking, writing, ...
    mode TEXT NOT NULL,
    topic TEXT,
    voice TEXT NOT NULL,
    model TEXT NOT NULL,
    report TEXT                 -- JSON, once written
);
CREATE TABLE IF NOT EXISTS messages (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,       -- order in the conversation
    role TEXT NOT NULL,         -- "examiner" or "candidate"
    text TEXT NOT NULL,
    answer INTEGER,             -- candidate answers: 0, 1, 2, ...
    delivery TEXT,              -- JSON: fluency and pronunciation numbers
    feedback TEXT,              -- JSON: the analyst's corrections
    PRIMARY KEY (session_id, seq)
);
"""


_ready = False  # the schema is created and up to date


@contextmanager
def connect():
    """A database connection that commits at the end of the block and then closes."""
    global _ready
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.DATA_DIR / "ielts.db")
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        if not _ready:
            db.executescript(SCHEMA)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(sessions)")}
            if "module" not in columns:  # a database from before the modules: all Speaking
                db.execute("ALTER TABLE sessions ADD COLUMN module TEXT NOT NULL DEFAULT 'speaking'")
                db.commit()
            _ready = True
        with db:
            yield db
    finally:
        db.close()


def audio_path(session_id: str, answer: int) -> Path:
    return config.DATA_DIR / "sessions" / session_id / f"answer-{answer}.wav"


def create_session(module: str, mode: str, topic: str | None, voice: str, model: str) -> str:
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    with connect() as db:
        db.execute(
            "INSERT INTO sessions (id, started_at, module, mode, topic, voice, model) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, datetime.now(timezone.utc).isoformat(), module, mode, topic, voice, model),
        )
    return session_id


def add_message(session_id: str, role: str, text: str, answer: int | None = None):
    with connect() as db:
        seq = db.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)).fetchone()[0]
        db.execute(
            "INSERT INTO messages (session_id, seq, role, text, answer) VALUES (?, ?, ?, ?, ?)",
            (session_id, seq, role, text, answer),
        )


def save_answer_audio(session_id: str, answer: int, audio: np.ndarray, sample_rate: int = 16000):
    path = audio_path(session_id, answer)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


def set_answer_field(session_id: str, answer: int, field: str, value: dict):
    assert field in ("delivery", "feedback")
    with connect() as db:
        db.execute(
            f"UPDATE messages SET {field} = ? WHERE session_id = ? AND answer = ?",
            (json.dumps(value), session_id, answer),
        )


def set_report(session_id: str, report: dict):
    with connect() as db:
        db.execute("UPDATE sessions SET report = ? WHERE id = ?", (json.dumps(report), session_id))


def set_topic(session_id: str, topic: str):
    with connect() as db:
        db.execute("UPDATE sessions SET topic = ? WHERE id = ?", (topic, session_id))


def list_sessions(module: str | None = None) -> list[dict]:
    """Newest first; only one module's with `module`."""
    with connect() as db:
        rows = db.execute(
            """SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id AND m.role = 'candidate') AS answers
               FROM sessions s WHERE ? IS NULL OR s.module = ? ORDER BY s.started_at DESC""",
            (module, module),
        ).fetchall()
    return [_session(row) for row in rows]


def get_session(session_id: str) -> dict | None:
    with connect() as db:
        row = db.execute(
            """SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id AND m.role = 'candidate') AS answers
               FROM sessions s WHERE s.id = ?""",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        messages = db.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY seq", (session_id,)).fetchall()
    session = _session(row)
    session["messages"] = [
        {
            "role": m["role"],
            "text": m["text"],
            "answer": m["answer"],
            "delivery": json.loads(m["delivery"]) if m["delivery"] else None,
            "feedback": json.loads(m["feedback"]) if m["feedback"] else None,
            "has_audio": m["answer"] is not None and audio_path(session_id, m["answer"]).exists(),
        }
        for m in messages
    ]
    return session


def delete_session(session_id: str):
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    shutil.rmtree(config.DATA_DIR / "sessions" / session_id, ignore_errors=True)


def _session(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "started_at": row["started_at"],
        "module": row["module"],
        "mode": row["mode"],
        "topic": row["topic"],
        "voice": row["voice"],
        "model": row["model"],
        "answers": row["answers"],
        "report": json.loads(row["report"]) if row["report"] else None,
    }
