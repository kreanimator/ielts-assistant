"""The voice loop: mic audio in → transcript → examiner reply → speech out.

HTTP:
  GET /api/options   voices, training modes and the LLM model, for the setup screen
  /api/sessions/...  past sessions and reports (see history.py)
  GET /              the Flutter app (after `make frontend`)
  GET /dev           a plain developer test page

WebSocket protocol on /ws:
  client → server  JSON  {"type": "start", "mode": "part1", "voice": "bf_emma", "topic": "travel"}
                         (all optional; mode is one of /api/options "modes")
                   bytes PCM16 mono 16 kHz microphone audio, any chunk size
                   JSON  {"type": "end"}                            finish: wait for pending feedback, then close
  server → client  JSON  {"type": "ready", "session": "<id>"}       models loaded, examiner about to speak
                   JSON  {"type": "listening"}                      the candidate started speaking
                   JSON  {"type": "partial", "text": "..."}         live transcript while they speak
                   JSON  {"type": "transcript", "text": "..."}      the finished answer
                   JSON  {"type": "examiner", "text": "..."}        one sentence of the reply
                   bytes PCM16 mono 24 kHz speech for that sentence
                   JSON  {"type": "examiner_done"}                  reply finished; client resumes the mic
                   JSON  {"type": "delivery", "answer": 0,          measured right after the answer
                          "fluency": {"seconds", "words", "wpm", "pauses", "longest_pause", "fillers", "repetitions"},
                          "pronunciation": {"score": 0..1, "words": [{"word", "expected", "heard"}],
                                            "sounds": [{"expected": "θ", "heard": "s", "count": 2}]}}
                   JSON  {"type": "feedback", "answer": 0,          feedback on answer number 0, 1, ...
                          "corrections": [{"category", "original", "better", "why"}],
                          "good": "...", "tip": "..."}             arrives a few seconds after the answer
                   JSON  {"type": "ended", "session": "<id>"}       everything saved; the report can be requested
"""
import asyncio
import json
import logging
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config, fluency, history, llm, storage
from .analyst import analyse
from .examiner import MODES, Conversation
from .pronunciation import PronunciationScorer
from .stt import Transcriber, Transcript
from .tts import Speaker
from .vad import SAMPLE_RATE, TurnDetector

log = logging.getLogger("ielts")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

app = FastAPI(title="IELTS Speaking Assistant")
# Lets `flutter run` (another localhost port) call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST", "DELETE"],
)
app.include_router(history.router)

transcriber = Transcriber(config.WHISPER_MODEL, config.DEVICE)
transcribe_lock = asyncio.Lock()  # one Whisper call at a time
speaker = Speaker(config.DEVICE)
pronunciation_scorer = PronunciationScorer(config.DEVICE)

DEV_PAGE = Path(__file__).parent / "static" / "index.html"
FRONTEND = Path(__file__).parents[2] / "frontend" / "build" / "web"
ACCENTS = {"a": "American", "b": "British"}
GENDERS = {"f": "female", "m": "male"}


@app.get("/api/options")
async def options():
    return {
        "model": await llm.model_name(),
        "voices": [
            {"id": v, "name": examiner_name(v), "accent": ACCENTS[v[0]], "gender": GENDERS[v[1]]}
            for v in config.VOICES
        ],
        "modes": [{"id": k, "title": m["title"], "description": m["description"]} for k, m in MODES.items()],
    }


@app.get("/dev")
def dev_page():
    return FileResponse(DEV_PAGE)


