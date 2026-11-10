# IELTS Speaking Assistant

A local, private practice partner for the IELTS Speaking test. You talk into the
microphone, an AI examiner talks back, a second agent checks your answers live, and
after each session you get a report with an estimated band for each IELTS criterion.

Everything runs on your own computer. No cloud APIs, no accounts, no telemetry.

> **Status:** milestones 1–14 work: a one-command install on Linux and Apple Silicon Macs, voice conversation with an AI examiner in the
> web app, the full exam with real timing, practice of each part on its own
> (including the Part 2 cue card with a preparation minute), topic cards by letter,
> drills for weak sounds and structures, corrections, fluency numbers and a
> pronunciation and intonation check on each answer, a band report at the end of each session
> (checked against human examiners' scores), a history with your recordings and
> progress charts, and real test questions imported from your own books. See [docs/PLAN.md](docs/PLAN.md).

## Run it

Works on **Linux** with an NVIDIA GPU (about 10 GB of free GPU memory; developed on an
RTX 4060 Ti 16 GB) and on **Macs with Apple Silicon** (M1 or newer, 16 GB of memory or
more; 8 GB with the smaller LLM). You also need `git`, `make` and `curl` (on a Mac:
`xcode-select --install`), Chrome or Edge, and about 15 GB of disk space.

```bash
git clone https://github.com/kreanimator/ielts-speaking-assistant.git
cd ielts-speaking-assistant
make install    # once: Python 3.12, the models (about 10 GB) and the web app
make start      # starts everything and opens http://127.0.0.1:8000; Ctrl+C stops it
```

Allow the microphone, choose a training mode and press **Start**. Use headphones if
you can. After the install nothing is downloaded: the app's fonts and renderer are
bundled. If something does not start, the servers' output is in `data/logs/`.

What `make install` sets up for your computer:

| | Linux + NVIDIA | Mac (Apple Silicon) |
|---|---|---|
| LLM (llama.cpp) | CUDA build (driver 570 or newer), else Vulkan | Metal build |
| Speech models (Kokoro, pronunciation) | GPU | Apple GPU |
| Whisper (speech to text) | `large-v3-turbo` on the GPU | `small.en` on the CPU |

- **Python** comes from [uv](https://docs.astral.sh/uv/), which is installed first if
  you don't have it. The project's Python stays in `.venv/`.
- **The web app** is built with Flutter if you have it (3.38 or newer); otherwise the
  build of the latest `main` is downloaded from the project's releases.
- **Smaller LLM:** with 8 GB of memory, or if answers come slowly, use the 4B model:
  `make install LLM=4B`, then `make start LLM=4B`. The band calibration was done
  with the 9B model, so bands from the 4B model are less certain.
- **Faster Whisper on a fast Mac:** `WHISPER_MODEL=large-v3-turbo make start` is
  more accurate, but slower on the CPU.
- **Other Linux GPUs:** AMD and Intel GPUs use the Vulkan build of llama.cpp; the
  speech models then run on the CPU. Without a GPU: `make install LLAMA_BUILD=ubuntu-x64`
  (slow). Windows is not supported; WSL2 may work.
- **With NVIDIA driver 580**, prefer the CUDA build (the default): the Vulkan build can
  leave the GPU at idle clocks and run 10 times slower.

The servers can also be started on their own, each in its own terminal: `make llm`
(the LLM server) and `make run` (the backend). For frontend work with hot reload, run
`make frontend-dev` and open http://127.0.0.1:5000. A plain developer test page is at
http://127.0.0.1:8000/dev.

### Practise with your own IELTS books

If you own IELTS books as PDF files, import their Speaking tests (with the LLM
server running):

```bash
make books BOOKS='~/Books/IELTS/*.pdf'
```

Scanned books are read with OCR, about 1 second per page; books with a text layer
take under a minute. Books in the three-part Speaking format work (Cambridge IELTS 3
and later); the older role-play format of Cambridge IELTS 1 and 2 is skipped. The tests are saved in `data/private/books/`, which git
ignores. Then choose a training mode and pick a test under **Questions**.

### The full exam

**Full exam** runs Parts 1, 2 and 3 in about 14 minutes, timed like the real test:

- **Part 1** (about 5 minutes): after 4½ minutes no new question is asked, and at
  5 minutes an answer still going on is cut off.
- **Part 2**: you get a cue card and one minute to prepare (you can type notes),
  then up to two minutes to talk. The examiner stops you at two minutes, or when
  you have been silent for 5 seconds, and asks one short follow-up question.
- **Part 3** (about 5 minutes): a discussion of ideas linked to your Part 2 topic,
  timed like Part 1.

Corrections stay hidden until the end, and then the band report opens. Without a
book test, the cue card is one of the app's own cards, or one written for the topic
you type. **Part 2 · Long turn** practises the long turn on its own, and there you
may start before the minute is over. The times can be changed for practice; see
`PART1_SECONDS` and the settings below it in [backend/app/config.py](backend/app/config.py).

### By letter

**By letter** practises with the topic cards of
[eslconversationquestions.com](https://www.eslconversationquestions.com/english-conversation-questions/topics/):
choose a letter (or roll a random one) and you are dealt a random topic that starts
with it, such as A: *Advice*. The examiner asks eight of that topic's questions, word
for word, from easy to hard (or all at one level, if you choose one), reacts to each
answer and asks for more when an answer is short. Download the cards once:

```bash
make esl-topics    # 141 topics, about 2.5 minutes, saved in data/private/esl/
```

The site's terms allow copying its free questions for your own lessons, with a link to
the source, but not publishing them as a collection. So the questions are downloaded
to your computer for your own practice, are never part of this repository, and each
card links to its page on the site. Thanks to ESL Conversation Questions for them.

### Topics

In the other modes, the topic field suggests topics as you type: the app's own A–Z
list and the topics of your imported tests.

Settings such as the voice or the end-of-turn pause are environment variables;
see [backend/app/config.py](backend/app/config.py).

### Drills

**Drill** practises one weak area. In a **sound drill** (/θ/, /ð/, /v/, /w/, /r/, /l/,
/ɪ/, /æ/) the examiner says six short sentences full of that sound, you repeat each
one, and you see how many of the sounds came out right and which words to try again.
In a **language drill** (past tenses, the future, conditionals, linking words,
comparisons, opinions with reasons) the examiner asks six questions that need that
structure, and the corrections check it first. The sounds you got wrong most often
in your recent sessions are suggested at the top of the list. Drills get no band
estimate.

## How realistic are the bands?

The bands are checked against scores that human experts gave, using two public
datasets. Neither is included in this repository: download them yourself into
`data/private/calibration/` (git-ignored) to repeat the checks.

| Criterion | Checked against | Result on held-out data |
|---|---|---|
| Pronunciation | [speechocean762](https://www.openslr.org/101) (CC BY 4.0): 5,000 English sentences by learners, each scored by five experts. 61 adult speakers held out | On average 0.16 bands too low, 0.57 bands off per speaker. (The first, uncalibrated mapping was 1.27 bands too low.) |
| Fluency and Coherence, Lexical Resource, Grammatical Range and Accuracy | [Speak & Improve Corpus 2025](https://researchdatasets.cambridge.org/datasets/speak-and-improve-corpus-2025) (Cambridge University Press & Assessment; free after registration, noncommercial licence, no redistribution): spontaneous learner speech with examiner scores aligned to CEFR | Overall, on 168 held-out tests: on average 0.06 bands too low, 0.72 bands off per test; within half a band of the examiners in 45% of tests and within one band in 76%. (Before calibration the LLM was 0.8 bands too low, and squeezed everyone between 4.5 and 5.5.) |

```bash
make calibrate-pronunciation          # downloads speechocean762 (about 500 MB) the first time
make calibrate-bands SET=eval N=60    # needs the Speak & Improve files and the LLM server
```

Limits to keep in mind:

- Speak & Improve scores are holistic CEFR levels, not IELTS bands. They are
  converted with the official IELTS–CEFR alignment (B1 = 4–5, B2 = 5.5–6.5,
  C1 = 7–8), which is itself approximate, so differences under half a band are noise.
- The LLM's bands follow the examiners' only moderately (correlation 0.55): the
  average is right, but a single session can be a band off, and very weak or very
  strong speakers are pulled toward the middle (examiners' band 4: about 1.4 too
  high; band 8: about 0.9 too low). Look at the trend over several sessions rather
  than one report.
- What did not help: judging each session three times and averaging, and mixing
  measured numbers (speaking speed, grammar errors per 100 words) into the bands.
  Fitted on 108 tests, the best mix was 0.05 bands closer on 120 others, which is
  within chance, and it all but ignored the examiner-style judgement.
- speechocean762 is read-aloud speech from Mandarin speakers; free speech and other
  accents may score a little differently.
- Pronunciation comes from individual sounds and is capped at 8.5, because word
  stress and intonation are part of the IELTS band but cannot raise ours (next point).
- **Intonation** is measured: the app tracks your pitch and shows "Flat intonation"
  when your voice moves less than 3 semitones in an answer (about 1 in 10 learners
  reading aloud in speechocean762). It is advice only: across speechocean762's
  speakers, pitch range followed the experts' prosody scores only weakly
  (correlation 0.19) and did not improve the band's accuracy on held-out speakers.
- **Word stress is not checked.** We tried: in each longer word, find the vowel
  that is loudest, highest and longest, and compare it with the dictionary. On
  words the experts marked correctly stressed, it disagreed 27% of the time, so 9
  of 10 of its warnings would have been false alarms. Showing them would mislead.

## Features

- **Modes:** full exam (Parts 1–3 with real timing), a single part, free-topic
  conversation, drills
- **Live panels:** examiner avatar, your live transcript, corrections
- **Report:** estimated band for Fluency & Coherence, Lexical Resource,
  Grammatical Range & Accuracy and Pronunciation, each backed by measured
  evidence and suggested fixes
- **History:** past sessions, replay of your recordings, progress over time
- **Your own material:** import questions from IELTS books you own (kept private,
  see below)

## Important notices

**Not affiliated with IELTS.** IELTS is a registered trademark of the British
Council, IDP: IELTS Australia and Cambridge University Press & Assessment. This
project is independent, and none of them endorse it. The name is used only to
describe what the software helps you practise.

**Scores are estimates.** The bands this software gives are automated estimates
for practice only. They are not official IELTS results, and they can differ from
what a real examiner would give.

**No exam content is distributed.** This repository contains no material from
published IELTS books or tests. The importer works only on files you supply,
and it stores them in `data/private/`, which git ignores. Do not commit or share
copyrighted material.

**Your data stays local.** Recordings, transcripts and reports are saved under
`data/` on your machine (`data/ielts.db` and `data/sessions/`) and are never
uploaded anywhere. Delete a session from the History page to remove it.

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md). You may use, modify and share this
software for any **noncommercial** purpose: personal study, teaching, research,
charities and similar. Commercial use requires separate permission from the
author.

The software is provided **as is, without warranty**, and the author is not
liable for any damages (see the "No Liability" section of the license).

Third-party models and libraries keep their own licenses; see
[THIRD_PARTY.md](THIRD_PARTY.md). Model weights are not included in this
repository. They are downloaded from their original sources on first run, under
their own licenses.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
