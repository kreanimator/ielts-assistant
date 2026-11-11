"""The Speaking module's routes. The voice loop: mic audio in → transcript → examiner reply → speech out.

HTTP:
  GET /api/speaking/options   voices, training modes and the LLM model, for the setup screen
  GET /api/speaking/books     the Speaking tests imported from your books (see books.py)
  GET /api/speaking/topics    topics to pick from: our A-Z list and your books' topics (see topics.py)
  GET /api/speaking/esl       the topic cards for the "By letter" mode, without their questions (see esl.py)
  GET /api/speaking/drills    drills to pick from, and the ones your past sessions suggest (see drills.py)
  (Past sessions and reports: /api/sessions/..., see core/history.py.)

WebSocket protocol on /ws/speaking:
  client → server  JSON  {"type": "start", "mode": "part1", "voice": "bf_emma", "topic": "travel",
                          "book": "cambridge-ielts-08", "test": 2, "drill": "sound:θ",
                          "esl": "advice", "level": "mixed"}
                         (all optional; mode is one of /api/speaking/options "modes"; book and test pick
                          a real test's questions instead of a topic, for every mode but free;
                          esl and level pick the topic card in the "letter" mode, level is
                          mixed or one of esl.LEVELS)
                   JSON  {"type": "mic", "turn": 3}                 mic opened after examiner_done turn 3;
                                                                    audio before it is ignored
                   bytes PCM16 mono 16 kHz microphone audio, any chunk size
                   JSON  {"type": "skip"}                           Part 2 practice: end the preparation now
                   JSON  {"type": "end"}                            finish: wait for pending feedback, then close
  server → client  JSON  {"type": "ready", "session": "<id>"}       models loaded, examiner about to speak
                   JSON  {"type": "listening"}                      the candidate started speaking
                   JSON  {"type": "partial", "text": "..."}         live transcript while they speak
                   JSON  {"type": "transcript", "text": "..."}      the finished answer
                   JSON  {"type": "examiner", "text": "...", "new": true}   one sentence of the reply;
                                                                    new: it starts a new examiner message
                   bytes PCM16 mono 24 kHz speech for that sentence
                   JSON  {"type": "examiner_done", "turn": 3}       reply finished; client resumes the mic
                   JSON  {"type": "part", "title": "Part 2 · Long turn"}   a part of the test starts
                   JSON  {"type": "cue_card", "task", "points", "seconds", "skippable"}   Part 2 card
                   JSON  {"type": "clock", "label": "Preparation", "seconds": 60}
                                                                    countdown from when the queued speech has
                                                                    played; label null hides it
                   JSON  {"type": "time_up"}                        time ran out before anything was said
                   JSON  {"type": "delivery", "answer": 0,          measured right after the answer
                          "fluency": {"seconds", "words", "wpm", "pauses", "longest_pause", "fillers", "repetitions"},
                          "pronunciation": {"score": 0..1, "words": [{"word", "expected", "heard"}],
                                            "sounds": [{"expected": "θ", "heard": "s", "count": 2}],
                                            "target": {"sound", "total", "right", "missed_words"}}}
                                                                    (target: sound drills only)
                   JSON  {"type": "feedback", "answer": 0,          feedback on answer number 0, 1, ...
                          "corrections": [{"category", "original", "better", "why"}],
                          "good": "...", "tip": "..."}             arrives a few seconds after the answer
                   JSON  {"type": "finished"}                       the session ended by itself (end of the test)
                   JSON  {"type": "ended", "session": "<id>"}       everything saved; the report can be requested

Timing (the full exam and Part 2) is kept here on the server; see exam.py.
"""
import asyncio
import contextlib
import json
import logging
import math
import time

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core import llm, modules, storage
from . import books, config, drills, esl, exam, fluency, prosody, report, topics
from .analyst import analyse
from .examiner import MODES, Conversation
from .pronunciation import PronunciationScorer
from .stt import Transcriber, Transcript
from .tts import Speaker
from .vad import SAMPLE_RATE, TurnDetector

log = logging.getLogger("ielts.speaking")

router = APIRouter()
modules.register("speaking", {k: m["title"] for k, m in MODES.items()}, report.build)

transcriber = Transcriber(config.WHISPER_MODEL, config.WHISPER_DEVICE)
transcribe_lock = asyncio.Lock()  # one Whisper call at a time
speaker = Speaker(config.DEVICE)
pronunciation_scorer = PronunciationScorer(config.DEVICE)

