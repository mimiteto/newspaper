"""Draft JSON -> one file per item.

A lane drafts its whole section in one JSON document (cheap for the model, one
write), and ``ingest`` splits it into ``NN-<id>.json`` files under the section
directory — the layout the brief is stored in.

Section writes default to **replace**: the lane owns its section directory, so a
re-run converges the directory to exactly the drafted items instead of leaving a
stale item from the previous attempt to render twice. Pass ``merge=True`` to add
to what is already there.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mb.model import Item, Relevance, SectionError
from mb.paths import SECTIONS, DayPath
from mb.store import load_section_items, section_dir, write_item

#: Draft orders step by 10 so a later manual insert can take 11, 12, ... without
#: renumbering everything (and without churning every file's git history).
ORDER_STEP = 10


def load_draft(path: Path) -> tuple[str | None, list[dict[str, Any]], dict[str, Any]]:
    """Read a draft file.

    Accepts ``[...]``, ``{"items": [...]}`` and ``{"section": ..., "items": [...],
    "meta": {...}}`` — the last form lets one file carry the day's meta.json too.

    Returns ``(section_or_None, item_records, meta_records)``.
    """
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SectionError(f"{path}: no such draft file") from exc
    except json.JSONDecodeError as exc:
        raise SectionError(f"{path}: invalid JSON — {exc}") from exc

    meta: dict[str, Any] = {}
    section: str | None = None
    if isinstance(record, list):
        items = record
    elif isinstance(record, dict):
        items = record.get("items")
        section = record.get("section")
        raw_meta = record.get("meta", {})
        if not isinstance(raw_meta, dict):
            raise SectionError(f"{path}: 'meta' must be an object")
        meta = raw_meta
    else:
        raise SectionError(f"{path}: expected a JSON array or an object with 'items'")

    if not isinstance(items, list) or not items:
        raise SectionError(f"{path}: no items to ingest (expected a non-empty list)")
    if section is not None and section not in SECTIONS:
        raise SectionError(f"{path}: 'section' must be one of {SECTIONS}, got {section!r}")
    return section, items, meta


def next_order(repo: Path, date: DayPath, section: str) -> int:
    """First free order slot in a section, for ``--merge`` appends."""
    highest = 0
    for item in load_section_items(repo, date, section):
        highest = max(highest, item.order)
    return highest + ORDER_STEP if highest else ORDER_STEP


def inherit_relevance(repo: Path, date: DayPath, items: list[Item]) -> int:
    """Carry an existing decisions-API verdict onto a re-drafted item.

    A lane that re-publishes ships fresh JSON, but the verdict belongs to the
    news, not to the file. Without this, every re-publish would silently
    un-judge yesterday's items and print them all. Matching is by ``id``: the
    slug is semantic, so a genuinely different story arrives unjudged and gets
    caught by ``verify --require-decisions``.

    Returns how many verdicts were carried over.
    """
    carried = 0
    by_section: dict[str, list[Item]] = {}
    for item in items:
        by_section.setdefault(item.section, []).append(item)
    for section, section_items in by_section.items():
        try:
            previous = load_section_items(repo, date, section)
        except (FileNotFoundError, SectionError):
            continue
        old = {prior.id: prior for prior in previous}
        for item in section_items:
            origin = old.get(item.id)
            if origin is None:
                continue
            if item.relevance is None and isinstance(origin.relevance, Relevance):
                item.relevance = origin.relevance
                carried += 1
            old_news = {entry.id: entry for entry in origin.news}
            for entry in item.news:
                prior = old_news.get(entry.id)
                if entry.relevance is None and prior is not None and isinstance(prior.relevance, Relevance):
                    entry.relevance = prior.relevance
                    carried += 1
    return carried


def ingest(
    repo: Path,
    date: DayPath,
    items: list[Item],
    *,
    replace: bool = True,
    inherit: bool = True,
) -> list[Path]:
    """Write validated items as ``NN-<id>.json``, then prune the section dir.

    Pruning happens after the write so a failed validation leaves the tree as
    it was rather than half-emptied.
    """
    if inherit:
        inherit_relevance(repo, date, items)
    by_section: dict[str, list[Item]] = {}
    for item in items:
        by_section.setdefault(item.section, []).append(item)

    written: list[Path] = []
    for section, section_items in by_section.items():
        ids = [item.id for item in section_items]
        duplicates = sorted({name for name in ids if ids.count(name) > 1})
        if duplicates:
            raise SectionError(f"{date.nested}/{section}: duplicate item ids: {', '.join(duplicates)}")
        keep = {item.filename() for item in section_items}
        directory = section_dir(repo, date, section)
        directory.mkdir(parents=True, exist_ok=True)
        for item in section_items:
            written.append(write_item(repo, date, item))
        if replace:
            for stale in directory.glob("*.json"):
                if stale.name not in keep:
                    stale.unlink()
    return written


def normalise_orders(records: list[dict[str, Any]], *, start: int = ORDER_STEP) -> list[dict[str, Any]]:
    """Fill in ``order`` for records that omit it, keeping draft order.

    Draft files are already written in reading order, so a lane can leave
    ``order`` out entirely and get ``10, 20, 30, ...``.
    """
    filled: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if isinstance(record, dict) and "order" not in record:
            record = {**record, "order": start + index * ORDER_STEP}
        filled.append(record)
    return filled


__all__ = ["ORDER_STEP", "ingest", "inherit_relevance", "load_draft", "next_order", "normalise_orders"]
