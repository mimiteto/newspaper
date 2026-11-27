"""Integration test: the real publish path against a local git remote.

Unit tests cover the pieces; this covers the sequence a brief is published in,
because every bug that reached a real morning (git argv order, verdict scope,
lost `--started` stamp) only showed up when lanes, pushes and rebases ran
together. The remote is a local bare repo, so the test needs no network and no
credentials.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from conftest_fixtures import REPO_ROOT, STOCK_DRAFT, VERDICTS

DATE = "2026-11-22"
NESTED = "2026/11/22"


def git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def run_mb(*argv: str | Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "mb", *[str(entry) for entry in argv]],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


class PublishFlowTests(unittest.TestCase):
    """publish (all three sections) -> finalize -> CI render."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mb-e2e-"))
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.tmp)], check=False))
        self.remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)

        # Seed a "master" that looks like the real repo: config + a legacy day.
        seed = self.tmp / "seed"
        seed.mkdir()
        git(["init", "-q", "-b", "master"], seed)
        git(["config", "user.name", "Seed"], seed)
        git(["config", "user.email", "seed@example.com"], seed)
        (seed / "_config.yml").write_text("theme: minima\n", encoding="utf-8")
        legacy = seed / "2026/11/17"
        legacy.mkdir(parents=True)
        (legacy / "index.md").write_text("# Morning Brief — 2026-11-17\n", encoding="utf-8")
        (seed / "index.md").write_text("# homepage\n", encoding="utf-8")
        git(["add", "-A"], seed)
        git(["commit", "-q", "-m", "seed"], seed)
        git(["push", "-q", str(self.remote), "HEAD:master"], seed)

        self.env = {
            **os.environ,
            "MB_REMOTE_URL": str(self.remote),
            "MB_REMOTE_URL_HTTPS": str(self.remote),
            "MB_GIT_DELAY": "0",
            "MB_SSH_LOCK": str(self.tmp / "git.lock"),
        }

        fixture = self.tmp / "drafts"
        fixture.mkdir()
        weather = {"section": "weather", "items": [
            {"id": "generation", "kind": "context", "text": "Forecast as of 09:15 local."},
            {"id": "temperature", "label": "Temperature today", "text": "High 12.0 °C.", "as_of": "09:15 local"},
        ]}
        (fixture / "weather.json").write_text(json.dumps(weather), encoding="utf-8")
        (fixture / "stocks.json").write_text(json.dumps(STOCK_DRAFT, ensure_ascii=False), encoding="utf-8")
        bg = {"section": "bulgarian-finances", "items": [
            {"id": "vat", "label": "ДДС-прагът 60 000 евро", "text": "Регистрационният праг се вдига.", "topic": "ДДС"},
        ]}
        (fixture / "bulgarian-finances.json").write_text(json.dumps(bg, ensure_ascii=False), encoding="utf-8")
        (fixture / "verdicts.json").write_text(json.dumps(VERDICTS), encoding="utf-8")
        self.fixture = fixture

    # ------------------------------------------------------------- the flow
    def test_publish_finalize_render(self):
        result = run_mb(
            "publish", "--date", DATE, "--dir", str(self.fixture),
            "--verdicts", str(self.fixture / "verdicts.json"),
            "--location", "Novi Iskar", "--started", "2026-11-22T09:18:37+02:00",
            env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("clone=ok", result.stdout)
        self.assertIn("publish=ok sections=3 items=", result.stdout)
        # Verdict files are shared across sections but scoped per section.
        self.assertIn("section=stocks applied=3", result.stdout)

        clone = self.tmp / "inspect"
        git(["clone", "-q", str(self.remote), str(clone)], self.tmp)
        names = sorted(path.relative_to(clone).as_posix() for path in (clone / NESTED).rglob("*.json"))
        self.assertIn(f"{NESTED}/stocks/20-sapse.json", names)
        self.assertIn(f"{NESTED}/weather/20-temperature.json", names)
        self.assertTrue((clone / NESTED / "meta.json").is_file())
        meta = json.loads((clone / NESTED / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["started"], "2026-11-22T09:18:37+02:00", "a lane's stamp must survive the other lanes")

        # No Markdown yet: the lanes push data, CI writes prose.
        self.assertFalse((clone / NESTED / "stocks.md").exists())

        closed = run_mb("finalize", "--date", DATE, "--finished", "2026-11-22T09:43:26+02:00", env=self.env)
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertIn("verify=ok", closed.stdout)
        self.assertIn("finalize=ok", closed.stdout)

        git(["fetch", "-q", "origin", "master"], clone)
        git(["reset", "-q", "--hard", "origin/master"], clone)
        meta = json.loads((clone / NESTED / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["finished"], "2026-11-22T09:43:26+02:00")

        # The CI job: render, then prove the result is stable.
        rendered = run_mb("--repo", str(clone), "render", "--write", env=self.env)
        self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
        body = (clone / NESTED / "stocks.md").read_text(encoding="utf-8")
        self.assertIn("**SAPSE.** €183.68 on Xetra (SAP.DE)", body)
        self.assertNotIn("October buyback", body, "a dropped news item stays out of the paper")
        self.assertIn("News triaged by the decisions API", body)
        check = run_mb("--repo", str(clone), "render", "--check", env=self.env)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_finalize_with_repo_closes_locally_and_never_pushes(self):
        """``--repo`` means "this checkout, origin untouched" — including for the
        one command whose whole job is to push. A rehearsal close that cloned the
        remote instead would stamp the real day, which is the opposite of a test.
        """
        published = run_mb(
            "publish", "--date", DATE, "--dir", str(self.fixture),
            "--verdicts", str(self.fixture / "verdicts.json"),
            "--location", "Novi Iskar", "--started", "2026-11-22T09:18:37+02:00",
            env=self.env,
        )
        self.assertEqual(published.returncode, 0, published.stdout + published.stderr)

        local = self.tmp / "local"
        git(["clone", "-q", str(self.remote), str(local)], self.tmp)
        closed = run_mb("--repo", str(local), "finalize", "--date", DATE,
                        "--finished", "2026-11-22T09:43:26+02:00", env=self.env)
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertNotIn("clone=", closed.stdout, "a local close must not reach for a remote")
        self.assertIn("push=skipped reason=local-repo", closed.stdout)
        self.assertEqual(json.loads((local / NESTED / "meta.json").read_text(encoding="utf-8"))["finished"],
                         "2026-11-22T09:43:26+02:00")

        # Origin never saw it, and the checkout's index was not touched either.
        elsewhere = self.tmp / "elsewhere"
        git(["clone", "-q", str(self.remote), str(elsewhere)], self.tmp)
        self.assertEqual(json.loads((elsewhere / NESTED / "meta.json").read_text(encoding="utf-8")).get("finished", ""), "")
        status = subprocess.run(["git", "status", "--porcelain"], cwd=local, capture_output=True, text=True)
        # Leading column means "unstaged": the file changed, the index did not.
        self.assertEqual(status.stdout, f" M {NESTED}/meta.json\n")

    def test_re_publishing_a_section_changes_nothing(self):
        first = run_mb("publish", "--date", DATE, "--dir", str(self.fixture), env=self.env)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        before = git(["rev-list", "--count", "master"], self._bare())

        again = run_mb("publish", "--date", DATE, "--dir", str(self.fixture), env=self.env)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(again.stdout.count("section=noop"), 3, "an identical re-run must not pollute history")
        self.assertEqual(git(["rev-list", "--count", "master"], self._bare()), before)

    def test_finalize_refuses_to_close_a_day_with_unjudged_news(self):
        """Triage is a step, not a suggestion.

        Published without `--verdicts`, every news line would print tagged
        `[news]` and the day would look normal. `verify` reports the count
        either way; only `finalize` treats it as a reason not to close.
        """
        published = run_mb("publish", "--date", DATE, "--dir", str(self.fixture), env=self.env)
        self.assertEqual(published.returncode, 0, published.stdout + published.stderr)

        closed = run_mb("finalize", "--date", DATE, "--finished", "2026-11-22T09:43:26+02:00", env=self.env)
        self.assertEqual(closed.returncode, 1, closed.stdout + closed.stderr)
        self.assertIn("UNJUDGED=3", closed.stdout)
        self.assertIn("finalize=failed reason=verify", closed.stdout)

        degraded = run_mb(
            "finalize", "--date", DATE, "--finished", "2026-11-22T09:43:26+02:00",
            "--no-require-decisions", env=self.env,
        )
        self.assertEqual(degraded.returncode, 0, degraded.stdout + degraded.stderr)
        self.assertIn("finalize=ok", degraded.stdout)

    def test_only_filter_publishes_a_single_section(self):
        result = run_mb("publish", "--date", DATE, "--dir", str(self.fixture), "--only", "stocks", env=self.env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("publish=ok sections=1", result.stdout)
        self.assertIn("stocks=4", result.stdout, "STOCK_DRAFT holds sapse, aapl, ivv and ivvl")
        self.assertNotIn("weather=", result.stdout)

    def test_bad_section_in_only_is_refused(self):
        result = run_mb("publish", "--date", DATE, "--dir", str(self.fixture), "--only", "sport", env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bad-section", result.stdout + result.stderr)

    def test_file_and_dir_together_is_refused(self):
        result = run_mb(
            "publish", "--date", DATE, "--file", str(self.fixture / "stocks.json"),
            "--dir", str(self.fixture), env=self.env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("choose-one", result.stdout + result.stderr)

    def _bare(self) -> Path:
        return self.remote


if __name__ == "__main__":
    unittest.main()
