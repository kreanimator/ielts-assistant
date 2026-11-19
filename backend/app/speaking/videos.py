"""Real examiners' questions from the mock-test videos of the Ross IELTS Academy YouTube channel.

    make examiner-videos

For your own study only, like the topic cards (esl.py). make install offers to run it once;
run it again later to add the channel's new videos (videos done before are skipped).
Everything is saved in data/private/examiner/ (git-ignored) and never belongs in this
repository: the videos are the channel's work, and YouTube's terms do not allow
downloading them. What the examiner does (the fixed lines, the short reactions, repeating
a question) is written in our own words in examiner.py and exam.py.

For each new video:
1. The channel's list of videos gives two kinds: mock tests ("IELTS Speaking Test band 7
   with feedback": a real examiner runs Parts 1-3, then gives feedback) and question videos
   ("... questions and band 9 answers": the teacher reads recent test questions).
2. YouTube's automatic captions. Newer ones have punctuation and mark each change of
   speaker with ">>"; older ones are lowercase words only. For those the audio (about 9 MB)
   is downloaded, transcribed with Whisper (about 20 s a video on an NVIDIA GPU, much longer
   on a CPU) and deleted.
3. A mock test's examiner lines are told apart from the candidate's answers (questions,
   the examiner's set phrases), up to the end of the test; the feedback after it is left out.
4. The LLM copies the questions (the LLM server must be running, or is started for this):
   a mock test becomes a test in the books' format (tests.json, listed with your books
   as "Mock tests (videos)"); a question video adds to the question bank (bank.json),
   used for Part 1 and Part 3 when you choose a topic it has.
"""
import asyncio
import difflib
import json
import logging
import os
import random
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import numpy as np

from ..core import config, llm
from . import books

CHANNEL = "https://www.youtube.com/@RossIELTSAcademy/videos"
BOOK_ID = "mock-tests-videos"
BOOK_TITLE = "Mock tests (videos)"
ROOT = Path(__file__).parents[3]
LLM_HEALTH = config.LLM_URL.removesuffix("/v1") + "/health"

MOCK = re.compile(r"^(full )?ielts speaking test|^band 8 ielts speaking test", re.I)
NOT_MOCK = re.compile(r"questions|sample answers|part [123]\b|weather|from band|boost|top 3|comparison| vs ", re.I)
QUESTION_VIDEO = re.compile(r"band (8|9)|answers|questions|cue card|part [123]", re.I)
NOT_QUESTIONS = re.compile(r"alternatives|collocations|connectives|complex sentences|vocabulary|mistakes|"
                           r"in ielts exam, listening", re.I)

log = logging.getLogger("videos")


def folder() -> Path:
    return config.DATA_DIR / "private" / "examiner"


def kind(title: str) -> str | None:
    """"mock", "questions" or None (tips, vocabulary, other skills)."""
    if "speak" not in title.lower():
        return None
    if MOCK.search(title) and not NOT_MOCK.search(title):
        return "mock"
    if QUESTION_VIDEO.search(title) and not NOT_QUESTIONS.search(title):
        return "questions"
    return None


# ---- downloading ----

def youtube(**options):
    import yt_dlp  # only needed here
    return yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noprogress": True,
                             "sleep_interval_requests": 1, **options})


def list_videos() -> list[dict]:
    with youtube(extract_flat=True) as y:
        info = y.extract_info(CHANNEL, download=False)
    videos = [{"id": e["id"], "title": e.get("title") or "", "seconds": e.get("duration")}
              for e in info.get("entries") or [] if e.get("id")]
    for v in videos:
        v["kind"] = kind(v["title"])
    return videos


def url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def captions(video_id: str) -> Path | None:
    path = folder() / "captions" / f"{video_id}.en-orig.json3"
    if not path.exists():
        with youtube(skip_download=True, writeautomaticsub=True, subtitleslangs=["en-orig"],
                     subtitlesformat="json3", sleep_interval_subtitles=2,
                     outtmpl=str(folder() / "captions" / "%(id)s.%(ext)s")) as y:
            y.download([url(video_id)])
    return path if path.exists() else None


def caption_events(path: Path) -> list[tuple[float, str]]:
    """(start in seconds, text) of each caption line."""
    data = json.loads(path.read_text())
    events = []
    for e in data.get("events", []):
        text = "".join(s.get("utf8", "") for s in e.get("segs", [])).replace("\n", " ")
        if text.strip():
            events.append((e["tStartMs"] / 1000, text))
    return events