ACCENTS = {"a": "American", "b": "British"}
GENDERS = {"f": "female", "m": "male"}


@router.get("/api/speaking/options")
async def options():
    return {
        "model": await llm.model_name(),
        "voices": [
            {"id": v, "name": examiner_name(v), "accent": ACCENTS[v[0]], "gender": GENDERS[v[1]]}
            for v in config.VOICES
        ],
        "modes": [{"id": k, "title": m["title"], "description": m["description"]} for k, m in MODES.items()],
    }


@router.get("/api/speaking/books")
def list_books():
    """Each book with a short outline of its tests (the questions stay on the server)."""
    return [
        {
            "id": b["id"],
            "title": b["title"],
            "tests": [
                {
                    "test": t["test"],
                    "part1": [x["topic"] for x in t["part1"]],
                    "part2": t["part2"]["task"],
                    "part3": [x["topic"] for x in t["part3"]],
                }
                for t in b["tests"]
            ],
        }
        for b in books.load_books()
        if b["tests"]
    ]


@router.get("/api/speaking/topics")
def list_topics():
    """Topics suggested in the topic field (see topics.py)."""
    return topics.all_topics()


@router.get("/api/speaking/esl")
def list_esl_topics():
    """The topic cards for the letter picker (empty until `make esl-topics`)."""
    return esl.catalogue()


@router.get("/api/speaking/drills")
def list_drills():
    """The drills, and the sounds your past sessions suggest (see drills.py)."""
    return drills.catalogue()


class EndRequested(Exception):
    """The client pressed End: finish the session now."""


@router.websocket("/ws/speaking")
async def session(ws: WebSocket):
    await ws.accept()
    talk = None
    try:
        start = await ws.receive_json()
        voice = start.get("voice") if start.get("voice") in config.VOICES else config.DEFAULT_VOICE
        mode = start.get("mode") if start.get("mode") in MODES else "part1"
        topic = start.get("topic")
        test = books.find_test(start.get("book", ""), start.get("test") or 0) if mode not in ("free", "drill", "letter") else None
        drill = drills.parse(start.get("drill"))
        card = esl.card(start.get("esl") or "", start.get("level") or "mixed") if mode == "letter" else None
        if mode == "letter" and not card:
            mode = "free"  # the topic cards are not downloaded
        if test:
            topic = f"{test['book']}, Test {test['test']}"
        if card:
            topic = card["name"]
        session_id = storage.create_session("speaking", mode, topic, voice, await llm.model_name())
        talk = Talk(ws, session_id, voice)
        await ws.send_json({"type": "ready", "session": session_id})
        try:
            await exam.run(talk, mode, examiner_name(voice), topic, test, drill, card)
            await ws.send_json({"type": "finished"})  # the session ended by itself
        except EndRequested:
            pass
        await talk.finish()
        await ws.send_json({"type": "ended", "session": session_id})
        await ws.close()
    except WebSocketDisconnect:
        pass
    finally:
        if talk:
            talk.cancel()
            if storage.get_session(talk.session_id)["answers"] == 0:
                storage.delete_session(talk.session_id)  # nothing was said: don't clutter the history
            log.info("session %s closed", talk.session_id)


