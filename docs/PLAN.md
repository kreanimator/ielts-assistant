# Plan

## Hardware target

The defaults fit one 16 GB GPU (developed on an RTX 4060 Ti 16 GB with 32 GB RAM):

| Model | VRAM |
|---|---|
| Whisper large-v3-turbo (int8) | ~2 GB |
| wav2vec2 phoneme model (fp16) | ~0.7 GB |
| Qwen3.5-9B Q5_K_M, 8k context | ~7 GB |
| Kokoro-82M | <1 GB |

On smaller GPUs or 8 GB Macs, use the 4B model (`make install LLM=4B`, then `make start LLM=4B`) or a smaller quantization (`make llm LLM_FILE=Qwen3.5-9B-Q4_K_M.gguf`)
and a smaller Whisper model. If the analyst needs more quality later, the next step
is Qwen3.6-35B-A3B (MoE) with part of the experts in system RAM.

Measured on the development machine (RTX 4060 Ti, Vulkan build): the LLM writes
about 35 tokens/s, Kokoro speaks a sentence in 0.05 s, Whisper transcribes an
answer in about 0.2 s. The first examiner audio starts 0.6–0.8 s after the
end-of-turn pause.

## Architecture

```
Flutter Web  ──WebSocket (audio chunks, events)──►  Python FastAPI backend
  - dialogue window + avatar                            ├─ VAD → Whisper → transcript (streamed)
  - live transcript panel                               ├─ Examiner agent (LLM) → Kokoro TTS → audio
  - corrections panel                                   ├─ Analyst agent (same LLM, async per answer)
  - session history, report view                        ├─ Pronunciation scorer (wav2vec2)
  - persona / voice / mode picker                       ├─ Scorer (metrics + rubric → bands)
                                                        └─ SQLite + audio files in data/
```

- One LLM plays both roles (examiner and analyst), so we need only one set of
  weights in VRAM. The analyst checks your last answer while the examiner's
  reply is being spoken.
- Whisper hides fillers ("um", "uh") and repetitions by default. We prompt it
  to keep them, use word timestamps, and measure pauses with the VAD.

### Modules

The app is split by IELTS skill. Each module has its own package, routes and screens,
on top of a shared core:

```
backend/app/
  main.py        builds the app and mounts each module's router
  core/          settings, the LLM client, SQLite storage, the history API,
                 reading your books' pages (text layer or OCR, cached), scanned pages in
                 reading order (columns), their answer keys (Listening and Reading), the
                 clock of timed tests, band tables
  speaking/      examiner, analyst, exam timing, STT/TTS/VAD, fluency, pronunciation,
                 intonation, report, drills, topics, book import
                 routes: /api/speaking/*, /ws/speaking
  writing/       Writing tests and answers from your books, new tasks from the LLM, the timed
                 full test, the assessor and report; routes: /api/writing/*
  reading/       Reading tests from your books as text (passages, question groups and their
                 controls), the timed test, marking with the answer key; routes: /api/reading/*
frontend/lib/
  main.dart      the app
  home/          the dashboard: a band per skill, the overall band, progress, recent sessions
  core/          what every module shares: the backend's address, history, the report view,
                 band charts, the history page
  modules/       registry.dart (each skill's card, page, session and history pages)
    speaking/
    writing/
    reading/
```

Sessions carry their module. A module registers itself in core/modules.py with its training
modes (for titles) and its report builder; `/api/dashboard` (core/dashboard.py) works out
each skill's band (the average of the last 5 sessions with a band, IELTS rounding) and the
overall band (the average of the skills with a band, marked partial until there are four).

## Modes

| Mode | Behaviour |
|---|---|
| Full exam | Parts 1–3 with official timing, a 1-minute Part 2 prep timer, no live corrections, full report at the end |
| Single part | Part 1, 2 or 3 only; live corrections optional |
| Free topic | Relaxed conversation partner, live corrections on |
| Drill | Practise one weak area (a phoneme, linking words, a tense) |

## Scoring

Each of the four criteria gets a band from 0 to 9. The overall band is their
average, rounded to the nearest half band.

1. **Measured features:** speech rate, pause length and frequency, fillers,
   self-corrections, vocabulary range and CEFR level, errors per 100 words,
   phoneme accuracy.
2. **Rubric judgment:** the LLM scores the transcript and the features against
   the public band descriptors, and must quote evidence from the answers.
3. **Calibration:** public datasets with expert scores check and tune the scorer
   (see "How realistic are the bands?" in the README).

## Your books

The importer reads PDFs from `data/private/books/` (never committed):

1. Extract text with pypdf/pdfplumber. Fall back to Tesseract OCR on pages
   without a text layer.
2. Find the Speaking sections and split them into Part 1 topics, Part 2 cue
   cards and Part 3 discussion questions.
3. Save them to the local SQLite question bank, tagged by book and test.
4. Optionally import sample answers and examiner comments for calibration.

The repository ships only a small set of original questions, so the app works
without any books.

## Milestones

1. ✅ Backend voice loop: mic → transcript → LLM reply → spoken reply
2. ✅ Flutter web UI: dialogue window with avatar, live transcript, mode and voice picker
   (free conversation, Part 1, Part 3; Part 2 and the full exam came with milestone 7)
3. ✅ Live analyst and corrections panel (grammar, vocabulary, fluency, coherence;
   can be hidden until the session ends)
