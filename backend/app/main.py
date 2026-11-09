"""The voice loop: mic audio in → transcript → examiner reply → speech out.

HTTP:
  GET /api/options   voices, training modes and the LLM model, for the setup screen
  GET /              the Flutter app (after `make frontend`)
  GET /dev           a plain developer test page

WebSocket protocol on /ws:
  client → server  JSON  {"type": "start", "mode": "part1", "voice": "bf_emma", "topic": "travel"}
                         (all optional; mode is one of /api/options "modes")
                   bytes PCM16 mono 16 kHz microphone audio, any chunk size
  server → client  JSON  {"type": "ready"}                          models loaded, examiner about to speak
                   JSON  {"type": "listening"}                      the candidate started speaking
                   JSON  {"type": "partial", "text": "..."}         live transcript while they speak
                   JSON  {"type": "transcript", "text": "..."}      the finished answer
                   JSON  {"type": "examiner", "text": "..."}        one sentence of the reply
                   bytes PCM16 mono 24 kHz speech for that sentence
                   JSON  {"type": "examiner_done"}                  reply finished; client resumes the mic
"""
import asyncio
import logging
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config, llm
from .examiner import MODES, Conversation
from .stt import Transcriber
from .tts import Speaker
from .vad import SAMPLE_RATE, TurnDetector

log = logging.getLogger("ielts")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

app = FastAPI(title="IELTS Speaking Assistant")
# Lets `flutter run` (another localhost port) call the API during development.
app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?", allow_methods=["GET"])

transcriber = Transcriber(config.WHISPER_MODEL, config.DEVICE)
transcribe_lock = asyncio.Lock()  # one Whisper call at a time
speaker = Speaker(config.DEVICE)

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
    try:
        start = await ws.receive_json()
        voice = start.get("voice") if start.get("voice") in config.VOICES else config.DEFAULT_VOICE
        mode = start.get("mode") if start.get("mode") in MODES else "part1"
        conversation = Conversation(mode, examiner_name(voice), start.get("topic"))
        turns = TurnDetector(config.END_OF_TURN_SILENCE_MS)
        await ws.send_json({"type": "ready"})
        await examiner_turn(ws, conversation, voice)

        partial = None  # the live-transcript task, if one is running
        last_partial = 0.0
        while True:
            for event in turns.feed(await ws.receive_bytes()):
                if isinstance(event, str):
                    await ws.send_json({"type": "listening"})
                    continue
                if partial:
                    await partial  # let it finish, so it can't arrive after the final text
                    partial = None
                text = await transcribe(event)
                log.info("candidate: %s", text)
                if not text:
                    continue
                await ws.send_json({"type": "transcript", "text": text})
                conversation.add_candidate(text)
                await examiner_turn(ws, conversation, voice)
                turns.reset()

            heard = turns.current()
            due = time.monotonic() - last_partial > config.PARTIAL_TRANSCRIPT_EVERY_S
            # Whisper invents text for very short audio, so wait for a second of speech.
            long_enough = heard is not None and len(heard) >= SAMPLE_RATE
            if long_enough and due and (partial is None or partial.done()):
                last_partial = time.monotonic()
                partial = asyncio.create_task(send_partial(ws, heard))
    except WebSocketDisconnect:
        log.info("session closed")


async def transcribe(audio: np.ndarray) -> str:
    async with transcribe_lock:
        return await asyncio.to_thread(transcriber.transcribe, audio)


async def send_partial(ws: WebSocket, audio: np.ndarray):
    text = await transcribe(audio)
    if text:
        await ws.send_json({"type": "partial", "text": text})


async def examiner_turn(ws: WebSocket, conversation: Conversation, voice: str):
    """Streams the reply sentence by sentence: each one is spoken while the next is written."""
    reply = []
    async for sentence in llm.stream_sentences(conversation.messages()):
        reply.append(sentence)
        await ws.send_json({"type": "examiner", "text": sentence})
        audio = await asyncio.to_thread(speaker.speak, sentence, voice)
        await ws.send_bytes(to_pcm16(audio))
    conversation.add_examiner(" ".join(reply))
    log.info("examiner: %s", " ".join(reply))
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
