VENV = .venv
PYTHON = $(VENV)/bin/python
# The LLM: 9B (6.6 GB, needs about 10 GB of GPU or Mac memory) or 4B (3 GB, for 8 GB Macs;
# the band calibration was done with 9B). Example: make install LLM=4B, then make start LLM=4B
LLM ?= 9B
LLM_FILE ?= Qwen3.5-$(LLM)-Q5_K_M.gguf
LLM_REPO ?= unsloth/Qwen3.5-$(LLM)-GGUF
REPO_URL = https://github.com/kreanimator/ielts-assistant
OS := $(shell uname -s)
ARCH := $(shell uname -m)

# llama.cpp release and build, chosen for this computer:
# - Mac with Apple Silicon: the Metal build.
# - Linux with an NVIDIA driver 570 or newer: the CUDA build (the Vulkan build can leave
#   NVIDIA GPUs at idle clocks with driver 580).
# - Other Linux: the Vulkan build (any recent NVIDIA, AMD or Intel GPU driver). Without a
#   GPU use LLAMA_BUILD=ubuntu-x64.
LLAMA_VERSION ?= b12233
NVIDIA_DRIVER := $(shell nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 | cut -d. -f1)
ifeq ($(OS),Darwin)
  LLAMA_BUILD ?= macos-arm64
  TORCH_INDEX =
else
  LLAMA_BUILD ?= $(if $(shell [ "$(NVIDIA_DRIVER)" -ge 570 ] 2>/dev/null && echo yes),ubuntu-cuda-12.8-x64,ubuntu-vulkan-x64)
  # PyTorch with CUDA when an NVIDIA driver is present, else the smaller CPU-only build.
  TORCH_INDEX = --index-url https://download.pytorch.org/whl/$(if $(NVIDIA_DRIVER),cu124,cpu)
endif
LLAMA_DIR = tools/llama-$(LLAMA_VERSION)-$(LLAMA_BUILD)

.PHONY: install install-esl start setup models app-models llm frontend frontend-dev run books writing-books reading-books esl-topics license-check \
	calibrate-pronunciation calibrate-bands calibrate-writing check-platform

# Everything in one go: Python environment, models, llama.cpp, the web app and the topic
# cards for the "By letter" mode (ESL=0 skips those).
ESL ?= 1
install: check-platform setup models app-models frontend $(if $(filter 1,$(ESL)),install-esl)
	@echo; echo "Installed. Start the app with: make start"

# The topic cards, unless they are already there. A failure does not stop the install.
install-esl:
	@if [ -s data/private/esl/topics.json ]; then echo "Topic cards: already downloaded (make esl-topics updates them)"; \
	else echo "Downloading the topic cards for the By letter mode (about 2.5 minutes) ..."; \
		PYTHONPATH=backend $(PYTHON) -m app.speaking.esl || \
		echo "Warning: could not download the topic cards. Try again later with: make esl-topics"; fi

# Start the LLM server and the backend, and open the app in the browser. Ctrl+C stops both.
start:
	@$(PYTHON) scripts/start.py

check-platform:
	@if [ "$(OS)" = Darwin ] && [ "$(ARCH)" != arm64 ]; then \
		echo "Intel Macs are not supported: PyTorch has no builds for them. A Mac with Apple Silicon (M1 or newer) works."; exit 1; fi
	@if [ "$(OS)" != Darwin ] && [ "$(OS)" != Linux ]; then echo "Linux or macOS is needed (on Windows, use WSL2)."; exit 1; fi

# The Python environment, with Python 3.12 from uv (installed first if missing).
setup:
	@command -v uv >/dev/null || { echo "Installing uv, the Python installer (https://docs.astral.sh/uv/)"; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; }
	PATH="$$HOME/.local/bin:$$PATH" uv venv --allow-existing -p 3.12 $(VENV)
	PATH="$$HOME/.local/bin:$$PATH" uv pip install -p $(PYTHON) torch==2.6.0 $(TORCH_INDEX)
	PATH="$$HOME/.local/bin:$$PATH" uv pip install -p $(PYTHON) -r backend/requirements.txt
	PATH="$$HOME/.local/bin:$$PATH" uv pip install -p $(PYTHON) --no-deps kokoro==0.9.4 misaki==0.9.4 g2p_en==2.1.0

# The LLM and the llama.cpp server.
models: models/$(LLM_FILE) $(LLAMA_DIR)/llama-server

# Whisper, Kokoro and the pronunciation model (about 3.5 GB), so the first start is quick.
app-models:
	$(PYTHON) scripts/fetch_models.py

# Download the LLM weights once (about 6.6 GB).
models/$(LLM_FILE):
	mkdir -p models
	curl -fL -C - -o $@ https://huggingface.co/$(LLM_REPO)/resolve/main/$(LLM_FILE)

# Download the llama.cpp server once.
$(LLAMA_DIR)/llama-server:
	mkdir -p $(LLAMA_DIR)
	curl -fL https://github.com/ggml-org/llama.cpp/releases/download/$(LLAMA_VERSION)/llama-$(LLAMA_VERSION)-bin-$(LLAMA_BUILD).tar.gz \
		| tar xz -C $(LLAMA_DIR) --strip-components=1