def usable(events: list[tuple[float, str]], kind: str) -> bool:
    """Captions with punctuation (and, for a mock test, the speaker marks the turns need)."""
    text = " ".join(t for _, t in events)
    return text.count(">>") >= 5 if kind == "mock" else text.count("?") > 5


def decode(path: Path) -> np.ndarray:
    """16 kHz mono float32 (faster-whisper's own decoder fails with newer PyAV versions)."""
    import av
    chunks = []
    with av.open(str(path)) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in container.decode(audio=0):
            chunks += [f.to_ndarray().reshape(-1) for f in resampler.resample(frame)]
        chunks += [f.to_ndarray().reshape(-1) for f in resampler.resample(None)]
    return np.concatenate(chunks).astype(np.float32) / 32768


_whisper = None


def transcribe(video_id: str) -> Path:
    """Whisper's transcript, in the captions' format; a pause of 0.8 s or more starts a new line
    with ">>". The audio is deleted afterwards."""
    global _whisper
    path = folder() / "whisper" / f"{video_id}.json3"
    if path.exists():
        return path
    audio_dir = folder() / "audio"
    with youtube(format="139/ba[abr<=70]/ba", sleep_interval=3, outtmpl=str(audio_dir / "%(id)s.%(ext)s")) as y:
        y.download([url(video_id)])
    audio = next(p for p in audio_dir.glob(f"{video_id}.*") if p.suffix not in (".part", ".ytdl"))
    if _whisper is None:
        from faster_whisper import WhisperModel
        from . import config as speaking
        _whisper = WhisperModel(speaking.WHISPER_MODEL, device=speaking.WHISPER_DEVICE,
                                compute_type="int8_float16" if speaking.WHISPER_DEVICE == "cuda" else "int8")
    segments, _ = _whisper.transcribe(decode(audio), language="en", vad_filter=True, condition_on_previous_text=False)
    events, last_end = [], None
    for s in segments:
        text = s.text.strip()
        if last_end is not None and s.start - last_end >= 0.8:
            text = ">> " + text
        events.append({"tStartMs": int(s.start * 1000), "segs": [{"utf8": text + " "}]})
        last_end = s.end
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"events": events}))
    audio.unlink()
    return path


# ---- the examiner's lines ----

EXAMINER = re.compile(
    r"let'?s (talk|move)|now,? (let'?s|we('ll| will)?|i'?d|i want)|part (one|two|three|1|2|3)\b|"
    r"i'?m going to give you|one minute|two minutes|you can (start|begin)|"
    r"thank you|that'?s the end|can i (see|have)|what'?s your (full )?name|"
    r"we'?ve been talking|i'?d (now )?like to|this is the end|in the first part", re.I)
FEEDBACK = re.compile(r"band score (you'?ll|you will|would)|let'?s (see|find out|look at)|feedback|what band", re.I)
TEST_END = re.compile(r"end of (the|this|your) (speaking )?test|test is (now )?over", re.I)
BACKCHANNEL = re.compile(r"^(okay|ok|all right|alright|right|great|good|perfect|wonderful|mhm|i see|"
                         r"thank you( very much| so much)?|thanks|sure|nice|lovely|brilliant|excellent|fine)[.,!]?$", re.I)


def turns(events: list[tuple[float, str]]) -> list[tuple[float, str]]:
    """The text between ">>" marks: one speaker's turn each."""
    out, current, start = [], [], 0.0
    for t, line in events:
        for i, part in enumerate(line.split(">>")):
            if i > 0:
                if current:
                    out.append((start, " ".join(current)))
                current, start = [], t
            if part.strip():
                current.append(part.strip())
    if current:
        out.append((start, " ".join(current)))
    return [(s, re.sub(r"\s+", " ", x).strip()) for s, x in out]


def sentences(events: list[tuple[float, str]]) -> list[tuple[float, str]]:
    out = []
    for start, turn in turns(events):
        out += [(start, m.group().strip()) for m in re.finditer(r"[^.?!]+[.?!]*", turn) if m.group().strip()]
    return out


def examiner_lines(events: list[tuple[float, str]]) -> list[str]:
    """The examiner's sentences of a mock test, in order, up to the end of the test.

    A short question or one of the examiner's set phrases is the examiner's, and so is a
    one-word reaction just before a question; everything else is taken as the candidate's.
    (Turns would be better, but the captions often run a question into its answer.)"""
    ss = sentences(events)
    lines, part3 = [], False
    for k, (start, x) in enumerate(ss):
        if re.search(r"third|part (three|3)", x, re.I):
            part3 = True
        if part3 and FEEDBACK.search(x) and not x.endswith("?"):
            break
        words = len(x.split())
        following = ss[k + 1][1] if k + 1 < len(ss) else ""
        if (x.endswith("?") and words <= 30) or (words <= 45 and EXAMINER.search(x)) or \
                (BACKCHANNEL.match(x) and following.endswith("?")):
            lines.append(x)
            if start > 480 and TEST_END.search(x):
                break
    return lines


