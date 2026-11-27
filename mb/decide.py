"""Apply decisions-API verdicts to brief JSON, deterministically.

The classifier answers two booleans per news item — *relevant to the brief* and
*relevant to the price move* — plus a category and a confidence. This module
turns those answers into a ``verdict`` stored in the item file, so rendering
never has to re-ask anything.

Verdict meanings (see :meth:`mb.model.Relevance.decide`):

``keep``     print in full — it matters to the owner, the move, or both
``context``  print demoted to a headline-only line — it explains the tape but
             says nothing about why the position is held
``drop``     not printed; the JSON stays on disk so the call is auditable

The producer of the verdicts file is the pi tool ``mb_decide`` (which calls the
Decisions API through pi's model registry); this module is the consumer, and it
is the only place the rule is applied.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mb.model import Item, Relevance
from mb.paths import SECTIONS, DayPath
from mb.store import load_section_items, write_item

VERDICTS_SCHEMA = "mb/verdicts@1"


class VerdictError(ValueError):
    """A verdict record could not be applied."""


def load_verdicts(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise VerdictError(f"{path}: no such verdicts file") from exc
    except json.JSONDecodeError as exc:
        raise VerdictError(f"{path}: invalid JSON — {exc}") from exc
    if not isinstance(record, dict) or not isinstance(record.get("verdicts"), list):
        raise VerdictError(f"{path}: expected {{'verdicts': [...]}}")
    schema = record.get("schema", VERDICTS_SCHEMA)
    if schema != VERDICTS_SCHEMA:
        raise VerdictError(f"{path}: schema must be {VERDICTS_SCHEMA!r}, got {schema!r}")
    return record


def _relevance_from(verdict: dict[str, Any], *, decided_by: str, decided_at: str, where: str) -> Relevance:
    for key in ("brief", "price_move"):
        if not isinstance(verdict.get(key), bool):
            raise VerdictError(f"{where}: {key!r} must be a boolean")
    explicit = verdict.get("verdict")
    if explicit is not None and str(explicit) not in ("keep", "context", "drop"):
        raise VerdictError(f"{where}: verdict must be keep|context|drop, got {explicit!r}")
    relevance = Relevance(
        brief=bool(verdict["brief"]),
        price_move=bool(verdict["price_move"]),
        category=str(verdict.get("category", "other")),
        confidence=None if verdict.get("confidence") is None else float(verdict["confidence"]),
        verdict=str(explicit) if explicit else Relevance.decide(bool(verdict["brief"]), bool(verdict["price_move"])),
        decided_by=str(verdict.get("decided_by", decided_by)),
        decided_at=str(verdict.get("decided_at", decided_at)),
        why=str(verdict.get("why", "")),
        # The tool's honesty flag has to survive the round trip, or "the
        # classifier wasn't sure" is indistinguishable from "the classifier was
        # sure and wrong" once it is printed in the paper.
        ambiguous=bool(verdict.get("ambiguous", False)),
    )
    # Re-validate through the model parser so an odd category fails here, not in CI.
    return Relevance.from_json(relevance.to_json(), where=where)


def _apply_to_item(
    item: Item,
    verdict: dict[str, Any],
    *,
    where: str,
    default_decided_by: str,
    default_decided_at: str,
) -> Relevance:
    """Attach one verdict to an item, or to one of its news entries.

    A file-level ``decided_by``/``decided_at`` labels the whole batch, so the
    classifier only has to stamp its model id once.
    """
    relevance = _relevance_from(
        verdict,
        decided_by=str(verdict.get("decided_by", default_decided_by)),
        decided_at=str(verdict.get("decided_at", default_decided_at)),
        where=where,
    )
    news_id = verdict.get("news_id")
    if news_id is None:
        item.relevance = relevance
        return relevance
    for entry in item.news:
        if entry.id == news_id:
            entry.relevance = relevance
            return relevance
    raise VerdictError(f"{where}: no news entry {news_id!r} in item {item.id}")


def _check_target(section: str, item_id: str, verdict: dict[str, Any], where: str) -> None:
    """Reject a verdict that would judge a whole watch-list line.

    A verdict with no ``news_id`` judges the item, which is right for a section
    of standalone stories and wrong for ``stocks``: there an item is a line on
    the list, ``drop`` hides items, so a classifier asked about news and finding
    none would silently delete a holding. That is a decision about the portfolio,
    and no classifier was asked to make it.
    """
    if section == "stocks" and not verdict.get("news_id"):
        raise VerdictError(
            f"{where}: a stocks verdict must name a news_id. Here an item is a watch-list line, not a "
            f"news entry, and drop would remove {item_id} from the paper — a decision about the "
            f"portfolio, not about the news. Judge its news[] entries, or leave the line alone."
        )


def apply_verdicts(
    repo: Path,
    date: DayPath,
    verdicts: dict[str, Any],
    *,
    write: bool = True,
    section: str | None = None,
) -> dict[str, Any]:
    """Attach verdicts to the matching items. Returns a summary dict.

    ``section`` scopes the batch to one section, which is what a publishing
    lane wants: three lanes race on the same day, and a verdict file naming
    another lane's sections would succeed or fail depending on whose push
    landed first. Out-of-scope verdicts are counted as ``skipped``.

    An unmatched ``(id[,news_id])`` inside the scope is an error rather than a
    warning: a silently ignored verdict means the pipeline and the classifier
    disagree about what exists, which is how a stale item ends up printed.

    A verdict with no ``news_id`` judges the whole item, which is what a section
    of standalone stories (Bulgaria) wants. It is refused for ``stocks``, where
    an item is a watch-list line: ``drop`` hides an item, so a classifier asked
    about news that found none would delete a holding from the paper.
    """
    scope = section
    decided_by = str(verdicts.get("decided_by", ""))
    decided_at = str(verdicts.get("decided_at", ""))
    items_by_section: dict[str, list[Item]] = {}
    summary = {"applied": 0, "keep": 0, "context": 0, "drop": 0, "skipped": 0, "sections": set()}

    for index, verdict in enumerate(verdicts["verdicts"]):
        if not isinstance(verdict, dict):
            raise VerdictError(f"verdicts[{index}]: expected an object")
        section = verdict.get("section")
        item_id = verdict.get("id")
        if section not in SECTIONS or not isinstance(item_id, str):
            raise VerdictError(f"verdicts[{index}]: need 'section' in {SECTIONS} and a string 'id'")
        if scope is not None and section != scope:
            summary["skipped"] += 1
            continue
        where = f"verdicts[{index}] {section}/{item_id}"
        _check_target(section, item_id, verdict, where)
        if section not in items_by_section:
            items_by_section[section] = load_section_items(repo, date, section)
        for item in items_by_section[section]:
            if item.id == item_id:
                relevance = _apply_to_item(
                    item,
                    verdict,
                    where=where,
                    default_decided_by=decided_by,
                    default_decided_at=decided_at,
                )
                summary["applied"] += 1
                summary[relevance.verdict] += 1
                summary["sections"].add(section)
                break
        else:
            raise VerdictError(f"{where}: no such item under {date.nested}/{section}/")

    if write:
        for items in items_by_section.values():
            for item in items:
                write_item(repo, date, item)

    summary["sections"] = sorted(summary["sections"])
    summary["scope"] = scope or "all"
    return summary


__all__ = ["VERDICTS_SCHEMA", "VerdictError", "apply_verdicts", "load_verdicts"]
