"""Tests for ``mb backfill`` — legacy Markdown in, JSON out, prose unchanged.

The behaviour that matters is the refusal: a backfill that silently reworded the
paper would publish a rewrite of history that nobody reads again. So every test
here either demands byte-identical output or demands that the tool decline to
write anything at all.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest

from conftest_fixtures import RepoTestCase
from test_backfill_fixtures import LEGACY_INDEX, legacy_records

from mb.cli import main
from mb.model import Day, Item, SectionError
from mb.paths import day_path
from mb.render import render_section
from mb.store import load_day, write_day

DATE = "2026-11-22"
STAMPS = ("2026-11-22T09:18:37+02:00", "2026-11-22T09:43:26+02:00")


class BackfillRepoTestCase(RepoTestCase):
    """A day whose only record is Markdown, exactly as the old lanes left it."""

    def setUp(self) -> None:
        super().setUp()
        self.date = day_path(DATE)
        self.directory = self.repo / self.date.nested
        self.directory.mkdir(parents=True, exist_ok=True)
        self.originals: dict[str, str] = {}
        day = Day(date=self.date, started=STAMPS[0], finished=STAMPS[1])
        for section, records in legacy_records().items():
            items = [Item.from_json(record, section=section, where=section) for record in records]
            text = render_section(day, section, items)
            (self.directory / f"{section}.md").write_text(text, encoding="utf-8")
            self.originals[section] = text
        (self.directory / "index.md").write_text(LEGACY_INDEX, encoding="utf-8")

    def item_files(self, section: str) -> list[str]:
        return sorted(path.name for path in (self.directory / section).glob("*.json"))

    def ids(self, section: str) -> set[str]:
        return {
            json.loads(path.read_text(encoding="utf-8"))["id"]
            for path in (self.directory / section).glob("*.json")
        }

    def backfill(self, *extra: str) -> tuple[int, str]:
        """Run the CLI with stdout captured — the refusals are the assertions."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = main(["--repo", str(self.repo), "backfill", "--date", DATE, *extra])
        return rc, buffer.getvalue()


class RoundTripTests(BackfillRepoTestCase):
    def test_the_fixture_round_trips(self):
        from mb.backfill import parse_day, round_trip

        parsed = parse_day(self.repo, self.date)
        self.assertEqual(round_trip(parsed), {}, "the fixture must be one the parser can reproduce")
        self.assertEqual(parsed.started, STAMPS[0], "the old stamps are part of the record")
        self.assertEqual(parsed.finished, STAMPS[1])

    def test_a_line_the_render_would_repair_is_refused(self):
        """The gate is about structure, not wording: a missing full stop here is
        one the renderer puts back, which would rewrite the paper by one byte."""
        path = self.directory / "weather.md"
        path.write_text(path.read_text(encoding="utf-8").replace("77% humidity.", "77% humidity"), encoding="utf-8")
        rc, out = self.backfill("--apply")
        self.assertEqual(rc, 1)
        self.assertIn("backfill=refused", out)
        self.assertIn("weather:", out)
        self.assertFalse((self.directory / "meta.json").exists(), "a refused day must be left completely alone")
        self.assertFalse((self.directory / "weather").exists())
        self.assertEqual((self.directory / "stocks.md").read_text(encoding="utf-8"), self.originals["stocks"])

    def test_prose_is_carried_across_verbatim_rather_than_reworded(self):
        """Rewording the day before backfilling is allowed: the JSON keeps the
        sentence it was given, which is the only way history survives a migration."""
        path = self.directory / "weather.md"
        reworded = path.read_text(encoding="utf-8").replace("Mainly clear,", "Mainly clear, with a late northerly,")
        path.write_text(reworded, encoding="utf-8")
        rc, out = self.backfill("--apply")
        self.assertEqual(rc, 0, out)
        conditions = next(
            json.loads(file.read_text(encoding="utf-8"))
            for file in (self.directory / "weather").glob("*.json")
            if json.loads(file.read_text(encoding="utf-8"))["id"] == "conditions"
        )
        self.assertEqual(conditions["text"], "Mainly clear, with a late northerly, 77% humidity.")

    def test_triaged_news_bullets_cannot_be_backfilled(self):
        """The printed paper hides the verdicts; rebuilding news[] would invent them."""
        from mb.backfill import parse_day

        bullet = "- **[macro]** Sector-wide — [Investing.com](https://example.com/a)\n"
        url_line = "https://finance.yahoo.com/quote/SAP.DE/\n"
        path = self.directory / "stocks.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn(url_line, text)
        path.write_text(text.replace(url_line, bullet + url_line), encoding="utf-8")
        with self.assertRaisesRegex(SectionError, "cannot backfill a day that already has triaged news"):
            parse_day(self.repo, self.date)

    def test_every_section_file_must_be_present(self):
        from mb.backfill import parse_day

        (self.directory / "bulgarian-finances.md").unlink()
        with self.assertRaisesRegex(SectionError, "bulgarian-finances.md: no such file"):
            parse_day(self.repo, self.date)