@app.websocket("/ws")
async def session(ws: WebSocket):
    await ws.accept()
    tasks = set()  # feedback still being worked out
    session_id = None

    def in_background(work):
        task = asyncio.create_task(work)
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    try:
        start = await ws.receive_json()
        voice = start.get("voice") if start.get("voice") in config.VOICES else config.DEFAULT_VOICE
        mode = start.get("mode") if start.get("mode") in MODES else "part1"
        topic = start.get("topic")
        conversation = Conversation(mode, examiner_name(voice), topic)
        session_id = storage.create_session(mode, topic, voice, await llm.model_name())
        turns = TurnDetector(config.END_OF_TURN_SILENCE_MS)
        await ws.send_json({"type": "ready", "session": session_id})
        await examiner_turn(ws, session_id, conversation, voice)

        partial = None  # the live-transcript task, if one is running
        last_partial = 0.0
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("text"):
                if json.loads(message["text"]).get("type") == "end":
                    if tasks:
                        await asyncio.wait(tasks, timeout=60)
                    await ws.send_json({"type": "ended", "session": session_id})
                    await ws.close()
                    break
                continue

            for event in turns.feed(message["bytes"]):
                if isinstance(event, str):
                    await ws.send_json({"type": "listening"})
                    continue
                if partial:
                    await partial  # let it finish, so it can't arrive after the final text
                    partial = None
                transcript = await transcribe(event, with_words=True)
                text = transcript.text
                log.info("candidate: %s", text)
                if not text:
                    continue
                await ws.send_json({"type": "transcript", "text": text})
                question = conversation.last_question()
                conversation.add_candidate(text)
                answer = conversation.answer_count() - 1
                storage.add_message(session_id, "candidate", text, answer)
                in_background(asyncio.to_thread(storage.save_answer_audio, session_id, answer, event))
                in_background(send_delivery(ws, session_id, answer, event, transcript))
                await examiner_turn(ws, session_id, conversation, voice)
                # Analyse while the examiner's reply plays, so it never delays the examiner.
                in_background(send_feedback(ws, session_id, answer, question, text))
                turns.reset()

            heard = turns.current()
            due = time.monotonic() - last_partial > config.PARTIAL_TRANSCRIPT_EVERY_S
            # Whisper invents text for very short audio, so wait for a second of speech.
            long_enough = heard is not None and len(heard) >= SAMPLE_RATE
            if long_enough and due and (partial is None or partial.done()):
                last_partial = time.monotonic()
                partial = asyncio.create_task(send_partial(ws, heard))
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        if session_id and storage.get_session(session_id)["answers"] == 0:
            storage.delete_session(session_id)  # nothing was said: don't clutter the history
        log.info("session %s closed", session_id)


async def send_feedback(ws: WebSocket, session_id: str, answer: int, question: str, text: str):
    try:
        feedback = await analyse(question, text)
        storage.set_answer_field(session_id, answer, "feedback", feedback)
        await ws.send_json({"type": "feedback", "answer": answer, **feedback})
    except Exception:  # feedback is extra: never end the session because of it
        log.exception("feedback failed")


async def send_delivery(ws: WebSocket, session_id: str, answer: int, audio: np.ndarray, transcript: Transcript):
    """Measured fluency and pronunciation: fast, so it arrives right after the answer."""
    try:
        pronunciation = await asyncio.to_thread(pronunciation_scorer.score, audio, transcript.text)
        delivery = {"fluency": fluency.measure(transcript.words), "pronunciation": pronunciation}
        storage.set_answer_field(session_id, answer, "delivery", delivery)
        await ws.send_json({"type": "delivery", "answer": answer, **delivery})
    except Exception:
        log.exception("delivery check failed")


async def transcribe(audio: np.ndarray, with_words: bool = False) -> Transcript:
    async with transcribe_lock:
        return await asyncio.to_thread(transcriber.transcribe, audio, with_words)


async def send_partial(ws: WebSocket, audio: np.ndarray):
    text = (await transcribe(audio)).text
    if text:
        await ws.send_json({"type": "partial", "text": text})


async def examiner_turn(ws: WebSocket, session_id: str, conversation: Conversation, voice: str):
    """Streams the reply sentence by sentence: each one is spoken while the next is written."""
    reply = []
    async for sentence in llm.stream_sentences(conversation.messages()):
        reply.append(sentence)
        await ws.send_json({"type": "examiner", "text": sentence})
        audio = await asyncio.to_thread(speaker.speak, sentence, voice)
        await ws.send_bytes(to_pcm16(audio))
    text = " ".join(reply)
    conversation.add_examiner(text)
    storage.add_message(session_id, "examiner", text)
    log.info("examiner: %s", text)
    await ws.send_json({"type": "examiner_done"})


def examiner_name(voice: str) -> str:
    return voice.split("_")[-1].title()


def to_pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()


# Last, so the routes above take priority over the static files.
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
else:
    @app.get("/")
    def no_frontend():
        return RedirectResponse("/dev")