4. ✅ Measured fluency (speed, pauses, fillers, repetitions) and pronunciation scoring
   (phoneme recognition aligned with the CMU dictionary; flags sound patterns like /θ/ said as /s/)
5. ✅ Session report with band estimates (the LLM judges Fluency and Coherence, Lexical Resource
   and Grammar against the band descriptors and quotes evidence; Pronunciation comes from the
   measured score, with a first-guess mapping still to calibrate), session history in SQLite with
   answer recordings, and progress charts
6. ✅ Book importer: Speaking tests from your own PDF books (text layer, or OCR for scanned
   pages), structured by the LLM into Part 1 topics, the Part 2 cue card and Part 3 topics;
   Part 1 and Part 3 practice can use a real test's questions
7. ✅ Full exam with strict timing (Part 1 and Part 3 about 5 minutes each, with no new question in
   the last 30 seconds and an answer cut off at the limit; Part 2 with the cue card, one minute
   to prepare and up to two minutes of talk, cut off at the limit, then a rounding-off question;
   no live corrections; the report at the end), and Part 2 as its own practice mode. Timing is
   kept on the server, so a slow browser cannot stretch it
8. ✅ Topics: suggestions while you type (our own A-Z list plus the topics of your imported
   tests). (Its first letter picker only filled the topic field; item 14 replaced it.)
9. ✅ Calibrated scores: the Pronunciation band is fitted to expert ratings (speechocean762),
   and the other bands are checked against examiners' scores (Speak & Improve Corpus 2025);
   `make calibrate-pronunciation` and `make calibrate-bands` repeat the checks
10. ✅ Drills: sound drills (repeat sentences full of one sound, see how many came out right)
   and language drills (questions that need one structure, checked first by the analyst),
   with the sounds you miss most suggested first
11. ✅ Easy install on Linux and Apple Silicon Macs (the Mac path is not yet tested on a real Mac): `make install` (Python from uv, models,
   llama.cpp build for the computer, the web app built or downloaded) and `make start`
   (both servers, the browser, Ctrl+C stops all); the device is chosen automatically
12. ✅ Intonation: the pitch range of each answer, "Flat intonation" below 3 semitones, and in
   the report's Pronunciation evidence (advice only: it did not predict experts' scores).
   Word stress was tried on speechocean762 and left out: 9 of 10 warnings would be false
13. ✅ Band accuracy checked on 168 held-out tests (MAE 0.72, no bias overall). Averaging
   several judgements and mixing in measured numbers were tried and did not help reliably;
   the report retries an LLM reply that is cut off or fails
14. ✅ By letter: choose or roll a letter, get a random topic card from
   eslconversationquestions.com (downloaded once with `make esl-topics` into data/private/,
   never committed), and the examiner asks eight of its questions word for word
15. ✅ Renamed to IELTS Assistant and split into modules: a shared core and the Speaking
   module (its routes moved to /api/speaking/* and /ws/speaking), so other skills can be added
16. ✅ Home screen: a dashboard to choose a skill, with the estimated band per skill (the
   average of the last 5 sessions with a band), an overall band (IELTS rounding, marked as
   partial until all four skills have one), progress and recent sessions; sessions have a
   module (older ones become Speaking), and history, reports and charts moved to the core
17. ✅ Writing tests from your books: General Training Task 1 (letters) and Task 2 (essays),
   and Academic Task 2 essays, with the books' sample answers (band and examiner's comment),
   model answers, and `make writing-books` to import them from the cached page texts.
   Headings and bands are read by the code; the LLM copies the prompts and finds where each
   answer starts, and never writes an answer. Answers printed in handwriting are read by OCR
   with the PDF, else only their band and comment are kept
18. ✅ Writing practice: Task 1 (letters) and Task 2 (essays) from your books or new ones written
   by the LLM, with a word counter, the clock and a draft kept in the browser; assessed on Task
   Achievement / Task Response, Coherence and Cohesion, Lexical Resource and Grammar (evidence
   quoted; words counted by the code, with a length penalty), corrections marked in the text,
   and a writing band (Task 2 counts twice when both tasks are done). The bands are checked
   against 36 sample answers in the books (`make calibrate-writing`): the LLM was 0.86 bands
   too low, and a +0.9 shift brings it to +0.04 on average, 0.62 bands off per answer
19. ✅ Full Writing test: both tasks of one test in 60 minutes, timed on the server (answers saved
   every 5 seconds, none accepted after the deadline, handed in when the time is up, and a
   test left open continues or ends by itself); every task counts (none: band 0, 20 words or
   fewer: band 1), Task 2 twice
20. ✅ Reading from your books, like the computer-delivered test: Academic and General Training
   passages as text beside their questions, each with its control (TRUE / FALSE / NOT GIVEN
   buttons, multiple choice, letters or headings to pick, gaps inside notes and sentences), a
   bar of the parts and question numbers, 60 minutes timed on the server, marked with the
   books' answer keys and given a band from the official raw-score tables, with the score of
   each passage and a marked review of the test. The scans are read with OCR by position: the
   passages in column order, the questions cut into groups by their headings, a group that
   cannot be read for sure shown as its part of the page. The keys are read three times at
   different sizes (an answer counts when two agree), and a test is offered only when all 40
   answers were read for sure and each letter is one of its question's choices
21. Listening from your books: the CD recordings played once, as in the test, with the
   questions shown and answered the same way as in Reading, answer keys (already read in milestone 20) and band table
