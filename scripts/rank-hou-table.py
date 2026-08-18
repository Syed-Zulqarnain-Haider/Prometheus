#!/usr/bin/env python3
"""Add the rank-by dropdown to the HOU Performance table.

Same control the Top Apps table got, adapted to how this table gets its data. Top Apps
had to change the SERVER sort with the picker, because it only ever holds the first 100
rows of a keyset-paginated endpoint. HOU is the opposite case: useBreakdown returns
EVERY HOU group and the table merges them client-side, so the full population is already
in hand and a client-side re-sort is exactly correct - no second request, no server
round-trip on change.

The options are built FROM the visible metric columns (minus the HOU identity column),
so they are RBAC-filtered for free: a column a role cannot see is a rank option that
role is never offered, and a future column added to METRIC_COLUMNS becomes a rank
option here with no edit.

Rides on the sortId/action props that scripts/rank-top-apps.py added to MetricTable -
run that first (the deploy order already does).

Anchored: every anchor must appear EXACTLY once or nothing is written. Idempotent.
Frontend rebuild required; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

TABLE = Path("frontend/components/overview/hou-table.tsx")
REVENUE_TABLE = Path("frontend/components/overview/revenue-table.tsx")

IMPORT_ANCHOR = 'import { useMemo } from "react";\n'
IMPORT_NEW = 'import { useMemo, useState } from "react";\n'

STATE_ANCHOR = """  // Fetch exactly the additive measures the visible columns need (all already permitted,
  // so the breakdown's own metric-permission check passes).
"""
STATE_ADD = """  // Rank options are the visible metric columns themselves - RBAC-filtered for free,
  // and a future METRIC_COLUMNS addition becomes an option here with no edit. Client-side
  // sorting is CORRECT for this table (unlike Top Apps): the breakdown returns every HOU
  // group, so the full population is already in hand.
  const rankOptions = columns.filter((c) => c.id !== HOU_IDENTITY.id);
  const [rankBy, setRankBy] = useState<string>("gross");
  // A saved choice can outlive the role that could see it; fall back rather than
  // sorting by nothing.
  const activeRank = rankOptions.find((c) => c.id === rankBy) ?? rankOptions[0];

"""

RENDER_ANCHOR = """  return (
    <MetricTable
      title="HOU Performance"
      columns={columns}
      rows={rows}
      rowKey={houKey}
      isLoading={breakdown.isLoading}
      isError={breakdown.isError}
    />
  );
"""
RENDER_NEW = """  return (
    <MetricTable
      title="HOU Performance"
      columns={columns}
      rows={rows}
      rowKey={houKey}
      isLoading={breakdown.isLoading}
      isError={breakdown.isError}
      sortId={activeRank?.id}
      action={
        rankOptions.length > 1 ? (
          <select
            aria-label="Rank HOUs by"
            value={activeRank?.id ?? ""}
            onChange={(event) => setRankBy(event.target.value)}
            className="h-8 rounded-[var(--radius-inner)] border border-input bg-background px-2 text-xs outline-none focus:ring-1 focus:ring-ring"
          >
            {rankOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        ) : undefined
      }
    />
  );
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not TABLE.exists():
        die(f"{TABLE} not found - run from the repository root")
    # Hard prerequisite: MetricTable must already accept sortId/action.
    if "sortId?: string" not in REVENUE_TABLE.read_text():
        die(f"{REVENUE_TABLE} lacks the sortId prop - run scripts/rank-top-apps.py first")

    text = TABLE.read_text()
    if "rankOptions" in text:
        print("already ranked - nothing to do")
        return

    for anchor in (IMPORT_ANCHOR, STATE_ANCHOR, RENDER_ANCHOR):
        if text.count(anchor) != 1:
            first = anchor.splitlines()[0].strip()
            die(f"{TABLE}: expected exactly one {first!r}, found {text.count(anchor)}")

    text = text.replace(IMPORT_ANCHOR, IMPORT_NEW, 1)
    text = text.replace(STATE_ANCHOR, STATE_ADD + STATE_ANCHOR, 1)
    text = text.replace(RENDER_ANCHOR, RENDER_NEW, 1)
    TABLE.write_text(text)
    print(f"patched {TABLE}: rank-by dropdown added")
    print("\nRebuild the frontend: docker compose -f docker-compose.prod.yml up -d --build frontend")


if __name__ == "__main__":
    main()
