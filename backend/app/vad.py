"""Splits the microphone stream into separate answers with Silero VAD."""
from collections import deque

import numpy as np
import torch
from silero_vad import VADIterator, load_silero_vad

SAMPLE_RATE = 16000
CHUNK = 512  # Silero needs exactly 512 samples per call at 16 kHz (32 ms)
PREROLL_CHUNKS = 10  # keep ~0.3 s before speech starts, so first sounds are not cut


class TurnDetector:
    """Feed raw PCM16 mic audio in; get back events when speech starts and ends."""

    def __init__(self, silence_ms: int):
        self.vad = VADIterator(
            load_silero_vad(),
            sampling_rate=SAMPLE_RATE,
            min_silence_duration_ms=silence_ms,
            speech_pad_ms=200,
        )
        self.pending = np.zeros(0, dtype=np.float32)
        self.preroll = deque(maxlen=PREROLL_CHUNKS)
        self.speech = None  # list of chunks while the user is speaking

    def feed(self, pcm16: bytes) -> list:
        """Returns a list of events: "speech_start", or a float32 array with a whole answer."""
        samples = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768
        self.pending = np.concatenate([self.pending, samples])
        events = []
        while len(self.pending) >= CHUNK:
            chunk, self.pending = self.pending[:CHUNK], self.pending[CHUNK:]
            result = self.vad(torch.from_numpy(chunk)) or {}
            if self.speech is None:
                self.preroll.append(chunk)
                if "start" in result:
                    self.speech = list(self.preroll)
                    events.append("speech_start")
            else:
                self.speech.append(chunk)
                if "end" in result:
                    events.append(np.concatenate(self.speech))
                    self.speech = None
                    self.preroll.clear()
        return events

    def reset(self):
        """Forget any half-heard speech, e.g. after the examiner has spoken."""
        self.vad.reset_states()
        self.pending = np.zeros(0, dtype=np.float32)
        self.preroll.clear()
        self.speech = None
