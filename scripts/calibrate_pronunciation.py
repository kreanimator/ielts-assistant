"""Calibrates the Pronunciation band against human experts' scores.

    make calibrate-pronunciation

Uses speechocean762 (https://www.openslr.org/101, CC BY 4.0, by Junbo Zhang et al., 2021):
5,000 English sentences read by 250 learners, each scored by five experts. Download it
into data/private/calibration/speechocean762/ (make calibrate-pronunciation does this).

Only adult speakers are used (IELTS candidates are adults; children's voices also confuse
the phoneme model). For each sentence the app's pronunciation score is compared with the
experts' sentence accuracy (0-10). The train split gives the app score that matches each
expert level; the held-out test split checks how well that mapping predicts the experts.

Expert accuracy becomes an IELTS Pronunciation band by matching the two rubrics:
  experts 9-10 "excellent, no obvious mistakes"            -> band 8-9
  experts 7-8  "good, a few mistakes"                       -> band 6-7
  experts 5-6  "understandable, many mistakes and accent"   -> band 5
  experts 3-4  "poor, serious mistakes"                     -> band 3-4
The printed POINTS go into report.pronunciation_band().
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "backend"))

DATA = ROOT / "data" / "private" / "calibration" / "speechocean762" / "speechocean762"
CACHE = ROOT / "data" / "private" / "calibration" / "pronunciation-scores.json"
# Expert sentence accuracy -> IELTS band (the rubric match in the docstring).
EXPERT_TO_BAND = [(2.0, 2.0), (3.5, 3.5), (5.5, 5.0), (7.5, 6.5), (9.5, 8.5), (10.0, 9.0)]
MIN_ADULT_AGE = 16


def expert_band(accuracy: float) -> float:
    return float(np.interp(accuracy, *zip(*EXPERT_TO_BAND)))


def adults(split: str) -> list[str]:
    ages = dict(line.split() for line in (DATA / split / "spk2age").read_text().splitlines())
    speakers = {s for s, a in ages.items() if int(a) >= MIN_ADULT_AGE}
    utt2spk = dict(line.split() for line in (DATA / split / "utt2spk").read_text().splitlines())
    return [u for u, s in utt2spk.items() if s in speakers]


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def app_scores(utterances: list[str]) -> dict[str, float]:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [u for u in utterances if u not in cache]
    if todo:
        from app import config
        from app.pronunciation import PronunciationScorer

        scorer = PronunciationScorer(config.DEVICE)
        texts = {}
        for split in ("train", "test"):
            texts.update(line.split("\t", 1) for line in (DATA / split / "text").read_text().splitlines())
        paths = {}
        for split in ("train", "test"):
            paths.update(line.split("\t", 1) for line in (DATA / split / "wav.scp").read_text().splitlines())
        for i, u in enumerate(todo):
            result = scorer.score(read_wav(DATA / paths[u]), texts[u])
            cache[u] = result["score"]
            if i % 200 == 199:
                print(f"  scored {i + 1}/{len(todo)}", flush=True)
                CACHE.write_text(json.dumps(cache))
        CACHE.write_text(json.dumps(cache))
    return {u: cache[u] for u in utterances if cache.get(u) is not None}


def main():
    experts = {u: v["accuracy"] for u, v in json.loads((DATA / "resource" / "scores.json").read_text()).items()}
    train, test = adults("train"), adults("test")
    scores = app_scores(train + test)
    train = [u for u in train if u in scores]
    test = [u for u in test if u in scores]
    print(f"Adult sentences scored: {len(train)} train, {len(test)} test")

    # The app score that matches each expert level: the median app score at that level,
    # made increasing, so a better app score never means a lower band.
    levels = sorted({experts[u] for u in train})
    print("\nExpert accuracy -> app score (train): median, middle 50%, sentences")
    medians = []
    for level in levels:
        s = np.array([scores[u] for u in train if experts[u] == level])
        if len(s) < 20:
            continue
        medians.append((float(np.median(s)), level))
        print(f"  {level:2d}: {np.median(s):.3f}  ({np.percentile(s, 25):.3f}-{np.percentile(s, 75):.3f})  {len(s)}")
    xs = np.maximum.accumulate([m for m, _ in medians])
    ys = [lv for _, lv in medians]

    def predict(score: float) -> float:
        return float(np.interp(score, xs, ys))

    # Held-out check, per sentence (a session averages many sentences, so it is less noisy).
    pred = np.array([predict(scores[u]) for u in test])
    truth = np.array([experts[u] for u in test])
    print(f"\nTest split, expert scale 0-10: mean difference {np.mean(pred - truth):+.2f}, "
          f"mean absolute {np.mean(np.abs(pred - truth)):.2f}, correlation {np.corrcoef(pred, truth)[0, 1]:.2f}")
    band_pred = np.array([expert_band(p) for p in pred])
    band_true = np.array([expert_band(t) for t in truth])
    print(f"Test split, IELTS bands:      mean difference {np.mean(band_pred - band_true):+.2f}, "
          f"mean absolute {np.mean(np.abs(band_pred - band_true)):.2f}")

    # Per speaker, like a session: the average of their sentences.
    speakers = {}
    utt2spk = dict(line.split() for line in (DATA / "test" / "utt2spk").read_text().splitlines())
    for u in test:
        speakers.setdefault(utt2spk[u], []).append(u)
    sp_pred = np.array([expert_band(predict(np.mean([scores[u] for u in us]))) for us in speakers.values()])
    sp_true = np.array([expert_band(np.mean([experts[u] for u in us])) for us in speakers.values()])
    print(f"Test split, per speaker ({len(speakers)}): mean difference {np.mean(sp_pred - sp_true):+.2f}, "
          f"mean absolute {np.mean(np.abs(sp_pred - sp_true)):.2f}, correlation {np.corrcoef(sp_pred, sp_true)[0, 1]:.2f}")

    # The app's mapping, old and new, per test speaker.
    from app import report
    for name, band in [("app mapping (report.py)", report.pronunciation_band)]:
        got = np.array([band(float(np.mean([scores[u] for u in us]))) for us in speakers.values()])
        print(f"{name}, per speaker: mean difference {np.mean(got - sp_true):+.2f}, "
              f"mean absolute {np.mean(np.abs(got - sp_true)):.2f}")

    print("\nPoints to use (app score -> band), from the medians above:")
    print([(round(float(x), 3), round(expert_band(y), 3)) for x, y in zip(xs, ys)])


if __name__ == "__main__":
    main()
