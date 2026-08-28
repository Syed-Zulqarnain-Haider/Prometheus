#!/usr/bin/env python3
"""Read-only. Everything the P0 items in the platform audit need, and nothing else.

WRITES NOTHING. This exists because the audit found six contradictions that each have
exactly one correct fix and several plausible wrong ones, and the deployed tree is not
the tree in this repository. Guessing at a fix for "two endpoints disagree about the
monthly target" without reading both endpoints is how you end up shipping a third
disagreeing number.

What it prints, in the order the audit ranks them:

  A. THE TWO TARGETS (audit #1). Both pacing routes and both services, side by side.
     One panel says 61.9% behind and the other says 38% ahead, for the same month.

  B. THE ADMIN ROUTE A FINANCE ACCOUNT CALLED (audit, security section). Which router
     `/admin/pod-owner-performance` hangs off, and what that router requires. If it is
     on the capability-gated admin router the request simply 403s and the bug is that
     the page asks at all; if it is registered anywhere else, that is a live hole and
     everything else waits.

  C. THE DRILL-DOWN (audit #6). Clicking a HOU fetched every pod globally - no `hou=`
     filter on the request - so a child rendered at 3x its parent.

  D. THE DATE WINDOW (audit #7). The preset label and the queried range disagree on
     first load, and "last 7 days" includes a day with no data.

  E. FRESHNESS (audit #3). The badge says "success" for a load that brought almost no
     store installs for six days. It checks that a load finished, not that it loaded.

  F. ANOMALIES (audit #11). 13537% from a near-zero baseline, rendered in green.

  G. THE ASSISTANT (audit #17). Down, with a correlation ref that is logged nowhere -
     a gap I flagged when we first enabled it and never closed.
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
    print(f"\n--- {title} " + "-" * max(0, 72 - len(title)))


def dump(path: Path, *, first: int | None = None, cap: int = 400) -> None:
    if not path.exists():
        print(f"  MISSING: {path}")
        return
    lines = path.read_text().splitlines()
    shown = lines[:first] if first else lines
    print(f"  {path}  ({len(lines)} lines)")
    for i, line in enumerate(shown[:cap], 1):
        print(f"  {i:>4}  {line}")
    if len(shown) > cap:
        print(f"  … {len(shown) - cap} more lines")


def regions(path: Path, needles: tuple[str, ...], before: int = 4, after: int = 26) -> None:
    """The neighbourhoods around each needle - enough to read, not the whole file."""
    if not path.exists():
        print(f"  MISSING: {path}")
        return
    lines = path.read_text().splitlines()
    wanted: set[int] = set()
    for i, line in enumerate(lines):
        if any(n in line for n in needles):
            wanted.update(range(max(0, i - before), min(len(lines), i + after)))
    if not wanted:
        print(f"  {path}: none of {needles} appear")
        return
    print(f"  {path}  ({len(lines)} lines)")
    last = -2
    for i in sorted(wanted):
        if i != last + 1:
            print("        …")
        print(f"  {i + 1:>4}  {lines[i]}")
        last = i


def find(*patterns: str, where: str = "backend/app") -> list[Path]:
    out: list[Path] = []
    for path in sorted((ROOT / where).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text()
        if any(p in text for p in patterns):
            out.append(path)
    return out


def find_ts(*patterns: str) -> list[Path]:
    out: list[Path] = []
    for pattern in ("frontend/**/*.tsx", "frontend/**/*.ts"):
        for path in sorted(ROOT.glob(pattern)):
            if {"node_modules", ".next"} & set(path.parts):
                continue
            text = path.read_text()
            if any(p in text for p in patterns):
                out.append(path)
    return out


# ── A. the two monthly targets ─────────────────────────────────────────────────────
def section_targets() -> None:
    head("A.  TWO MONTHLY TARGETS, OPPOSITE VERDICTS  (audit #1)")
    print(
        "  One panel: MTD $137.8K of $400K, 61.9% behind.\n"
        "  The other: MTD $137.8K of $100K, 38% ahead.\n"
        "  Both routes and both services follow, so the fix can pick a winner rather\n"
        "  than inventing a third."
    )
    for rel in ("backend/app/api/v1/metrics.py", "backend/app/api/v1/scoped_targets.py"):
        sub(rel)
        regions(ROOT / rel, ("pacing", "forecast", "target"))
    for path in find("def pacing", "monthly_target", "revenue_target", "def target"):
        if "service" in path.name or "service" in str(path.parent):
            sub(str(path))
            regions(path, ("def pacing", "target", "month"))
    sub("the targets tables")
    for rel in ("backend/app/models/targets.py", "backend/app/models/scoped_targets.py"):
        dump(ROOT / rel)


# ── B. the admin route a finance account called ────────────────────────────────────
def section_admin_route() -> None:
    head("B.  ADMIN ROUTE CALLED BY A FINANCE ACCOUNT  (audit, security)")
    print(
        "  The audit saw GET /api/v1/admin/pod-owner-performance fire during a normal\n"
        "  Overview render for a finance-role account. It did NOT claim data came back.\n"
        "  Two very different bugs, and this is what tells them apart:\n"
        "    - on the capability-gated admin router  -> the call 403s; the bug is that\n"
        "      the page asks at all (noise, and a widget rendered for the wrong role)\n"
        "    - registered anywhere else              -> a live hole; everything waits"
    )
    hosts = find("pod-owner-performance", "pod_owner_performance")
    if not hosts:
        print("\n  Not found under backend/app - check the deployed tree, not this one.")
    for path in hosts:
        sub(str(path))
        text = path.read_text()
        for match in re.finditer(r"^\w+\s*=\s*APIRouter\((?:[^)]*\n)*?[^)]*\)", text, re.M):
            print("  ROUTER:")
            for line in match.group(0).splitlines():
                print(f"        {line}")
        regions(path, ("pod-owner-performance", "pod_owner_performance", "require_capability"))

    sub("every router and what it requires")
    for path in sorted((ROOT / "backend/app/api/v1").glob("*.py")):
        text = path.read_text()
        for match in re.finditer(r"^(\w+)\s*=\s*APIRouter\((?P<args>(?:[^)]*\n)*?[^)]*)\)", text, re.M):
            args = " ".join(match.group("args").split())
            print(f"  {path.name:<24} {match.group(1):<14} {args[:120]}")

    sub("who renders the pod-owner widget on the frontend, and under what guard")
    for path in find_ts("pod-owner-performance", "PodOwnerPerformance", "usePodOwnerPerformance"):
        regions(path, ("pod-owner-performance", "PodOwner", "capabilities", "roles"), before=6, after=14)


# ── C. the drill-down ──────────────────────────────────────────────────────────────
def section_drilldown() -> None:
    head("C.  DRILL-DOWN IGNORES THE PARENT  (audit #6)")
    print(
        "  Clicking a HOU worth ~$27K opened a child worth $82K, because the request\n"
        "  carried group_by=pod and no hou= filter. The breadcrumb was decorative."
    )
    for path in find_ts("revenue-drill", "RevenueDrill", "breadcrumb", "drill"):
        if "drill" in path.name.lower():
            sub(str(path))
            dump(path)


# ── D. the date window ─────────────────────────────────────────────────────────────
def section_dates() -> None:
    head("D.  PRESET LABEL vs QUERIED WINDOW  (audit #7)")
    print(
        '  On first load the pill read "This month so far" while the request asked for\n'
        "  2026-07-29 to 2026-08-27 - a rolling 30 days. Re-picking the same preset\n"
        "  asked for 2026-08-01 to 2026-08-28. Same label, same day, two numbers.\n"
        '  Separately "Last 7 days" includes today, which has no data yet, so the\n'
        "  per-day averages divide by seven when five days have figures."
    )
    sub("frontend/lib/filters.ts")
    dump(ROOT / "frontend/lib/filters.ts")
    for rel in ("frontend/lib/use-filters.ts", "frontend/components/filters/filter-bar.tsx"):
        sub(rel)
        regions(
            ROOT / rel,
            ("useSearchParams", "router.replace", "router.push", "preset", "hydrat", "localStorage"),
            before=5,
            after=18,
        )


# ── E. freshness ───────────────────────────────────────────────────────────────────
def section_freshness() -> None:
    head("E.  FRESHNESS SAYS 'SUCCESS' FOR A LOAD THAT BROUGHT ALMOST NOTHING  (audit #3)")
    print(
        "  Store installs collapsed from 80-95K/day to near zero on 21 Aug and the\n"
        "  badge has read success ever since. It checks that a load FINISHED, not that\n"
        "  it loaded a plausible volume. The sync already has a row-delta check - this\n"
        "  is about what the badge is allowed to claim."
    )
    for path in find("bq_built_at", "is_stale", "def freshness", "source_freshness"):
        sub(str(path))
        regions(path, ("bq_built_at", "is_stale", "freshness", "rows_loaded", "status"))


# ── F. anomalies ───────────────────────────────────────────────────────────────────
def section_anomalies() -> None:
    head("F.  ANOMALIES WITH NO BASELINE FLOOR  (audit #11)")
    print(
        "  13537%, 13042%, 6658% - every one a division by a near-zero baseline, and\n"
        "  every one rendered green as though it were good news."
    )
    for path in find("_score", "anomaly", "def evaluate"):
        if "anomal" in path.name:
            sub(str(path))
            dump(path, cap=260)


# ── G. the assistant ───────────────────────────────────────────────────────────────
def section_assistant() -> None:
    head("G.  ASSISTANT DOWN, REF LOGGED NOWHERE  (audit #17)")
    print(
        "  'temporarily unavailable (ref: fd8b3902…)' after 5 seconds. The ref is the\n"
        "  right idea and it is useless if nothing writes it next to the exception that\n"
        "  caused it. This is a gap I flagged when we enabled the assistant and did not\n"
        "  close; the audit found it from the outside."
    )
    for rel in ("backend/app/services/chat_service.py", "backend/app/api/v1/chat.py"):
        sub(rel)
        regions(
            ROOT / rel,
            ("ref", "unavailable", "logger", "except", "GEMINI", "gemini", "timeout"),
            before=4,
            after=14,
        )


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    print("READ-ONLY. This run writes nothing.")
    section_admin_route()   # first: it is the only item that could be a live hole
    section_targets()
    section_drilldown()
    section_dates()
    section_freshness()
    section_anomalies()
    section_assistant()

    print(f"\n\n{RULE}\nNothing was written. Every section above only read files.\n{RULE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
