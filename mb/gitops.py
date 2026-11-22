"""Git plumbing for publishing brief JSON, with the box's known quirks baked in.

Two facts drove this module (and the shell scripts it replaces):

* ``git clone git@github.com:...`` fails intermittently here. The GitHub
  identity is a gcr ssh-agent socket plus a host certificate, and three
  parallel lanes hitting that identity at once frequently get
  ``Permission denied (publickey)``. So SSH clones take an advisory lock
  (held per attempt, never across a sleep), every attempt falls back to the
  HTTPS remote, and the whole thing retries.
* push rejection is normal: lanes race on the same branch. A rejection is
  answered with fetch + rebase + retry, not with a human.

Stdlib only, so CI can import it too.
"""

from __future__ import annotations

import enum
import fcntl
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SSH_URL = "git@github.com:mimiteto/newspaper.git"
DEFAULT_HTTPS_URL = "https://github.com/mimiteto/newspaper.git"
DEFAULT_SSH_AGENT = "/run/user/1000/gcr/ssh"
# A coordination point between lanes owned by this user, not a place to put
# data: tempfile.gettempdir() honours TMPDIR (so it is not pinned to a
# world-shared directory on multi-user boxes) and the file is created 0600.
# Override with MB_SSH_LOCK.
DEFAULT_LOCK = os.environ.get("MB_SSH_LOCK") or os.path.join(tempfile.gettempdir(), "mb-git.lock")
DEFAULT_BRANCH = "master"


class Push(enum.Enum):
    """Outcome vocabulary — kept as ``key=value`` strings for log grepping."""

    PUSHED = "pushed"
    PUSHED_AFTER_REBASE = "pushed-after-rebase"
    NOOP = "noop"
    FAILED = "failed"


@dataclass(frozen=True)
class GitSettings:
    ssh_url: str = DEFAULT_SSH_URL
    https_url: str = DEFAULT_HTTPS_URL
    ssh_agent: str = DEFAULT_SSH_AGENT
    lock_path: str = DEFAULT_LOCK
    branch: str = DEFAULT_BRANCH
    tries: int = 3
    delay: float = 10.0
    author_name: str = "Morning Bot"
    author_email: str = "morning-brief@newspaper.local"

    @classmethod
    def from_env(cls) -> GitSettings:
        env = os.environ
        return cls(
            ssh_url=env.get("MB_REMOTE_URL", DEFAULT_SSH_URL),
            https_url=env.get("MB_REMOTE_URL_HTTPS", DEFAULT_HTTPS_URL),
            ssh_agent=env.get("MB_SSH_AGENT", DEFAULT_SSH_AGENT),
            lock_path=env.get("MB_SSH_LOCK", DEFAULT_LOCK),
            branch=env.get("MB_BRANCH", DEFAULT_BRANCH),
            tries=int(env.get("MB_GIT_TRIES", "3")),
            delay=float(env.get("MB_GIT_DELAY", "10")),
            author_name=env.get("MB_GIT_AUTHOR_NAME", "Morning Bot"),
            author_email=env.get("MB_GIT_AUTHOR_EMAIL", "morning-brief@newspaper.local"),
        )


def run_git(
    args: list[str],
    cwd: Path | None = None,
    *,
    env: dict[str, str] | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:400]}")
    return proc


