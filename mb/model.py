"""Data model + validation for Morning Brief JSON.

Two record types:

``mb/day@1``  — ``YYYY/MM/DD/meta.json``, one per published day.
``mb/item@1`` — ``YYYY/MM/DD/<section>/<order>-<id>.json``, one per brief item.

Validation is deliberately strict because the producer is an LLM drafting a
JSON array: a clear error naming the offending item beats a Markdown file that
renders wrong three steps later. Unknown keys are rejected for the same reason
— a typo like ``soruces`` must not silently drop a citation.

Item ``kind`` decides where a rendered item lands:

``item``     a normal ``**Label.** prose`` bullet in its section
``context``  prose right under the section title (snapshot / generation line)
``flag``     collected under the section's trailing ``Flags:`` block
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from mb.paths import SECTIONS, DayPath, item_filename, parse_item_filename

DAY_SCHEMA = "mb/day@1"
ITEM_SCHEMA = "mb/item@1"

KINDS: tuple[str, ...] = ("item", "context", "flag")

#: Item fields every section may use. Anything else is a schema error.
COMMON_FIELDS: frozenset[str] = frozenset(
    {
        "schema", "id", "order", "section", "kind", "label", "text",
        "as_of", "sources", "flags", "relevance", "notes",
    }
)

#: Section-specific fields, on top of COMMON_FIELDS.
SECTION_FIELDS: dict[str, frozenset[str]] = {
    "weather": frozenset({"metric", "provider"}),
    "stocks": frozenset(
        {
            "ticker", "name", "listing", "currency", "price", "change_abs",
            "change_pct_1d", "change_pct_5d", "change_pct_1m", "news",
            "holdings", "fund",
        }
    ),
    "bulgarian-finances": frozenset({"topic", "bill", "effective_date", "amount"}),
}

#: Where a stock-news relevance verdict leaves the item in the rendered brief.
VERDICTS: tuple[str, ...] = ("keep", "context", "drop")

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class SectionError(ValueError):
    """A JSON record failed validation. Message names the item and the field."""


def _require_str(record: dict[str, Any], key: str, where: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SectionError(f"{where}: {key!r} must be a non-empty string, got {value!r}")
    return value.strip()


def _check_unknown(record: dict[str, Any], allowed: set[str] | frozenset[str], where: str) -> None:
    unknown = sorted(set(record) - set(allowed))
    if unknown:
        raise SectionError(
            f"{where}: unknown field(s) {', '.join(unknown)} — allowed: {', '.join(sorted(allowed))}"
        )


def _norm_sources(value: Any, where: str) -> list[dict[str, str]]:
    """Accept ``["https://x"]`` or ``[{"title": "...", "url": "..."}]``."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise SectionError(f"{where}: 'sources' must be a list, got {type(value).__name__}")
    out: list[dict[str, str]] = []
    for index, entry in enumerate(value):
        if isinstance(entry, str):
            url = entry.strip()
            if not url:
                raise SectionError(f"{where}: sources[{index}] is empty")
            out.append({"url": url})
            continue
        if isinstance(entry, dict):
            url = _require_str(entry, "url", f"{where} sources[{index}]")
            extra = set(entry) - {"url", "title"}
            if extra:
                raise SectionError(f"{where}: sources[{index}] unknown field(s): {', '.join(sorted(extra))}")
            title = entry.get("title")
            out.append({"url": url, "title": title.strip()} if isinstance(title, str) and title.strip() else {"url": url})
            continue
        raise SectionError(f"{where}: sources[{index}] must be a string or {{title,url}} object")
    return out


def _norm_str_list(value: Any, where: str, key: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(entry, str) and entry.strip() for entry in value):
        raise SectionError(f"{where}: {key!r} must be a list of non-empty strings")
    return [entry.strip() for entry in value]


