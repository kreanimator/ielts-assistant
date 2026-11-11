"""The home screen's numbers: an estimated band per skill and overall, and progress.

  GET /api/dashboard

A skill's band is the average of the overall bands of your last RECENT sessions that have
a band estimate (drills and short sessions have none), rounded like IELTS. The overall
band is the average of the skills' bands, rounded the same way, as in the real test; until
every skill has a band it is marked partial ("from 1 of 4 skills").
"""
from fastapi import APIRouter

from . import storage
from .bands import round_band
from .modules import MODULES

RECENT = 5

router = APIRouter()


@router.get("/api/dashboard")
def dashboard():
    return summary(storage.list_sessions())


def summary(sessions: list[dict]) -> dict:
    """sessions: newest first, as storage.list_sessions() returns them."""
    skills = []
    for module in MODULES.values():
        own = [s for s in sessions if s["module"] == module.id]
        scored = [s for s in own if (s["report"] or {}).get("overall") is not None]
        recent = [s["report"]["overall"] for s in scored[:RECENT]]
        skills.append({
            "id": module.id,
            "title": module.title,
            "available": module.available,
            "modes": module.modes,
            "band": round_band(sum(recent) / len(recent)) if recent else None,
            "from_sessions": len(recent),  # how many sessions the band averages
            "latest": recent[0] if recent else None,
            "sessions": len(own),
            "unscored": sum(s["report"] is None for s in own),  # no report written yet
            "last_practised": own[0]["started_at"] if own else None,
            "progress": [{"date": s["started_at"], "band": s["report"]["overall"]} for s in reversed(scored)],
        })
    bands = [s["band"] for s in skills if s["band"] is not None]
    return {
        "overall": {
            "band": round_band(sum(bands) / len(bands)) if bands else None,
            "skills": len(bands),
            "of": len(skills),
        },
        "recent": RECENT,
        "skills": skills,
    }
