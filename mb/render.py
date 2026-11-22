"""JSON -> Markdown. The only place brief prose is formatted.

Everything here is deterministic: the same JSON renders to the same bytes on the
runner and on a laptop, which is what lets CI commit generated files and
``mb render --check`` prove nobody hand-edited them.

House style, carried over unchanged from the hand-written era:
``**Label.** prose`` one-liners, source links on their own line directly below,
a trailing ``Flags:`` block, no prose between items.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

from mb.model import Day, Item, NewsEntry
from mb.paths import MONTHS, DayPath

MINUS = "\u2212"  # typographic minus, as the brief has always used
ENDASH = "\u2013"  # ranges (21–22 Nov). MINUS is for numbers; ENDASH is not
CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "BGN": "лв"}

SECTION_TITLES = {
    "weather": "Weather",
    "stocks": "Holdings",
    "bulgarian-finances": "Bulgaria",
}


def _num(value: object) -> float | None:
    """Coerce a JSON number, or ``None`` for anything else.

    Section-specific fields are not type-checked by the model layer, and a
    price quoted as ``"183.68"`` or ``"n/a"`` must degrade to "no number"
    rather than kill the whole render halfway through CI.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


# --------------------------------------------------------------- formatters
def fmt_pct(value: object) -> str:
    """``-1.79`` -> ``−1.79%``. Anything non-numeric renders as nothing."""
    number = _num(value)
    if number is None:
        return ""
    text = f"{abs(number):.2f}%"
    if number > 0:
        return f"+{text}"
    if number < 0:
        return f"{MINUS}{text}"
    return text


def fmt_amount(value: object, currency: str = "") -> str:
    """``183.68, EUR`` -> ``€183.68``. Keeps a third decimal when the source has one."""
    number = _num(value)
    if number is None:
        return ""
    decimals = 2 if round(number, 2) == number else 3
    body = f"{abs(number):,.{decimals}f}"
    symbol = CURRENCY_SYMBOLS.get((currency or "").upper(), "")
    signed = f"{MINUS}{body}" if number < 0 else body
    return f"{symbol}{signed}" if symbol else body


def _sources_block(item: Item) -> list[str]:
    lines: list[str] = []
    for source in item.sources:
        title = source.get("title", "")
        url = source["url"]
        lines.append(f"[{title}]({url})" if title else url)
    return lines


def _news_tag(entry: NewsEntry) -> str:
    relevance = entry.relevance
    return relevance.category if relevance is not None else "news"


def _news_bullet(entry: NewsEntry, *, full: bool = True) -> str:
    """One classified news line.

    ``full`` prints the summary the decisions API kept; ``context`` (a move
    driver that says nothing about the thesis) stays a headline-only line.
    """
    tag = _news_tag(entry)
    body = entry.body if full else (entry.headline or entry.body)
    link = ""
    if entry.url:
        label = (entry.source or "source") if entry.summary else entry.headline or entry.source or "source"
        link = f" — [{label}]({entry.url})"
    return f"- **[{tag}]** {body}{link}"


def _price_line(item: Item, *, include_as_of: bool = True) -> str:
    """``€183.68 on Xetra (SAP.DE), −1.79% 1d, −13.95% 5d`` from structured fields."""
    data = item.data
    pieces: list[str] = []
    amount = fmt_amount(data.get("price"), str(data.get("currency", "")))
    if amount:
        # The absolute change is quoted in the same currency as the price, so
        # it carries no symbol of its own: "€694.06, −25.22 (−3.51%)".
        change_abs = _num(data.get("change_abs"))
        if change_abs is not None:
            amount = f"{amount}, {fmt_pct(change_abs).replace('%', '')}"
        pieces.append(amount)
    listing = str(data.get("listing") or "").strip()
    if listing and amount:
        pieces[-1] = f"{pieces[-1]} on {listing}"
    elif listing:
        pieces.append(listing)
    for key, label in (("change_pct_1d", "1d"), ("change_pct_5d", "5d"), ("change_pct_1m", "1m")):
        text = fmt_pct(data.get(key))
        if text:
            pieces.append(f"{text} {label}")
    if item.as_of and include_as_of:
        pieces.append(f"as of {item.as_of}")
    return ", ".join(pieces)


