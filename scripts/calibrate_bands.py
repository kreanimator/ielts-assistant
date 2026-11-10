"""Checks the band report against human examiners' scores (the LLM server must be running).

    make calibrate-bands SET=dev N=60        (or: SET=eval for the held-out check)

Uses the Speak & Improve Corpus 2025 from Cambridge University Press & Assessment, which
you download yourself after accepting its licence (it may not be redistributed), into
data/private/calibration/speak-and-improve/. Only its transcripts and scores are used.

Each test is rebuilt as an app session: the questions, the human transcripts (hesitations
become "um", restarts are kept) and word timings spread over the human phrase timings,
hesitations as "um". Silent pauses are not marked in the corpus, so pauses are left out
(the report then judges fluency without them). The app's own analyst and report then score it,
exactly as after a real session, and the result is compared with the human score.

Human scores are on a 0-6 scale aligned with CEFR (3 = B1, 4 = B2, 5 = C1). They become
IELTS bands with the official IELTS-CEFR alignment (B1 = 4-5, B2 = 5.5-6.5, C1 = 7-8),
taking each level's middle: band = 1.5 x score. That alignment is only approximate, so
treat any difference under half a band as noise.
"""
import argparse
import asyncio
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import fluency, report  # noqa: E402
from app.analyst import analyse  # noqa: E402
from app.stt import Word  # noqa: E402

CORPUS = ROOT / "data" / "private" / "calibration" / "speak-and-improve" / "sandi-corpus-2025" / "reference-materials"
OUT = ROOT / "data" / "private" / "calibration"
HESITATION_S = 0.4  # an "um"
CRITERIA = ["fluency_coherence", "lexical_resource", "grammar"]


def human_band(score: float) -> float:
    return min(9.0, max(1.0, 1.5 * score))


def timings(path: Path) -> dict[str, tuple[float, float]]:
    """Start and end of each response, from the human phrase timings."""
    spans = {}
    for line in path.read_text().splitlines():
        if line.startswith(";;"):
            continue
        parts = line.split()
        file_id, start, end = parts[0], float(parts[3]), float(parts[4])
        s, e = spans.get(file_id, (start, end))
        spans[file_id] = (min(s, start), max(e, end))
    return spans


def answer(tokens: list[dict], span: tuple[float, float]) -> tuple[str, list[Word]]:
    """The transcript as Whisper would write it, and word timings spread over the response."""
    words = []
    for t in tokens:
        if t.get("tag") == "hesitation":
            words.append("um")
        elif t.get("tag", "").startswith("speech-unit") and words:
            words[-1] += "?" if t["tag"].endswith("question") else "."
        elif "word" in t:
            w = t["word"].lower()
            w = "I" if w == "i" else w.replace("i'", "I'") if w.startswith("i'") else w
            words.append(w + "-" if "partial" in t.get("marks", []) else w)
    if not words:
        return "", []
    pauses = sum(w.startswith("um") for w in words) * HESITATION_S
    start, end = span
    step = max(0.15, (end - start - pauses) / max(1, sum(not w.startswith("um") for w in words)))
    timed, now = [], start
    for w in words:
        if w.startswith("um"):
            timed.append(Word(w, now, now + HESITATION_S))
            now += HESITATION_S
        else:
            timed.append(Word(w, now, now + step * 0.85))
            now += step
    text = " ".join(words)
    return text[:1].upper() + text[1:], timed


def load(dataset: str) -> dict[str, list[dict]]:
    """Each test (speaker) with its responses in order."""
    files = json.loads((CORPUS / "annotations" / f"{dataset}-trans-ref.json").read_text())["files"]
    spans = timings(CORPUS / "stms" / f"{dataset}-asr.stm")
    tests = defaultdict(list)
    for f in sorted(files, key=lambda f: f["File-id"]):
        if f["File-id"] not in spans:
            continue
        question = " ".join(json.loads(f["Question"])["text"].replace("\\n", " ").split())
        text, words = answer(f["Transcript"], spans[f["File-id"]])
        if text:
            tests[f["File-id"].rsplit("-", 1)[0]].append({"question": question, "text": text, "words": words})
    return tests


async def session(test: list[dict]) -> list[dict]:
    """The test as app session messages, checked by the app's analyst like a real session."""
    messages = []
    for i, a in enumerate(test):
        feedback = await analyse(a["question"], a["text"])
        measured = fluency.measure(a["words"])
        for unknown in ("pauses", "longest_pause"):  # silences are not in the corpus
            measured.pop(unknown, None)
        delivery = {"fluency": measured, "pronunciation": {"score": None, "words": [], "sounds": []}}
        messages.append({"role": "examiner", "text": a["question"], "answer": None, "delivery": None, "feedback": None})
        messages.append({"role": "candidate", "text": a["text"], "answer": i, "delivery": delivery, "feedback": feedback})
    return messages