@dataclass
class Relevance:
    """A decisions-API verdict on one stock news item.

    ``brief`` = worth printing for the owner of the position;
    ``price_move`` = plausibly explains the observed move.
    ``verdict`` is the decision the renderer obeys.
    """

    brief: bool = False
    price_move: bool = False
    category: str = "other"
    confidence: float | None = None
    verdict: str = "keep"
    decided_by: str = ""
    decided_at: str = ""
    why: str = ""

    ALLOWED_CATEGORY = frozenset(
        {"guidance", "analyst", "strategic", "macro", "stale", "noise", "other"}
    )

    @classmethod
    def from_json(cls, record: Any, where: str) -> Relevance:
        if not isinstance(record, dict):
            raise SectionError(f"{where}: 'relevance' must be an object")
        allowed = {"brief", "price_move", "category", "confidence", "verdict", "decided_by", "decided_at", "why"}
        _check_unknown(record, allowed, where)
        verdict = str(record.get("verdict", "keep"))
        if verdict not in VERDICTS:
            raise SectionError(f"{where}: relevance.verdict must be one of {VERDICTS}, got {verdict!r}")
        category = str(record.get("category", "other"))
        if category not in cls.ALLOWED_CATEGORY:
            raise SectionError(
                f"{where}: relevance.category must be one of {sorted(cls.ALLOWED_CATEGORY)}, got {category!r}"
            )
        confidence = record.get("confidence")
        if confidence is not None and not isinstance(confidence, (int, float)):
            raise SectionError(f"{where}: relevance.confidence must be a number")
        for key in ("brief", "price_move"):
            if key in record and not isinstance(record[key], bool):
                raise SectionError(f"{where}: relevance.{key} must be a boolean")
        return cls(
            brief=bool(record.get("brief", False)),
            price_move=bool(record.get("price_move", False)),
            category=category,
            confidence=None if confidence is None else float(confidence),
            verdict=verdict,
            decided_by=str(record.get("decided_by", "")),
            decided_at=str(record.get("decided_at", "")),
            why=str(record.get("why", "")),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "brief": self.brief,
            "price_move": self.price_move,
            "category": self.category,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "why": self.why,
        }

    @staticmethod
    def decide(brief: bool, price_move: bool) -> str:
        """Map the two decisions-API booleans to a rendering verdict.

        ``keep``     matters to the owner of the position, move or no move
        ``context``  explains the tape but says nothing about the thesis, so it
                     is demoted to a headline-only line instead of a paragraph
        ``drop``     neither; out of the paper, though the JSON keeps the record
        """
        if brief:
            return "keep"
        if price_move:
            return "context"
        return "drop"


@dataclass
class NewsEntry:
    """One piece of news attached to a holding.

    This is the unit the decisions API judges: a headline is either worth the
    brief, worth blaming for the day's move, both, or neither. The verdict
    lives here so the renderer never has to re-derive it.
    """

    id: str
    headline: str = ""
    summary: str = ""
    published: str = ""
    url: str = ""
    source: str = ""
    relevance: Relevance | None = None

    @classmethod
    def from_json(cls, record: Any, *, where: str) -> NewsEntry:
        if not isinstance(record, dict):
            raise SectionError(f"{where}: expected a JSON object")
        allowed = {"id", "headline", "summary", "published", "url", "source", "relevance"}
        _check_unknown(record, allowed, where)
        entry_id = record.get("id")
        if entry_id is not None and (not isinstance(entry_id, str) or not _ID_RE.match(entry_id)):
            raise SectionError(f"{where}: news id {entry_id!r} must match {_ID_RE.pattern}")
        for key in ("headline", "summary", "published", "url", "source"):
            if key in record and not isinstance(record[key], str):
                raise SectionError(f"{where}: news.{key} must be a string")
        headline = str(record.get("headline", "")).strip()
        summary = str(record.get("summary", "")).strip()
        if not headline and not summary:
            raise SectionError(f"{where}: a news entry needs a headline or a summary")
        relevance = record.get("relevance")
        return cls(
            id=str(entry_id or "") or slugify(headline[:60] or "news"),
            headline=headline,
            summary=summary,
            published=str(record.get("published", "")).strip(),
            url=str(record.get("url", "")).strip(),
            source=str(record.get("source", "")).strip(),
            relevance=Relevance.from_json(relevance, f"{where} relevance") if relevance is not None else None,
        )

    def to_json(self) -> dict[str, Any]:
        record: dict[str, Any] = {"id": self.id}
        for key, value in (
            ("headline", self.headline), ("summary", self.summary),
            ("published", self.published), ("url", self.url), ("source", self.source),
        ):
            if value:
                record[key] = value
        if self.relevance is not None:
            record["relevance"] = self.relevance.to_json()
        return record

    @property
    def dropped(self) -> bool:
        return self.relevance is not None and self.relevance.verdict == "drop"

    @property
    def body(self) -> str:
        """Printable text: the summary when present, else the headline."""
        return self.summary or self.headline


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """ASCII slug for auto ids; empty for anything untransliterated."""
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug[:48]