def _item_label(item: Item) -> str:
    """Bold lead-in: the raw style was bare tickers for stocks and a
    ``TICKER — Fund name`` label for ETFs (recognisable by top-5 holdings)."""
    if item.label:
        return item.label
    ticker = str(item.data.get("ticker", "")).strip()
    name = str(item.data.get("name", "")).strip()
    if ticker and name and item.data.get("holdings"):
        return f"{ticker.upper()} — {name}"
    return ticker or name or item.id


def _holdings_lines(item: Item) -> list[str]:
    holdings = item.data.get("holdings") or []
    if not isinstance(holdings, list):
        return []
    lines: list[str] = []
    for index, entry in enumerate(holdings, start=1):
        if isinstance(entry, str):
            lines.append(entry)
            continue
        rank = entry.get("rank", index)
        name = str(entry.get("name", "")).strip()
        weight = _num(entry.get("weight_pct"))
        as_of = str(entry.get("as_of", "")).strip()
        tail = ""
        if weight is not None:
            tail = f"{weight:.2f}%"
        if as_of:
            tail = f"{tail} as of {as_of}" if tail else f"as of {as_of}"
        lines.append(f"**{rank}.** {name}" + (f" — {tail}" if tail else ""))
    return lines


def _has_market_data(item: Item) -> bool:
    return any(
        item.data.get(key) is not None
        for key in ("price", "change_abs", "change_pct_1d", "change_pct_5d", "change_pct_1m")
    )


def _head(label: str) -> str:
    """``**Label.**`` — and no doubled period when the label already ends in one."""
    if not label:
        return ""
    return f"**{label}**" if label.endswith((".", "!", "?", ":")) else f"**{label}.**"


def render_item(item: Item) -> list[str]:
    """One rendered item as Markdown lines (paragraph + optional bullets/links)."""
    label = _item_label(item)
    market = _has_market_data(item)
    lead = _price_line(item, include_as_of=market)
    body = item.text
    # A holding stamps its as-of inside the market clause; a plain item puts it
    # at the end of its prose, where it reads as a caveat and not a headline.
    if item.as_of and not market:
        # Drop the prose's own full stop so the stamp does not become "°C. (as of …)".
        body = f"{body.rstrip('.')} (as of {item.as_of})" if body else f"as of {item.as_of}"

    chunks = [chunk for chunk in (lead, body) if chunk]
    if not chunks:
        return []
    sentence = ". ".join(chunk.rstrip(".") for chunk in chunks) + "."
    head = _head(label)
    paragraph = f"{head} {sentence}" if head else sentence

    lines = [paragraph]

    kept = [entry for entry in item.news if not entry.dropped and entry.relevance is not None and entry.relevance.verdict == "keep"]
    demoted = [entry for entry in item.news if entry.relevance is not None and entry.relevance.verdict == "context"]
    for entry in kept:
        lines.append(_news_bullet(entry, full=True))
    for entry in demoted:
        lines.append(_news_bullet(entry, full=False))

    lines.extend(_holdings_lines(item))
    lines.extend(_sources_block(item))
    for note in item.notes:
        lines.append(f"> {note}")
    return lines


def section_title(day: Day, section: str) -> str:
    pretty = day.date.pretty
    if section == "weather":
        return f"# Weather — {day.location}, {pretty}"
    if section == "stocks":
        return f"# Holdings — {pretty}"
    return f"# Bulgaria — economic & labour-law news, last 2 days ({_window(day.date)})"


def _window(date: DayPath, days: int = 2) -> str:
    """``21–22 Nov 2026`` for a 2-day window ending on the brief date."""
    end = dt.date(date.year, date.month, date.day)
    start = end - dt.timedelta(days=days - 1)
    if start.month == end.month and start.year == end.year:
        return f"{start.day}{ENDASH}{end.day} {MONTHS[end.month - 1]} {end.year}"
    if start.year == end.year:
        return f"{start.day} {MONTHS[start.month - 1]}{ENDASH}{end.day} {MONTHS[end.month - 1]} {end.year}"
    return f"{start.day} {MONTHS[start.month - 1]} {start.year}{ENDASH}{end.day} {MONTHS[end.month - 1]} {end.year}"


