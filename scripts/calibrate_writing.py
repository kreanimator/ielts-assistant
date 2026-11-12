"""Checks the Writing bands against the examiners' bands of the sample answers in your books
(the LLM server must be running, and your books imported with make books).

    make calibrate-writing                  judges the answers not judged before, then reports
    make calibrate-writing ARGS=--rejudge   judges every answer again (after a prompt change)

The books print candidates' answers with the band an examiner gave them. Each answer is judged
as the app judges yours (with a note that the text was scanned, so scan slips are not counted as
the candidate's errors), and the app's task band is compared with the examiner's.

The books give one band per answer, not one per criterion, so one shift is fitted for all four
criteria: the shift that makes the app's bands right on average. Its accuracy is measured by
leaving each answer out in turn: the shift is fitted on the other answers and tested on the one
left out, so no answer is scored by a shift fitted on itself.

Not every imported answer can be used: the import keeps page footers (cut here), and some answers
are cut off at a page break, run into other text, or are garbled by OCR. Those are left out, and
the report says which and why. The LLM's judgements are cached in
data/private/calibration/writing-samples.json (git-ignored, like the books).
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.bands import round_band  # noqa: E402
from app.core.text import readability, word_count  # noqa: E402
from app.writing import assessor, books, tasks  # noqa: E402

CACHE = ROOT / "data" / "private" / "calibration" / "writing-samples.json"
PARALLEL = 3  # the LLM server has 4 slots
# A line of a page footer or watermark, not of the answer.
FOOTER = re.compile(r"www\.|©|photocopiable|UCLES|DP\d+/\d+|[^\x00-\x7f]{2,}|^\W*\d{1,3}(\s+\d{1,3})*\W*$"
                    r"|\d{3}\s*\d{3}\s*\d{3}|band score|marker'?s initials|^\W*(listening\s*)?total\W*$", re.I)
# How a letter ends: the closing and a name.
CLOSING = re.compile(r"yours|regards|sincere|faithful|best wishes|love|take care|cheers|all the best", re.I)
# The examiner's comment run into the answer (one book prints it right after the answer).
COMMENT = re.compile(r"the meaning is (still )?clear|error-free|the candidate|this answer|grammatical|lexical"
                     r"|cohesive|capitalisation|paragraphing", re.I)
MAX_LENGTH = {1: 1.8, 2: 1.6}  # times the minimum: longer is an answer run into other text


def clean(text: str) -> str:
    """The answer without the page footers at its end."""
    lines = text.rstrip().splitlines()
    while lines and (not lines[-1].strip() or FOOTER.search(lines[-1])):
        lines.pop()
    return "\n".join(lines).strip()


def problem(task: int, text: str, minimum: int) -> str | None:
    """Why the answer cannot be used, or None."""
    if COMMENT.search(text):
        return "the examiner's comment is mixed into it"
    if word_count(text) > MAX_LENGTH[task] * minimum:
        return f"{word_count(text)} words: runs into other text"
    if readability(text) < 0.9:
        return "garbled by OCR"
    last = text.splitlines()[-1].strip()
    if task == 1:
        if not CLOSING.search(" ".join(text.splitlines()[-3:])):
            return f"cut off (ends {last[-30:]!r})"
    elif not re.search(r"[.!?)\"']$", last) or last.endswith(".."):
        return f"cut off (ends {last[-30:]!r})"
    return None


def samples() -> tuple[list[dict], list[tuple[str, str]]]:
    """The usable sample answers with their task and band, and the others with the reason."""
    usable, left_out = [], []
    for book in books.load_books():
        for test in book["tests"]:
            for a in test["answers"]:
                if a["kind"] != "sample" or not a["answer"] or not a["band"]:
                    continue
                if a["task"] == 1 and test["type"] != "general":
                    continue  # an Academic chart
                item = test[f"task{a['task']}"]
                if not item:
                    continue
                item = {"bullets": [], "begin": "", **item}
                if a["task"] == 1:
                    item = tasks.tidy_letter(item)
                task = {**(tasks.LETTER if a["task"] == 1 else tasks.ESSAY), **item}
                key = f"{book['id']}/{test['test']}/{a['task']}"
                text = clean(a["answer"])
                reason = problem(a["task"], text, task["words"])
                if reason:
                    left_out.append((key, reason))
                else:
                    usable.append({"key": key, "task": task, "answer": text, "examiner": a["band"]})
    return usable, left_out


async def judge_all(items: list[dict], cache: dict, rejudge: bool):
    todo = [s for s in items if rejudge or s["key"] not in cache]
    limit = asyncio.Semaphore(PARALLEL)

    async def one(s):
        async with limit:
            stats, judged = await assessor.judge(s["task"], s["answer"], scanned=True)
        cache[s["key"]] = {"words": stats["words"], "llm": {k: judged[k]["band"] for k in assessor.CRITERIA}}
        CACHE.write_text(json.dumps(cache, indent=1))
        print(f"  {len(cache)}: {s['key']} examiner {s['examiner']}, LLM "
              f"{', '.join(str(v) for v in cache[s['key']]['llm'].values())}", flush=True)

    if todo:
        print(f"Judging {len(todo)} answers ({PARALLEL} at a time, about 40 s each)...")
        await asyncio.gather(*(one(s) for s in todo))


def band(s: dict, cache: dict, shift: float) -> float:
    entry = cache[s["key"]]
    return assessor.task_band(assessor.corrected(entry["llm"], entry["words"], s["task"]["words"], shift))


def fit(items: list[dict], cache: dict) -> float:
    """The shift (to a tenth of a band) with the smallest average error, unrounded so the fit is smooth."""
    def error(shift):
        diffs = []
        for s in items:
            entry = cache[s["key"]]
            bands = assessor.corrected(entry["llm"], entry["words"], s["task"]["words"], shift)
            diffs.append(sum(bands.values()) / len(bands) - s["examiner"])
        return abs(np.mean(diffs))
    return min((round(x, 1) for x in np.arange(-1.0, 2.51, 0.1)), key=error)


def summary(name: str, examiner: list[float], app: list[float]):
    d = np.array(app) - np.array(examiner)
    print(f"{name:<34} bias {d.mean():+.2f}  MAE {np.abs(d).mean():.2f}  within ½ band {np.mean(np.abs(d) <= 0.5):.0%}"
          f"  within 1 {np.mean(np.abs(d) <= 1):.0%}  correlation {np.corrcoef(examiner, app)[0, 1]:.2f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rejudge", action="store_true", help="judge every answer again")
    args = parser.parse_args()

    items, left_out = samples()
    print(f"{len(items)} sample answers usable, {len(left_out)} left out:")
    for key, reason in left_out:
        print(f"  {key}: {reason}")
    if len(items) < 10:
        sys.exit("Too few sample answers: import your Cambridge books with make books first.")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    asyncio.run(judge_all(items, cache, args.rejudge))

    examiner = [s["examiner"] for s in items]
    print()
    summary("Uncorrected", examiner, [band(s, cache, 0.0) for s in items])
    summary(f"Current shift ({assessor.SHIFT:+.1f})", examiner, [band(s, cache, assessor.SHIFT) for s in items])
    held_out = []
    for i, s in enumerate(items):
        shift = fit(items[:i] + items[i + 1:], cache)
        held_out.append(band(s, cache, shift))
    summary("Shift fitted without each answer", examiner, held_out)
    shift = fit(items, cache)
    print(f"\nBest shift on all {len(items)} answers: {shift:+.1f} (set assessor.SHIFT to it)")
    for task in (1, 2):
        part = [s for s in items if s["task"]["task"] == task]
        if part:
            summary(f"Task {task} ({len(part)}), shift {shift:+.1f}", [s["examiner"] for s in part],
                    [band(s, cache, shift) for s in part])
    print("\nBy the examiners' band (shift fitted without each answer):")
    for level in sorted({round_band(e) for e in examiner}):
        diffs = [a - e for a, e in zip(held_out, examiner) if e == level]
        print(f"  band {level:g}: {len(diffs):2} answers, app {np.mean(diffs):+.2f} on average")


if __name__ == "__main__":
    main()
