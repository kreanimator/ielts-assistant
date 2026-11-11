"""Starts the LLM server and the backend, opens the app in the browser, and stops both on Ctrl+C.

    make start            (make start LLM=4B for the smaller LLM)

Both servers write their output to data/logs/. An LLM server already running on port 8081
is used as it is.
"""
import os
import platform
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parents[1]
LOGS = ROOT / "data" / "logs"
LLM_HEALTH = "http://127.0.0.1:8081/health"
APP = "http://127.0.0.1:8000"
MIN_MEMORY_GB = 10  # the 9B LLM, Whisper, Kokoro and the pronunciation model together


def answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def memory_note():
    """A warning when the GPU (or a Mac's shared memory) looks too small for the 9B LLM."""
    if "LLM=4B" in os.environ.get("MAKEFLAGS", ""):
        return
    try:
        if sys.platform == "darwin":
            gb = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 2**30
            if gb < 16:
                print(f"This Mac has {gb:.0f} GB of memory. If the app is slow, use the smaller LLM:\n"
                      "  make install LLM=4B && make start LLM=4B\n")
        else:
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True).stdout.split()
            if out and int(out[0]) / 1024 < MIN_MEMORY_GB:
                print(f"The GPU has {int(out[0]) / 1024:.1f} GB free; about {MIN_MEMORY_GB} GB is needed. "
                      "Close other GPU programs, or use the smaller LLM: make start LLM=4B\n")
    except (OSError, ValueError):
        pass


def launch(target: str, log: Path) -> subprocess.Popen:
    return subprocess.Popen(["make", "-s", target], cwd=ROOT, stdout=log.open("w"), stderr=subprocess.STDOUT,
                            start_new_session=True)  # its own process group, so stopping it stops its children


def wait_for(url: str, process: subprocess.Popen, log: Path, what: str, minutes: float) -> None:
    deadline = time.time() + minutes * 60
    while not answers(url):
        if process.poll() is not None:
            tail = "\n".join(log.read_text(errors="replace").splitlines()[-15:])
            raise SystemExit(f"\nThe {what} stopped. The end of {log.relative_to(ROOT)}:\n{tail}")
        if time.time() > deadline:
            raise SystemExit(f"\nThe {what} did not start in {minutes:.0f} minutes; see {log.relative_to(ROOT)}.")
        time.sleep(1)


def stop(process: subprocess.Popen | None):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)


def interrupt(*_):
    raise KeyboardInterrupt


def main():
    for sig in (signal.SIGTERM, signal.SIGHUP):  # a closed terminal or kill stops both servers too
        signal.signal(sig, interrupt)
    sys.stdout.reconfigure(line_buffering=True)  # show each line at once, also when written to a file
    if not (ROOT / "frontend" / "build" / "web" / "index.html").exists():
        raise SystemExit("The web app is missing. Run: make install")
    LOGS.mkdir(parents=True, exist_ok=True)
    memory_note()
    llm = backend = None
    try:
        if answers(LLM_HEALTH):
            print("Using the LLM server already running on port 8081.")
        else:
            print("Starting the LLM server (the first time it downloads the model, 3 to 7 GB) ...")
            llm = launch("llm", LOGS / "llm.log")
            wait_for(LLM_HEALTH, llm, LOGS / "llm.log", "LLM server", 60)
        if answers(f"{APP}/api/speaking/topics"):
            raise SystemExit("Something already runs on port 8000. Stop it, or open " + APP)
        print("Starting the backend (loading the speech models takes up to a minute) ...")
        backend = launch("run", LOGS / "backend.log")
        wait_for(f"{APP}/api/speaking/topics", backend, LOGS / "backend.log", "backend", 15)
        print(f"\nReady: {APP}  (Chrome or Edge; allow the microphone). Press Ctrl+C to stop.")
        webbrowser.open(APP)
        while backend.poll() is None and (llm is None or llm.poll() is None):
            time.sleep(1)
        print("A server stopped; see data/logs/.")
    except KeyboardInterrupt:
        print("\nStopping ...")
    finally:
        stop(backend)
        stop(llm)


if __name__ == "__main__":
    if platform.system() not in ("Linux", "Darwin"):
        raise SystemExit("Linux or macOS is needed.")
    main()
