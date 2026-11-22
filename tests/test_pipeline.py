"""End-to-end: draft JSON -> per-item files -> verdicts -> Markdown.

These are the guarantees the pipeline is built on:

* one draft becomes one file per item, under the nested day path
* a re-publish converges the section directory (no stale item renders twice)
* the decisions-API verdict decides print / demote / omit
* render is byte-stable, so CI can commit it and `--check` can guard it
* legacy Markdown-only days are never rewritten
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from conftest_fixtures import REPO_ROOT, STOCK_DRAFT, VERDICTS, RepoTestCase

from mb.cli import main
from mb.paths import day_path
from mb.render import render_section
from mb.store import load_day, load_section_items

DATE = "2026-11-22"


def run_mb(*argv: str | Path) -> int:
    """Call the CLI in-process; paths are accepted for convenience."""
    return main([str(entry) for entry in argv])


class IngestTests(RepoTestCase):
    def test_one_file_per_item_under_nested_path(self):
        draft = self.write_draft(STOCK_DRAFT)
        self.assertEqual(run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", str(draft)), 0)
        directory = self.repo / "2026/11/22/stocks"
        self.assertTrue(directory.is_dir(), "items must live under YYYY/MM/DD/<section>/")
        self.assertEqual(
            sorted(path.name for path in directory.glob("*.json")),
            ["10-snapshot.json", "20-sapse.json", "30-sxr8.json", "40-timing.json"],
        )
        self.assertTrue((self.repo / "2026/11/22/meta.json").is_file())

    def test_flat_date_never_creates_a_flat_directory(self):
        """The old failure mode: a stray top-level 2026-11-22/ nothing linked to."""
        draft = self.write_draft(STOCK_DRAFT)
        run_mb("--repo", str(self.repo), "ingest", "--date", "2026/11/22", "--file", str(draft))
        self.assertFalse((self.repo / "2026-11-22").exists())

    def test_republish_prunes_items_the_new_draft_does_not_have(self):
        draft = self.write_draft(STOCK_DRAFT)
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", str(draft))
        trimmed = {**STOCK_DRAFT, "items": STOCK_DRAFT["items"][:2]}
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(trimmed, "trim.json"))
        names = sorted(path.name for path in (self.repo / "2026/11/22/stocks").glob("*.json"))
        self.assertEqual(names, ["10-snapshot.json", "20-sapse.json"])

    def test_merge_keeps_existing_items(self):
        draft = self.write_draft(STOCK_DRAFT)
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", str(draft))
        single = {"section": "stocks", "items": [{"id": "ko", "ticker": "KO", "price": 96.99}]}
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(single, "one.json"), "--merge")
        names = sorted(path.name for path in (self.repo / "2026/11/22/stocks").glob("*.json"))
        self.assertIn("50-ko.json", names)
        self.assertIn("20-sapse.json", names)

    def test_duplicate_ids_are_rejected(self):
        duplicated = {**STOCK_DRAFT, "items": [STOCK_DRAFT["items"][0], STOCK_DRAFT["items"][0]]}
        self.assertEqual(
            run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(duplicated, "dup.json")),
            1,
        )

    def test_bad_item_exits_nonzero_and_names_the_item(self):
        broken = {"section": "stocks", "items": [{"id": "ok", "text": "fine"}, {"id": "BAD ID", "text": "x"}]}
        self.assertEqual(
            run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(broken, "bad.json")),
            1,
        )

    def test_meta_from_draft_does_not_overwrite_existing_stamps(self):
        draft = {**STOCK_DRAFT, "meta": {"started": "2026-11-22T06:00:00+02:00", "location": "Novi Iskar"}}
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(draft))
        second = {**STOCK_DRAFT, "meta": {"started": "2026-11-22T09:00:00+02:00", "location": "Sofia"}}
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(second, "two.json"))
        day = load_day(self.repo, day_path(DATE))
        self.assertEqual(day.started, "2026-11-22T06:00:00+02:00", "first writer wins, lanes must not stomp")
        self.assertEqual(day.location, "Novi Iskar")


class DecideTests(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.draft = self.write_draft(STOCK_DRAFT)
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", str(self.draft))

    def test_verdicts_split_into_keep_context_and_drop(self):
        summary = run_mb(
            "--repo", str(self.repo), "decide", "--date", DATE,
            "--verdicts", self.write_draft(VERDICTS, "v.json"),
        )
        self.assertEqual(summary, 0)
        items = load_section_items(self.repo, day_path(DATE), "stocks")
        sapse = next(item for item in items if item.id == "sapse")
        judged = [(entry.id, entry.relevance) for entry in sapse.news]
        self.assertTrue(all(relevance is not None for _, relevance in judged), "every news entry got a verdict")
        verdicts = {entry_id: (relevance.verdict if relevance else "<none>") for entry_id, relevance in judged}
        self.assertEqual(
            verdicts,
            {"ms-conference": "keep", "old-buyback": "drop", "sec-probe": "context"},
        )

    def test_dry_run_changes_nothing(self):
        before = (self.repo / "2026/11/22/stocks/20-sapse.json").read_text(encoding="utf-8")
        run_mb("--repo", str(self.repo), "decide", "--date", DATE,
               "--verdicts", self.write_draft(VERDICTS, "v.json"), "--dry-run")
        self.assertEqual((self.repo / "2026/11/22/stocks/20-sapse.json").read_text(encoding="utf-8"), before)

    def test_verdict_for_unknown_item_is_an_error(self):
        bogus = {"schema": "mb/verdicts@1", "verdicts": [{"section": "stocks", "id": "nope", "brief": True, "price_move": False}]}
        self.assertEqual(
            run_mb("--repo", str(self.repo), "decide", "--date", DATE, "--verdicts", self.write_draft(bogus, "b.json")),
            1,
        )

    def test_a_lane_only_applies_its_own_sections_verdicts(self):
        """Three lanes race on one day: a shared verdict file must not reach
        into another lane's sections, or its success depends on who pushed first."""
        weather = {
            "section": "weather",
            "items": [{"id": "temperature", "label": "Temperature today", "text": "High 12 °C."}],
        }
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(weather, "w.json"))
        mixed = {
            "schema": "mb/verdicts@1",
            "verdicts": [
                {"section": "stocks", "id": "sapse", "news_id": "ms-conference", "brief": True, "price_move": False},
                {"section": "weather", "id": "temperature", "brief": True, "price_move": False},
            ],
        }
        self.assertEqual(
            run_mb("--repo", str(self.repo), "decide", "--date", DATE,
                   "--verdicts", self.write_draft(mixed, "mixed.json"), "--section", "stocks"),
            0,
        )
        weather_item = load_section_items(self.repo, day_path(DATE), "weather")[0]
        self.assertIsNone(weather_item.relevance, "the weather lane owns the weather verdicts")
        # Same file, no scope: both sections are applied.
        self.assertEqual(
            run_mb("--repo", str(self.repo), "decide", "--date", DATE,
                   "--verdicts", self.write_draft(mixed, "mixed.json")),
            0,
        )
        weather_item = load_section_items(self.repo, day_path(DATE), "weather")[0]
        self.assertIsNotNone(weather_item.relevance)

    def test_verdicts_survive_a_republish_of_the_same_draft(self):
        """Re-ingesting after judging must not silently un-judge the items."""
        run_mb("--repo", str(self.repo), "decide", "--date", DATE, "--verdicts", self.write_draft(VERDICTS, "v.json"))
        self.assertEqual(run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", str(self.draft)), 0)
        item = next(entry for entry in load_section_items(self.repo, day_path(DATE), "stocks") if entry.id == "sapse")
        judged = next(entry for entry in item.news if entry.id == "old-buyback")
        self.assertIsNotNone(judged.relevance)
        self.assertEqual(judged.relevance.verdict if judged.relevance else None, "drop")


class RenderTests(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.date = day_path(DATE)
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(STOCK_DRAFT))
        run_mb("--repo", str(self.repo), "decide", "--date", DATE, "--verdicts", self.write_draft(VERDICTS, "v.json"))
        self.assertEqual(run_mb("--repo", str(self.repo), "render", "--date", DATE, "--write"), 0)

    def _section(self, name: str) -> str:
        return (self.repo / "2026/11/22" / f"{name}.md").read_text(encoding="utf-8")

    def test_section_shape_follows_house_style(self):
        body = self._section("stocks")
        self.assertTrue(body.startswith("# Holdings — 22 Nov 2026\n"), body.splitlines()[0])
        self.assertIn("**SAPSE.** €183.68 on Xetra (SAP.DE), −1.79% 1d, −13.95% 5d", body)
        self.assertIn("**SXR8 — iShares Core S&P 500 UCITS ETF Acc.** €694.06, −25.22", body)
        self.assertIn("**1.** Apple — 8.14% as of 19 Nov 2026", body)
        self.assertIn("Flags:\n- Friday 20 Nov closes, published Sunday.", body)

    def test_context_item_is_the_lead_paragraph(self):
        body = self._section("stocks").splitlines()
        self.assertEqual(body[2], "Market snapshot: S&P 500 6,910.39, -3.70% on the day.")

    def test_verdict_decides_what_is_printed(self):
        body = self._section("stocks")
        self.assertIn("**[guidance]** CFO repeated the 2026 outlook", body)      # keep -> full summary
        self.assertIn("**[macro]** AI-capex complex sold off on an SEC probe report", body)  # context -> headline only
        self.assertNotIn("Sector-wide.", body)                                    # context body suppressed
        self.assertNotIn("October buyback", body)                                 # drop -> omitted
        self.assertIn("News triaged by the decisions API: 2 of 3 kept", body)     # and it says so

    def test_render_is_byte_stable(self):
        before = {path: path.read_text(encoding="utf-8") for path in (self.repo / "2026/11/22").glob("*.md")}
        self.assertEqual(run_mb("--repo", str(self.repo), "render", "--write"), 0)
        after = {path: path.read_text(encoding="utf-8") for path in (self.repo / "2026/11/22").glob("*.md")}
        self.assertEqual(before, after)

    def test_check_passes_after_write_and_fails_after_tampering(self):
        self.assertEqual(run_mb("--repo", str(self.repo), "render", "--check"), 0)
        path = self.repo / "2026/11/22/stocks.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
        self.assertEqual(run_mb("--repo", str(self.repo), "render", "--check"), 1)

    def test_legacy_day_is_never_rewritten(self):
        legacy = self.repo / "2026/11/17/weather.md"
        before = legacy.read_text(encoding="utf-8")
        run_mb("--repo", str(self.repo), "render", "--write")
        self.assertEqual(legacy.read_text(encoding="utf-8"), before, "pre-JSON days are not the pipeline's to edit")

    def test_homepage_lists_managed_and_legacy_days(self):
        root = (self.repo / "index.md").read_text(encoding="utf-8")
        self.assertIn("[2026-11-22](2026/11/22/index.md)", root)
        self.assertIn("[2026-11-17](2026/11/17/index.md)", root)
        self.assertIn("Generated by `mb render`", root)

    def test_day_index_reports_item_counts(self):
        body = (self.repo / "2026/11/22/index.md").read_text(encoding="utf-8")
        self.assertIn("[Holdings](./stocks.md) (4 items)", body)
        self.assertIn("[Weather](./weather.md) (not published)", body)

    def test_dropped_item_disappears_but_its_json_remains(self):
        path = self.repo / "2026/11/22/stocks/20-sapse.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["relevance"] = {"brief": False, "price_move": False, "verdict": "drop", "category": "noise"}
        path.write_text(json.dumps(record), encoding="utf-8")
        run_mb("--repo", str(self.repo), "render", "--date", DATE, "--write")
        self.assertNotIn("**SAPSE.**", self._section("stocks"))
        self.assertTrue(path.is_file(), "the paper hides it, the record stays auditable")

    def test_render_section_handles_an_empty_day(self):
        day = load_day(self.repo, self.date)
        body = render_section(day, "weather", [])
        self.assertEqual(body, "# Weather — Novi Iskar, 22 Nov 2026\n")


class MetaStampTests(RepoTestCase):
    """meta.json is written by three lanes, so filling it in must be careful.

    The bug this pins down: a lane's `--started` flag was overwritten by the
    empty `started` of the draft's own meta block, so the day published with no
    start stamp at all. `date` is guarded too — a stamp merge that could write
    a string over the day identity would corrupt the record.
    """

    def test_cli_flags_outrank_an_empty_draft_meta(self):
        from mb.cli import _ensure_day
        from mb.model import Day

        draft_meta = Day(date=day_path(DATE)).to_json()  # a draft with no meta block
        day = _ensure_day(self.repo, day_path(DATE), started="2026-11-22T06:00:00+02:00", meta=draft_meta)
        self.assertEqual(day.started, "2026-11-22T06:00:00+02:00")
        self.assertEqual(load_day(self.repo, day_path(DATE)).started, "2026-11-22T06:00:00+02:00")

    def test_stamp_merge_never_rewrites_the_day_identity(self):
        from mb.cli import _ensure_day

        _ensure_day(self.repo, day_path(DATE), meta={"date": "1999-01-01", "sections": ["weather"], "schema": "evil"})
        stored = json.loads((self.repo / "2026/11/22/meta.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["date"], DATE)
        self.assertEqual(stored["sections"], ["weather", "stocks", "bulgarian-finances"])
        self.assertEqual(stored["schema"], "mb/day@1")

    def test_first_non_empty_wins_unless_forced(self):
        from mb.cli import _ensure_day

        _ensure_day(self.repo, day_path(DATE), started="2026-11-22T06:00:00+02:00")
        _ensure_day(self.repo, day_path(DATE), started="2026-11-22T09:00:00+02:00")
        self.assertEqual(load_day(self.repo, day_path(DATE)).started, "2026-11-22T06:00:00+02:00")
        _ensure_day(self.repo, day_path(DATE), started="2026-11-22T09:00:00+02:00", force_meta=True)
        self.assertEqual(load_day(self.repo, day_path(DATE)).started, "2026-11-22T09:00:00+02:00")


class ProseStyleTests(RepoTestCase):
    """Small typography regressions that make the paper look machine-made."""

    def _render(self, item: dict) -> str:
        from mb.cli import _ensure_day
        from mb.ingest import ingest
        from mb.model import Item

        _ensure_day(self.repo, day_path(DATE), location="Novi Iskar")
        day = load_day(self.repo, day_path(DATE))
        parsed = Item.from_json({**item, "section": item.get("section", "weather")})
        ingest(self.repo, day.date, [parsed])
        return render_section(day, item.get("section", "weather"), [parsed])

    def test_as_of_is_a_prose_suffix_when_there_is_no_market_data(self):
        body = self._render({"id": "temperature", "label": "Temperature today", "text": "High 12.0 °C.", "as_of": "09:15 local"})
        self.assertIn("**Temperature today.** High 12.0 °C (as of 09:15 local).", body)
        self.assertNotIn(".** as of", body, "an as-of must not become the headline")

    def test_market_items_keep_their_as_of_in_the_priced_clause(self):
        body = self._render({"id": "aapl", "section": "stocks", "ticker": "AAPL", "price": 342.56, "currency": "USD", "as_of": "16:00 ET"})
        self.assertIn("**AAPL.** $342.56, as of 16:00 ET.", body)

    def test_label_ending_in_a_period_does_not_double_it(self):
        body = self._render({"id": "mrz", "label": "МРЗ 660 евро от 1 януари 2027 г.", "text": "Прието."})
        self.assertIn("**МРЗ 660 евро от 1 януари 2027 г.** Прието.", body)
        self.assertNotIn("..", body)

    def test_date_range_uses_an_en_dash(self):
        from mb.cli import _ensure_day
        from mb.render import section_title

        # A window crossing a month boundary proves the range is formatted, not
        # just the day string echoed back.
        date = day_path("2026-11-01")
        _ensure_day(self.repo, date)
        title = section_title(load_day(self.repo, date), "bulgarian-finances")
        self.assertIn("(31 Oct–1 Nov 2026)", title)

    def test_same_month_window_is_compact(self):
        from mb.cli import _ensure_day
        from mb.render import section_title

        _ensure_day(self.repo, day_path(DATE))
        title = section_title(load_day(self.repo, day_path(DATE)), "bulgarian-finances")
        self.assertIn("(21–22 Nov 2026)", title)


class IngestFailureTests(RepoTestCase):
    """What a failed ingest must leave behind.

    `ingest` prunes a section directory, so a partial failure is the one way the
    pipeline could damage a day rather than reject a draft.
    """

    def test_a_bad_id_in_a_later_section_writes_nothing_at_all(self):
        from mb.ingest import ingest
        from mb.model import Item, SectionError

        items = [
            Item.from_json({"id": "temperature", "section": "weather", "text": "Mild."}),
            Item.from_json({"id": "sapse", "section": "stocks", "ticker": "SAP.DE"}),
            Item.from_json({"id": "sapse", "section": "stocks", "ticker": "SAP"}),
        ]
        with self.assertRaisesRegex(SectionError, "duplicate item ids"):
            ingest(self.repo, day_path(DATE), items)
        self.assertFalse((self.repo / "2026/11/22/weather").exists(), "the good section must not be half-written")
        self.assertFalse((self.repo / "2026/11/22/stocks").exists())

    def test_corrupt_stored_json_is_not_mistaken_for_no_verdicts(self):
        """Silence here would un-judge the day and print every news line."""
        from mb.ingest import inherit_relevance
        from mb.model import Item, SectionError

        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(STOCK_DRAFT))
        corrupt = sorted((self.repo / "2026/11/22/stocks").glob("*.json"))[0]
        corrupt.write_text("{ this is not json", encoding="utf-8")

        fresh = [Item.from_json({"id": "sapse", "section": "stocks", "ticker": "SAP.DE", "price": 1.0})]
        with self.assertRaises(SectionError):
            inherit_relevance(self.repo, day_path(DATE), fresh)

    def test_a_section_with_nothing_stored_yet_inherits_quietly(self):
        from mb.ingest import inherit_relevance
        from mb.model import Item

        fresh = [Item.from_json({"id": "mrz", "section": "bulgarian-finances", "label": "МРЗ", "text": "x"})]
        self.assertEqual(inherit_relevance(self.repo, day_path(DATE), fresh), 0)


class AmbiguousVerdictTests(RepoTestCase):
    """`ambiguous` is the decisions API saying "this one was a coin flip".

    It used to be dropped on apply, which made a guess indistinguishable from a
    confident call — in the JSON, in `verify`, and in the paper.
    """

    def _verify_output(self) -> str:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            run_mb("--repo", str(self.repo), "verify", "--date", DATE)
        return buffer.getvalue()

    def _verdicts(self, *rows: dict) -> Path:
        payload = {"schema": "mb/verdicts@1", "decided_by": "llama.cpp/test-model", "decided_at": "now", "verdicts": list(rows)}
        path = self.repo / "uncertain.verdicts.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_the_flag_survives_apply_and_reaches_the_paper(self):
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(STOCK_DRAFT))
        verdicts = self._verdicts(
            {"section": "stocks", "id": "sapse", "news_id": "ms-conference",
             "brief": True, "price_move": True, "category": "guidance", "confidence": 0.51, "ambiguous": True, "why": "Two readings"},
            {"section": "stocks", "id": "sapse", "news_id": "old-buyback",
             "brief": False, "price_move": False, "category": "stale", "confidence": 0.95},
        )
        self.assertEqual(run_mb("--repo", str(self.repo), "decide", "--date", DATE, "--verdicts", str(verdicts), "--section", "stocks"), 0)

        day = load_day(self.repo, day_path(DATE))
        items = load_section_items(self.repo, day.date, "stocks")
        sapse = next(item for item in items if item.id == "sapse")
        judged = {entry.id: entry.relevance for entry in sapse.news if entry.relevance}
        self.assertTrue(judged["ms-conference"].ambiguous)
        self.assertFalse(judged["old-buyback"].ambiguous, "an absent flag stays confident")
        self.assertIn("1 judged uncertain", render_section(day, "stocks", items))

    def test_verify_counts_uncertain_verdicts(self):
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(STOCK_DRAFT))
        verdicts = self._verdicts(
            {"section": "stocks", "id": "sapse", "news_id": "ms-conference",
             "brief": True, "price_move": False, "category": "guidance", "ambiguous": True}
        )
        run_mb("--repo", str(self.repo), "decide", "--date", DATE, "--verdicts", str(verdicts), "--section", "stocks")
        self.assertIn("uncertain=1", self._verify_output())

    def test_a_non_boolean_flag_is_refused(self):
        from mb.model import Item, SectionError

        with self.assertRaisesRegex(SectionError, "ambiguous"):
            Item.from_json({"id": "x", "section": "stocks", "ticker": "X",
                            "relevance": {"brief": True, "price_move": False, "ambiguous": "yes"}})


