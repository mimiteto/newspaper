# Morning Brief

Published briefs for Novi Iskar: weather, holdings, Bulgarian economic and
labour-law news. Site: <https://mimiteto.github.io/newspaper/>

## The one rule

**JSON is the source of truth. Markdown is generated.**

Every `.md` file in a `YYYY/MM/DD/` directory here — and the root `index.md` —
is produced by `mb render` from the JSON next to it, by
[`.github/workflows/render-brief.yml`](.github/workflows/render-brief.yml).
Editing a generated file by hand is a bug: the next render overwrites it, and CI
fails the PR that did it (`mb generated-check`).

## Layout

    YYYY/MM/DD/
      meta.json                        day record: mb/day@1
      weather/                         section directory, one per section
        10-temperature.json            one item per file: mb/item@1
        20-conditions.json
      stocks/
        10-snapshot.json               kind=context -> lead paragraph
        20-sapse.json                  one holding (+ its news[])
        90-timing.json                 kind=flag -> Flags: block
      bulgarian-finances/
        10-vat-threshold.json
      index.md                         GENERATED day index
      weather.md  stocks.md  bulgarian-finances.md   GENERATED sections

    index.md                           GENERATED homepage (all days, newest first)
    mb/                                the pipeline (Python, stdlib only)
    tests/                             unit tests
    .github/workflows/render-brief.yml the render pipeline

The date directory is always nested (`2026/11/22`), never flat. `mb` normalises
a flat `YYYY-MM-DD` argument and refuses anything else, which is why the old
`repair-date-path.sh` no longer exists.

## Item schema (`mb/item@1`)

Common fields — everything else is rejected, so a typo like `soruces` fails at
publish time instead of silently dropping a citation:

| field | meaning |
|---|---|
| `id` | slug, unique in the section, becomes the filename |
| `order` | sort key; omit it and `ingest` assigns 10, 20, 30… |
| `kind` | `item` (default) · `context` (lead paragraph) · `flag` (Flags block) |
| `label` | bold lead-in; defaults to the ticker, or `TICKER — Fund name` for an ETF |
| `text` | prose |
| `as_of` | what timestamp the numbers are valid for |
| `sources` | `["https://…"]` or `[{"title": "…", "url": "…"}]` |
| `flags` | extra caveats appended to the section's `Flags:` block |
| `relevance` | decisions-API verdict (see below) |

Per-section extras: `weather` → `metric`, `provider`;
`bulgarian-finances` → `topic`, `bill`, `effective_date`, `amount`;
`stocks` → `ticker`, `name`, `listing`, `currency`, `price`, `change_abs`,
`change_pct_1d|5d|1m`, `holdings[]`, `news[]`.

`stocks.holdings[]` renders the ETF top-5 list; `stocks.news[]` is the unit the
relevance classifier judges:

```json
{
  "id": "ms-conference",
  "headline": "SAP says it remains on track with its 2026 plan",
  "summary": "CFO repeated the 2026 outlook at the Morgan Stanley conference.",
  "published": "2026-11-19",
  "url": "https://…",
  "source": "Investing.com",
  "relevance": {
    "brief": true, "price_move": true, "category": "guidance",
    "confidence": 0.81, "verdict": "keep",
    "decided_by": "llama.cpp/unsloth/Qwen3.8-Flash-Next-GGUF:IQ4_XS",
    "decided_at": "2026-11-22T10:00:00+02:00"
  }
}
```

## News relevance

Each news item carries two booleans from a classifier (the Decisions API, driven
from the `mb_decide` pi tool), and one derived `verdict`:

| `brief` | `price_move` | `verdict` | what the paper does |
|---|---|---|---|
| yes | any | `keep` | prints it in full, tagged with its category |
| no | yes | `context` | demotes it to a headline-only line |
| no | no | `drop` | does not print it; the JSON keeps the record |

The rendered section always says what was filtered — e.g. `News triaged by the
decisions API: 2 of 3 kept, model: …` — so a quiet day is visibly a decision,
not an accident.

A verdict also carries `ambiguous`: the tool sets it when the classifier's answer
came back near a coin flip (`mb verify` then reports `uncertain=N`, the footer
reads `2 of 3 kept, 1 judged uncertain`). A dropped item is a decision; an
uncertain one is a question, and printing the second as the first is the failure
mode this record exists to prevent.

A verdict with no `news_id` judges the whole item. That is right for Bulgaria,
where an item *is* a story, and refused for `stocks`: there an item is a line on
the watch list, `drop` hides items, so a classifier asked about news and finding
none would delete a holding from the paper. Triage in `stocks` is done against
`news[]`, never against the line.

## Working with it

Python 3.11+, standard library only, no install step:

