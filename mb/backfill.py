"""Legacy Markdown day -> JSON items, with a byte-exact round-trip gate.

Days published before this pipeline are prose the model formatted by hand. A
backfill has exactly one acceptable outcome: the JSON, rendered, produces the
same bytes as the file that is on the site today. Anything else is a rewrite of
history dressed up as a migration, so :func:`round_trip` diffs every section and
the caller refuses the day when a single line moves.

The gate is what makes the operation safe to run unattended: parsing is
deterministic, the original Markdown is read into memory first and never touched
(``mb render`` owns it afterwards), and a parser bug shows up as a diff here
rather than as a silently reworded newspaper.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mb.model import ITEM_SCHEMA, Day, Item, SectionError, slugify
from mb.paths import SECTIONS, DayPath
from mb.render import render_section
from mb.store import day_dir, write_day

#: Bulgarian labels have no ASCII slug, and a hash for every id makes the corpus
#: unreadable. Cyrillic is transliterated once, here, so ids stay stable and
#: reviewable; anything left over falls back to a short digest.
_CYRILLIC: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sht", "ъ": "a", "ь": "y", "ю": "yu", "я": "ya",
}

_ITEM_RE = re.compile(r"^\*\*(?P<label>.+?)\.\*\*(?:\s+(?P<text>.*))?$")
_HOLDING_RE = re.compile(r"^\*\*(?P<rank>\d+)\.\*\*\s+(?P<rest>.+)$")
_HEADING_RE = re.compile(r"^#\s")
_URL_RE = re.compile(r"^https?://\S+$")
_FLAGS_RE = re.compile(r"^Flags:\s*$")
_BULLET_RE = re.compile(r"^-\s+(?P<body>.+)$")
_WEIGHT_RE = re.compile(r"^(?P<name>.+?)\s+—\s+(?P<weight>\d+(?:\.\d+)?)%(?:\s+as of\s+(?P<as_of>.+))?$")
_TICKER_RE = re.compile(r"^(?P<ticker>[A-Za-z][A-Za-z0-9]{0,5})(?=$|[ —-])")
_ZONE_RE = re.compile(r"[A-Z][a-z]+/[A-Z][a-zA-Z_]+")  # 'Europe/Sofia' in a generation stamp


@dataclass
class ParsedDay:
    """What the Markdown said, before any of it is trusted."""

    date: DayPath
    location: str
    timezone: str
    started: str = ""
    finished: str = ""
    #: section -> item records, in document order
    sections: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    #: section -> the original file text, kept for the round-trip gate
    originals: dict[str, str] = field(default_factory=dict)
    #: section -> the original bytes. Text comparison alone would let a CRLF or
    #: BOM file through: Python reads both as clean UTF-8, and the render would
    #: then rewrite every line ending of a file it claims to reproduce.
    raw: dict[str, bytes] = field(default_factory=dict)


def _blocks(text: str) -> list[list[str]]:
    """Non-empty blank-line-separated blocks, H1 dropped."""
    out: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                out.append(current)
                current = []
            continue
        if _HEADING_RE.match(line):
            continue
        current.append(line.rstrip())
    if current:
        out.append(current)
    return out


def _transliterate(value: str) -> str:
    lowered = value.lower()
    for cyr, latin in _CYRILLIC.items():
        lowered = lowered.replace(cyr, latin)
    return slugify(lowered)


def _item_id(section: str, label: str, taken: set[str]) -> str:
    """A stable, readable id. The same label must always yield the same id:
    ids are filenames and the key the decisions API votes against."""
    ticker = _TICKER_RE.match(label.strip())
    base = ticker.group("ticker").lower() if ticker and section == "stocks" else ""
    base = base or _transliterate(label) or _transliterate(section) or section
    if not base:
        base = f"{section}-{hashlib.sha256(label.encode('utf-8')).hexdigest()[:8]}"
    candidate, suffix = base, 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def _parse_holding(rest: str) -> dict[str, Any]:
    """``Apple — 8.14% as of 19 Nov 2026`` from the renderer's own format."""
    match = _WEIGHT_RE.match(rest)
    if not match:
        return {"name": rest}
    entry: dict[str, Any] = {"name": match.group("name")}
    authored = match.group("weight")
    entry["weight_pct"] = float(authored)
    # Only record the authored figure when the pipeline's own formatting would
    # print it differently, so most backfilled holdings stay plain numbers.
    if f"{entry['weight_pct']:.2f}" != authored:
        entry["weight_display"] = f"{authored}%"
    if match.group("as_of"):
        entry["as_of"] = match.group("as_of")
    return entry


def _parse_item(block: list[str], section: str, taken: set[str], order: int) -> dict[str, Any] | None:
    match = _ITEM_RE.match(block[0])
    if not match:
        return None
    label = match.group("label").strip()
    if _HOLDING_RE.match(block[0]):  # a stray holding line is not an item
        return None
    text_parts = [match.group("text") or ""]
    sources: list[str] = []
    holdings: list[dict[str, Any]] = []
    for line in block[1:]:
        holding = _HOLDING_RE.match(line)
        if holding:
            entry = _parse_holding(holding.group("rest"))
            entry.setdefault("rank", int(holding.group("rank")))
            holdings.append(entry)
        elif _URL_RE.match(line.strip()):
            sources.append(line.strip())
        elif line.lstrip().startswith("- "):
            # A bullet inside an item is normally the renderer's triaged-news
            # line: the JSON behind it carries verdicts, confidences and news ids
            # that the printed paper deliberately does not, so rebuilding `news[]`
            # here would invent them. Anything else that bullet could have been,
            # the renderer cannot reproduce either — so refuse, either way.
            raise SectionError(
                f"{section}: item {label!r} contains a bullet line. Triaged news cannot be "
                f"backfilled (its verdicts live only in JSON), and no other bullet renders back "
                f"from item fields, so this day is not convertible as written"
            )
        else:
            text_parts.append(line)
    text = "\n".join(part for part in text_parts if part).strip()
    record: dict[str, Any] = {
        "schema": ITEM_SCHEMA,
        "section": section,
        "id": _item_id(section, label, taken),
        "order": order,
        "kind": "item",
        "label": label,
        "text": text,
    }
    if sources:
        record["sources"] = sources
    if holdings:
        record["holdings"] = holdings
    return record


