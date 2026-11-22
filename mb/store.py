"""Reading and writing a brief day on disk.

A day is *pipeline-managed* only when it has ``meta.json``. Days published
before the JSON pipeline are Markdown-only; they stay untouched, and
:func:`mb.render` never rewrites their files — it only still lists them on the
homepage so existing links keep working.
"""

from __future__ import annotations

import json
from pathlib import Path

from mb.model import Day, Item, load_item_bytes, load_meta_bytes, sort_items
from mb.paths import DAY_DIR_RE, SECTIONS, DayPath, day_path, parse_item_filename

META_NAME = "meta.json"
#: Files this package owns and regenerates. Nothing else may be clobbered.
GENERATED_NAMES: tuple[str, ...] = ("index.md", "weather.md", "stocks.md", "bulgarian-finances.md")


def day_dir(repo: Path, date: DayPath | str) -> Path:
    return repo / day_path(date).nested


def list_day_dirs(repo: Path) -> list[DayPath]:
    """Every ``YYYY/MM/DD`` directory in the repo, newest first."""
    found: list[DayPath] = []
    for year in sorted(repo.glob("????")):
        if not (year.is_dir() and year.name.isdigit()):
            continue
        for month in sorted(year.glob("??")):
            if not month.is_dir():
                continue
            for day in sorted(month.glob("??")):
                if day.is_dir() and DAY_DIR_RE.match(f"{year.name}/{month.name}/{day.name}"):
                    found.append(day_path(f"{year.name}-{month.name}-{day.name}"))
    return sorted(found, key=lambda item: item.flat, reverse=True)


def has_meta(repo: Path, date: DayPath) -> bool:
    return (day_dir(repo, date) / META_NAME).is_file()


def managed_days(repo: Path) -> list[DayPath]:
    """Days this pipeline renders (they carry meta.json), newest first."""
    return [date for date in list_day_dirs(repo) if has_meta(repo, date)]


def legacy_days(repo: Path) -> list[DayPath]:
    """Pre-JSON days: a directory tree with an index.md but no meta.json."""
    return [
        date
        for date in list_day_dirs(repo)
        if not has_meta(repo, date) and (day_dir(repo, date) / "index.md").is_file()
    ]


def load_day(repo: Path, date: DayPath | str) -> Day:
    target = day_path(date)
    path = day_dir(repo, target) / META_NAME
    if not path.is_file():
        raise FileNotFoundError(f"{path}: no such day (write meta.json first)")
    return load_meta_bytes(path.read_bytes(), path=str(path.relative_to(repo)), date=target)


def write_day(repo: Path, day: Day) -> Path:
    target = day_dir(repo, day.date)
    target.mkdir(parents=True, exist_ok=True)
    path = target / META_NAME
    path.write_text(json.dumps(day.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def section_dir(repo: Path, date: DayPath, section: str) -> Path:
    if section not in SECTIONS:
        raise ValueError(f"unknown section {section!r} — expected one of {SECTIONS}")
    return day_dir(repo, date) / section


def load_section_items(repo: Path, date: DayPath, section: str) -> list[Item]:
    """Parse every item file in a section directory, in publication order.

    Raises:
        FileNotFoundError: a stray non-item ``*.json`` sits in the directory —
            silence here means an item the pipeline silently never rendered.
    """
    directory = section_dir(repo, date, section)
    if not directory.is_dir():
        return []
    items: list[Item] = []
    for path in sorted(directory.glob("*.json")):
        if parse_item_filename(path.name) is None:
            raise FileNotFoundError(
                f"{path.relative_to(repo)}: not an item filename (expected NN-<id>.json)"
            )
        items.append(
            load_item_bytes(
                path.read_bytes(),
                path=str(path.relative_to(repo)),
                section_hint=section,
            )
        )
    return sort_items(items)


def write_item(repo: Path, date: DayPath, item: Item) -> Path:
    directory = section_dir(repo, date, item.section)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / item.filename()
    path.write_text(json.dumps(item.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def item_paths(repo: Path, date: DayPath) -> dict[str, list[Path]]:
    """Section -> sorted list of item files on disk (no parsing)."""
    return {
        section: sorted(section_dir(repo, date, section).glob("*.json"))
        if section_dir(repo, date, section).is_dir()
        else []
        for section in SECTIONS
    }


def counts(repo: Path, date: DayPath) -> dict[str, int]:
    """Item counts per section, for status lines and verify output."""
    result: dict[str, int] = {}
    for section in SECTIONS:
        directory = section_dir(repo, date, section)
        result[section] = len(sorted(directory.glob("*.json"))) if directory.is_dir() else 0
    return result
