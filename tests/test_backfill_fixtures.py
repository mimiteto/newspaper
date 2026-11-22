"""Item records for a legacy-looking day, used by the backfill tests.

These are deliberately the constructs the real 2026-11-22 paper contains: a
plain lead paragraph, bold-labelled items with bare source URLs, an ETF whose
prose ends in a colon before its holdings, weights quoted at two different
precisions, and a trailing ``Flags:`` block. A fixture the parser cannot
round-trip would test nothing, so ``RoundTripTests`` asserts that first.
"""

from __future__ import annotations

from typing import Any

#: The old lanes wrote this by hand: no item counts, no generated footer, and a
#: "Created by" line the pipeline does not reproduce.
LEGACY_INDEX = """# Morning Brief — 2026-11-22

**Started:** 2026-11-22T09:18:37+02:00
**Finished:** 2026-11-22T09:43:26+02:00
**Created by:** `publish-weather`

## Sections

- [Weather](./weather.md)
- [Holdings](./stocks.md)
- [Bulgaria](./bulgarian-finances.md)
"""


def legacy_records() -> dict[str, list[dict[str, Any]]]:
    """section -> item records, in the order the old paper printed them."""
    return {
        "weather": [
            {
                "id": "generation",
                "kind": "context",
                "text": "Generated 2026-11-22 09:19 Europe/Sofia; the forecast is as of 09:15 local.",
            },
            {
                "id": "temperature",
                "label": "Temperature today",
                "text": "High 12.0 °C / low 3.0 °C, with 5.3 °C at 09:15.",
                "sources": ["https://api.open-meteo.com/v1/forecast?daily=temperature_2m_max"],
            },
            {"id": "conditions", "label": "Conditions", "text": "Mainly clear, 77% humidity."},
            {"id": "flag-rain", "kind": "flag", "text": "Evening rain is a single-provider signal."},
        ],
        "stocks": [
            {
                "id": "snapshot",
                "kind": "context",
                "text": "**Snapshot context:** every price below is Friday's close; 22 Nov is a Sunday.",
            },
            {
                "id": "sapse",
                "label": "SAPSE",
                "text": "€183.68 on Xetra (SAP.DE), −1.79% Friday and −13.95% across the week.",
                "sources": ["https://finance.yahoo.com/quote/SAP.DE/"],
            },
            {
                "id": "sxr8",
                "label": "SXR8 — iShares Core S&P 500 UCITS ETF Acc",
                "text": "€694.06, −25.22 (−3.51%). Top five weights per stockanalysis.com, as of 19 Nov 2026:",
                "holdings": [
                    {"rank": 1, "name": "Apple", "weight_pct": 8.14, "as_of": "19 Nov 2026"},
                    {"rank": 2, "name": "Novartis", "weight_pct": 2.0, "weight_display": "2.00%"},
                ],
                "sources": ["https://stockanalysis.com/etf/sxr8/"],
            },
            {
                "id": "vhyl",
                "label": "VHYL",
                "text": "67.155 GBP on the London line, −1.21%. Top holdings per etftrace:",
                "holdings": [
                    {"rank": 1, "name": "Samsung Electronics", "weight_pct": 2.4, "weight_display": "2.4%"},
                    {"rank": 2, "name": "ASML", "weight_pct": 2.0, "weight_display": "2.0%"},
                ],
            },
            {"id": "flag-timing", "kind": "flag", "text": "Friday 20 Nov closes, published Sunday 22 Nov."},
        ],
        "bulgarian-finances": [
            {"id": "sources", "kind": "context", "text": "Sources: БТА, БНР, Investor.bg, dv.parliament.bg."},
            {
                "id": "mrz",
                "label": "МРЗ 660 евро от 1 януари 2027 г.",
                "text": "The projected minimum wage is €660 a month from 1 Jan 2027.",
                "sources": ["https://www.mlsp.government.bg/ministr-efremova"],
            },
            {"id": "flag-window", "kind": "flag", "text": "Window honesty: the budget was approved 16 Nov."},
        ],
    }
