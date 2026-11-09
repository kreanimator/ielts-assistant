# Plan

## Hardware target

The defaults fit one 16 GB GPU (developed on an RTX 4060 Ti 16 GB with 32 GB RAM):

| Model | VRAM |
|---|---|
| Whisper large-v3-turbo (int8) | ~2 GB |
| wav2vec2 phoneme model (milestone 4) | ~1.3 GB |
| Qwen3.5-9B Q5_K_M, 8k context | ~7 GB |
| Kokoro-82M | <1 GB |

On smaller GPUs, use a smaller quantization (`make llm LLM_FILE=Qwen3.5-9B-Q4_K_M.gguf`)
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
3. **Calibration:** sample answers with known examiner bands (from your own
   books, kept in `data/private/`) are used to check and tune the scorer.

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
2. Flutter web UI: dialogue window, live transcript, mode picker
3. Live analyst and corrections panel
4. Measured fluency features and pronunciation scoring
5. Final report with band estimates; history and progress charts
6. Book importer
7. Full exam mode with strict timing