class ApplyTests(BackfillRepoTestCase):
    def test_default_is_a_dry_run(self):
        rc, out = self.backfill()
        self.assertEqual(rc, 0, out)
        self.assertIn("backfill=ready", out)
        self.assertFalse((self.directory / "meta.json").exists())

    def test_apply_writes_one_file_per_item_and_leaves_the_paper_alone(self):
        rc, out = self.backfill("--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("backfill=applied", out)

        day = load_day(self.repo, self.date)
        self.assertEqual(day.started, STAMPS[0])
        self.assertEqual(day.source, "backfill from markdown")

        for section, original in self.originals.items():
            files = self.item_files(section)
            self.assertTrue(files, f"{section}: no item files written")
            self.assertTrue(all(name[:2].isdigit() for name in files), files)
            self.assertEqual(
                (self.directory / f"{section}.md").read_text(encoding="utf-8"),
                original,
                "backfill must not touch the generated paper",
            )

        # These ids are what the decisions API votes against on the next re-publish.
        stocks = self.ids("stocks")
        self.assertLessEqual(
            {"snapshot-context-every-price-below", "sapse", "sxr8", "vhyl", "flag-01"}, stocks
        )
        bg = self.ids("bulgarian-finances")
        self.assertTrue(all(part.isascii() for part in bg), bg)

    def test_the_json_then_renders_the_same_paper(self):
        """The point of the exercise: JSON in, identical newspaper out."""
        self.backfill("--apply")
        self.assertEqual(main(["--repo", str(self.repo), "render", "--write"]), 0)
        for section, original in self.originals.items():
            self.assertEqual(
                (self.directory / f"{section}.md").read_text(encoding="utf-8"),
                original,
                f"{section}.md changed when re-rendered from the backfilled JSON",
            )
        index = (self.directory / "index.md").read_text(encoding="utf-8")
        self.assertIn("_Generated by `mb render`", index, "the day index becomes a generated file")
        self.assertNotIn("Created by", index)

    def test_an_already_managed_day_is_left_alone(self):
        write_day(self.repo, Day(date=self.date, started=STAMPS[0]))
        (self.directory / "stocks").mkdir(exist_ok=True)
        (self.directory / "stocks" / "10-sapse.json").write_text(
            json.dumps({"schema": "mb/item@1", "section": "stocks", "id": "sapse", "label": "SAPSE"}),
            encoding="utf-8",
        )
        rc, out = self.backfill("--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("already-managed", out)
        self.assertEqual(self.ids("stocks"), {"sapse"}, "stored verdicts must not be overwritten")


class IdAndPrecisionTests(unittest.TestCase):
    def test_cyrillic_labels_get_readable_stable_ids(self):
        from mb.backfill import parse_section

        markdown = (
            "# Bulgaria — news\n\n"
            "**МРЗ 660 евро от 1 януари 2027 г.** The projected minimum wage is €660.\n"
            "https://example.com/a\n\n"
            "**МРЗ 660 евро от 1 януари 2027 г.** A duplicate headline still needs its own file.\n"
        )
        ids = [record["id"] for record in parse_section(markdown, "bulgarian-finances")]
        self.assertTrue(all(part.isascii() and part for part in ids), ids)
        self.assertIn("mrz-660-evro-ot-1-yanuari-2027-g", ids)
        self.assertEqual(len(ids), len(set(ids)), ids)
        self.assertEqual(ids, [record["id"] for record in parse_section(markdown, "bulgarian-finances")])

    def test_weight_precision_survives_the_round_trip(self):
        """stockanalysis writes 2.00%, etftrace 2.4% — a float cannot tell them apart."""
        from mb.backfill import parse_section

        day = Day(date=day_path(DATE))
        source = render_section(
            day,
            "stocks",
            [
                Item.from_json(
                    {
                        "id": "vhyl",
                        "label": "VHYL",
                        "text": "Top holdings per etftrace, as of 30 Sep 2026:",
                        "holdings": [
                            {"rank": 1, "name": "Samsung Electronics", "weight_pct": 2.4, "weight_display": "2.4%"},
                            {"rank": 2, "name": "ASML", "weight_pct": 2.0, "weight_display": "2.0%"},
                            {"rank": 3, "name": "Novartis", "weight_pct": 2.0, "weight_display": "2.00%"},
                        ],
                    },
                    section="stocks",
                    where="vhyl",
                )
            ],
        )
        records = parse_section(source, "stocks")
        holdings = next(record["holdings"] for record in records if record["id"] == "vhyl")
        # Only the figures the pipeline would print differently carry an authored
        # display; "2.00%" is what it prints anyway, so it stays a plain number.
        self.assertEqual([entry.get("weight_display") for entry in holdings], ["2.4%", "2.0%", None])
        self.assertEqual([entry["weight_pct"] for entry in holdings], [2.4, 2.0, 2.0])
        again = render_section(day, "stocks", [Item.from_json(r, section="stocks", where=r["id"]) for r in records])
        self.assertEqual(again, source)

    def test_a_lead_in_ending_in_a_colon_gains_no_full_stop(self):
        from mb.render import _sentence

        self.assertEqual(_sentence(["", "Top five weights, as of 19 Nov 2026:"]), "Top five weights, as of 19 Nov 2026:")
        self.assertEqual(_sentence(["€694.06", "it tracked the index"]), "€694.06. it tracked the index.")
        self.assertEqual(_sentence(["", "High 12.0 °C."]), "High 12.0 °C.")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