class VerifyCliTests(RepoTestCase):
    def test_verify_reports_per_section_counts(self):
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(STOCK_DRAFT))
        code = run_mb("--repo", str(self.repo), "verify", "--date", DATE, "--allow-empty")
        self.assertEqual(code, 0)

    def test_verify_fails_on_an_empty_section_without_the_flag(self):
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(STOCK_DRAFT))
        self.assertEqual(run_mb("--repo", str(self.repo), "verify", "--date", DATE), 1)

    def test_generated_check_flags_a_missing_render(self):
        """JSON without its rendered Markdown is the failure this guard exists for."""
        draft = self.write_draft(STOCK_DRAFT)
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", draft)
        self.assertEqual(
            run_mb("--repo", str(self.repo), "generated-check", "2026/11/22/stocks.md", "2026/11/22/stocks/20-sapse.json"),
            1,
        )
        # The data file itself is always fair game — that is what a lane pushes.
        self.assertEqual(run_mb("--repo", str(self.repo), "generated-check", "2026/11/22/stocks/20-sapse.json"), 0)

    def test_generated_check_lets_through_what_render_just_wrote(self):
        """A generated file is only a hand-edit if it differs from the render.

        Otherwise the commit that introduces the pipeline's own output can never
        pass CI, and the guard would have to be switched off exactly when it is
        most needed.
        """
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(STOCK_DRAFT))
        self.assertEqual(run_mb("--repo", str(self.repo), "render", "--write"), 0)
        self.assertEqual(run_mb("--repo", str(self.repo), "generated-check", "2026/11/22/stocks.md"), 0)

        (self.repo / "2026/11/22/stocks.md").write_text("# I wrote this by hand\n", encoding="utf-8")
        self.assertEqual(run_mb("--repo", str(self.repo), "generated-check", "2026/11/22/stocks.md"), 1)

    def _generated_check(self, *paths: str) -> str:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            run_mb("--repo", str(self.repo), "generated-check", *paths)
        return buffer.getvalue()

    def test_generated_check_leaves_legacy_markdown_alone(self):
        """Nothing renders a Markdown-only day, so nothing erases editing it.

        But "allowed" must not be read as "verified": the guard has no opinion
        about those bytes, and saying which of the two it means is the
        difference between a line an operator can act on and one they cannot.
        """
        legacy = self.repo / "2026/11/17"
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / "weather.md").write_text("# Weather — Novi Iskar, 17 Nov 2026\n", encoding="utf-8")
        out = self._generated_check("2026/11/17/weather.md")
        self.assertIn("not rendered by the pipeline", out)
        self.assertIn("unverified=1", out)
        self.assertNotIn("matches the pipeline", out)
        self.assertIn("generated-check=clean", out)

    def test_generated_check_says_which_files_it_actually_checked(self):
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(STOCK_DRAFT))
        run_mb("--repo", str(self.repo), "render", "--write")
        (self.repo / "2026/11/17").mkdir(parents=True, exist_ok=True)
        (self.repo / "2026/11/17/weather.md").write_text("legacy\n", encoding="utf-8")
        out = self._generated_check("2026/11/22/stocks.md", "2026/11/17/weather.md")
        self.assertIn("matches the pipeline byte for byte: 2026/11/22/stocks.md", out)
        self.assertIn("not rendered by the pipeline, so not verified either: 2026/11/17/weather.md", out)
        self.assertIn("owned=2 offenders=0 unverified=1", out)