```bash
python3 -m mb status                                  # days and item counts
python3 -m mb ingest  --date 2026-11-22 --file draft.json --section stocks
python3 -m mb decide  --date 2026-11-22 --verdicts verdicts.json
python3 -m mb publish --date 2026-11-22 --dir drafts/ --verdicts verdicts.json   # whole day, one clone
python3 -m mb publish --date 2026-11-22 --file draft.json --section stocks --verdicts verdicts.json
python3 -m mb render  --write                         # regenerate every day + homepage
python3 -m mb render  --check                         # CI: fail if generated files are stale
python3 -m mb verify  --date 2026-11-22 --require-decisions
python3 -m mb finalize --date 2026-11-22              # verify + stamp finished + push
python3 -m mb --repo ./clone finalize --date 2026-11-22   # same, locally: no clone, no push
python3 -m mb backfill --date 2026-11-22              # legacy Markdown day -> JSON, byte-gated
python3 -m unittest discover -s tests
```

`publish --dir <fixture>` takes a directory of `<section>.json` drafts and
publishes the whole day in one clone, one commit per section — that is what the
morning-brief run does. `--only stocks` re-publishes a single section, and an
unchanged section commits nothing (`section=noop`), so retrying is free.

The pi side calls the same commands through
`~/.pi/agent/scripts/morning-brief/mb-cli`, so the box and CI never run two
dialects of the same logic.

`publish`, `finalize` and `backfill` clone a fresh copy themselves when you do
not name a checkout (a publish decision is only worth what a current
`origin/master` makes it): SSH first through the gcr ssh-agent, HTTPS fallback,
advisory lock and retries — because a re-run from the box can still land while
Actions is pushing generated Markdown. See `mb/gitops.py`. Naming `--repo` flips
all three to "this checkout, origin untouched", which is what makes a rehearsal
of the real commands possible at all; a write command that ignored it would turn
a dry run into a publication.

## Legacy days

Days published before this pipeline are Markdown-only. `mb render` never touches
their files; it only lists them on the homepage, so every historical link works.

To move one over, `mb backfill` parses its Markdown into JSON items:

```bash
python3 -m mb backfill --date 2026-11-22           # parse and report, write nothing
python3 -m mb backfill --date 2026-11-22 --apply   # write the JSON (and push, without --repo)
```

It is gated, because the failure mode is a newspaper quietly reworded by a
parser and then re-published as if it had always been generated: every section
file is rendered back from the parsed items and compared, byte for byte, with
what is on disk. One difference refuses the day (`backfill=refused
reason=round-trip`) and nothing at all is written — naming the construct that
blocked it, because a diff fragment at 07:00 is not a diagnosis:

```text
  weather: flags are one inline paragraph ("Flags: …"); the pipeline prints a trailing "Flags:" list
  stocks:  the headline is authored ('# Holdings — Sat 14 Nov 2026') while the pipeline derives '# Holdings — 14 Nov 2026'
```

Anything the renderer cannot reproduce stays a refusal, with the construct named:
a mid-file lead paragraph, a `Flags:` sentence in the middle of a section, a day
that printed only some of its sections. The homepage lists those days anyway and
`generated-check` reports them as unverified rather than pretending otherwise.

### `--allow-restyle`

Five layout differences lose nothing, so `--allow-restyle` accepts exactly those:

| rule | what it changes |
| --- | --- |
| `headline-derived` | an authored `# Holdings — Sat 14 Nov 2026` becomes the headline derived from the date |
| `items-split` | items that ran together get the blank line the renderer puts between blocks |
| `sources-bare` | `- https://…` prints bare; several links on one line become one per line |
| `holdings-format` | `5. **Name** — 2.1%` becomes `**5.** Name — 2.1%` |
| `flags-inline` | a closing `Flags: …` sentence becomes the trailing `Flags:` list |

With the flag, the gate compares the render against **the original file with
those five rules applied** — so a sixth difference still fails — and the counts
are printed and written into the commit message of the commit that changes a page:

```text
backfill=applied date=2026-11-03 items=33 restyle=items-split=8,flags-inline=2
```

What no flag buys is movement. Reordering a lead paragraph below the items it
introduces, or a caveat away from the sentence it qualifies, is an edit to the
paper, and the refusal says so: `44 line(s) moved: … Moving prose is an edit, not
a migration`. A `## ETFs` grouping, by contrast, needed no concession — it is a
`kind: "heading"` item now, printed where the day put it.

What comes across: lead paragraphs as `context` items, `**Label.**` items with
their source URLs (bulleted in the old papers, bare in the pipeline's own
output), holdings lines back into `holdings[]` — including the
figure's authored precision, so etftrace's `2.4%` stays `2.4%` rather than
becoming `2.40%` (`weight_display` carries it) — and the `Flags:` block as
`kind: flag` items. The old `Started`/`Finished` stamps are read back out of the
hand-written `index.md`, and prose is carried over verbatim: rewording a legacy
day is a deliberate edit, not something a parser does on its own.

What does not: a day whose Markdown already contains triaged news bullets —
bullets that are neither source URLs nor the pipeline's own `Flags:` list. Those
were rendered from `news[]` verdicts the paper deliberately does not print, so
rebuilding them would mean inventing decisions — the backfill refuses instead.

Without `--allow-restyle` the day's own `index.md` is the only file that changes,
because it becomes a generated page: item counts, generated footer, no
`Created by` line. The Markdown is not written by the migration itself — the
render job regenerates it from the JSON, which is the whole point.
