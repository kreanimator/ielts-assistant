# Third-party components

This project depends only on components with **permissive licenses** (MIT, BSD,
Apache-2.0, public domain). LGPL components are allowed only when they run as a
separate process. This keeps the project free to use its own noncommercial
license, and keeps it legally safe to redistribute.

Model weights are **not** stored in this repository. They are downloaded from
their original source, and each stays under its own license.

## Models

| Purpose | Model | License | Source |
|---|---|---|---|
| Voice activity detection | Silero VAD | MIT | https://github.com/snakers4/silero-vad |
| Speech to text | Whisper large-v3-turbo | MIT | https://huggingface.co/openai/whisper-large-v3-turbo |
| Phoneme recognition (pronunciation) | wav2vec2-xlsr-53-espeak-cv-ft | Apache-2.0 | https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft |
| Examiner and analyst LLM | Qwen3-14B / Qwen3-8B (GGUF) | Apache-2.0 | https://huggingface.co/Qwen |
| Alternative LLM | Mistral Small 3.x | Apache-2.0 | https://huggingface.co/mistralai |
| Text to speech | Kokoro-82M | Apache-2.0 | https://huggingface.co/hexgrad/Kokoro-82M |

## Libraries and tools

| Purpose | Component | License |
|---|---|---|
| Speech-to-text runtime | faster-whisper / CTranslate2 | MIT |
| LLM runtime | llama.cpp / llama-cpp-python | MIT |
| TTS text processing | misaki (without the espeak-ng fallback) | Apache-2.0 |
| Pronunciation dictionary | CMUdict | BSD-2-Clause |
| Grapheme to phoneme | g2p_en | Apache-2.0 |
| ML framework | PyTorch | BSD-3-Clause |
| Backend | FastAPI, Uvicorn | MIT, BSD-3-Clause |
| Database | SQLite | Public domain |
| PDF text extraction | pypdf, pdfplumber | BSD-3-Clause, MIT |
| OCR (scanned pages) | Tesseract | Apache-2.0 |
| Frontend | Flutter / Dart | BSD-3-Clause |
| Grammar check (optional, separate process) | LanguageTool | LGPL-2.1 |

## Not allowed

These are excluded on purpose:

| Component | Reason |
|---|---|
| Llama, Gemma models | Custom licenses with usage restrictions, not open source |
| XTTS-v2, F5-TTS weights | Weights licensed for noncommercial use only, with their own extra terms |
| eSpeak-ng, any GPL/AGPL library | Copyleft terms conflict with this project's license when combined |
| PyMuPDF | AGPL-3.0 |
| Any cloud API | Everything must run locally |

Before adding a new dependency, check its license and add it to this file.
