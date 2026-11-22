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
from mb.render import format_holding, render_section, section_title
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
_BULLETED_URL_RE = re.compile(r"^-\s*(?P<url>https?://\S+)\s*$")
_FLAGS_RE = re.compile(r"^Flags:\s*$")
_BULLET_RE = re.compile(r"^-\s+(?P<body>.+)$")
_WEIGHT_RE = re.compile(r"^(?P<name>.+?)\s+—\s+(?P<weight>\d+(?:\.\d+)?)%(?:\s+as of\s+(?P<as_of>.+))?$")
_TICKER_RE = re.compile(r"^(?P<ticker>[A-Za-z][A-Za-z0-9]{0,5})(?=$|[ —-])")
_ZONE_RE = re.compile(r"[A-Z][a-z]+/[A-Z][a-zA-Z_]+")  # 'Europe/Sofia' in a generation stamp
_SUBHEAD_RE = re.compile(r"^##\s+\S")
_INLINE_FLAGS_RE = re.compile(r"^Flags:\s+(?P<body>\S.*)$")
# An item's first line. A holding line (``**1.** Apple …``) belongs to the item
# above it, so it is excluded and never opens a block of its own.
_ITEM_LEAD_RE = re.compile(r"^\*\*(?!\d+\.\*\*).+?\.\*\*\s")
# Holdings in the older house style: ``5. **Meta Platforms Class A** — 2.1% as of …``.
_HOLDING_ALT_RE = re.compile(r"^(?P<rank>\d+)\.\s+\*\*(?P<name>.+?)\*\*\s+—\s+(?P<rest>.+)$")
_WEIGHT_ONLY_RE = re.compile(r"^(?P<weight>\d+(?:\.\d+)?)%(?:\s+as of\s+(?P<as_of>.+))?$")

#: The only layout changes a backfill may make, each by this name. Anything
#: outside the list has to come back byte for byte.
RESTYLE_RULES: tuple[str, ...] = (
    "headline-derived",
    "items-split",
    "sources-bare",
    "holdings-format",
    "flags-inline",
)


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


def _starts_block(line: str) -> bool:
    """Would the renderer print a blank line before this line?

    Item lead-ins and sub-headings, and an inline ``Flags: …`` paragraph: the
    renderer always emits flags as their own trailing block, so a flag written
    directly under the last item is a block of its own even when the old paper
    left out the blank line.
    """
    return bool(
        _SUBHEAD_RE.match(line)
        or _INLINE_FLAGS_RE.match(line)
        or (_ITEM_LEAD_RE.match(line) and not _HOLDING_RE.match(line))
    )


def _split_blocks(block: list[str]) -> list[list[str]]:
    """Split a paragraph at item lead-ins and sub-headings.

    The old papers ran several items and their source lines together with no
    blank line between them, while the renderer separates blocks with one.
    Splitting is the parser being accurate, not permission to restyle: every
    item, source and order is preserved, and the blank lines the renderer adds
    are counted and reported by :func:`restyle`.
    """
    parts: list[list[str]] = []
    current: list[str] = []
    for line in block:
        if current and _starts_block(line):
            parts.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        parts.append(current)
    return parts


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
    entry.update(_weight_fields(match.group("weight")))
    if match.group("as_of"):
        entry["as_of"] = match.group("as_of")
    return entry


def _weight_fields(authored: str) -> dict[str, Any]:
    """A weight as a number, plus the authored figure when the pipeline's own
    two-decimal formatting would print it differently — etftrace's `2.4%` must
    not come back as `2.40%`.
    """
    value = float(authored)
    fields: dict[str, Any] = {"weight_pct": value}
    if f"{value:.2f}" != authored:
        fields["weight_display"] = f"{authored}%"
    return fields


def _parse_holding_alt(match: re.Match[str]) -> dict[str, Any]:
    """``5. **Meta Platforms Class A** — 2.1% as of 2026-10-29``."""
    entry: dict[str, Any] = {"rank": int(match.group("rank")), "name": match.group("name").strip()}
    weight = _WEIGHT_ONLY_RE.match(match.group("rest").strip())
    if weight:
        entry.update(_weight_fields(weight.group("weight")))
        if weight.group("as_of"):
            entry["as_of"] = weight.group("as_of").strip()
    return entry


