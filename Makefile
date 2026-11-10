VENV = .venv
LLM_FILE ?= Qwen3.5-9B-Q5_K_M.gguf
LLM_REPO ?= unsloth/Qwen3.5-9B-GGUF
# llama.cpp release and build. With an NVIDIA driver 570 or newer the CUDA build is used:
# it is faster, and the Vulkan build can leave NVIDIA GPUs at idle clocks (driver 580).
# Otherwise Vulkan, which runs on any recent NVIDIA, AMD or Intel GPU driver.
LLAMA_VERSION ?= b12233
NVIDIA_DRIVER := $(shell nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 | cut -d. -f1)
LLAMA_BUILD ?= $(if $(shell [ "$(NVIDIA_DRIVER)" -ge 570 ] 2>/dev/null && echo yes),ubuntu-cuda-12.8-x64,ubuntu-vulkan-x64)
LLAMA_DIR = tools/llama-$(LLAMA_VERSION)-$(LLAMA_BUILD)

.PHONY: setup llm frontend frontend-dev run books license-check calibrate-pronunciation calibrate-bands

# Create the Python environment.
setup:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
	$(VENV)/bin/pip install -r backend/requirements.txt
	$(VENV)/bin/pip install --no-deps kokoro==0.9.4 misaki==0.9.4 g2p_en==2.1.0

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

# Build the Flutter web app; the backend serves it at http://127.0.0.1:8000
frontend:
	cd frontend && flutter build web --release --no-web-resources-cdn --pwa-strategy=none

# Flutter with hot reload at http://127.0.0.1:5000 (the backend must be running too).
frontend-dev:
	cd frontend && flutter run -d web-server --web-hostname 127.0.0.1 --web-port 5000 --no-web-resources-cdn \
		--dart-define=BACKEND=http://127.0.0.1:8000

# Start the backend at http://127.0.0.1:8000 (the developer test page is at /dev).
run:
	cd backend && ../$(VENV)/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Import the Speaking tests from your own IELTS books (the LLM server must be running):
#   make books BOOKS='~/Books/*.pdf'      (escape spaces in names: BOOKS='~/My\ Books/*.pdf')
# They are saved in data/private/books/ (git-ignored). Never commit them.
books:
	PYTHONPATH=backend $(VENV)/bin/python -m app.books $(BOOKS)

# Check the Pronunciation band against experts' scores (speechocean762, CC BY 4.0, about 500 MB).
CALIBRATION = data/private/calibration
$(CALIBRATION)/speechocean762/speechocean762/resource/scores.json:
	mkdir -p $(CALIBRATION)/speechocean762
	curl -fL -C - -o $(CALIBRATION)/speechocean762.tar.gz https://www.openslr.org/resources/101/speechocean762.tar.gz
	tar xzf $(CALIBRATION)/speechocean762.tar.gz -C $(CALIBRATION)/speechocean762

calibrate-pronunciation: $(CALIBRATION)/speechocean762/speechocean762/resource/scores.json
	$(VENV)/bin/python scripts/calibrate_pronunciation.py

# Check the other bands against examiners' scores (the LLM server must be running). Needs the
# Speak & Improve Corpus 2025, downloaded after registration (see README) and unzipped into
# data/private/calibration/speak-and-improve/. SET is dev or eval; N tests, spread over all levels.
SET ?= dev
N ?= 60
calibrate-bands:
	$(VENV)/bin/python -u scripts/calibrate_bands.py --set $(SET) --n $(N)

# Fail if a GPL or AGPL package got installed.
license-check:
	$(VENV)/bin/python -I scripts/license_check.py