# ---- the LLM ----

MOCK_PROMPT = """You get the examiner's lines from the transcript of a recorded IELTS Speaking mock test,
in order. The transcript was made by speech recognition, so it has slips, and a few lines may be
the candidate's. Copy the test's questions:
- part1: each Part 1 topic, named in two or three words ("Hometown", "Street markets"), with the
  examiner's questions on it in order. Leave out the questions about the candidate's name and ID.
- part2: task is the cue card's "Describe ..." sentence; points are the "You should say" prompts
  if the examiner read them out, otherwise an empty list.
- part3: the discussion questions, grouped by theme.
Copy each question as the examiner asked it. Fix only clear recognition slips and the examiner's
slips of the tongue. Never add a question that is not in the lines; leave out the candidate's lines."""
QUESTIONS_PROMPT = """You get the transcript of a video in which an IELTS teacher reads recent IELTS Speaking
test questions and answers them. The transcript was made by speech recognition, so it has slips.
List the test questions the teacher reads out (not the answers, and not the teacher's own remarks):
- part1: each Part 1 topic, named in two or three words, with its questions.
- part2: each cue card: task is the "Describe ..." sentence; points are its "You should say"
  prompts as read out, otherwise an empty list.
- part3: each discussion theme with its questions.
Copy each question as it was read, once (teachers often read a list again before answering).
Fix only clear recognition slips. Never add a question that is not in the transcript.
Leave a part empty if the video has none."""
TASK_PROMPT = """This is the transcript of a recorded IELTS Speaking mock test, made by speech recognition.
In Part 2 the candidate talked for up to two minutes about a cue card that the examiner did not
read out. Write the cue card's task as it would be printed: one sentence starting "Describe",
general enough for anyone ("Describe a park you like", not the candidate's own park). Use what
the examiner says ("We've been talking about ...") and what the candidate talks about."""
TASK_SCHEMA = {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}
POINTS_PROMPT = """Write the four "You should say" prompts for this IELTS Speaking Part 2 cue card, as
printed on real cards: short phrases in lower case, without a full stop, that fit this card;
the last one starts "and explain". For example, for "Describe a book you enjoyed reading":
"what the book is", "when you read it", "what it is about", "and explain why you enjoyed it"."""
CARD = {"type": "object", "properties": {"task": {"type": "string"},
                                         "points": {"type": "array", "maxItems": 4, "items": {"type": "string"}}},
        "required": ["task", "points"]}
BANK_SCHEMA = {
    "type": "object",
    "properties": {"part1": {"type": "array", "items": books.TOPIC},
                   "part2": {"type": "array", "items": CARD},
                   "part3": {"type": "array", "items": books.TOPIC}},
    "required": ["part1", "part2", "part3"],
}
POINTS_SCHEMA = {"type": "object", "properties": {"points": {"type": "array", "minItems": 4, "maxItems": 4,
                                                             "items": {"type": "string"}}},
                 "required": ["points"]}


