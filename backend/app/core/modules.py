"""The IELTS skills, one module each. A module that works registers itself (see
speaking/router.py): its training modes, for titles in the history and the dashboard,
and how to write a session's band report."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class Module:
    id: str
    title: str
    available: bool = False  # False: shown on the dashboard as "coming soon"
    modes: dict[str, str] = field(default_factory=dict)  # mode id → title
    report: Callable[[dict], Awaitable[dict]] | None = None  # session → band report


MODULES = {m.id: m for m in (Module("listening", "Listening"), Module("reading", "Reading"),
                             Module("writing", "Writing"), Module("speaking", "Speaking"))}


def register(module_id: str, modes: dict[str, str], report: Callable[[dict], Awaitable[dict]]) -> None:
    module = MODULES[module_id]
    module.available, module.modes, module.report = True, modes, report