# Start the LLM server (keep it running in its own terminal).
llm: models/$(LLM_FILE) $(LLAMA_DIR)/llama-server
	LD_LIBRARY_PATH=$(LLAMA_DIR) $(LLAMA_DIR)/llama-server -m models/$(LLM_FILE) --alias qwen3.5-9b \
		--host 127.0.0.1 --port 8081 -ngl 99 -c 16384 -fa off --reasoning off

# Build the Flutter web app; the backend serves it at http://127.0.0.1:8000. Without
# Flutter, the app built from main is downloaded from the project's releases instead.
# (Flutter's output goes through cat: it can exit with 255 when its output is a file.)
# A failed build is tried once more after `flutter clean`: Flutter's cache can keep old
# names, for example after the app was renamed.
FLUTTER_BUILD = flutter build web --release --no-web-resources-cdn --pwa-strategy=none 2>&1 | cat
frontend:
	@if command -v flutter >/dev/null; then \
		bash -o pipefail -c 'cd frontend && { $(FLUTTER_BUILD) || { echo "Build failed: clearing the Flutter cache and trying again"; \
			flutter clean >/dev/null && $(FLUTTER_BUILD); }; }'; \
	else \
		echo "Flutter not found: downloading the built web app"; \
		rm -rf frontend/build/web && mkdir -p frontend/build/web && \
		curl -fL $(REPO_URL)/releases/download/web-latest/web.tar.gz | tar xz -C frontend/build/web; \
	fi

# Flutter with hot reload at http://127.0.0.1:5000 (the backend must be running too).
frontend-dev:
	cd frontend && flutter run -d web-server --web-hostname 127.0.0.1 --web-port 5000 --no-web-resources-cdn \
		--dart-define=BACKEND=http://127.0.0.1:8000

# Start the backend at http://127.0.0.1:8000 (the developer test page is at /dev).
# A long WebSocket ping timeout: a turn's heavy work (TTS, pronunciation, the slow LLM)
# can stall the event loop past uvicorn's default 20 s, which would otherwise drop the
# session mid-conversation ("Lost the connection"). On localhost there is no network to
# keep alive, so a generous timeout only prevents false drops.
run:
	cd backend && ../$(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
		--ws-ping-interval 30 --ws-ping-timeout 300

# Import the Speaking, Writing and Reading tests from your own IELTS books (the LLM server must be
# running):
#   make books BOOKS='~/Books/*.pdf'      (escape spaces in names: BOOKS='~/My\ Books/*.pdf')
# They are saved in data/private/books/ (git-ignored). Never commit them.
books:
	PYTHONPATH=backend $(PYTHON) -m app.speaking.books $(BOOKS)
	PYTHONPATH=backend $(PYTHON) -m app.writing.books $(BOOKS)
	PYTHONPATH=backend $(PYTHON) -m app.reading.books $(BOOKS)

# Import the Reading tests of books imported before (their pages and answer keys need the PDFs
# once; no LLM needed):  make reading-books BOOKS='~/Books/*.pdf'   (or without BOOKS: from what
# was saved then)
reading-books:
	PYTHONPATH=backend $(PYTHON) -m app.reading.books $(or $(BOOKS),--cached)

# Import the Writing tests from the books imported before, from their saved page texts (no
# PDFs needed; without them, answers printed in handwriting cannot be read with OCR).
writing-books:
	PYTHONPATH=backend $(PYTHON) -m app.writing.books --cached

# Download the topic cards of eslconversationquestions.com for the "By letter" mode (make
# install does this once; this also fetches topics added to the site since). For your own
# practice only: they are saved in data/private/esl/.
esl-topics:
	PYTHONPATH=backend $(PYTHON) -m app.speaking.esl

# Check the Pronunciation band against experts' scores (speechocean762, CC BY 4.0, about 500 MB).
CALIBRATION = data/private/calibration
$(CALIBRATION)/speechocean762/speechocean762/resource/scores.json:
	mkdir -p $(CALIBRATION)/speechocean762
	curl -fL -C - -o $(CALIBRATION)/speechocean762.tar.gz https://www.openslr.org/resources/101/speechocean762.tar.gz
	tar xzf $(CALIBRATION)/speechocean762.tar.gz -C $(CALIBRATION)/speechocean762

calibrate-pronunciation: $(CALIBRATION)/speechocean762/speechocean762/resource/scores.json
	$(PYTHON) scripts/calibrate_pronunciation.py

# Check the other bands against examiners' scores (the LLM server must be running). Needs the
# Speak & Improve Corpus 2025, downloaded after registration (see README) and unzipped into
# data/private/calibration/speak-and-improve/. SET is dev or eval; N tests, spread over all levels.
SET ?= dev
N ?= 60
calibrate-bands:
	$(PYTHON) -u scripts/calibrate_bands.py --set $(SET) --n $(N)

# Check the Writing bands against the examiners' bands of the sample answers in your books
# (needs your books imported with make books, and the LLM server). ARGS=--rejudge judges again.
calibrate-writing:
	$(PYTHON) -u scripts/calibrate_writing.py $(ARGS)

# Fail if a GPL or AGPL package got installed.
license-check:
	$(PYTHON) -I scripts/license_check.py