@dataclass
class Item:
    """One brief item = one JSON file."""

    id: str
    section: str
    label: str
    text: str = ""
    order: int = 100
    kind: str = "item"
    as_of: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    relevance: Relevance | None = None
    news: list[NewsEntry] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ parse
    @classmethod
    def from_json(cls, record: Any, *, section: str | None = None, where: str = "item") -> Item:
        if not isinstance(record, dict):
            raise SectionError(f"{where}: expected a JSON object, got {type(record).__name__}")
        section_name = record.get("section", section)
        if not isinstance(section_name, str) or section_name not in SECTIONS:
            raise SectionError(f"{where}: 'section' must be one of {SECTIONS}, got {section_name!r}")
        allowed = set(COMMON_FIELDS) | set(SECTION_FIELDS.get(section_name, frozenset()))
        _check_unknown(record, allowed, where)

        schema = record.get("schema", ITEM_SCHEMA)
        if schema != ITEM_SCHEMA:
            raise SectionError(f"{where}: schema must be {ITEM_SCHEMA!r}, got {schema!r}")

        item_id = _require_str(record, "id", where)
        if not _ID_RE.match(item_id):
            raise SectionError(f"{where}: id {item_id!r} must match {_ID_RE.pattern}")

        kind = str(record.get("kind", "item"))
        if kind not in KINDS:
            raise SectionError(f"{where}: kind must be one of {KINDS}, got {kind!r}")

        label = record.get("label")
        if label is not None and (not isinstance(label, str) or not label.strip()):
            raise SectionError(f"{where}: 'label' must be a non-empty string when present")
        text = record.get("text", "")
        if not isinstance(text, str):
            raise SectionError(f"{where}: 'text' must be a string")
        # A holding line can be built from structured fields alone (ticker,
        # price, news), so `text` stays optional there — but an item with
        # nothing at all is always a drafting mistake.
        has_structured = any(key not in COMMON_FIELDS for key in record)
        if not (label or text or has_structured):
            raise SectionError(f"{where}: needs label, text, or structured fields")

        order = record.get("order", 100)
        if not isinstance(order, int) or isinstance(order, bool):
            raise SectionError(f"{where}: 'order' must be an integer, got {order!r}")

        as_of = record.get("as_of")
        if as_of is not None and not isinstance(as_of, str):
            raise SectionError(f"{where}: 'as_of' must be a string")

        relevance = record.get("relevance")
        parsed_relevance = (
            Relevance.from_json(relevance, f"{where} relevance") if relevance is not None else None
        )

        news_records = record.get("news", [])
        if not isinstance(news_records, list):
            raise SectionError(f"{where}: 'news' must be a list")
        news = [
            NewsEntry.from_json(entry, where=f"{where} news[{index}]")
            for index, entry in enumerate(news_records)
        ]

        data = {key: value for key, value in record.items() if key not in COMMON_FIELDS}
        return cls(
            id=item_id,
            section=section_name,
            label=(label or "").strip(),
            text=text.strip(),
            order=int(order),
            kind=kind,
            as_of=(as_of or "").strip(),
            sources=_norm_sources(record.get("sources"), where),
            flags=_norm_str_list(record.get("flags"), where, "flags"),
            notes=_norm_str_list(record.get("notes"), where, "notes"),
            relevance=parsed_relevance,
            news=news,
            data=data,
        )

    # ------------------------------------------------------------------- emit
    def to_json(self) -> dict[str, Any]:
        record: dict[str, Any] = {"schema": ITEM_SCHEMA, "id": self.id, "section": self.section}
        record.update(self.data)
        record["kind"] = self.kind
        if self.label:
            record["label"] = self.label
        if self.text:
            record["text"] = self.text
        record["order"] = self.order
        if self.as_of:
            record["as_of"] = self.as_of
        if self.sources:
            record["sources"] = self.sources
        if self.flags:
            record["flags"] = self.flags
        if self.notes:
            record["notes"] = self.notes
        if self.relevance is not None:
            record["relevance"] = self.relevance.to_json()
        if self.news:
            record["news"] = [entry.to_json() for entry in self.news]
        return record

    def filename(self) -> str:
        return item_filename(self.order, self.id)

    @property
    def dropped(self) -> bool:
        """True when a decisions-API verdict removed this item from the paper."""
        return self.relevance is not None and self.relevance.verdict == "drop"

    # ---------------------------------------------------------------- helpers
    @property
    def number(self) -> int | None:
        """Explicit ETF/stock list number, when the item carries one."""
        value = self.data.get("number")
        return value if isinstance(value, int) and not isinstance(value, bool) else None


