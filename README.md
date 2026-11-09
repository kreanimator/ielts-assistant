# IELTS Speaking Assistant

A local, private practice partner for the IELTS Speaking test. You talk into the
microphone, an AI examiner talks back, a second agent checks your answers live, and
after each session you get a report with an estimated band for each IELTS criterion.

Everything runs on your own computer. No cloud APIs, no accounts, no telemetry.

> **Status:** milestones 1–5 work: voice conversation with an AI examiner in the
> web app, in three training modes, with corrections, fluency numbers and a
> pronunciation check on each answer, a band report at the end of each session,
> and a history with your recordings and progress charts. Importing your own exam
> books comes next. See [docs/PLAN.md](docs/PLAN.md).

## Run it

You need Linux, Python 3.12, Flutter 3.38+, a GPU with about 10 GB of free memory
(developed on an RTX 4060 Ti 16 GB) and Chrome or Edge.

```bash
make setup      # Python environment (once, a few minutes)
make frontend   # build the web app (after each frontend change)
make llm        # downloads the LLM (6.6 GB) and llama.cpp once, then runs the LLM server
make run        # in a second terminal: the backend
```

Open http://127.0.0.1:8000, allow the microphone, choose a training mode and
press **Start**. Use headphones if you can. Whisper and Kokoro download their
models (about 3.5 GB) the first time the backend starts. After that, nothing is
downloaded: the app's fonts and renderer are bundled.

For frontend work with hot reload, run `make frontend-dev` and open
http://127.0.0.1:5000. A plain developer test page is at http://127.0.0.1:8000/dev.

The LLM server uses llama.cpp's **Vulkan** build, because it works with any recent
NVIDIA, AMD or Intel driver. With NVIDIA driver 570 or newer you can use the
faster CUDA build: `make llm LLAMA_BUILD=ubuntu-cuda-12.8-x64`.

Settings such as the voice or the end-of-turn pause are environment variables;
see [backend/app/config.py](backend/app/config.py).

## Features (planned)

- **Modes:** full exam (Parts 1–3 with real timing), a single part, free-topic
  conversation, targeted drills
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
