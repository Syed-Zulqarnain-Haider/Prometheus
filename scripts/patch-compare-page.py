#!/usr/bin/env python3
"""Wire up the /compare split-screen page + two small fixes in drifted files.

Run from the repository root:

    python3 scripts/patch-compare-page.py

Same contract as patch-app-master-filters.py: these files have drifted between trees, so
they are edited by anchored replacement, never overwritten. Every anchor must match EXACTLY
ONCE or the script aborts having written nothing. Re-running is a no-op.

What it changes:
  frontend/lib/nav.ts                        + the Compare page in the sidebar (after Reports)
  frontend/lib/compare.ts                    previousWindow(): calendar-day arithmetic via
                                             date-fns instead of raw 86400000ms math, which
                                             shifts the window a day across DST changes
  frontend/components/overview/monthly-trend.tsx
                                             drop the stale "Target line: set in Admin
                                             (Step 7)" caption - Step 7 shipped long ago and
                                             the promised line was never drawn

The /compare page itself ships as new files (app/(app)/compare/, components/compare/).
"""

from __future__ import annotations

import sys
from pathlib import Path

# (path, already-applied marker, [(anchor, replacement), ...])
PATCHES: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "frontend/lib/nav.ts",
        '"/compare"',
        [
            (
                "  Megaphone,\n",
                "  Megaphone,\n  Scale,\n",
            ),
            (
                '  { href: "/reports", label: "Reports", icon: FileText },\n',
                '  { href: "/reports", label: "Reports", icon: FileText },\n'
                '  { href: "/compare", label: "Compare", icon: Scale },\n',
            ),
        ],
    ),
    (
        "frontend/lib/compare.ts",
        "differenceInCalendarDays",
        [
            (
                'function parseLocal(d: string): Date {\n'
                '  const [y, m, day] = d.slice(0, 10).split("-").map(Number);\n'
                "  return new Date(y, m - 1, day);\n"
                "}\n"
                "\n"
                "function iso(d: Date): string {\n"
                "  const y = d.getFullYear();\n"
                '  const m = String(d.getMonth() + 1).padStart(2, "0");\n'
                '  const day = String(d.getDate()).padStart(2, "0");\n'
                "  return `${y}-${m}-${day}`;\n"
                "}\n"
                "\n"
                "export function previousWindow(\n"
                "  dateFrom: string,\n"
                "  dateTo: string,\n"
                "): { from: string; to: string } {\n"
                "  const from = parseLocal(dateFrom);\n"
                "  const to = parseLocal(dateTo);\n"
                "  const dayMs = 24 * 60 * 60 * 1000;\n"
                "  const length = Math.round((to.getTime() - from.getTime()) / dayMs) + 1;\n"
                "  const prevTo = new Date(from.getTime() - dayMs);\n"
                "  const prevFrom = new Date(prevTo.getTime() - (length - 1) * dayMs);\n"
                "  return { from: iso(prevFrom), to: iso(prevTo) };\n"
                "}\n",
                'import { differenceInCalendarDays, format, parseISO, subDays } from "date-fns";\n'
                "\n"
                "export function previousWindow(\n"
                "  dateFrom: string,\n"
                "  dateTo: string,\n"
                "): { from: string; to: string } {\n"
                "  // Calendar-day arithmetic, NOT raw *86400000 millisecond math: subtracting 24h\n"
                "  // across a DST change lands at 23:00 or 01:00 of the WRONG calendar day, which\n"
                "  // shifted the whole comparison window by one day for viewers in DST timezones.\n"
                "  const from = parseISO(dateFrom.slice(0, 10));\n"
                "  const to = parseISO(dateTo.slice(0, 10));\n"
                "  const length = differenceInCalendarDays(to, from) + 1;\n"
                "  const prevTo = subDays(from, 1);\n"
                "  const prevFrom = subDays(prevTo, length - 1);\n"
                '  return { from: format(prevFrom, "yyyy-MM-dd"), to: format(prevTo, "yyyy-MM-dd") };\n'
                "}\n",
            ),
        ],
    ),
    (
        "frontend/components/overview/monthly-trend.tsx",
        '<ChartCard title="Monthly Revenue Trend">',
        [
            (
                "    <ChartCard\n"
                '      title="Monthly Revenue Trend"\n'
                "      action={\n"
                '        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">\n'
                "          Target line: set in Admin (Step 7)\n"
                "        </span>\n"
                "      }\n"
                "    >\n",
                '    <ChartCard title="Monthly Revenue Trend">\n',
            ),
        ],
    ),
]


def main() -> int:
    root = Path.cwd()
    if not (root / "frontend").is_dir():
        print("ERROR: run this from the repository root (the folder holding frontend/),")
        print("       e.g. cd ~/final_project/main_final_project/Prometheus")
        return 2

    planned: list[tuple[Path, str]] = []
    skipped: list[str] = []

    # Pass 1: verify everything before writing anything - a clean abort beats a half-apply.
    for rel, marker, edits in PATCHES:
        path = root / rel
        if not path.is_file():
            print(f"ERROR: {rel} not found.")
            return 2
        text = path.read_text(encoding="utf-8")
        if marker in text:
            skipped.append(rel)
            continue
        for anchor, replacement in edits:
            count = text.count(anchor)
            if count != 1:
                print(f"ERROR: {rel}: expected exactly 1 match, found {count}, for:")
                print("-" * 60)
                print(anchor.rstrip("\n"))
                print("-" * 60)
                print("Nothing was written. The file has probably changed since this patch")
                print("was written - send me the file and I'll rebuild the patch.")
                return 1
            text = text.replace(anchor, replacement)
        planned.append((path, text))

    for path, text in planned:
        path.write_text(text, encoding="utf-8")
        print(f"patched  {path.relative_to(root)}")
    for rel in skipped:
        print(f"skipped  {rel} (already patched)")

    if not planned:
        print("\nNothing to do - every file was already patched.")
    else:
        print("\nDone. Next:")
        print("  docker compose -f docker-compose.prod.yml up -d --build frontend")
    return 0


if __name__ == "__main__":
    sys.exit(main())
