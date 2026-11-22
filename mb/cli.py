"""``python3 -m mb`` — the one entry point the skill and CI share.

Machine-readable output on purpose: every command ends with ``key=value`` lines
(``mb=ok``, ``section=published``, ``verify=ok``) so a caller can branch on them
without parsing prose. Exit code 0 = success, 1 = hard failure, 2 = usage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import tempfile
from pathlib import Path

from mb import backfill as backfill_mod
from mb import decide as decide_mod
from mb import gitops
from mb import render as render_mod
from mb.ingest import ORDER_STEP, ingest, load_draft, next_order, normalise_orders
from mb.model import Day, Item, SectionError
from mb.paths import SECTIONS, DayPath, day_path
from mb.store import (
    GENERATED_NAMES,
    counts,
    day_dir,
    legacy_days,
    load_day,
    load_section_items,
    managed_days,
    write_day,
)

REPO_ROOT_MARKER = "_config.yml"

#: meta.json fields a publisher may fill in. ``date`` and ``sections`` are
#: deliberately absent: they identify the day, so completing a stamp from a
#: draft must never be able to rewrite them.
STAMP_FIELDS: tuple[str, ...] = ("location", "timezone", "started", "finished", "source")


def resolve_repo(explicit: str | None) -> Path:
    """Repo root: --repo, else walk up from cwd looking for ``_config.yml``."""
    if explicit:
        return Path(explicit).resolve()
    current = Path.cwd()
    for candidate in (current, *current.parents):
        if (candidate / REPO_ROOT_MARKER).is_file() and (candidate / "mb").is_dir():
            return candidate
    sys.exit("mb=failed reason=not-in-repo pass --repo <clone-dir>")


def today_iso(*, tz_name: str = "Europe/Sofia") -> str:
    try:
        from zoneinfo import ZoneInfo

        now = dt.datetime.now(ZoneInfo(tz_name))
    except Exception:  # pragma: no cover - zoneinfo/tzdata missing on odd images
        now = dt.datetime.now().astimezone()
    return now.isoformat(timespec="seconds")


def _ensure_day(
    repo: Path,
    date: DayPath,
    *,
    location: str = "",
    started: str = "",
    finished: str = "",
    meta: dict[str, object] | None = None,
    force_meta: bool = False,
) -> Day:
    """Create or fill in ``meta.json`` without stomping what a lane already wrote.

    Three lanes publish the same day, so a field is only written when it is
    empty (or when ``--meta`` explicitly asks to overwrite). That is what lets
    any lane create the day first without racing on its contents — the old
    ``claim-index.sh`` slot-claim dance is gone because there is no contested
    file left to claim.
    """
    try:
        day = load_day(repo, date)
    except FileNotFoundError:
        day = Day(date=date)
    # CLI flags outrank the draft's meta block, and both outrank nothing: a
    # field already on disk keeps its value unless --meta says otherwise.
    flags = {"location": location, "started": started, "finished": finished}
    draft = {key: value for key, value in (meta or {}).items() if key in STAMP_FIELDS}
    for key in STAMP_FIELDS:
        value = str(flags.get(key) or draft.get(key) or "").strip()
        if not value:
            continue
        if force_meta or not str(getattr(day, key, "") or ""):
            setattr(day, key, value)
    write_day(repo, day)
    return day


def _draft_items(
    repo: Path,
    date: DayPath,
    file: str,
    section: str | None,
    *,
    merge: bool = False,
) -> tuple[list[Item], Day]:
    draft_path = Path(file)
    draft_section, records, meta = load_draft(draft_path)
    chosen = section or draft_section
    if not chosen:
        # Every stored mb/item@1 names its own section, so a bare list of such
        # records is already a complete draft — only a draft that names two
        # sections is genuinely ambiguous.
        named = {str(record.get("section", "")).strip() for record in records if isinstance(record, dict)}
        named.discard("")
        if len(named) == 1:
            chosen = named.pop()
        elif len(named) > 1:
            sys.exit(f"mb=failed reason=draft-names-multiple-sections {', '.join(sorted(named))} — split it per section")
    if not chosen:
        sys.exit("mb=failed reason=no-section pass --section or put \"section\" in the draft")
    if chosen not in SECTIONS:
        sys.exit(f"mb=failed reason=bad-section {chosen!r} not in {SECTIONS}")

    day = Day.from_json({**meta, "date": meta.get("date", date.flat)}, date=date)
    # --merge appends, so a draft without explicit orders must start after the
    # items already in the directory rather than on top of them.
    start = next_order(repo, date, chosen) if merge else ORDER_STEP
    items = [
        Item.from_json(record, section=chosen, where=f"{draft_path.name}[{index}]")
        for index, record in enumerate(normalise_orders(records, start=start))
    ]
    wrong = sorted({item.section for item in items if item.section != chosen})
    if wrong:
        sys.exit(f"mb=failed reason=section-mismatch draft says {', '.join(wrong)}, --section {chosen}")
    return items, day


# ----------------------------------------------------------------- commands
def cmd_ingest(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.repo)
    date = day_path(args.date)
    items, day = _draft_items(repo, date, args.file, args.section, merge=args.merge)
    _ensure_day(repo, date, meta=day.to_json(), force_meta=args.meta)
    written = ingest(repo, date, items, replace=not args.merge)
    print(f"section={args.section or items[0].section} items={len(written)} dir={date.nested}")
    print("mb=ok")
    return 0


def _discover_drafts(directory: Path, only: list[str]) -> list[tuple[str | None, str]]:
    """Find ``<section>.json`` (or ``<section>/items.json``) drafts to publish.

    Batch mode is why one command can replace the three-lane fan-out: a JSON
    publish is a clone plus a small commit, so running the sections in
    sequence against a single clone is both faster and free of the push race
    the parallel lanes needed locks, rebases and slot-claims to survive.
    """
    if not directory.is_dir():
        sys.exit(f"mb=failed reason=no-such-dir {directory}")
    found: list[tuple[str | None, str]] = []
    for section in only or list(SECTIONS):
        flat = directory / f"{section}.json"
        nested = directory / section / "items.json"
        if flat.is_file():
            found.append((section, str(flat)))
        elif nested.is_file():
            found.append((section, str(nested)))
    if not found:
        sys.exit(f"mb=failed reason=no-drafts-in {directory} (expected <section>.json)")
    return found


def _only_sections(value: str) -> list[str]:
    if not value:
        return []
    wanted = [part.strip() for part in value.split(",") if part.strip()]
    bogus = sorted(set(wanted) - set(SECTIONS))
    if bogus:
        sys.exit(f"mb=failed reason=bad-section {', '.join(bogus)} not in {', '.join(SECTIONS)}")
    return wanted


def cmd_publish(args: argparse.Namespace) -> int:
    date = day_path(args.date)
    settings = gitops.GitSettings.from_env()
    scratch: tempfile.TemporaryDirectory[str] | None = None

    if bool(args.file) == bool(args.dir):
        sys.exit("mb=failed reason=choose-one pass either --file <draft> or --dir <fixture-dir>")
    only = _only_sections(args.only)
    drafts = _discover_drafts(Path(args.dir), only) if args.dir else [(args.section, args.file)]

    if args.repo:
        repo = Path(args.repo).resolve()
    else:
        scratch = tempfile.TemporaryDirectory(prefix="mb-publish-")
        repo = Path(scratch.name)
        ok, via, attempt, error = gitops.clone(repo, settings)
        print(f"clone={'ok' if ok else 'failed'} via={via} attempt={attempt}"
              + (f" error={error}" if not ok and error else ""))
        if not ok:
            print("mb=failed reason=clone")
            return 1
        repo = repo / "repo"

    rc = 0
    totals: dict[str, int] = {}
    try:
        for section, draft in drafts:
            section_rc, count = _publish_into(repo, date, args, settings, draft_file=draft, section=section)
            totals[section or "?"] = count
            rc = rc or section_rc
    finally:
        if scratch is not None:
            scratch.cleanup()

    print(f"publish={'ok' if rc == 0 else 'failed'} sections={len(totals)} items={sum(totals.values())} "
          + " ".join(f"{name}={count}" for name, count in totals.items()))
    return rc


#: Both mean the commit is safe locally and never reached origin; only the
#: recovery advice differs, so the reason string says which.
_PUSH_FAILURES = (gitops.Push.FAILED, gitops.Push.CONFLICT)


def _publish_into(
    repo: Path,
    date: DayPath,
    args: argparse.Namespace,
    settings: gitops.GitSettings,
    *,
    draft_file: str,
    section: str | None,
) -> tuple[int, int]:
    items, draft_meta = _draft_items(repo, date, draft_file, section, merge=args.merge)
    section = items[0].section

    _ensure_day(
        repo,
        date,
        location=args.location,
        started=args.started,
        finished=args.finished,
        meta=draft_meta.to_json(),
    )
    written = ingest(repo, date, items, replace=not args.merge)

    if args.verdicts:
        verdicts = decide_mod.load_verdicts(Path(args.verdicts))
        # Scoped to this lane's section: a verdict file that also names the
        # other two sections must not depend on whose push landed first.
        summary = decide_mod.apply_verdicts(repo, date, verdicts, section=section)
        skipped = f" skipped={summary['skipped']}" if summary["skipped"] else ""
        print(
            f"decide=ok section={section} applied={summary['applied']} "
            f"keep={summary['keep']} context={summary['context']} drop={summary['drop']}{skipped}"
        )

    if args.render:
        _render_day(repo, date, write=True)

    paths = [f"{date.nested}/"]
    gitops.stage(repo, paths)
    pushed = gitops.commit_and_push(
        repo,
        paths,
        f"feat(brief): publish {section} items for {date.flat} ({len(written)})",
        settings,
    )
    sha = gitops.head_sha(repo, short=8)
    print(f"section={pushed.value} file={section} items={len(written)} sha={sha} path={date.nested}/{section}")
    if pushed in _PUSH_FAILURES:
        reason = "push-conflict" if pushed is gitops.Push.CONFLICT else "push"
        print(f"mb=failed reason={reason} section={section}")
        return 1, len(written)
    return 0, len(written)


def cmd_decide(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.repo)
    date = day_path(args.date)
    verdicts = decide_mod.load_verdicts(Path(args.verdicts))
    summary = decide_mod.apply_verdicts(repo, date, verdicts, write=not args.dry_run, section=args.section)
    prefix = "decide=dry-run" if args.dry_run else "decide=ok"
    print(
        f"{prefix} scope={summary['scope']} applied={summary['applied']} keep={summary['keep']} "
        f"context={summary['context']} drop={summary['drop']} skipped={summary['skipped']} "
        f"sections={','.join(summary['sections']) or '-'}"
    )
    print("mb=ok")
    return 0


def _read_text(path: Path) -> str:
    """File contents, or ``""`` when the file does not exist yet."""
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _render_day(repo: Path, date: DayPath, *, write: bool) -> list[str]:
    """Render one day; returns the relative paths that differ (or were written)."""
    day = load_day(repo, date)
    stale: list[str] = []
    for section in day.sections:
        items = load_section_items(repo, date, section)
        body = render_mod.render_section(day, section, items)
        target = day_dir(repo, date) / f"{section}.md"
        if _read_text(target) != body:
            if write:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
            stale.append(f"{date.nested}/{section}.md")

    index_body = render_mod.render_day_index(day, counts(repo, date))
    index_path = day_dir(repo, date) / "index.md"
    if _read_text(index_path) != index_body:
        if write:
            index_path.write_text(index_body, encoding="utf-8")
        stale.append(f"{date.nested}/index.md")
    return stale


def cmd_render(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.repo)
    if args.date:
        dates = [day_path(args.date)]
    else:
        dates = managed_days(repo)
        if not dates:
            # Nothing is JSON-managed yet (a fresh clone, or a PR that only
            # touches mb/). Not an error — but the homepage is still ours to
            # check below, since it lists legacy days too.
            print("render=noop days=0 reason=no-json-managed-days")

    changed: list[str] = []
    for date in dates:
        changed.extend(_render_day(repo, date, write=args.write))

    root = repo / "index.md"
    root_body = render_mod.render_root_index(_root_entries(repo))
    # Only claim the homepage when it actually changed, so "files=N" counts
    # real writes under --write and real drift under --check.
    if _read_text(root) != root_body:
        if args.write:
            root.write_text(root_body, encoding="utf-8")
        changed.append("index.md")

    print(f"render={'wrote' if args.write else 'check'} days={len(dates)} files={len(changed)}")
    for path in changed:
        print(f"  {'written' if args.write else 'stale'} {path}")
    if not args.write and changed:
        print("mb=failed reason=generated-files-stale")
        return 1
    print("mb=ok")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.repo)
    date = day_path(args.date)
    directory = day_dir(repo, date)
    if not directory.is_dir():
        print(f"verify=failed reason=no-such-day {date.nested}")
        return 1
    try:
        day = load_day(repo, date)
    except FileNotFoundError:
        # A Markdown-only legacy day, or a lane that wrote items without ever
        # creating the day record. Either way nothing here is pipeline-managed.
        print(f"verify=failed reason=no-meta-json path={date.nested} (legacy day or missing meta.json)")
        return 1
    total = 0
    failed = False
    for section in day.sections:
        items = load_section_items(repo, date, section)
        kept = [item for item in items if not item.dropped]
        total += len(kept)
        suffix = ""
        if section == "stocks":
            news = [entry for item in items for entry in item.news]
            judged = [entry for entry in news if entry.relevance is not None]
            unjudged = len(news) - len(judged)
            uncertain = [entry for entry in judged if entry.relevance and entry.relevance.ambiguous]
            suffix = f" news={len(judged)}/{len(news)}"
            if uncertain:
                suffix += f" uncertain={len(uncertain)}"
            if unjudged:
                # Reported even when not enforced: a day closed with
                # --no-require-decisions should still say so in its own output.
                suffix += f" UNJUDGED={unjudged}"
                if args.require_decisions:
                    print(f"  {section}: {unjudged} news items without a decisions verdict")
                    failed = True
        print(f"  {section:20s} items={len(kept)}/{len(items)}{suffix}")
        if not kept and not args.allow_empty:
            print(f"  {section}: EMPTY — nothing to print")
            failed = True
    print(f"verify={'failed' if failed else 'ok'} path={date.nested} items={total}")
    return 1 if failed else 0


def cmd_finalize(args: argparse.Namespace) -> int:
    """Verify a published day, stamp ``finished``, and push if meta changed."""
    date = day_path(args.date)
    settings = gitops.GitSettings.from_env()
    scratch = tempfile.TemporaryDirectory(prefix="mb-finalize-")
    repo = Path(scratch.name)
    ok, via, attempt, error = gitops.clone(repo, settings)
    print(f"clone={'ok' if ok else 'failed'} via={via} attempt={attempt}"
          + (f" error={error}" if not ok and error else ""))
    if not ok:
        print("finalize=failed reason=clone")
        return 1
    repo = repo / "repo"

    rc = cmd_verify(argparse.Namespace(repo=str(repo), date=args.date, allow_empty=args.allow_empty, require_decisions=args.require_decisions))
    if rc != 0:
        print("finalize=failed reason=verify")
        return 1

    day = load_day(repo, date)
    day.finished = args.finished or today_iso()
    write_day(repo, day)
    gitops.stage(repo, [f"{date.nested}/meta.json"])
    pushed = gitops.commit_and_push(repo, [f"{date.nested}/meta.json"], f"chore(brief): close {date.flat}", settings)
    print(f"meta={pushed.value} finished={day.finished}")
    if pushed in _PUSH_FAILURES:
        print(f"finalize=failed reason={'push-conflict' if pushed is gitops.Push.CONFLICT else 'push'}")
        return 1
    print("finalize=ok render=github-actions")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.repo)
    managed = managed_days(repo)
    legacy = legacy_days(repo)
    print(f"days managed={len(managed)} legacy={len(legacy)}")
    for date in (managed if not args.date else [day_path(args.date)]):
        tally = counts(repo, date)
        try:
            day = load_day(repo, date)
            stamp = f"started={day.started or '-'} finished={day.finished or '-'}"
        except SectionError as exc:
            stamp = f"meta-error={exc}"
        print(f"  {date.flat} " + " ".join(f"{name}={tally[name]}" for name in SECTIONS) + f" {stamp}")
    for date in legacy:
        print(f"  {date.flat} legacy (markdown only, not pipeline-managed)")
    print("mb=ok")
    return 0


def _root_entries(repo: Path) -> list[tuple[DayPath, bool]]:
    """Every brief on the site, newest first: JSON-managed and legacy alike."""
    entries: list[tuple[DayPath, bool]] = [(date, True) for date in managed_days(repo)]
    entries += [(date, False) for date in legacy_days(repo)]
    entries.sort(key=lambda entry: entry[0].flat, reverse=True)
    return entries


def _generated_drift(repo: Path) -> set[str]:
    """Generated paths whose bytes differ from what the pipeline renders.

    This is the honest definition of "pipeline-owned": a file the next render
    would overwrite. It is also what makes a hand-written legacy day editable
    — nothing renders those, so nothing erases them.
    """
    drift: set[str] = set()
    for date in managed_days(repo):
        drift.update(_render_day(repo, date, write=False))
    if _read_text(repo / "index.md") != render_mod.render_root_index(_root_entries(repo)):
        drift.add("index.md")
    return drift


def _rendered_paths(repo: Path) -> set[str]:
    """Every path the pipeline writes.

    A generated-*named* file outside this set belongs to nobody: a legacy
    day's ``weather.md`` has the right name but no renderer, so nothing can
    vouch for its bytes and nothing will erase them either.
    """
    out: set[str] = {"index.md"}
    for date in managed_days(repo):
        for section in load_day(repo, date).sections:
            out.add(f"{date.nested}/{section}.md")
        out.add(f"{date.nested}/index.md")
    return out


def cmd_generated_check(args: argparse.Namespace) -> int:
    """Guard for CI: a human commit must not edit what the next render erases.

    Only a *mismatch* counts. A generated file that a commit changes to exactly
    what `mb render` produces is not a hand-edit to punish — that is how this
    pipeline's own generated files get introduced — whereas a file that drifts
    is one the render job will silently overwrite on the next push.
    """
    repo = resolve_repo(args.repo)
    rendered = _rendered_paths(repo)
    drift = _generated_drift(repo)
    touched = [
        path
        for path in (args.paths or [])
        if Path(path).name in GENERATED_NAMES and ("/" in path or path == "index.md")
    ]
    offenders = sorted(path for path in touched if path in drift)
    verified = sorted(path for path in touched if path in rendered and path not in drift)
    unrendered = sorted(path for path in touched if path not in rendered)
    for path in verified:
        print(f"  matches the pipeline byte for byte: {path}")
    for path in unrendered:
        # Saying "fine" here would be a lie of omission: it is not verified,
        # merely unprotected. The reader has to know which of the two they have.
        print(f"  not rendered by the pipeline, so not verified either: {path}")
    for path in offenders:
        print(f"  hand-edited generated file (the next render overwrites it): {path}")
    print(
        f"generated-check={'clean' if not offenders else 'violations'} "
        f"owned={len(touched)} offenders={len(offenders)} unverified={len(unrendered)}"
    )
    return 1 if offenders else 0


def _restyle_summary(report: dict[str, dict[str, int]]) -> str:
    """``headline-derived=2 items-split=7`` — the restyle, counted, for logs and commits."""
    totals = {rule: sum(counts.get(rule, 0) for counts in report.values()) for rule in backfill_mod.RESTYLE_RULES}
    return " ".join(f"{rule}={count}" for rule, count in totals.items() if count)


def _backfill_plan(
    repo: Path, date: DayPath, *, apply: bool, allow_restyle: bool = False
) -> tuple[int, list[str], str]:
    """Parse a legacy day, and write it as JSON only if the render reproduces it.

    This is the one place where prose a model formatted becomes data, and the
    failure mode is a quietly reworded newspaper nobody notices because the file
    is "generated now". So the day is refused unless every section file comes back
    byte for byte — or, with ``allow_restyle``, byte for byte against the four
    declared layout normalisations, whose counts are printed and carried into the
    commit message. A refusal writes nothing at all.
    """
    if date in managed_days(repo):
        print(f"backfill=skipped reason=already-managed path={date.nested}")
        print("  the JSON is the source of truth for this day; re-running would discard stored verdicts")
        return 0, [], ""

    parsed = backfill_mod.parse_day(repo, date)
    problems = backfill_mod.round_trip(parsed, allow_restyle=allow_restyle)
    if problems:
        print(f"backfill=refused path={date.nested} reason=round-trip")
        print("  re-rendering the parsed items would change the published paper, so nothing was written:")
        for section, diff in sorted(problems.items()):
            print(f"  {section}: {diff}")
        return 1, [], ""

    report = backfill_mod.restyle_report(parsed) if allow_restyle else {}
    summary = _restyle_summary(report)
    total = sum(len(records) for records in parsed.sections.values())
    for section, records in sorted(parsed.sections.items()):
        counts = report.get(section, {})
        detail = ",".join(f"{rule}:{counts[rule]}" for rule in backfill_mod.RESTYLE_RULES if rule in counts)
        print(f"  {section}: {len(records)} items" + (f"  restyle={detail}" if detail else ""))
    if not apply:
        print(
            f"backfill=ready path={date.nested} items={total}"
            + (f" restyle={summary.replace(' ', ',')}" if summary else "")
            + " — pass --apply to write"
        )
        return 0, [], summary

    written = backfill_mod.write_backfill(repo, parsed)
    paths = sorted(str(path.relative_to(repo)) for path in written)
    paths.append(f"{date.nested}/meta.json")
    print(
        f"backfill=applied date={date.iso} items={total}"
        + (f" restyle={summary.replace(' ', ',')}" if summary else "")
        + f" location={parsed.location!r} started={parsed.started or '—'}"
    )
    if summary:
        print("  layout only: every word, figure and URL is carried across unchanged")
    print("  the markdown files were not touched: the render job rewrites them from this JSON")
    return 0, paths, summary


def cmd_backfill(args: argparse.Namespace) -> int:
    """Convert a legacy Markdown day into the JSON this pipeline owns."""
    date = day_path(args.date)
    apply = args.apply and not args.dry_run

    if args.repo:
        rc, _, _ = _backfill_plan(Path(args.repo).resolve(), date, apply=apply, allow_restyle=args.allow_restyle)
        return rc

    settings = gitops.GitSettings.from_env()
    scratch = tempfile.TemporaryDirectory(prefix="mb-backfill-")
    repo = Path(scratch.name)
    ok, via, attempt, error = gitops.clone(repo, settings)
    print(f"clone={'ok' if ok else 'failed'} via={via} attempt={attempt}"
          + (f" error={error}" if not ok and error else ""))
    if not ok:
        print("backfill=failed reason=clone")
        return 1
    repo = repo / "repo"

    rc, paths, summary = _backfill_plan(repo, date, apply=apply, allow_restyle=args.allow_restyle)
    if rc or not paths:
        return rc
    message = args.message or f"feat(brief): backfill {date.iso} from markdown"
    if summary and not args.message:
        # The commit that changes a published page has to say what it changed,
        # because the JSON diff alone will not show a rewrapped headline.
        message += (
            f"\n\nLayout restyled by --allow-restyle: {summary}."
            "\nProse, figures, holdings and source URLs are carried across verbatim;"
            " the pre-migration files remain in history."
        )
    gitops.stage(repo, paths)
    pushed = gitops.commit_and_push(repo, paths, message, settings)
    print(f"json={pushed.value} files={len(paths)}")
    if pushed in _PUSH_FAILURES:
        print(f"backfill=failed reason={'push-conflict' if pushed is gitops.Push.CONFLICT else 'push'}")
        return 1
    print("backfill=ok render=github-actions")
    return 0


# --------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mb", description="Morning Brief JSON pipeline")
    parser.add_argument("--repo", help="repo root or clone directory (default: walk up from cwd)")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="list published days and item counts")
    status.add_argument("--date")
    status.set_defaults(func=cmd_status)

    ingest_cmd = sub.add_parser("ingest", help="split a draft JSON into per-item files (no git)")
    ingest_cmd.add_argument("--date", required=True)
    ingest_cmd.add_argument("--file", required=True, help="draft: [ {...} ] or {section, items[], meta{}}")
    ingest_cmd.add_argument("--section", choices=SECTIONS)
    ingest_cmd.add_argument("--merge", action="store_true", help="keep existing items in the section dir")
    ingest_cmd.add_argument("--meta", action="store_true", help="also write meta.json from the draft's meta block")
    ingest_cmd.set_defaults(func=cmd_ingest)

    publish = sub.add_parser("publish", help="clone (unless --repo), ingest, commit, push")
    publish.add_argument("--date", required=True)
    publish.add_argument("--file", help="one draft JSON file (single section)")
    publish.add_argument("--dir", help="fixture dir with <section>.json drafts: publishes them all in one clone")
    publish.add_argument("--only", default="", help="with --dir: comma-separated sections to publish")
    publish.add_argument("--section", choices=SECTIONS)
    publish.add_argument("--verdicts", help="decisions-API verdicts file to apply before pushing")
    publish.add_argument("--location", default="")
    publish.add_argument("--started", default="")
    publish.add_argument("--finished", default="")
    publish.add_argument("--merge", action="store_true")
    publish.add_argument("--render", action="store_true", help="also render the markdown here instead of in CI")
    publish.set_defaults(func=cmd_publish)

    decide = sub.add_parser("decide", help="apply decisions-API verdicts to items on disk")
    decide.add_argument("--date", required=True)
    decide.add_argument("--verdicts", required=True)
    decide.add_argument("--section", choices=SECTIONS, help="apply only this section's verdicts")
    decide.add_argument("--dry-run", action="store_true")
    decide.set_defaults(func=cmd_decide)

    render = sub.add_parser("render", help="generate the markdown from JSON")
    render.add_argument("--date", help="default: every pipeline-managed day")
    render_mode = render.add_mutually_exclusive_group()
    render_mode.add_argument("--write", action="store_true", help="write the generated files")
    render_mode.add_argument("--check", action="store_true", help="default: fail if they are stale")
    render.set_defaults(func=cmd_render)

    verify = sub.add_parser("verify", help="check a day's JSON is complete and valid")
    verify.add_argument("--date", required=True)
    verify.add_argument("--allow-empty", action="store_true")
    verify.add_argument(
        "--require-decisions",
        action="store_true",
        help="fail on stock news with no verdict (diagnostic here; finalize enforces it by default)",
    )
    verify.set_defaults(func=cmd_verify)

    finalize = sub.add_parser("finalize", help="clone, verify, stamp finished, push meta.json")
    finalize.add_argument("--date", required=True)
    finalize.add_argument("--finished", default="")
    finalize.add_argument("--allow-empty", action="store_true")
    finalize.add_argument(
        "--require-decisions",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="the day may not close with stock news nobody judged (default); "
        "--no-require-decisions is for a run where the classifier was unavailable",
    )
    finalize.set_defaults(func=cmd_finalize)

    gen = sub.add_parser("generated-check", help="CI guard: flag hand-edits to generated files")
    gen.add_argument("paths", nargs="*")
    gen.set_defaults(func=cmd_generated_check)

    backfill = sub.add_parser(
        "backfill",
        help="convert a legacy Markdown day to JSON, refused unless the render is byte-identical",
    )
    backfill.add_argument("--date", required=True)
    backfill.add_argument("--apply", action="store_true", help="write the JSON (default: parse and report)")
    backfill.add_argument("--dry-run", action="store_true", help="with --apply: parse and report only")
    backfill.add_argument(
        "--allow-restyle",
        action="store_true",
        help="accept the four declared layout normalisations (headline, blank lines between "
        "items, bare source lines, inline Flags into the trailing list); each is counted and "
        "named in the output and the commit message",
    )
    backfill.add_argument("--message", default="")
    backfill.set_defaults(func=cmd_backfill)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SectionError as exc:
        print(f"mb=failed reason=invalid-json {exc}")
        return 1
    except decide_mod.VerdictError as exc:
        print(f"mb=failed reason=invalid-verdicts {exc}")
        return 1
    except FileNotFoundError as exc:
        print(f"mb=failed reason={exc}")
        return 1
    except RuntimeError as exc:
        print(f"mb=failed reason={exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