def _source_urls(line: str) -> list[str]:
    """The URLs on a source line, one per link.

    Older papers bulleted the line and sometimes ran several links on it
    separated by ``·``; the pipeline prints one bare URL per line. Nothing but
    the separator and the bullet move.
    """
    content = line.strip()
    if content.startswith("- "):
        content = content[2:].strip()
    parts = [part.strip() for part in content.split(" · ")]
    if len(parts) > 1 and all(_URL_RE.match(part) for part in parts):
        return parts
    return [content] if _URL_RE.match(content) else []


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
        elif alternate := _HOLDING_ALT_RE.match(line.strip()):
            # The same fact in the older house style. The pipeline's own form is
            # what it becomes, and `restyle` counts the rewrite.
            holdings.append(_parse_holding_alt(alternate))
        elif (urls := _source_urls(line)) and urls != [line.strip()]:
            # A bulleted line, or several links on one: the URL is the data, the
            # bullet and the separator are layout.
            sources.extend(urls)
        elif _URL_RE.match(line.strip()):
            sources.append(line.strip())
        elif line.lstrip().startswith("- "):
            # A bullet that is not a source URL is normally the renderer's
            # triaged-news line: the JSON behind it carries verdicts, confidences
            # and news ids that the printed paper deliberately does not, so
            # rebuilding `news[]` here would invent them. Anything else that
            # bullet could have been, the renderer cannot reproduce it either.
            raise SectionError(
                f"{section}: item {label!r} contains a bullet that is not a source URL. A triaged "
                f"news bullet cannot be backfilled — its verdict lives only in JSON — and no other "
                f"bullet renders back from item fields, so this day is not convertible as written"
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


def _inline_flags(block: list[str]) -> list[str]:
    """``Flags: one sentence`` paragraphs — one flag each, continuations joined."""
    out: list[str] = []
    for line in block:
        stripped = line.strip()
        match = _INLINE_FLAGS_RE.match(stripped)
        if match:
            out.append(match.group("body"))
        elif out:
            out[-1] = f"{out[-1]} {stripped}"
        else:
            out.append(stripped)
    return out


def parse_section(text: str, section: str) -> list[dict[str, Any]]:
    """One section file into item records: contexts, sub-headings, items (with
    holdings and sources), then the ``Flags:`` block as flag items."""
    blocks = [part for block in _blocks(text) for part in _split_blocks(block)]
    records: list[dict[str, Any]] = []
    taken: set[str] = set()
    order = 10
    flags: list[str] = []
    for index, block in enumerate(blocks):
        first = block[0].strip()
        if _FLAGS_RE.match(first):
            flags.extend(match.group("body") for line in block[1:] if (match := _BULLET_RE.match(line.strip())))
            continue
        if index == len(blocks) - 1 and _INLINE_FLAGS_RE.match(first):
            # The old papers' closing "Flags: …" paragraph. The renderer always
            # prints flags last, so a final one lands on the trailing list
            # unchanged; a flag written mid-file would MOVE, and moving a caveat
            # around the prose it qualifies is an editorial decision, not a
            # migration. Those are left to the gate to refuse.
            flags.extend(_inline_flags(block))
            continue
        if _SUBHEAD_RE.match(first):
            records.append(
                {
                    "schema": ITEM_SCHEMA,
                    "section": section,
                    "id": _item_id(section, first, taken),
                    "order": order,
                    "kind": "heading",
                    "text": first.removeprefix("## ").strip(),
                }
            )
            order += 10
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
    missing = [section for section in SECTIONS if not (directory / f"{section}.md").is_file()]
    if missing:
        # A day that printed only some sections cannot be taken over: the render
        # writes every section in meta.json, so it would add pages the old paper
        # never had. Better a refusal than a half-populated archive day.
        raise SectionError(
            f"{date.nested}: not a complete day — no "
            f"{', '.join(f'{name}.md' for name in missing)}; "
            f"a backfill would print placeholder sections where the paper printed nothing"
        )
    for section in SECTIONS:
        path = directory / f"{section}.md"
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


def restyle(text: str, title: str) -> tuple[str, dict[str, int]]:
    """The original file with only the declared layout normalisations applied.

    Five changes, none of which loses a word, a figure or a link: a headline
    re-derived from the date (the old ones carried a weekday nobody needs when
    the path says ``2026/11/14``), items that ran together given the blank line
    the renderer puts between blocks, source lines de-bulleted and split one URL
    per line, holdings written ``5. **Name** — 2.1%`` given the pipeline's
    ``**5.** Name — 2.1%``, and a closing ``Flags: …`` sentence moved into the
    trailing list.

    The counts come back with the text because the caller has to print what it is
    about to change. A migration that restyles a published page in silence is
    precisely what the gate exists to prevent, so ``round_trip`` compares against
    this and nothing more permissive.
    """
    counts: dict[str, int] = {}
    lines = text.splitlines()
    if lines and lines[0].startswith("# ") and lines[0] != title:
        counts["headline-derived"] = 1

    raw = _blocks(text)
    splits = sum(len(_split_blocks(block)) - 1 for block in raw)
    if splits:
        counts["items-split"] = splits

    # The same block list the parser sees, so "is this the closing paragraph?"
    # is answered identically on both sides of the gate.
    pieces = [part for block in raw for part in _split_blocks(block)]
    blocks: list[str] = []
    flags: list[str] = []
    for index, piece_block in enumerate(pieces):
        first = piece_block[0].strip()
        if index == len(pieces) - 1 and _INLINE_FLAGS_RE.match(first) and not _FLAGS_RE.match(first):
            flags = _inline_flags(piece_block)
            counts["flags-inline"] = len(flags)
            continue
        piece: list[str] = []
        for line in piece_block:
            alternate = _HOLDING_ALT_RE.match(line.strip())
            if alternate:
                piece.append(format_holding(_parse_holding_alt(alternate)))
                counts["holdings-format"] = counts.get("holdings-format", 0) + 1
                continue
            urls = _source_urls(line)
            if urls and urls != [line.strip()]:
                piece.extend(urls)
                counts["sources-bare"] = counts.get("sources-bare", 0) + 1
                continue
            piece.append(line.rstrip())
        blocks.append("\n".join(piece))

    if flags:
        blocks.append("Flags:\n" + "\n".join(f"- {flag}" for flag in flags))
    return "\n\n".join([title, *blocks]) + "\n", counts


def restyle_report(parsed: ParsedDay) -> dict[str, dict[str, int]]:
    """Per section, the rules a restyled conversion would apply. Sections that
    need nothing are omitted, so an empty report means nothing is rewritten."""
    day = load_day_from(parsed)
    report: dict[str, dict[str, int]] = {}
    for section, original in parsed.originals.items():
        _, counts = restyle(original, section_title(day, section))
        if counts:
            report[section] = counts
    return report


def round_trip(parsed: ParsedDay, *, allow_restyle: bool = False) -> dict[str, str]:
    """section -> why re-rendering the parsed items would change that file.

    Empty means every section file is reproduced byte for byte — or, when
    ``allow_restyle`` is set, byte for byte against the declared normalisations
    in :func:`restyle`. A non-empty value names the construct responsible where
    one is recognisable, so a refusal says what to do about it.
    """
    day = load_day_from(parsed)
    problems: dict[str, str] = {}
    for section, records in parsed.sections.items():
        items = [Item.from_json(record, section=section, where=f"{section}/{record.get('id')}") for record in records]
        rendered = render_section(day, section, items)
        original = parsed.originals[section]
        title = section_title(day, section)
        if rendered != original and allow_restyle:
            expected, _ = restyle(original, title)
            # A restyled file is expected to differ from what is on disk; nothing
            # else is, so the byte check below only governs an exact conversion.
            if rendered == expected:
                continue
        if rendered == original:
            # Same characters, different bytes: the file is still about to change.
            if parsed.raw.get(section) != rendered.encode("utf-8"):
                problems[section] = (
                    "line endings or encoding differ from what the render writes "
                    "(the text matches, so this is invisible in a prose diff)"
                )
            continue
        problems[section] = _diagnose(section, original, rendered, records, title, allow_restyle=allow_restyle)
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


def _diagnose(
    section: str,
    original: str,
    rendered: str,
    records: list[dict[str, Any]],
    title: str,
    *,
    allow_restyle: bool = False,
) -> str:
    """Name the construct that blocks the conversion.

    ``reason=round-trip`` plus a diff fragment makes an operator guess. Each cause
    is matched against the original text rather than inferred from a diff, and
    carries the restyle rule that would resolve it — so the refusal either names
    the flag to pass or states plainly that no flag will do.
    """
    lines = original.splitlines()
    first = lines[0] if lines else ""
    raw = _blocks(original)
    blocks = [part for block in raw for part in _split_blocks(block)]
    causes: list[tuple[str, str]] = []

    if first.startswith("# ") and first != title:
        causes.append(("headline-derived", f"the headline is authored ({first!r}) while the pipeline derives {title!r}"))
    inline = [i for i, block in enumerate(blocks) if _INLINE_FLAGS_RE.match(block[0].strip())]
    if inline:
        last_only = inline == [len(blocks) - 1]
        where = "as the closing paragraph" if last_only else "mid-file, where the pipeline cannot put them"
        causes.append((
            "flags-inline" if last_only else "",
            f'flags are one inline paragraph ("Flags: …") {where}; the pipeline prints a trailing "Flags:" list',
        ))
    if any(_BULLETED_URL_RE.match(line.strip()) for line in lines):
        causes.append(("sources-bare", 'source URLs are list items ("- https://…"); the pipeline prints them bare'))
    if any(len(_source_urls(line)) > 1 for line in lines):
        causes.append(("sources-bare", "several source URLs share one line; the pipeline prints one per line"))
    if any(_HOLDING_ALT_RE.match(line.strip()) for line in lines):
        causes.append((
            "holdings-format",
            'holdings are written "5. **Name** — 2.1%"; the pipeline prints "**5.** Name — 2.1%"',
        ))

    if allow_restyle:
        # Those rules already fired, so blaming them again would send the operator
        # hunting for a flag they already passed. What is left is the real blocker.
        causes = [(rule, text) for rule, text in causes if not rule]
    elif causes and all(rule for rule, _ in causes):
        return "; ".join(text for _, text in causes[:3]) + " — --allow-restyle converts this (" + ", ".join(sorted({rule for rule, _ in causes})) + ")"

    if not causes:
        # Nothing recognisable: show the first line that still differs, against
        # the text the gate actually compared with.
        expected, _ = restyle(original, title) if allow_restyle else (original, {})
        return _first_difference(expected, rendered)
    return "; ".join(text for _, text in causes[:3])


def _first_difference(before: str, after: str) -> str:
    """A refusal an operator can act on, because ``+`` alone tells them nothing.

    Blank lines dominate these diffs — the pipeline separates blocks, the old
    papers did not — so the count is reported and the first line with characters
    in it is quoted from each side.
    """
    from difflib import unified_diff

    changed = [
        line
        for line in unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
        if line[:1] in "+-" and line[:3] not in ("+++", "---")
    ]
    if not changed:
        return "the files differ by whitespace alone"

    def quote(line: str) -> str:
        body = line[1:].strip()
        return f"{line[0]} {body[:110]}…" if len(body) > 110 else f"{line[0]} {body}"

    removed = sorted(line[1:].strip() for line in changed if line[0] == "-" and line[1:].strip())
    added = sorted(line[1:].strip() for line in changed if line[0] == "+" and line[1:].strip())
    if removed and removed == added:
        # Every line that vanished reappears: nothing was changed, only shuffled.
        # That is the pipeline's fixed layout — lead paragraphs first, flags last
        # — and relocating a sentence relative to the prose it qualifies is an
        # editorial decision, so no restyle flag will talk its way past this.
        return (
            f"{len(removed)} line(s) moved: the pipeline fixes the order (lead paragraphs first, "
            f"flags last) and this day placed “{removed[0][:70]}” elsewhere. "
            f"Moving prose is an edit, not a migration"
        )
    removed_line = next((line for line in changed if line[1:].strip()), "")
    added_line = next((line for line in changed if line[0] == "+" and line[1:].strip()), "")
    parts = [f"{len(changed)} line(s) differ"]
    if removed_line:
        parts.append(f"on disk: {quote(removed_line)}")
    if added_line:
        parts.append(f"rendered: {quote(added_line)}")
    return " │ ".join(parts)


def write_backfill(repo: Path, parsed: ParsedDay) -> list[Path]:
    """Commit the parsed day to disk as JSON. Callers must gate on round_trip()."""
    from mb.ingest import ingest

    write_day(repo, load_day_from(parsed))
    written: list[Path] = []
    for section, records in parsed.sections.items():
        items = [Item.from_json(record, section=section, where=f"{section}/{record.get('id')}") for record in records]
        written.extend(ingest(repo, parsed.date, items, replace=True, inherit=False))
    return written


__all__ = [
    "RESTYLE_RULES",
    "ParsedDay",
    "parse_day",
    "parse_section",
    "restyle",
    "restyle_report",
    "round_trip",
    "write_backfill",
]
