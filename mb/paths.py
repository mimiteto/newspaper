"""Path and date conventions for the Morning Brief repository layout.

The canonical on-disk layout is NESTED: ``2026/11/22/stocks/01-aapl.json``.
Callers habitually pass the flat ``2026-11-22`` form (it is what the chat
reply and the commit messages use), so :func:`day_path` normalises flat ->
nested and refuses anything else. Every other module takes the nested form.

A past incident: a lane fed the flat form straight into a ``mkdir -p`` and
published a stray top-level ``2026-11-22/`` tree nothing linked to, which
verify then reported as MISSING. Normalising here instead of in five shell
scripts keeps that impossible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Section directory names, in publication order.
SECTIONS: tuple[str, ...] = ("weather", "stocks", "bulgarian-finances")

#: Default timezone for every timestamp in a brief.
TZ = "Europe/Sofia"

_FLAT = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_NESTED = re.compile(r"^(\d{4})/(\d{2})/(\d{2})$")
# A day directory is only a brief day when it looks like 2026/11/22.
DAY_DIR_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")


class DateError(ValueError):
    """Raised for anything that is not a usable brief date."""


def parse_date(value: str) -> str:
    """Return ``YYYY-MM-DD`` for a flat or nested date string.

    Raises:
        DateError: ``value`` is neither ``YYYY-MM-DD`` nor ``YYYY/MM/DD``.
    """
    text = (value or "").strip()
    match = _FLAT.match(text) or _NESTED.match(text)
    if not match:
        raise DateError(f"bad date {value!r} — expected YYYY-MM-DD or YYYY/MM/DD")
    year, month, day = (int(part) for part in match.groups())
    # Reject 2026-13-45 style input here rather than deep in a datetime call.
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise DateError(f"bad date {value!r} — month/day out of range")
    return f"{year:04d}-{month:02d}-{day:02d}"


@dataclass(frozen=True)
class DayPath:
    """A brief day: both spellings of the same date, kept together."""

    year: int
    month: int
    day: int

    @property
    def flat(self) -> str:
        """``2026-11-22`` — labels, commit messages, CLI arguments."""
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"

    @property
    def nested(self) -> str:
        """``2026/11/22`` — the only directory name allowed in the repo."""
        return f"{self.year:04d}/{self.month:02d}/{self.day:02d}"

    @property
    def iso(self) -> str:
        return self.flat

    @property
    def pretty(self) -> str:
        """``22 Nov 2026`` — the section title style used since day one."""
        return f"{self.day} {MONTHS[self.month - 1]} {self.year}"

    def segments(self) -> tuple[str, str, str]:
        return (f"{self.year:04d}", f"{self.month:02d}", f"{self.day:02d}")


MONTHS: tuple[str, ...] = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def day_path(value: str | DayPath) -> DayPath:
    """Build a :class:`DayPath` from ``YYYY-MM-DD``, ``YYYY/MM/DD`` or itself."""
    if isinstance(value, DayPath):
        return value
    iso = parse_date(value)
    year, month, day = (int(part) for part in iso.split("-"))
    return DayPath(year=year, month=month, day=day)


def item_filename(order: int, item_id: str) -> str:
    """``01-aapl.json`` — sortable, and the id stays readable in ``git log``."""
    return f"{int(order):02d}-{item_id}.json"


def parse_item_filename(name: str) -> tuple[int, str] | None:
    """Inverse of :func:`item_filename`; ``None`` when the name is not an item."""
    match = re.match(r"^(\d+)-([a-z0-9][a-z0-9._-]*)\.json$", name)
    if not match:
        return None
    return int(match.group(1)), match.group(2)
