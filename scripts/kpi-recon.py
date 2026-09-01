#!/usr/bin/env python3
"""READ-ONLY. Everything the Looker-parity work needs, and nothing else. Writes nothing.

WHY THIS RUNS BEFORE ANY OF IT IS WRITTEN
-----------------------------------------
The owner's Looker screenshot settles the definitions by arithmetic:

    Ads 79.5K + IAP 26.8K = 106.3K = Gross Revenue          (exact)
    ROAS 127.29% x 82.0K UA        = 104.4K                 (a DIFFERENT revenue)
    104.4K - 82.0K UA - 1.48K tech = 20.9K ~ Net Revenue 20.5K

So the IAP basis CHANGES between cards: Gross Revenue uses IAP gross, while Net Revenue
and ROAS use IAP net, after refunds. Our locked contract defines total_revenue_usd as
total_iap_net_usd + total_ad_revenue_usd - the NET basis - so anything labelled "gross"
and computed from it is understated by exactly the refunds. That is almost certainly the
wrong number in the apps table.

"Almost certainly" is not good enough to start editing revenue columns, because there is
also an rpt_gross_revenue_usd column that the Overview KPIs read and that this repository's
copy of the metric registry does not contain. One of those two is what the table shows.
This prints enough to know which, rather than shipping a third disagreeing number.

It also collects what the rest of the batch needs: the real column lists to add IAP / Ad
ROAS / IAP ROAS to, where totals rows would go, whether app_category is already exposed as
a filter, and what the freshness banner actually claims.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
RULE = "=" * 78


def head(title: str) -> None:
    print(f"\n\n{RULE}\n{title}\n{RULE}")


def sub(title: str) -> None:
    print(f"\n--- {title} " + "-" * max(0, 70 - len(title)))


def dump(rel: str, *, cap: int = 200) -> None:
    path = ROOT / rel
    if not path.exists():
        print(f"  MISSING: {rel}")
        return
    lines = path.read_text(errors="replace").splitlines()
    print(f"  {rel}  ({len(lines)} lines)")
    for i, line in enumerate(lines[:cap], 1):
        print(f"  {i:>4}  {line}")
    if len(lines) > cap:
        print(f"  … {len(lines) - cap} more")


def grep(rel: str, pattern: str, *, context: int = 0) -> None:
    path = ROOT / rel
    if not path.exists():
        print(f"  MISSING: {rel}")
        return
    rx = re.compile(pattern)
    lines = path.read_text(errors="replace").splitlines()
    wanted: set[int] = set()
    for i, line in enumerate(lines):
        if rx.search(line):
            wanted.update(range(max(0, i - context), min(len(lines), i + context + 1)))
    if not wanted:
        print(f"  {rel}: no match for {pattern!r}")
        return
    print(f"  {rel}")
    last = -2
    for i in sorted(wanted):
        if i != last + 1:
            print("        …")
        print(f"  {i + 1:>4}  {lines[i]}")
        last = i


def find(pattern: str, *roots: str) -> list[Path]:
    rx = re.compile(pattern)
    out: list[Path] = []
    for root in roots:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            if {"node_modules", ".next", "__pycache__"} & set(path.parts):
                continue
            if rx.search(path.read_text(errors="replace")):
                out.append(path)
    return out


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root on the server.", file=sys.stderr)
        return 1
    print("READ-ONLY. This run writes nothing.")

    # ── A. which "gross" is real ────────────────────────────────────────────────────
    head("A.  THE TWO GROSSES  -  which column does the apps table actually show?")
    sub("app/core/metric_registry.py: every revenue-ish column")
    grep("backend/app/core/metric_registry.py", r"gross|revenue|iap|ad_rev|tech_cost|rpt_")
    sub("is rpt_gross_revenue_usd served at all?")
    roots = ("backend/app", "frontend/components", "frontend/lib")
    for path in find(r"rpt_gross_revenue_usd", *roots):
        print(f"  {path}")

    # ── B. the tables that show wrong numbers ───────────────────────────────────────
    head("B.  THE TABLES  -  current columns, and where IAP / Ad ROAS / IAP ROAS go")
    for rel in (
        "frontend/components/apps/apps-explorer.tsx",
        "frontend/components/overview/revenue-table.tsx",
        "frontend/components/overview/top-apps-table.tsx",
    ):
        sub(rel)
        grep(rel, r"label:|requires:|value:|field:|id: \"", context=1)

    # ── C. the KPI strip ────────────────────────────────────────────────────────────
    head("C.  THE KPI STRIP  -  what it reads today, vs the eight Looker cards")
    print(
        "  Looker: Total Installs | Ads Revenue | IAP | Gross Revenue\n"
        "          Tech Cost      | UA Cost     | Net Revenue | ROAS\n"
        "  each with a delta vs the comparison period and a sparkline."
    )
    dump("frontend/components/overview/kpi-row.tsx", cap=120)

    # ── D. data maturity ────────────────────────────────────────────────────────────
    head("D.  DATA MATURITY  -  what the banner claims and where it comes from")
    for path in find(r"bq_built_at|freshness|data as of|dataAsOf", "backend/app", "frontend"):
        sub(str(path))
        grep(str(path.relative_to(ROOT)), r"bq_built_at|freshness|as of|asOf|stale|lag", context=2)

    # ── E. filters ──────────────────────────────────────────────────────────────────
    head("E.  FILTERS  -  is app_category already exposed?")
    sub("backend: filter model and the dimension endpoints")
    grep("backend/app/schemas/metrics.py", r"apps|pods|publishers|hou|platform|category")
    for path in find(r"app_category", "backend/app", "frontend"):
        print(f"  mentions app_category: {path}")
    sub("frontend/components/filters/dimensions.ts")
    dump("frontend/components/filters/dimensions.ts", cap=70)

    print(f"\n\n{RULE}\nNothing was written. Every section above only read files.\n{RULE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
