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


class VerifyCliTests(RepoTestCase):
    def test_verify_reports_per_section_counts(self):
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(STOCK_DRAFT))
        code = run_mb("--repo", str(self.repo), "verify", "--date", DATE, "--allow-empty")
        self.assertEqual(code, 0)

    def test_verify_fails_on_an_empty_section_without_the_flag(self):
        run_mb("--repo", str(self.repo), "ingest", "--date", DATE, "--file", self.write_draft(STOCK_DRAFT))
        self.assertEqual(run_mb("--repo", str(self.repo), "verify", "--date", DATE), 1)

    def test_generated_check_flags_hand_edits(self):
        self.assertEqual(
            run_mb("--repo", str(self.repo), "generated-check", "2026/11/22/stocks.md", "2026/11/22/stocks/20-sapse.json"),
            1,
        )
        self.assertEqual(run_mb("--repo", str(self.repo), "generated-check", "2026/11/22/stocks/20-sapse.json"), 0)


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
        allowed = {"__future__", "argparse", "collections", "contextlib", "dataclasses", "datetime",
                   "enum", "fcntl", "json", "os", "pathlib", "re", "subprocess", "sys",
                   "tempfile", "time", "typing", "zoneinfo"}
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