class SubprocessTests(RepoTestCase):
    """`python3 -m mb` must work with nothing installed but the stdlib."""

    def test_module_entry_point(self):
        proc = subprocess.run(
            [sys.executable, "-m", "mb", "--repo", str(self.repo), "status"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("days managed=0 legacy=1", proc.stdout)

    def test_stdlib_only(self):
        """CI runs this on a bare runner: no third-party imports anywhere in mb/."""
        # The point is "no third-party imports": the CI runner has nothing installed.
        # difflib and hashlib are stdlib, added with backfill.py's diff report and
        # Cyrillic-id fallback; keeping the list explicit is what makes it a guard.
        allowed = {"__future__", "argparse", "collections", "contextlib", "dataclasses", "datetime",
                   "difflib", "enum", "fcntl", "hashlib", "json", "os", "pathlib", "re",
                   "subprocess", "sys", "tempfile", "time", "typing", "zoneinfo"}
        offenders = set()
        for path in (REPO_ROOT / "mb").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")  # syntax must stay valid for the runner's Python
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")):
                    root = stripped.replace("from ", "import ").split()[1].split(".")[0]
                    if root not in allowed and root != "mb":
                        offenders.add(root)
        self.assertFalse(offenders, f"mb must stay stdlib-only, found: {sorted(offenders)}")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
