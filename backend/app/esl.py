"""Topic cards from eslconversationquestions.com, for the "By letter" mode.

    make esl-topics

downloads the site's A-Z topics and their questions once, for your own practice, into
data/private/esl/ (git-ignored). The site's terms allow copying its free questions for
your own lessons, with a link to the source page, but not publishing a collection of
them: so they are never part of this repository, and the card links to the source.
The download is polite: one page a second, and pages already saved are not fetched again.
"""
import html
import json
import logging
import random
import re
import sys
import time

import httpx

from . import config

SITE = "https://www.eslconversationquestions.com"
INDEX = f"{SITE}/english-conversation-questions/topics/"
AGENT = "Mozilla/5.0 (X11; Linux x86_64) ielts-speaking-assistant (personal practice)"
LEVELS = ["A1-A2", "A2", "B1", "B2", "C1"]  # the site's sections, easiest first
LEVEL_NAMES = {"A1-A2": "Beginner", "A2": "Elementary", "B1": "Intermediate", "B2": "Upper-intermediate",
               "C1": "Advanced"}
SITE_PAGES = {"ecq-publishing", "english-conversation-questions", "about-contact", "privacy-policy",
              "terms-and-conditions"}  # links in the index that are not topics
QUESTIONS = 8  # asked in one session
# "mixed" rises from easy to hard, like an exam: 2 elementary, 3 intermediate, 2 upper, 1 advanced.
MIXED = [("A2", 2), ("B1", 3), ("B2", 2), ("C1", 1)]

log = logging.getLogger("esl")


def folder():
    return config.DATA_DIR / "private" / "esl"


def text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_index(page: str) -> list[dict]:
    """The topic links of the A-Z index: [{"name", "slug"}]."""
    main = page[page.find("<h1"):]  # after the site menu
    main = main[:main.find("<footer")] if "<footer" in main else main
    topics, seen = [], set()
    for slug, name in re.findall(r'<a[^>]*href="/([a-z0-9-]+)/"[^>]*>([^<]{1,60})</a>', main):
        if slug not in seen and slug not in SITE_PAGES:
            seen.add(slug)
            topics.append({"name": text(name), "slug": slug})
    return topics


def parse_topic(page: str) -> dict[str, list[str]]:
    """The questions of a topic page by level: {"B1": ["...?", ...]}."""
    levels = {}
    sections = re.split(r'<h2 data-feed-content>', page)[1:]
    for section in sections:
        heading = re.match(r"(.*?)</h2>", section, re.S)
        level = re.search(r"\(([ABC][12](?:-[ABC][12])?)\)", heading.group(1)) if heading else None
        name = {"A1": "A1-A2"}.get(level.group(1), level.group(1)) if level else None  # pages differ
        if name not in LEVELS:
            continue
        questions = [text(li) for li in re.findall(r"<li[^>]*>(.*?)</li>", section, re.S)]
        levels[name] = [q for q in questions if q.endswith("?") and 3 < len(q) < 300]
    return levels


def download():
    """Saves every topic with its questions in data/private/esl/topics.json."""
    folder().mkdir(parents=True, exist_ok=True)
    saved = folder() / "topics.json"
    have = {t["slug"]: t for t in load_topics()}
    with httpx.Client(headers={"User-Agent": AGENT}, timeout=30, follow_redirects=True) as client:
        index = parse_index(client.get(INDEX).raise_for_status().text)
        log.info("%d topics on %s", len(index), INDEX)
        topics = []
        for i, topic in enumerate(index, 1):
            if topic["slug"] in have:
                topics.append(have[topic["slug"]])
                continue
            time.sleep(1)  # one page a second
            url = f"{SITE}/{topic['slug']}/"
            try:
                levels = parse_topic(client.get(url).raise_for_status().text)
            except httpx.HTTPError as e:
                log.warning("%s: %s (run it again later to fetch the missing ones)", url, e)
                continue
            if sum(map(len, levels.values())) < QUESTIONS:
                log.warning("%s: too few questions, skipped", url)
                continue
            topics.append({**topic, "url": url, "levels": levels})
            log.info("[%d/%d] %s: %d questions", i, len(index), topic["name"], sum(map(len, levels.values())))
            saved.write_text(json.dumps(topics, indent=1))  # so an interrupted download keeps its pages
    saved.write_text(json.dumps(topics, indent=1))
    log.info("Saved %d topics in %s", len(topics), saved)


def load_topics() -> list[dict]:
    try:
        return json.loads((folder() / "topics.json").read_text())
    except (OSError, ValueError):
        return []


def letter(name: str) -> str:
    """The letter the site files a topic under: "The Unexplained" is under U."""
    return re.sub(r"^the\s+", "", name, flags=re.I)[:1].upper()


def catalogue() -> list[dict]:
    """The topics for the letter picker, without their questions."""
    return [
        {"slug": t["slug"], "name": t["name"], "url": t["url"], "letter": letter(t["name"]),
         "questions": sum(len(q) for q in t["levels"].values())}
        for t in load_topics()
    ]


def card(slug: str, level: str = "mixed") -> dict | None:
    """A topic with QUESTIONS of its questions, in the site's order within each level."""
    topic = next((t for t in load_topics() if t["slug"] == slug), None)
    if not topic:
        return None
    levels = topic["levels"]
    plan = MIXED if level not in levels else [(level, QUESTIONS)]
    chosen = []
    for name, count in plan:
        pool = [q for q in levels.get(name, []) if q not in chosen]
        chosen += [pool[i] for i in sorted(random.sample(range(len(pool)), min(count, len(pool))))]
    # A level with too few questions is topped up from the neighbouring ones.
    rest = [q for name in LEVELS for q in levels.get(name, []) if q not in chosen]
    chosen += random.sample(rest, min(QUESTIONS - len(chosen), len(rest))) if len(chosen) < QUESTIONS else []
    return {"name": topic["name"], "url": topic["url"], "questions": chosen}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    download()
    sys.exit(0 if load_topics() else 1)