def pick(marks: dict[str, float], n: int, seed: int) -> list[str]:
    """n tests spread evenly over the score range, so every level is checked."""
    ordered = sorted(marks, key=lambda k: marks[k])
    if n >= len(ordered):
        return ordered
    rng = random.Random(seed)
    bins = [ordered[i * len(ordered) // n:(i + 1) * len(ordered) // n] for i in range(n)]
    return [rng.choice(b) for b in bins]


async def main(dataset: str, n: int, parallel: int, seed: int, rejudge: bool, tag: str):
    marks = {}
    for line in (CORPUS / "sla-marks" / f"{dataset}-sla-overall.tsv").read_text().splitlines():
        test_id, value = line.split("\t")
        marks[test_id] = float(value)
    tests = load(dataset)
    chosen = [t for t in pick({k: v for k, v in marks.items() if k in tests}, n, seed)]
    out = OUT / f"bands-{dataset}-{len(chosen)}{tag}.json"
    results = json.loads(out.read_text()) if out.exists() and not rejudge else {}  # resume after a stop
    # The analysed sessions are kept, so a changed report prompt can be checked quickly (--rejudge).
    cache = OUT / f"sessions-{dataset}.json"
    sessions = json.loads(cache.read_text()) if cache.exists() else {}
    gate = asyncio.Semaphore(parallel)

    async def one(test_id: str):
        if test_id in results:
            return
        async with gate:
            try:
                if test_id not in sessions:
                    sessions[test_id] = await session(tests[test_id])
                    cache.write_text(json.dumps(sessions))
                r = await report.build({"messages": sessions[test_id]})
            except Exception as e:
                print(f"{test_id}: failed ({type(e).__name__}: {e})", flush=True)
                return
        if not r.get("enough"):
            return
        results[test_id] = {
            "human": human_band(marks[test_id]),
            "human_score": marks[test_id],
            "bands": {c["id"]: c["band"] for c in r["criteria"]},
            "llm_bands": {c["id"]: c.get("llm_band", c["band"]) for c in r["criteria"]},
            "overall": r["overall"],
            "stats": r["stats"],
        }
        out.write_text(json.dumps(results, indent=1))
        print(f"{len(results):3d}/{len(chosen)}  {test_id}  human {results[test_id]['human']:.2f}  app {r['overall']}", flush=True)

    await asyncio.gather(*(one(t) for t in chosen))
    summary(results)


def summary(results: dict):
    rows = list(results.values())
    if not rows:
        return
    print(f"\n{len(rows)} tests. Difference = app - human (IELTS bands). Positive means the app is too generous.")
    for key in [*CRITERIA, "overall"]:
        app = [r["bands"][key] if key in CRITERIA else r["overall"] for r in rows]
        diff = [a - r["human"] for a, r in zip(app, rows)]
        mean = sum(diff) / len(diff)
        mae = sum(abs(d) for d in diff) / len(diff)
        hum = [r["human"] for r in rows]
        mh, ma = sum(hum) / len(hum), sum(app) / len(app)
        cov = sum((h - mh) * (a - ma) for h, a in zip(hum, app))
        sd = (sum((h - mh) ** 2 for h in hum) * sum((a - ma) ** 2 for a in app)) ** 0.5
        print(f"  {key:18s} mean difference {mean:+.2f}   mean absolute {mae:.2f}   correlation {cov / sd if sd else 0:.2f}")
    print("\n  By level (human band): app overall average")
    groups = defaultdict(list)
    for r in rows:
        groups[round(r["human"])].append(r["overall"])
    for level in sorted(groups):
        g = groups[level]
        print(f"    about {level}: {sum(g) / len(g):.2f}  ({len(g)} tests)")


def fit(results: dict):
    """Per criterion, the offset that removes the LLM's average difference from the human
    examiners. The slope stays 1: a fitted slope either shrinks the spread (least squares)
    or stretches it beyond the levels the tests cover, inflating strong speakers."""
    rows = list(results.values())
    human = sum(r["human"] for r in rows) / len(rows)
    print(f"Fitted on {len(rows)} tests (paste into report.CORRECTION):")
    out = {}
    for key in CRITERIA:
        llm = sum(r.get("llm_bands", r["bands"])[key] for r in rows) / len(rows)
        out[key] = (1.0, round(human - llm, 1))
    print(f"CORRECTION = {out}")


def reapply(results: dict) -> dict:
    """The saved results with the current report.CORRECTION applied to the LLM's bands."""
    out = {}
    for test_id, r in results.items():
        bands = {}
        for key in CRITERIA:
            slope, offset = report.CORRECTION[key]
            bands[key] = report.round_band(min(9.0, max(1.0, slope * r.get("llm_bands", r["bands"])[key] + offset)))
        if "pronunciation" in r["bands"]:
            bands["pronunciation"] = r["bands"]["pronunciation"]
        overall = report.round_band(sum(bands.values()) / len(bands))
        out[test_id] = {**r, "bands": bands, "overall": overall}
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--set", default="dev", choices=["dev", "eval", "train"])
    parser.add_argument("--n", type=int, default=60)
    parser.add_argument("--parallel", type=int, default=3)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--rejudge", action="store_true",
                        help="score again from the saved analysed sessions (after a report prompt change)")
    parser.add_argument("--tag", default="", help="saved as bands-SET-N-TAG.json, to compare variants")
    parser.add_argument("--passes", type=int, help="override report.PASSES")
    parser.add_argument("--temperature", type=float, help="override report.PASS_TEMPERATURE")
    parser.add_argument("--summary", action="store_true", help="only print the summary of saved results")
    parser.add_argument("--fit", action="store_true",
                        help="fit report.CORRECTION on saved results (use the dev set, then check on eval)")
    parser.add_argument("--apply", action="store_true",
                        help="with --summary: show what the current report.CORRECTION gives on saved results")
    args = parser.parse_args()
    if args.fit:
        for p in sorted(OUT.glob(f"bands-{args.set}-*.json")):
            fit(json.loads(p.read_text()))
    elif args.summary and args.apply:
        for p in sorted(OUT.glob(f"bands-{args.set}-*.json")):
            print(p.name)
            summary(reapply(json.loads(p.read_text())))
    elif args.summary:
        for p in sorted(OUT.glob(f"bands-{args.set}-*.json")):
            print(p.name)
            summary(json.loads(p.read_text()))
    else:
        if args.passes:
            report.PASSES = args.passes
        if args.temperature is not None:
            report.PASS_TEMPERATURE = args.temperature
        asyncio.run(main(args.set, args.n, args.parallel, args.seed, args.rejudge, f"-{args.tag}" if args.tag else ""))