def _relevance_footer(items: Iterable[Item]) -> list[str]:
    """Say out loud what the decisions API filtered — never hide it in a diff."""
    total = dropped = 0
    models: set[str] = set()
    for item in items:
        entries = list(item.news)
        if item.relevance is not None:
            entries.append(NewsEntry(id=item.id, headline=item.label or item.id, relevance=item.relevance))
        for entry in entries:
            if entry.relevance is None:
                continue
            total += 1
            if entry.relevance.decided_by:
                models.add(entry.relevance.decided_by)
            if entry.dropped:
                dropped += 1
    if not total:
        return []
    model = f", model: `{', '.join(sorted(models))}`" if models else ""
    return [f"News triaged by the decisions API: {total - dropped} of {total} kept{model}."]


def render_section(day: Day, section: str, items: list[Item]) -> str:
    """Full Markdown body of one section file."""
    visible = [item for item in items if not item.dropped]
    contexts = [item for item in visible if item.kind == "context"]
    body_items = [item for item in visible if item.kind == "item"]
    flags = [item for item in visible if item.kind == "flag"]

    blocks: list[str] = [section_title(day, section)]
    for item in contexts:
        blocks.append(item.text or item.label)
    for item in body_items:
        blocks.append("\n".join(render_item(item)))

    flag_lines = [item.text or item.label for item in flags if (item.text or item.label)]
    inline_flags = [flag for item in visible for flag in item.flags]
    collected = flag_lines + inline_flags
    if collected:
        blocks.append("Flags:\n" + "\n".join(f"- {flag}" for flag in collected))

    footer = _relevance_footer(items)
    if footer:
        blocks.append("\n".join(footer))

    return "\n\n".join(block for block in blocks if block.strip()) + "\n"


def render_day_index(day: Day, counts: dict[str, int], *, generated: bool = True) -> str:
    """The per-day ``index.md`` the homepage links to.

    This used to be a race: three lanes each tried to create it and a slot-claim
    script arbitrated. The pipeline owns it now, so the race is gone.
    """
    lines = [f"# Morning Brief — {day.date.flat}"]
    # Only print a stamp that exists: a day still mid-publish has a start and
    # no finish, and "Finished: -" would be a lie in the paper.
    stamps = [label for label, value in (("Started", day.started), ("Finished", day.finished)) if value]
    if stamps:
        lines.append("")
        lines.extend(f"**{label}:** {value}" for label, value in (("Started", day.started), ("Finished", day.finished)) if value)
    lines += ["", "## Sections", ""]
    for section in day.sections:
        name = SECTION_TITLES.get(section, section)
        suffix = f" ({counts.get(section, 0)} items)" if counts.get(section) else " (not published)"
        lines.append(f"- [{name}](./{section}.md){suffix}")
    if generated:
        lines += ["", "_Generated by `mb render` from the JSON in this directory._"]
    return "\n".join(lines) + "\n"


def render_root_index(entries: list[tuple[DayPath, bool]]) -> str:
    """Homepage listing every published brief, newest first.

    ``entries`` is ``[(day, managed), ...]``; legacy (Markdown-only) days are
    still listed so the site keeps every link it has ever had.
    """
    blocks = [
        "---",
        "layout: page",
        "title: Morning Brief",
        "---",
        "",
        "Published briefs, newest first.",
    ]
    for date, _managed in entries:
        blocks += [
            "",
            f"## [{date.flat}]({date.nested}/index.md)",
            "",
            " · ".join(
                f"[{SECTION_TITLES[section]}]({date.nested}/{section}.md)" for section in ("weather", "stocks", "bulgarian-finances")
            ),
        ]
    blocks += ["", "---", "", "*Generated by `mb render`; do not edit by hand.*"]
    return "\n".join(blocks) + "\n"
