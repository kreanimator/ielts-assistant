"""Pitch and loudness over time, for word stress and intonation.

Pitch is found with a small version of the YIN method (de Cheveigné and Kawahara, 2002):
for each 10 ms step, the delay at which the sound best repeats itself is its period.
"""
import numpy as np

SAMPLE_RATE = 16000
HOP = 160  # 10 ms
WINDOW = 640  # 40 ms
LOW_HZ, HIGH_HZ = 70, 400  # the range of speaking voices
THRESHOLD = 0.2  # how well a period must repeat to count as voiced
# A pitch range below this sounds flat. About 1 in 10 learners reading aloud in speechocean762
# stay below it; lively conversation usually moves over 5 semitones or more.
FLAT_SEMITONES = 3.0


def frames(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if len(audio) < WINDOW:
        audio = np.pad(audio, (0, WINDOW - len(audio)))
    count = 1 + (len(audio) - WINDOW) // HOP
    index = np.arange(WINDOW)[None, :] + HOP * np.arange(count)[:, None]
    return audio[index]


def loudness(audio: np.ndarray) -> np.ndarray:
    """Loudness per 10 ms step, in dB."""
    return 10 * np.log10(np.mean(frames(audio) ** 2, axis=1) + 1e-10)


def pitch(audio: np.ndarray) -> np.ndarray:
    """Pitch per 10 ms step in Hz, 0 where the sound is unvoiced or silent."""
    x = frames(audio)
    x = x - x.mean(axis=1, keepdims=True)
    longest = SAMPLE_RATE // LOW_HZ
    shortest = SAMPLE_RATE // HIGH_HZ
    width = WINDOW - longest
    # Difference between the frame and itself delayed by tau, for every tau at once.
    size = 1 << int(np.ceil(np.log2(WINDOW + width)))
    spectrum = np.fft.rfft(x, size) * np.conj(np.fft.rfft(x[:, :width], size))
    correlation = np.fft.irfft(spectrum, size)[:, :longest + 1]
    squares = np.concatenate([np.zeros((len(x), 1)), np.cumsum(x ** 2, axis=1)], axis=1)
    taus = np.arange(longest + 1)
    energy_at = squares[:, taus + width] - squares[:, taus]
    difference = squares[:, [width]] + energy_at - 2 * correlation
    # Normalised by its running mean, so the best period is the first deep dip.
    running = np.cumsum(difference[:, 1:], axis=1) / np.arange(1, longest + 1)
    normal = np.ones_like(difference)
    normal[:, 1:] = difference[:, 1:] / np.maximum(running, 1e-10)
    normal[:, :shortest] = np.inf
    below = normal < THRESHOLD
    first = np.where(below.any(axis=1), below.argmax(axis=1), normal.argmin(axis=1))
    # Walk down to the bottom of that dip.
    rows = np.arange(len(x))
    for _ in range(24):
        step = first + 1 <= longest
        nxt = np.where(step, first + 1, first)
        better = normal[rows, nxt] < normal[rows, first]
        first = np.where(better, nxt, first)
    voiced = (normal[rows, first] < THRESHOLD * 1.5) & (loudness(audio) > loudness(audio).max() - 35)
    # Between whole samples: the bottom of a parabola through the dip and its neighbours.
    left = normal[rows, np.clip(first - 1, 0, longest)]
    right = normal[rows, np.clip(first + 1, 0, longest)]
    middle = normal[rows, first]
    with np.errstate(invalid="ignore", divide="ignore"):
        shift = 0.5 * (left - right) / (left - 2 * middle + right)
    period = first + np.where(np.isfinite(shift) & (np.abs(shift) < 1), shift, 0.0)
    return np.where(voiced, SAMPLE_RATE / np.maximum(period, 1), 0.0)


def semitones(hz: np.ndarray) -> np.ndarray:
    """Voiced pitches in semitones relative to the speaker's median, so voices compare fairly."""
    voiced = hz[hz > 0]
    if len(voiced) == 0:
        return voiced
    return 12 * np.log2(voiced / np.median(voiced))


def intonation(audio: np.ndarray) -> dict | None:
    """The pitch range of an answer, and whether it sounds flat."""
    spread = pitch_range(audio)
    return None if spread is None else {"range": round(spread, 1), "flat": spread < FLAT_SEMITONES}


def pitch_range(audio: np.ndarray) -> float | None:
    """How much the voice rises and falls: the spread of pitch (semitones) between the 10th
    and 90th percentile. Flat, monotone speech has a small range."""
    tones = semitones(pitch(audio))
    if len(tones) < 50:  # under half a second of voice
        return None
    return float(np.percentile(tones, 90) - np.percentile(tones, 10))
