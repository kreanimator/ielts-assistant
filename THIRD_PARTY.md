# Third-party components

## Policy

- Code and models must have a **permissive license**: MIT, BSD, Apache-2.0, ISC, PSF
  or public domain.
- Weak copyleft (**LGPL, MPL**) is allowed only for libraries installed unmodified
  as normal dependencies, never copied into this repository.
- Fonts may be **SIL OFL 1.1**. They are bundled unmodified, with their license file.
- **GPL and AGPL are not allowed**, including as dependencies of dependencies.
  Their terms conflict with this project's noncommercial license.
- Model weights and third-party binaries are **not stored in this repository**.
  `make setup` and `make llm` download them from their original sources, and they
  stay under their own licenses.

Before adding a dependency, check its license and add it here.

## Models

| Purpose | Model | License | Source |
|---|---|---|---|
| Voice activity detection | Silero VAD | MIT | https://github.com/snakers4/silero-vad |
| Speech to text | Whisper large-v3-turbo (CTranslate2 conversion) | MIT | https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo (formerly mobiuslabsgmbh; original: https://huggingface.co/openai/whisper-large-v3-turbo) |
| Examiner and analyst LLM | Qwen3.5-9B, GGUF Q5_K_M | Apache-2.0 | https://huggingface.co/unsloth/Qwen3.5-9B-GGUF (original: https://huggingface.co/Qwen/Qwen3.5-9B) |
| Larger LLM option | Qwen3.6-35B-A3B | Apache-2.0 | https://huggingface.co/Qwen/Qwen3.6-35B-A3B |
| Text to speech | Kokoro-82M | Apache-2.0 | https://huggingface.co/hexgrad/Kokoro-82M |
| English tagger for TTS | spaCy en_core_web_sm | MIT | https://github.com/explosion/spacy-models |
| Phoneme recognition (pronunciation) | wav2vec2-lv-60-espeak-cv-ft | Apache-2.0 | https://huggingface.co/facebook/wav2vec2-lv-60-espeak-cv-ft |
| OCR for scanned book pages | PP-OCRv6 detection and recognition, PP-OCR text direction (ONNX, shipped inside the rapidocr package) | Apache-2.0 | https://github.com/RapidAI/RapidOCR (original: https://github.com/PaddlePaddle/PaddleOCR) |

## Data

| Purpose | Data | License |
|---|---|---|
| Pronunciation dictionary | CMUdict, downloaded through nltk | BSD-2-Clause |
| Calibrating the Pronunciation band (optional, never committed) | speechocean762, Zhang et al., Interspeech 2021, https://www.openslr.org/101 | CC BY 4.0 |
| Checking the other bands (optional, never committed) | Speak & Improve Corpus 2025, Cambridge University Press & Assessment, https://researchdatasets.cambridge.org/datasets/speak-and-improve-corpus-2025. Transcripts and scores only, used with the local LLM | Speak & Improve Corpus licence: noncommercial use, registration required, no redistribution |

## Main libraries and tools

| Purpose | Component | License |
|---|---|---|
| LLM server | llama.cpp (prebuilt Vulkan release, downloaded by `make llm`) | MIT |
| Speech to text | faster-whisper, CTranslate2 | MIT |
| Voice activity detection | silero-vad, onnxruntime | MIT |
| ML framework | PyTorch | BSD-3-Clause |
| Text to speech | kokoro, misaki (installed without their eSpeak dependencies) | Apache-2.0 |
| Unknown-word pronunciation | g2p_en (installed without the unused GPL `Distance` package) | Apache-2.0 |
| Kokoro's text encoder | transformers, tokenizers, huggingface_hub, safetensors | Apache-2.0 |
| English text processing | spaCy, thinc, nltk, inflect, regex, addict | MIT, MIT, Apache-2.0, MIT, Apache-2.0, MIT |
| Number words for TTS | num2words | LGPL-2.1 (unmodified library) |
| Backend | FastAPI, Starlette, Uvicorn, httpx, websockets | MIT, BSD-3-Clause, BSD-3-Clause, BSD-3-Clause, BSD-3-Clause |
| Database | SQLite (Python's built-in sqlite3) | Public domain |
| Book importer: PDF text | pypdf, cryptography (for encrypted PDFs) | BSD-3-Clause, Apache-2.0 OR BSD-3-Clause |
| Book importer: OCR | pypdfium2 (PDFium), rapidocr, onnxruntime, Shapely, pyclipper, omegaconf, colorlog, Pillow | Apache-2.0 / BSD-3-Clause, Apache-2.0, MIT, BSD-3-Clause, MIT, BSD-3-Clause, MIT, MIT-CMU |
| Book importer: images | opencv-python-headless (its wheel bundles FFmpeg libraries, LGPL-2.1, unmodified) | Apache-2.0 |
| Frontend | Flutter, Dart, packages `http` and `web` | BSD-3-Clause |
| Frontend font | Roboto, Noto Sans (bundled in `frontend/assets/fonts`) | SIL OFL 1.1 |

Smaller transitive dependencies are all MIT, BSD, Apache-2.0, ISC, PSF or MPL-2.0
(certifi, tqdm). `make license-check` lists them.

## Not open source, but required for the GPU

The PyTorch CUDA build installs NVIDIA's CUDA runtime libraries (cuBLAS, cuDNN, etc.).
They are free to use and redistribute, but proprietary, under the NVIDIA license.
They are runtime libraries like the GPU driver, not part of this project.

## Excluded

| Component | Reason |
|---|---|
| eSpeak-ng, phonemizer | GPL-3.0; Kokoro's default fallback, replaced by CMUdict + g2p_en |
| Distance | GPL; declared by g2p_en but never used by it |
| PyMuPDF | AGPL-3.0 |
| pdf2image, pdftotext (Poppler) | GPL; pypdf and PDFium do the same job |
| Llama, Gemma models | Custom licenses with usage restrictions, not open source |
| XTTS-v2, F5-TTS weights | Licenses with extra noncommercial terms of their own |
| Any cloud API | Everything must run locally |
