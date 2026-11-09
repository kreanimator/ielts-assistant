# Third-party components

## Policy

- Code and models must have a **permissive license**: MIT, BSD, Apache-2.0, ISC, PSF
  or public domain.
- Weak copyleft (**LGPL, MPL**) is allowed only for libraries installed unmodified
  as normal dependencies, never copied into this repository.
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
| Phoneme recognition (milestone 4) | wav2vec2-xlsr-53-espeak-cv-ft | Apache-2.0 | https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft |

## Data

| Purpose | Data | License |
|---|---|---|
| Pronunciation dictionary | CMUdict, downloaded through nltk | BSD-2-Clause |

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
| Planned: database | SQLite | Public domain |
| Planned: PDF text and OCR | pypdf, pdfplumber, Tesseract | BSD-3-Clause, MIT, Apache-2.0 |
| Planned: frontend | Flutter / Dart | BSD-3-Clause |

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
| Llama, Gemma models | Custom licenses with usage restrictions, not open source |
| XTTS-v2, F5-TTS weights | Licenses with extra noncommercial terms of their own |
| Any cloud API | Everything must run locally |