@dataclass
class Day:
    """A published brief day."""

    date: DayPath
    location: str = "Novi Iskar"
    timezone: str = "Europe/Sofia"
    started: str = ""
    finished: str = ""
    sections: tuple[str, ...] = SECTIONS
    source: str = "pi morning-brief"
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, record: Any, *, date: DayPath | None = None, where: str = "meta.json") -> Day:
        if not isinstance(record, dict):
            raise SectionError(f"{where}: expected a JSON object")
        allowed = {"schema", "date", "location", "timezone", "started", "finished", "sections", "source"}
        _check_unknown(record, allowed, where)
        schema = record.get("schema", DAY_SCHEMA)
        if schema != DAY_SCHEMA:
            raise SectionError(f"{where}: schema must be {DAY_SCHEMA!r}, got {schema!r}")
        from mb.paths import day_path as _day_path

        date_value = record.get("date")
        if date is not None:
            resolved = date
        elif isinstance(date_value, (str, DayPath)):
            resolved = _day_path(date_value)
        else:
            raise SectionError(f"{where}: 'date' is required")
        sections = record.get("sections", list(SECTIONS))
        if not isinstance(sections, list) or not all(entry in SECTIONS for entry in sections):
            raise SectionError(f"{where}: 'sections' must be a list from {SECTIONS}")
        for key in ("location", "timezone", "started", "finished", "source"):
            if key in record and not isinstance(record[key], str):
                raise SectionError(f"{where}: {key!r} must be a string")
        return cls(
            date=resolved,
            location=str(record.get("location", "Novi Iskar")),
            timezone=str(record.get("timezone", "Europe/Sofia")),
            started=str(record.get("started", "")),
            finished=str(record.get("finished", "")),
            sections=tuple(sections),  # type: ignore[arg-type]
            source=str(record.get("source", "pi morning-brief")),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": DAY_SCHEMA,
            "date": self.date.flat,
            "location": self.location,
            "timezone": self.timezone,
            "started": self.started,
            "finished": self.finished,
            "sections": list(self.sections),
            "source": self.source,
        }


# --------------------------------------------------------------------- loader


def load_item_bytes(raw: bytes | str, *, path: str, section_hint: str | None = None) -> Item:
    """Parse + validate one item file."""
    try:
        record = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SectionError(f"{path}: invalid JSON — {exc}") from exc
    section = section_hint
    if section is None:
        # .../<section>/NN-id.json -> the parent directory names the section.
        parts = path.replace("\\", "/").split("/")
        section = parts[-2] if len(parts) >= 2 else None
    return Item.from_json(record, section=section, where=path)


def load_meta_bytes(raw: bytes | str, *, path: str, date: DayPath | None = None) -> Day:
    try:
        record = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SectionError(f"{path}: invalid JSON — {exc}") from exc
    return Day.from_json(record, date=date, where=path)


def sort_items(items: list[Item]) -> list[Item]:
    """Stable publication order: order, then kind, then id."""
    kind_rank = {"context": 0, "item": 1, "flag": 2}
    return sorted(items, key=lambda item: (item.order, kind_rank[item.kind], item.id))


__all__ = [
    "DAY_SCHEMA",
    "ITEM_SCHEMA",
    "KINDS",
    "COMMON_FIELDS",
    "SECTION_FIELDS",
    "VERDICTS",
    "Day",
    "Item",
    "NewsEntry",
    "Relevance",
    "SectionError",
    "slugify",
    "item_filename",
    "load_item_bytes",
    "load_meta_bytes",
    "parse_item_filename",
    "sort_items",
]