def parse_section(text: str, section: str) -> list[dict[str, Any]]:
    """One section file into item records: contexts, items (with holdings and
    sources), then the ``Flags:`` block as flag items."""
    records: list[dict[str, Any]] = []
    taken: set[str] = set()
    order = 10
    flags: list[str] = []
    for block in _blocks(text):
        first = block[0].strip()
        if _FLAGS_RE.match(first):
            flags.extend(match.group("body") for line in block[1:] if (match := _BULLET_RE.match(line.strip())))
            continue
        item = _parse_item(block, section, taken, order)
        if item is not None:
            records.append(item)
            order += 10
            continue
        # No bold lead-in: a lead paragraph the renderer prints un-bulleted.
        records.append(
            {
                "schema": ITEM_SCHEMA,
                "section": section,
                "id": _item_id(section, first[:40] or "context", taken),
                "order": order,
                "kind": "context",
                "text": "\n".join(block),
            }
        )
        order += 10
    for index, flag in enumerate(flags, start=1):
        records.append(
            {
                "schema": ITEM_SCHEMA,
                "section": section,
                "id": f"flag-{index:02d}",
                "order": 900 + index,
                "kind": "flag",
                "text": flag,
            }
        )
        taken.add(f"flag-{index:02d}")
    return records


def _stamp(index_text: str, key: str) -> str:
    match = re.search(rf"^\*\*{key}:\*\*\s*(.+?)\s*$", index_text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_day(repo: Path, date: DayPath) -> ParsedDay:
    """Read a legacy day's Markdown. Raises if any section file is missing,
    because a half-parsed day must not be backfilled into a complete-looking one."""
    directory = day_dir(repo, date)
    index_path = directory / "index.md"
    index_text = index_path.read_text(encoding="utf-8") if index_path.is_file() else ""

    parsed = ParsedDay(
        date=date,
        location="Novi Iskar",
        timezone="Europe/Sofia",
        started=_stamp(index_text, "Started"),
        finished=_stamp(index_text, "Finished"),
    )
    for section in SECTIONS:
        path = directory / f"{section}.md"
        if not path.is_file():
            raise SectionError(f"{date.nested}/{section}.md: no such file — nothing to backfill")
        text = path.read_text(encoding="utf-8")
        parsed.originals[section] = text
        parsed.raw[section] = path.read_bytes()
        parsed.sections[section] = parse_section(text, section)
        if section == "weather":
            title = next((line for line in text.splitlines() if line.startswith("# Weather — ")), "")
            # `# Weather — <location>, <D Mon YYYY>`
            head = title.removeprefix("# Weather — ").strip()
            parsed.location = head.rsplit(",", 1)[0].strip() or parsed.location
            # The generation stamp names the zone the day was written in. Market
            # timestamps are exchange clocks and must not be mistaken for it.
            zone = _ZONE_RE.search(text)
            if zone:
                parsed.timezone = zone.group(0)
    return parsed


def round_trip(parsed: ParsedDay) -> dict[str, str]:
    """section -> first difference between the render and the original file.

    Empty means every section file is reproduced byte for byte, which is the only
    result a backfill may act on.
    """
    day = load_day_from(parsed)
    problems: dict[str, str] = {}
    for section, records in parsed.sections.items():
        items = [Item.from_json(record, section=section, where=f"{section}/{record.get('id')}") for record in records]
        rendered = render_section(day, section, items)
        original = parsed.originals[section]
        if rendered == original:
            # Same characters, different bytes: the file is still about to change.
            if parsed.raw.get(section) != rendered.encode("utf-8"):
                problems[section] = (
                    "line endings or encoding differ from what the render writes "
                    "(the text matches, so this is invisible in a prose diff)"
                )
            continue
        problems[section] = _first_difference(original, rendered)
    return problems


def load_day_from(parsed: ParsedDay) -> Day:
    """The day record implied by the parsed Markdown (not yet on disk)."""
    return Day(
        date=parsed.date,
        location=parsed.location,
        timezone=parsed.timezone,
        started=parsed.started,
        finished=parsed.finished,
        source="backfill from markdown",
    )


def _first_difference(before: str, after: str) -> str:
    """A diff that names the line, because 'it differs' is useless at 07:00."""
    from difflib import unified_diff

    lines = list(unified_diff(before.splitlines(), after.splitlines(), "original", "rendered", lineterm="", n=1))
    for line in lines:
        if line.startswith(("-", "+")) and not line.startswith(("---", "+++")):
            return f"{line[:160]}…" if len(line) > 160 else line
    return f"{len(lines)} line(s) differ"


def write_backfill(repo: Path, parsed: ParsedDay) -> list[Path]:
    """Commit the parsed day to disk as JSON. Callers must gate on round_trip()."""
    from mb.ingest import ingest

    write_day(repo, load_day_from(parsed))
    written: list[Path] = []
    for section, records in parsed.sections.items():
        items = [Item.from_json(record, section=section, where=f"{section}/{record.get('id')}") for record in records]
        written.extend(ingest(repo, parsed.date, items, replace=True, inherit=False))
    return written


__all__ = ["ParsedDay", "parse_day", "parse_section", "round_trip", "write_backfill"]