def words_of(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def heard(question: str, transcript: str) -> bool:
    """The question is really in the transcript: at least 3 in 4 of its words, in order, in one
    place, with its last word (the LLM may fix recognition slips, but must not write questions
    of its own)."""
    q, t = words_of(question), words_of(transcript)
    if len(q) < 2:
        return False
    for i in range(0, max(1, len(t) - len(q) + 1)):
        window = t[i:i + len(q) + 4]
        if q[-1] not in window:  # the last word usually says what the question is about
            continue
        found = sum(b.size for b in difflib.SequenceMatcher(None, q, window, autojunk=False).get_matching_blocks())
        if found >= 0.75 * len(q):
            return True
    return False


def task_only(task: str) -> str:
    """The card's first line: "Describe a hobby you enjoy." (some videos read the points with it)."""
    task = re.split(r"[.,]?\s*you should say", task.strip(), flags=re.I)[0].strip().rstrip(".,")
    return task + "." if task else ""


def plain(question: str) -> str:
    """Without the examiner's "Okay, and ..." (the app adds its own; see examiner.lead_in)."""
    q = re.sub(r"^((okay|ok|all right|alright|right|so|and|well|now)[,.]?\s+)+", "", question.strip(), flags=re.I)
    return q[:1].upper() + q[1:]


def keep_heard(topics: list[dict], transcript: str) -> list[dict]:
    out = []
    for topic in topics:
        questions = []
        for q in topic["questions"]:
            q = plain(q)
            if q.endswith("?") and heard(q, transcript) and q.lower() not in map(str.lower, questions):
                questions.append(q)
        if questions:
            out.append({"topic": topic["topic"].strip(), "questions": questions})
    return out


async def points_for(task: str) -> list[str]:
    reply = await llm.complete_json([{"role": "system", "content": POINTS_PROMPT}, {"role": "user", "content": task}],
                                    POINTS_SCHEMA)
    return reply["points"]


def full_text(events: list[tuple[float, str]]) -> str:
    return re.sub(r"\s+", " ", " ".join(t for _, t in events).replace(">>", " ")).strip()


async def mock_test(lines: list[str], events: list[tuple[float, str]]) -> dict | None:
    """A test in the books' format, or None when too little of it could be read."""
    transcript = "\n".join(lines)
    test = await llm.complete_json([{"role": "system", "content": MOCK_PROMPT}, {"role": "user", "content": transcript}],
                                   books.SCHEMA)
    part1, part3 = keep_heard(test["part1"], transcript), keep_heard(test["part3"], transcript)
    if sum(len(t["questions"]) for t in part1) < 3 or sum(len(t["questions"]) for t in part3) < 2:
        return None  # random_test() fills a short Part 1 from the bank
    task = task_only(test["part2"]["task"]).rstrip(".")
    if not task.lower().startswith("describe") or not heard(task, transcript):
        # The examiner seldom reads the card out: the LLM works the task out from the talk.
        reply = await llm.complete_json([{"role": "system", "content": TASK_PROMPT},
                                         {"role": "user", "content": full_text(events)[:24000]}], TASK_SCHEMA)
        task = task_only(reply["task"]).rstrip(".")
        if not task.lower().startswith("describe"):
            return None
        test["part2"]["points"] = []  # written for the task below
    card = {"task": task + ".", "points": test["part2"]["points"]}
    return {"part1": part1, "part2": {**card, "points": await card_points(card, transcript)}, "part3": part3}


async def card_points(card: dict, transcript: str) -> list[str]:
    """The card's points as read out; examiners seldom read them, so usually our own."""
    points = [p.strip() for p in card["points"] if not p.lower().startswith("you should say")]
    if len(points) == 4 and all(heard(p, transcript) for p in points) and points[-1].lower().startswith("and explain"):
        return points
    return await points_for(card["task"])


async def question_bank(events: list[tuple[float, str]]) -> dict:
    transcript = full_text(events)
    bank = await llm.complete_json([{"role": "system", "content": QUESTIONS_PROMPT},
                                    {"role": "user", "content": transcript}], BANK_SCHEMA, max_tokens=8192)
    cards = [{"task": task_only(c["task"]), "points": await card_points(c, transcript)}
             for c in bank["part2"] if c["task"].strip().lower().startswith("describe") and heard(c["task"], transcript)]
    return {"part1": keep_heard(bank["part1"], transcript), "part2": cards, "part3": keep_heard(bank["part3"], transcript)}


# ---- one video, and the whole channel ----

async def process(video: dict) -> dict | None:
    """Reads one video; None when it could not be downloaded (tried again next time)."""
    import yt_dlp
    try:
        path = captions(video["id"])
        events = caption_events(path) if path else []
        if not usable(events, video["kind"]):
            events = caption_events(transcribe(video["id"]))
    except (yt_dlp.utils.DownloadError, StopIteration, OSError) as e:
        log.warning("%s: %s (run it again later)", video["id"], e)
        return None
    result = {"id": video["id"], "title": video["title"], "kind": video["kind"]}
    if video["kind"] == "mock":
        lines = examiner_lines(events)
        result["examiner"] = lines
        result["test"] = await mock_test(lines, events) if len(lines) >= 10 else None
    else:
        result["bank"] = await question_bank(events)
    return result


def merge(topics: list[dict], new: list[dict]):
    """Adds topics to a bank part: same topic name, new questions only."""
    by_name = {t["topic"].lower(): t for t in topics}
    for topic in new:
        mine = by_name.get(topic["topic"].lower())
        if mine is None:
            mine = by_name[topic["topic"].lower()] = {"topic": topic["topic"], "questions": []}
            topics.append(mine)
        have = {q.lower() for q in mine["questions"]}
        mine["questions"] += [q for q in topic["questions"] if q.lower() not in have]


def build():
    """tests.json and bank.json from every video read so far."""
    results = [json.loads(p.read_text()) for p in sorted((folder() / "read").glob("*.json"))]
    tests = [{"test": i, "video": r["id"], **r["test"]}
             for i, r in enumerate((r for r in results if r.get("test")), 1)]
    book = {"id": BOOK_ID, "title": BOOK_TITLE, "file": CHANNEL, "tests": tests}
    (folder() / "tests.json").write_text(json.dumps(book, indent=1, ensure_ascii=False))
    bank = {"part1": [], "part2": [], "part3": []}
    for r in results:
        parts = r.get("bank") or ({k: r["test"][k] for k in ("part1", "part3")} | {"part2": [r["test"]["part2"]]}
                                  if r.get("test") else None)
        if not parts:
            continue
        merge(bank["part1"], parts["part1"])
        merge(bank["part3"], parts["part3"])
        tasks = {c["task"].lower() for c in bank["part2"]}
        bank["part2"] += [c for c in parts["part2"] if c["task"].lower() not in tasks]
    (folder() / "bank.json").write_text(json.dumps(bank, indent=1, ensure_ascii=False))
    log.info("%d mock tests, %d Part 1 topics, %d cue cards, %d Part 3 themes in %s", len(tests), len(bank["part1"]),
             len(bank["part2"]), len(bank["part3"]), folder())


def llm_running() -> bool:
    try:
        return httpx.get(LLM_HEALTH, timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def start_llm() -> subprocess.Popen | None:
    """Starts the LLM server for the import, unless it is already running."""
    if llm_running():
        return None
    log.info("Starting the LLM server ...")
    server = subprocess.Popen(["make", "-s", "llm"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              start_new_session=True)
    deadline = time.time() + 600
    while not llm_running():
        if server.poll() is not None or time.time() > deadline:
            raise SystemExit("The LLM server did not start: try `make llm` to see why.")
        time.sleep(1)
    return server


async def run():
    folder().mkdir(parents=True, exist_ok=True)
    (folder() / "read").mkdir(exist_ok=True)
    videos = [v for v in list_videos() if v["kind"]]
    (folder() / "videos.json").write_text(json.dumps(videos, indent=1, ensure_ascii=False))
    new = [v for v in videos if not (folder() / "read" / f"{v['id']}.json").exists()]
    log.info("%d mock tests and question videos on the channel, %d new", len(videos), len(new))
    server = start_llm() if new else None
    try:
        for i, video in enumerate(new, 1):
            result = await process(video)
            if result is None:
                continue
            (folder() / "read" / f"{video['id']}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
            got = ("a test" if result.get("test") else "no test") if video["kind"] == "mock" else \
                f"{sum(len(t['questions']) for p in ('part1', 'part3') for t in result['bank'][p])} questions"
            log.info("[%d/%d] %s: %s", i, len(new), video["title"], got)
    finally:
        if server:
            os.killpg(server.pid, signal.SIGINT)
            server.wait(30)
    build()


# ---- used by the app ----

def load_book() -> dict | None:
    path = folder() / "tests.json"
    if not path.exists():
        return None
    book = json.loads(path.read_text())
    return book if book["tests"] else None


PART1_QUESTIONS = 9  # about five minutes


def random_test() -> dict | None:
    """A whole mock test, for a session started without a book test or topic. Part 1 is
    filled up to PART1_QUESTIONS with topics from the bank (the transcripts miss some)."""
    book = load_book()
    if not book:
        return None
    test = random.choice(book["tests"])
    part1 = list(test["part1"])
    have = {t["topic"].lower() for t in part1}
    spare = [t for t in load_bank()["part1"] if t["topic"].lower() not in have and len(t["questions"]) >= 3]
    random.shuffle(spare)
    while sum(len(t["questions"]) for t in part1) < PART1_QUESTIONS and spare:
        part1.append({**(t := spare.pop()), "questions": t["questions"][:3]})
    return {**test, "part1": part1, "book": book["title"]}


def load_bank() -> dict:
    path = folder() / "bank.json"
    return json.loads(path.read_text()) if path.exists() else {"part1": [], "part2": [], "part3": []}


def bank_topic(part: str, name: str) -> dict | None:
    """The bank's questions on a topic ("part1" or "part3"), matched by name: "pets" finds "Pets
    and animals"."""
    wanted = set(words_of(name)) - {"and", "the", "a", "of", "your"}
    if not wanted:
        return None
    matches = [t for t in load_bank()[part] if wanted <= set(words_of(t["topic"])) and len(t["questions"]) >= 3]
    return random.choice(matches) if matches else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(run())
