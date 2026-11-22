"""Shared fixtures for the mb test suite."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

STOCK_DRAFT: dict = {
    "section": "stocks",
    "items": [
        {
            "id": "snapshot",
            "kind": "context",
            "text": "Market snapshot: S&P 500 6,910.39, -3.70% on the day.",
        },
        {
            "id": "sapse",
            "ticker": "SAPSE",
            "name": "SAP SE",
            "listing": "Xetra (SAP.DE)",
            "currency": "EUR",
            "price": 183.68,
            "change_pct_1d": -1.79,
            "change_pct_5d": -13.95,
            "as_of": "20 Nov 17:36 CET",
            "sources": ["https://finance.yahoo.com/quote/SAP.DE/"],
            "news": [
                {
                    "id": "ms-conference",
                    "headline": "SAP says it remains on track with its 2026 plan",
                    "summary": "CFO repeated the 2026 outlook at the Morgan Stanley TMT conference.",
                    "published": "2026-11-19",
                    "url": "https://example.com/transcript",
                    "source": "Investing.com",
                },
                {
                    "id": "old-buyback",
                    "headline": "SAP closed an October buyback tranche",
                    "summary": "Back in October.",
                    "published": "2026-10-30",
                },
                {
                    "id": "sec-probe",
                    "headline": "AI-capex complex sold off on an SEC probe report",
                    "summary": "Sector-wide.",
                    "published": "2026-11-20",
                },
            ],
        },
        {
            "id": "sxr8",
            "ticker": "SXR8",
            "name": "iShares Core S&P 500 UCITS ETF Acc",
            "listing": "Xetra",
            "currency": "EUR",
            "price": 694.06,
            "change_abs": -25.22,
            "change_pct_1d": -3.51,
            "text": "Tracked an S&P 500 that fell 3.70%.",
            "holdings": [
                {"rank": 1, "name": "Apple", "weight_pct": 8.14, "as_of": "19 Nov 2026"},
                {"rank": 2, "name": "Microsoft", "weight_pct": 5.96, "as_of": "19 Nov 2026"},
            ],
        },
        {"id": "timing", "kind": "flag", "text": "Friday 20 Nov closes, published Sunday."},
    ],
}

VERDICTS: dict = {
    "schema": "mb/verdicts@1",
    "decided_by": "llama.cpp/test-model",
    "decided_at": "2026-11-22T10:00:00+02:00",
    "verdicts": [
        {"section": "stocks", "id": "sapse", "news_id": "ms-conference",
         "brief": True, "price_move": True, "category": "guidance", "confidence": 0.81},
        {"section": "stocks", "id": "sapse", "news_id": "old-buyback",
         "brief": False, "price_move": False, "category": "stale", "confidence": 0.9},
        {"section": "stocks", "id": "sapse", "news_id": "sec-probe",
         "brief": False, "price_move": True, "category": "macro", "confidence": 0.6},
    ],
}


class RepoTestCase(unittest.TestCase):
    """A throwaway repo that looks like the real one (plus the legacy tree)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mb-test-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        (self.repo / "_config.yml").write_text("theme: minima\n", encoding="utf-8")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.legacy_day = "2026-11-17"
        legacy = self.repo / "2026/11/17"
        legacy.mkdir(parents=True)
        (legacy / "index.md").write_text("# Morning Brief — 2026-11-17\n", encoding="utf-8")
        (legacy / "weather.md").write_text("# Weather\n", encoding="utf-8")

    def write_draft(self, payload: dict, name: str = "draft.json") -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path
