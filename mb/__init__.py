"""Morning Brief toolkit.

Source of truth for a published day is JSON, never Markdown:

    YYYY/MM/DD/meta.json                     day metadata (mb/day@1)
    YYYY/MM/DD/<section>/<order>-<id>.json    one item per file (mb/item@1)

Everything Markdown you see in this repository — the three section files, the
per-day index.md and the repository-root homepage — is GENERATED from that JSON
by ``python3 -m mb render`` (run in CI on every JSON push, see
.github/workflows/render-brief.yml). Hand-editing a generated .md file is a bug:
the next render overwrites it.

Stdlib only, Python >= 3.11, so both GitHub Actions runners and the pi helper
that calls into a fresh clone can run it with no install step.
"""

from mb.model import Day, Item, SectionError
from mb.paths import SECTIONS, DayPath, day_path, parse_date

__all__ = [
    "Day",
    "Item",
    "SECTIONS",
    "DayPath",
    "SectionError",
    "day_path",
    "parse_date",
]
