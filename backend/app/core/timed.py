"""The clock of a timed test (the full Writing test, the Reading test), kept on the server.

A test's deadline is stored in its session's details. The app saves the answers every few
seconds; the server accepts them until the deadline, plus GRACE_SECONDS for a save already on
its way, so a slow or paused browser cannot add time. A test whose time ran out is finished with
what was saved, the next time it is opened or its report is asked for.
"""
from datetime import datetime, timedelta, timezone

GRACE_SECONDS = 10


class TimeUp(Exception):
    """The answer came after the deadline."""


def now() -> datetime:
    return datetime.now(timezone.utc)


def deadline(minutes: int) -> str:
    return (now() + timedelta(minutes=minutes)).isoformat()


def seconds_left(details: dict) -> float:
    return (datetime.fromisoformat(details["deadline"]) - now()).total_seconds()


def in_time(details: dict) -> bool:
    """Answers are still accepted (the grace period included)."""
    return not details["finished"] and seconds_left(details) >= -GRACE_SECONDS


def expired(details: dict) -> bool:
    """The time and the grace period are over, and the test is not finished yet."""
    return not details["finished"] and seconds_left(details) < -GRACE_SECONDS


def seconds_taken(details: dict) -> int:
    total = details["minutes"] * 60
    return round(min(total, total - max(0.0, seconds_left(details))))