class Talk:
    """One session's audio both ways: hears the candidate's answers and speaks the examiner.

    The mic is gated by turns: after each examiner_done (turn n) the client opens its mic
    and sends {"type": "mic", "turn": n}. Audio before that is ignored, so speech from an
    answer that was cut off can never leak into the next one."""

    def __init__(self, ws: WebSocket, session_id: str, voice: str):
        self.ws, self.session_id, self.voice = ws, session_id, voice
        self.tasks = set()  # feedback still being worked out
        self.answers = 0
        self.turn = 0  # examiner turns that handed over to the candidate
        self.playing_until = 0.0  # when the client will have played all speech sent so far
        self.was_cut = False  # the last answer was cut off at its time limit
        self.unchecked = []  # answers waiting for the analyst: (answer, question, text)
        self.analyse_answers = True  # off for sound drills: reading aloud needs no grammar feedback
        self.focus = None  # a language drill's focus, for the analyst
        self.target = None  # a sound drill's sound, for the pronunciation check
        self.turns = TurnDetector(config.END_OF_TURN_SILENCE_MS)

    def in_background(self, work):
        task = asyncio.create_task(work)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def check_answers(self):
        """Starts the analyst on the answers given so far. Called when the candidate's turn
        starts, so the analyst never competes with the examiner's reply on the LLM server."""
        for answer, question, text in self.unchecked:
            self.in_background(self.send_feedback(answer, question, text))
        self.unchecked = []

    async def finish(self):
        """Waits for pending feedback, so the report has it."""
        self.check_answers()
        if self.tasks:
            await asyncio.wait(self.tasks, timeout=60)

    def cancel(self):
        for task in self.tasks:
            task.cancel()

    async def receive(self, until: float | None = None):
        """The next message, or None once `until` (time.monotonic()) has passed."""
        timeout = None if until is None else max(0.0, until - time.monotonic())
        try:
            message = await asyncio.wait_for(self.ws.receive(), timeout)
        except asyncio.TimeoutError:
            return None
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect()
        if message.get("text"):
            message["json"] = json.loads(message["text"])
            if message["json"].get("type") == "end":
                raise EndRequested()
        return message

    # ---- the examiner ----

    async def part(self, title: str):
        await self.ws.send_json({"type": "part", "title": title})

    async def clock(self, label: str | None, seconds: float | None = None):
        """A countdown in the app, starting when the speech sent so far has played."""
        await self.ws.send_json({"type": "clock", "label": label, "seconds": seconds})

    async def speak(self, sentence: str, first: bool = False):
        """first: the sentence starts a new examiner message (a new bubble in the app)."""
        await self.ws.send_json({"type": "examiner", "text": sentence, "new": first})
        audio = await asyncio.to_thread(speaker.speak, sentence, self.voice)
        await self.ws.send_bytes(to_pcm16(audio))
        self.playing_until = max(self.playing_until, time.monotonic()) + len(audio) / 24000

    async def handover(self):
        """The examiner has finished: the candidate's turn starts once the speech has played."""
        self.check_answers()
        self.turn += 1
        await self.ws.send_json({"type": "examiner_done", "turn": self.turn})

    async def say(self, text: str, done: bool = True):
        """A fixed line of the examiner's script."""
        for i, sentence in enumerate(llm.SENTENCE_END.split(text)):
            await self.speak(sentence, first=i == 0)
        storage.add_message(self.session_id, "examiner", text)
        log.info("examiner: %s", text)
        if done:
            await self.handover()

    async def examiner_turn(self, conversation: Conversation):
        """Streams the reply sentence by sentence: each one is spoken while the next is written."""
        reply = []
        instruction, question = conversation.next_step()  # a book test's question, said word for word

        async def say(sentence: str):
            reply.append(sentence)
            await self.speak(sentence, first=len(reply) == 1)

        if instruction is not None:
            # aclosing: stopping early closes the LLM request at once
            async with contextlib.aclosing(llm.stream_sentences(conversation.messages())) as sentences:
                async for sentence in sentences:
                    if question:  # only a short reaction before the test question, never a question of its own
                        if not sentence.endswith("?"):
                            await say(sentence)
                        break
                    await say(sentence)
        if question:
            await say(question)
        text = " ".join(reply)
        conversation.add_examiner(text)
        storage.add_message(self.session_id, "examiner", text)
        log.info("examiner: %s", text)
        if not conversation.over:
            await self.handover()

    @staticmethod
    def count_sound(text: str, sound: str) -> int:
        return pronunciation_scorer.count(text, sound)

    def set_topic(self, topic: str):
        """What the session is about, for the history (e.g. the cue card's subject)."""
        storage.set_topic(self.session_id, topic)

    async def cue_card(self, card: dict, seconds: float, skippable: bool):
        """Shows the Part 2 card and waits out the preparation time (or until skipped)."""
        storage.add_message(self.session_id, "examiner", exam.card_text(card))
        await self.ws.send_json({"type": "cue_card", **card, "seconds": seconds, "skippable": skippable})
        await self.clock("Preparation", seconds)
        until = max(self.playing_until, time.monotonic()) + seconds
        while (message := await self.receive(until)) is not None:
            if skippable and message.get("json", {}).get("type") == "skip":
                break
        await self.clock(None)

    # ---- the candidate ----

    async def answer(self, question: str, cut_at: float | None = None, limit: float | None = None,
                     silence_ms: int | None = None) -> str | None:
        """Waits for the candidate's answer and returns its text.

        cut_at (time.monotonic()) and limit (seconds after the mic opens) end the answer
        where it is; if nothing was said by then, returns None. silence_ms: the pause that
        ends the answer (longer in the Part 2 talk, where people stop to think)."""
        self.was_cut = False
        self.turns.reset()
        self.turns.set_silence(silence_ms or config.END_OF_TURN_SILENCE_MS)
        mic_open = False
        partial, last_partial = None, 0.0
        while True:
            message = await self.receive(cut_at)
            if message is None:  # time is up
                if partial:
                    await partial
                heard = self.turns.current()
                if heard is None or len(heard) < SAMPLE_RATE // 2:
                    await self.ws.send_json({"type": "time_up"})
                    return None
                self.was_cut = True
                return await self.hear(question, heard)
            if "json" in message:
                if message["json"].get("type") == "mic" and message["json"].get("turn") == self.turn:
                    mic_open = True
                    if limit:
                        cut_at = min(cut_at or math.inf, time.monotonic() + limit)
                        await self.clock("Speaking time", limit)
                continue
            if not mic_open or not message.get("bytes"):
                continue

            for event in self.turns.feed(message["bytes"]):
                if isinstance(event, str):
                    await self.ws.send_json({"type": "listening"})
                    continue
                if partial:
                    await partial  # let it finish, so it can't arrive after the final text
                    partial = None
                text = await self.hear(question, event)
                if text:
                    return text

            heard = self.turns.current()
            due = time.monotonic() - last_partial > config.PARTIAL_TRANSCRIPT_EVERY_S
            # Whisper invents text for very short audio, so wait for a second of speech.
            long_enough = heard is not None and len(heard) >= SAMPLE_RATE
            if long_enough and due and (partial is None or partial.done()):
                last_partial = time.monotonic()
                # Only the last 20 s: the live text stays fast during a two-minute talk.
                partial = asyncio.create_task(self.send_partial(heard[-20 * SAMPLE_RATE:]))

    async def hear(self, question: str, audio: np.ndarray) -> str:
        """Transcribes one answer, saves it and starts its checks. Returns "" for no words."""
        transcript = await transcribe(audio, with_words=True)
        text = transcript.text
        log.info("candidate: %s", text)
        if not text:
            return ""
        await self.ws.send_json({"type": "transcript", "text": text})
        answer = self.answers
        self.answers += 1
        storage.add_message(self.session_id, "candidate", text, answer)
        self.in_background(asyncio.to_thread(storage.save_answer_audio, self.session_id, answer, audio))
        self.in_background(self.send_delivery(answer, audio, transcript, question))
        if self.analyse_answers:
            self.unchecked.append((answer, question, text))  # analysed while the examiner's reply plays
        return text

    async def send_partial(self, audio: np.ndarray):
        text = (await transcribe(audio)).text
        if text:
            await self.ws.send_json({"type": "partial", "text": text})

    async def send_feedback(self, answer: int, question: str, text: str):
        try:
            feedback = await analyse(question, text, self.focus)
            storage.set_answer_field(self.session_id, answer, "feedback", feedback)
            await self.ws.send_json({"type": "feedback", "answer": answer, **feedback})
        except Exception:  # feedback is extra: never end the session because of it
            log.exception("feedback failed")

    async def send_delivery(self, answer: int, audio: np.ndarray, transcript: Transcript, question: str):
        """Measured fluency and pronunciation: fast, so it arrives right after the answer."""
        try:
            # A sound drill checks the sentence you were asked to say, so a misheard word still counts.
            text = question if self.target else transcript.text
            pronunciation = await asyncio.to_thread(pronunciation_scorer.score, audio, text, self.target)
            delivery = {"fluency": fluency.measure(transcript.words), "pronunciation": pronunciation,
                        "intonation": await asyncio.to_thread(prosody.intonation, audio)}
            storage.set_answer_field(self.session_id, answer, "delivery", delivery)
            await self.ws.send_json({"type": "delivery", "answer": answer, **delivery})
        except Exception:
            log.exception("delivery check failed")


async def transcribe(audio: np.ndarray, with_words: bool = False) -> Transcript:
    async with transcribe_lock:
        return await asyncio.to_thread(transcriber.transcribe, audio, with_words)


def examiner_name(voice: str) -> str:
    return voice.split("_")[-1].title()


def to_pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()

