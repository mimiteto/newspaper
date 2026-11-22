"""Git plumbing tests.

These exist because of a bug no unit test caught in the first pass: the clone
arguments were built as ``git --quiet clone ...``. Global git flags belong
after the subcommand, so every lane failed to clone — and from the outside a
git usage error looks exactly like an ssh-auth failure.
"""

from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

from mb import gitops
from mb.gitops import GitSettings


class RecordingGit:
    """Stands in for ``gitops.run_git`` and records how it was called."""

    def __init__(self, failures: int = 0, message: str = "fatal: boom"):
        self.calls: list[list[str]] = []
        self.failures = failures
        self.message = message

    def __call__(self, args, cwd=None, *, env=None, check=False):  # noqa: ANN001 - test double
        self.calls.append(list(args))
        code = 129 if len(self.calls) <= self.failures else 0
        return subprocess.CompletedProcess(["git", *args], code, stdout="", stderr=self.message if code else "")


class CloneTests(unittest.TestCase):
    def setUp(self):
        self.real_run = gitops.run_git
        self.real_rm = gitops.subprocess.run
        # A scratch directory owned by this process only: clone() is stubbed so
        # nothing is written, but the path it builds is asserted below.
        self.dest = pathlib.Path(tempfile.mkdtemp(prefix="mb-gitops-")) / "scratch"
        # Never let a test touch the real network or delete anything outside it.
        gitops.subprocess.run = lambda *a, **k: None  # type: ignore[assignment]
        self.addCleanup(self.restore)

    def restore(self):
        gitops.run_git = self.real_run
        gitops.subprocess.run = self.real_rm

    def _clone(self, failures: int = 0, tries: int = 3):
        recorder = RecordingGit(failures=failures)
        gitops.run_git = recorder  # type: ignore[assignment]
        settings = GitSettings(
            ssh_url="git@example.com:o/r.git", https_url="https://example.com/o/r.git", tries=tries, delay=0
        )
        ok, via, attempt, error = gitops.clone(self.dest, settings)
        return ok, via, attempt, error, recorder, settings

    def test_success_first_try_over_ssh(self):
        ok, via, attempt, error, recorder, _ = self._clone()
        self.assertTrue(ok)
        self.assertEqual((via, attempt), ("ssh", 1))
        self.assertEqual(error, "")
        self.assertEqual(len(recorder.calls), 1)

    def test_clone_arguments_put_the_subcommand_first(self):
        """The regression: `git --quiet clone` is a usage error, not an auth error."""
        _ok, _via, _attempt, _error, recorder, settings = self._clone()
        argv = recorder.calls[0]
        self.assertEqual(argv[0], "clone", f"git flags must follow the subcommand, got {argv}")
        self.assertIn("--quiet", argv)
        self.assertLess(argv.index("clone"), argv.index("--quiet"))
        self.assertEqual(argv, ["clone", "--quiet", settings.ssh_url, str(self.dest / "repo")])

    def test_https_fallback_when_ssh_fails(self):
        ok, via, attempt, error, recorder, settings = self._clone(failures=1)
        self.assertTrue(ok)
        self.assertEqual(via, "https")
        self.assertEqual(attempt, 1)
        self.assertEqual(recorder.calls[1][2], settings.https_url)

    def test_failure_reports_the_git_stderr(self):
        ok, via, attempt, error, _recorder, _ = self._clone(failures=99, tries=2)
        self.assertFalse(ok)
        self.assertEqual(via, "none")
        self.assertEqual(attempt, 2)
        self.assertIn("boom", error, "clone=failed has to say why, or a lane can only guess")

    def test_quiet_false_omits_the_flag(self):
        recorder = RecordingGit()
        gitops.run_git = recorder  # type: ignore[assignment]
        settings = GitSettings(ssh_url="git@example.com:o/r.git", tries=1, delay=0)
        gitops.clone(self.dest, settings, quiet=False)
        self.assertEqual(recorder.calls[0], ["clone", settings.ssh_url, str(self.dest / "repo")])


class RunGitTests(unittest.TestCase):
    def test_command_is_git_plus_args_in_order(self):
        seen: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # noqa: ANN001 - test double
            seen.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="sha123\n", stderr="")

        real = gitops.subprocess.run
        gitops.subprocess.run = fake_run  # type: ignore[assignment]
        try:
            proc = gitops.run_git(["rev-parse", "--short=8", "HEAD"])
        finally:
            gitops.subprocess.run = real  # type: ignore[assignment]
        self.assertEqual(seen, [["git", "rev-parse", "--short=8", "HEAD"]])
        self.assertEqual(proc.stdout.strip(), "sha123")


class SettingsTests(unittest.TestCase):
    def test_env_overrides(self):
        import os

        saved = {key: os.environ.get(key) for key in ("MB_REMOTE_URL", "MB_BRANCH", "MB_GIT_TRIES", "MB_GIT_DELAY")}
        os.environ.update({"MB_REMOTE_URL": "git@x:y/z.git", "MB_BRANCH": "preview", "MB_GIT_TRIES": "7", "MB_GIT_DELAY": "0"})
        try:
            settings = GitSettings.from_env()
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual((settings.ssh_url, settings.branch, settings.tries, settings.delay), ("git@x:y/z.git", "preview", 7, 0.0))

    def test_lock_path_is_not_world_writable_by_default(self):
        self.assertTrue(GitSettings().lock_path.endswith("mb-git.lock"))


if __name__ == "__main__":
    unittest.main()
