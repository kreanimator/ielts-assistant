"""The voice loop: mic audio in → transcript → examiner reply → speech out.

WebSocket protocol on /ws:
  client → server  JSON  {"type": "start", "voice": "bf_emma", "topic": "travel"}  (both optional)
                   bytes PCM16 mono 16 kHz microphone audio, any chunk size
  server → client  JSON  {"type": "ready"}                          models loaded, examiner about to speak
                   JSON  {"type": "listening"}                      the candidate started speaking
                   JSON  {"type": "transcript", "text": "..."}      what the candidate said
                   JSON  {"type": "examiner", "text": "..."}        one sentence of the reply
                   bytes PCM16 mono 24 kHz speech for that sentence
                   JSON  {"type": "examiner_done"}                  reply finished; client resumes the mic
"""
import asyncio
import logging
from pathlib import Path

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from . import config, llm
from .examiner import Conversation
from .stt import Transcriber
from .tts import Speaker
from .vad import TurnDetector

log = logging.getLogger("ielts")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

app = FastAPI(title="IELTS Speaking Assistant")
transcriber = Transcriber(config.WHISPER_MODEL, config.DEVICE)
speaker = Speaker(config.DEVICE)
DEV_PAGE = Path(__file__).parent / "static" / "index.html"


@app.get("/")
def dev_page():
    return FileResponse(DEV_PAGE)


@app.websocket("/ws")
async def session(ws: WebSocket):
    await ws.accept()
    try:
        start = await ws.receive_json()
        voice = start.get("voice") or config.DEFAULT_VOICE
        conversation = Conversation(examiner_name=voice.split("_")[-1].title(), topic=start.get("topic"))
        turns = TurnDetector(config.END_OF_TURN_SILENCE_MS)
        await ws.send_json({"type": "ready"})
        await examiner_turn(ws, conversation, voice)

        while True:
            for event in turns.feed(await ws.receive_bytes()):
                if isinstance(event, str):
                    await ws.send_json({"type": "listening"})
                    continue
                text = await asyncio.to_thread(transcriber.transcribe, event)
                log.info("candidate: %s", text)
                if not text:
                    continue
                await ws.send_json({"type": "transcript", "text": text})
                conversation.add_candidate(text)
                await examiner_turn(ws, conversation, voice)
                turns.reset()
    except WebSocketDisconnect:
        log.info("session closed")


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


def to_pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