@contextmanager
def _network_lock(lock_path: str):
    """Serialise networked git work between parallel lanes.

    Held per attempt only, so a lane that sleeps between retries cannot block
    the others forever.
    """
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        # 0o600 from the moment of creation (no world-writable window), and
        # O_CLOEXEC so a spawned git cannot inherit the lock descriptor.
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    except OSError as exc:
        raise RuntimeError(f"cannot open git lock {lock_path}: {exc}") from exc
    handle = os.fdopen(fd, "a")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def clone(
    destination: Path,
    settings: GitSettings | None = None,
    *,
    quiet: bool = True,
) -> tuple[bool, str, int]:
    """Clone the brief repo into ``<destination>/repo``.

    Returns ``(ok, via, attempt)``. Always starts from scratch: a publish
    decision must be taken against a current ``origin/master``, so a reused
    clone could mis-report "already published".
    """
    settings = settings or GitSettings.from_env()
    repo = destination / "repo"
    destination.mkdir(parents=True, exist_ok=True)
    flag = ["--quiet"] if quiet else []

    for attempt in range(1, settings.tries + 1):
        subprocess.run(["rm", "-rf", str(repo)], check=False)
        ssh_env = {**os.environ, "SSH_AUTH_SOCK": settings.ssh_agent}
        with _network_lock(settings.lock_path):
            proc = run_git([*flag, "clone", settings.ssh_url, str(repo)], env=ssh_env)
        if proc.returncode == 0:
            return True, "ssh", attempt
        subprocess.run(["rm", "-rf", str(repo)], check=False)

        # gh's git-credential helper serves the HTTPS remote, so this keeps
        # working while ssh-agent auth is misbehaving.
        with _network_lock(settings.lock_path):
            proc = run_git([*flag, "clone", settings.https_url, str(repo)])
        if proc.returncode == 0:
            return True, "https", attempt
        subprocess.run(["rm", "-rf", str(repo)], check=False)
        if attempt < settings.tries:
            time.sleep(settings.delay)

    return False, "none", settings.tries


def head_sha(repo: Path, *, short: int = 0) -> str:
    proc = run_git(["rev-parse"] + ([f"--short={short}"] if short else []) + ["HEAD"], cwd=repo)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def commit_and_push(
    repo: Path,
    paths: list[str],
    message: str,
    settings: GitSettings | None = None,
    *,
    allow_empty: bool = False,
) -> Push:
    """Commit ``paths`` and push ``HEAD:<branch>``, re-taking the branch on rejection.

    ``-X ours`` on a rebase prefers the branch being rebased ONTO, i.e.
    upstream — the race-safe rule the old slot-claim script used: when two
    lanes push competing versions of a generated file, upstream wins and the
    loser re-renders from JSON on the next run.
    """
    settings = settings or GitSettings.from_env()
    author = ["-c", f"user.name={settings.author_name}", "-c", f"user.email={settings.author_email}"]

    if run_git(["diff", "--cached", "--quiet", "--", *paths], cwd=repo).returncode == 0 and not allow_empty:
        # Nothing staged relative to HEAD; also confirm there is no untracked
        # new file hiding from `git diff --cached` before calling it a no-op.
        return Push.NOOP

    commit = run_git([*author, "commit", "-m", message], cwd=repo)
    if commit.returncode != 0:
        if "nothing to commit" in (commit.stdout + commit.stderr):
            return Push.NOOP
        raise RuntimeError(f"commit failed: {(commit.stderr or commit.stdout).strip()[:400]}")

    for attempt in range(1, settings.tries + 1):
        with _network_lock(settings.lock_path):
            push = run_git(["push", "--quiet", "origin", f"HEAD:{settings.branch}"], cwd=repo)
        if push.returncode == 0:
            return Push.PUSHED if attempt == 1 else Push.PUSHED_AFTER_REBASE
        with _network_lock(settings.lock_path):
            run_git(["fetch", "--quiet", "origin", settings.branch], cwd=repo)
            run_git(["rebase", "--quiet", "-X", "ours", f"origin/{settings.branch}"], cwd=repo)
        if attempt < settings.tries:
            time.sleep(settings.delay)

    return Push.FAILED


def stage(repo: Path, paths: list[str]) -> None:
    run_git(["add", "--", *paths], cwd=repo, check=True)


def remote_has(repo: Path, branch: str, path: str) -> bool:
    """True when ``origin/<branch>`` already carries ``path`` (bare tree probe)."""
    proc = run_git(["cat-file", "-e", f"origin/{branch}:{path}"], cwd=repo)
    return proc.returncode == 0
