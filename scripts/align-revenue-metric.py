#!/usr/bin/env python3
"""Make YTD/MTD progress and the Monthly Revenue Trend use REPORTED gross revenue.

The Revenue KPI card reports ``rpt_gross_revenue_usd`` (the reported ladder), but the
two progress-to-target donuts and the Monthly Revenue Trend between them computed from
``total_revenue_usd`` (IAP net + ad revenue) - two different definitions of "revenue"
on the same screen, so YTD/MTD never reconciled with the card above them. Owner call:
the reported figure is the truth, everything aligns to it.

Three surfaces, one metric swap each:

  backend/app/services/pacing_service.py       _REVENUE constant - drives the pacing
                                               actuals, projections, and the RBAC gate
                                               on disclosing the target (both metrics
                                               sit in the same profitability group, so
                                               nobody gains or loses visibility)
  frontend/components/overview/revenue-progress.tsx  the donuts' actual
  frontend/components/overview/monthly-trend.tsx     the bar chart between them

Anchored: every anchor must appear the EXPECTED number of times or nothing is written -
all files validate before any is touched, because donuts on one definition and the
trend on another is exactly the inconsistency being fixed. Idempotent. Backend restart
+ frontend rebuild; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

PACING = Path("backend/app/services/pacing_service.py")
PROGRESS = Path("frontend/components/overview/revenue-progress.tsx")
TREND = Path("frontend/components/overview/monthly-trend.tsx")

PACING_ANCHOR = '_REVENUE = "total_revenue_usd"\n'
PACING_NEW = (
    "# The REPORTED figure, matching the Revenue KPI card - not total_revenue_usd\n"
    "# (IAP net + ad), which made YTD/MTD disagree with the card on the same screen.\n"
    '_REVENUE = "rpt_gross_revenue_usd"\n'
)

PROGRESS_ANCHOR = "  const actual = summary.data?.current.total_revenue_usd ?? 0;\n"
PROGRESS_NEW = (
    "  // Reported gross revenue - the same metric the Revenue KPI card shows, so the\n"
    "  // donut and the card can never tell two different YTD/MTD stories.\n"
    "  const actual = summary.data?.current.rpt_gross_revenue_usd ?? 0;\n"
)

TREND_OLD = '"total_revenue_usd"'
TREND_NEW = '"rpt_gross_revenue_usd"'
TREND_EXPECTED = 4  # two hook calls + two metricValues reads


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    for path in (PACING, PROGRESS, TREND):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    pacing = PACING.read_text()
    progress = PROGRESS.read_text()
    trend = TREND.read_text()

    todo: dict[Path, str] = {}

    if "rpt_gross_revenue_usd" in pacing:
        print(f"{PACING}: already aligned")
    else:
        if pacing.count(PACING_ANCHOR) != 1:
            die(f"{PACING}: expected exactly one {PACING_ANCHOR.strip()!r}")
        todo[PACING] = pacing.replace(PACING_ANCHOR, PACING_NEW, 1)

    if "rpt_gross_revenue_usd" in progress:
        print(f"{PROGRESS}: already aligned")
    else:
        if progress.count(PROGRESS_ANCHOR) != 1:
            die(f"{PROGRESS}: expected exactly one {PROGRESS_ANCHOR.strip()!r}")
        todo[PROGRESS] = progress.replace(PROGRESS_ANCHOR, PROGRESS_NEW, 1)

    if TREND_NEW in trend:
        print(f"{TREND}: already aligned")
    else:
        found = trend.count(TREND_OLD)
        if found != TREND_EXPECTED:
            die(f"{TREND}: expected {TREND_EXPECTED} of {TREND_OLD}, found {found}")
        todo[TREND] = trend.replace(TREND_OLD, TREND_NEW)

    if not todo:
        print("already aligned - nothing to do")
        return

    for path, text in todo.items():
        path.write_text(text)
        print(f"patched {path}")

    print("\nYTD/MTD progress, pacing projections and the monthly trend now all read")
    print("rpt_gross_revenue_usd - the same figure as the Revenue KPI card.")
    print("Rebuild both: docker compose -f docker-compose.prod.yml up -d --build backend frontend")


if __name__ == "__main__":
    main()
