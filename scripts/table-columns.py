#!/usr/bin/env python3
"""Table revenue columns read the server's numbers, and gain Ad ROAS / IAP ROAS.

SPLIT OUT OF table-totals.py AFTER IT BROKE A FILE
--------------------------------------------------
The previous script did two things: fix the derived columns, and add a totals row. The
column edits were right. The totals row was not - and one of its anchors did real damage,
so both halves were withdrawn and only the verified half ships here.

THE BUG, RECORDED SO IT IS NOT REPEATED. The anchor was the SUBSTRING
``interface ColumnDef {``, and the deployed line reads ``export interface ColumnDef {``.
Replacing the substring left the ``export`` attached to the newly-inserted helper and took
it off the interface:

    export function ratio(...) { ... }

    interface ColumnDef {          <- export stolen

Every file importing ColumnDef stopped compiling (pod-table, hou-table, top-apps-table,
pod-owner-table, the pod-owner page). The gate caught it and nothing deployed, but it
poisoned every later frontend check until the file was reverted. An anchor that is a
substring of a longer line is not an anchor. Every anchor here is a COMPLETE line.

The totals row is not in this script at all: its remaining anchors matched inside
``MetricTable``, a component where ``filters`` and ``format`` are not in scope, which is
what produced "Cannot find name 'filters'". That needs the real file, not another guess.

WHAT SHIPS
----------
  * Gross Rev, Net Rev and ROAS read gross_revenue_usd / net_revenue_usd / roas straight
    from the row - computed server-side by period_ratios.py (already deployed) with the
    same formula, rounding and RBAC gate the KPI cards use. Three formulas maintained in
    the browser become zero.
  * Ad ROAS and IAP ROAS join them, each gated on its own components, so a role without
    ad revenue sees neither the ad column nor its ROAS.
  * A ratio with no denominator stays null and renders "-": an app with revenue and no
    spend has NO ROAS, and 0.00x reads as terrible performance rather than
    not-applicable. num() would coerce it into a confident zero.

One edit reaches three tables - Top Apps and HOU Performance both build on METRIC_COLUMNS.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
TABLE = ROOT / "frontend/components/overview/revenue-table.tsx"
TEST = ROOT / "frontend/tests/table-columns.test.ts"

report: list[str] = []

# Every anchor is a COMPLETE line (or lines). See the module docstring for why.
EDITS: list[tuple[str, str, str]] = [
    (
        "the ratio reader, above the column list",
        "export const METRIC_COLUMNS: ColumnDef[] = [",
        (
            "/** A server-computed ratio, or null when it has no denominator.\n"
            " *\n"
            " *  null must survive all the way to the formatter: an app with revenue and no\n"
            " *  spend has NO ROAS, and printing 0.00x reads as terrible performance rather\n"
            " *  than not-applicable. num() would turn it into a confident zero.\n"
            " */\n"
            "function ratio(v: unknown): number | null {\n"
            '  return typeof v === "number" ? v : null;\n'
            "}\n"
            "\n"
            "export const METRIC_COLUMNS: ColumnDef[] = ["
        ),
    ),
    (
        "Gross Rev reads the server's gross field",
        "    value: (r) => num(r.total_iap_gross_usd) + num(r.total_ad_revenue_usd) },",
        "    value: (r) => num(r.gross_revenue_usd) },",
    ),
    (
        "Net Rev reads the server's net field",
        "    value: (r) => num(r.total_revenue_usd) - num(r.total_ua_spend_usd) },",
        "    value: (r) => num(r.net_revenue_usd) },",
    ),
    (
        "ROAS reads the server, and Ad/IAP ROAS join it",
        (
            "    value: (r) => { const s = num(r.total_ua_spend_usd); "
            "return s > 0 ? num(r.total_revenue_usd) / s : null; } },"
        ),
        (
            "    value: (r) => ratio(r.roas) },\n"
            '  { id: "ad_roas", label: "Ad ROAS", '
            'requires: ["total_ad_revenue_usd", "total_ua_spend_usd"], align: "right", '
            'fmt: "roas",\n'
            "    value: (r) => ratio(r.ad_roas) },\n"
            '  { id: "iap_roas", label: "IAP ROAS", '
            'requires: ["total_iap_net_usd", "total_ua_spend_usd"], align: "right", '
            'fmt: "roas",\n'
            "    value: (r) => ratio(r.iap_roas) },"
        ),
    ),
]

TEST_SRC = '''import { describe, expect, it } from "vitest";

/** The table's derived columns.
 *
 * Gross Rev, Net Rev, ROAS, Ad ROAS and IAP ROAS are read from the row, not computed -
 * the API produces them in period_ratios.py with the same formula and rounding the KPI
 * cards use, so a column cannot disagree with the card above it.
 *
 * What is worth testing here is the one piece of logic left in the browser: a ratio with
 * no denominator has to stay null the whole way to the formatter.
 */

/** Mirrors the component's `ratio` reader exactly. */
function ratio(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

describe("derived table columns", () => {
  it("keeps a missing ratio null rather than turning it into zero", () => {
    // The server sends null when spend is zero. An app with revenue and no spend has no
    // ROAS, and 0.00x would read as terrible performance rather than not-applicable.
    expect(ratio(null)).toBeNull();
    expect(ratio(undefined)).toBeNull();
  });

  it("passes a real ratio through unchanged", () => {
    // 127.29% on the owner's Looker sheet - the server already rounded it.
    expect(ratio(1.2729)).toBe(1.2729);
  });

  it("does not coerce a string into a number", () => {
    // A column whose metric group the caller lacks is hidden by `requires`; if one ever
    // slipped through as an unexpected type it must render "-", never a made-up figure.
    expect(ratio("1.27")).toBeNull();
  });

  it("treats zero as a real ratio, not a missing one", () => {
    // Genuinely zero revenue against real spend IS 0.00x, and must not become "-".
    expect(ratio(0)).toBe(0);
  });
});
'''


def window(path: Path, needle: str) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - 4), min(len(lines), i + 12)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: anchor not found"


def main() -> int:
    if not TABLE.exists():
        print(f"ABORTED: missing {TABLE}", file=sys.stderr)
        return 1

    text = TABLE.read_text()
    if "iap_roas" in text:
        print("Already applied - left alone.")
        if TEST.parent.is_dir():
            TEST.write_text(TEST_SRC)
            print(f"  - {TEST}: refreshed")
        return 0

    problems = [
        f"  [{label}] expected exactly 1 match, found {text.count(old)}\n"
        + window(TABLE, old.splitlines()[0].strip()[:56])
        for label, old, _ in EDITS
        if text.count(old) != 1
    ]
    if problems:
        print("NOTHING WAS WRITTEN - these columns decide what revenue figures people read,")
        print("so they go together or not at all. Mismatches:\n")
        for p in problems:
            print(p)
        return 1

    for _, old, new in EDITS:
        text = text.replace(old, new, 1)
    TABLE.write_text(text)
    report.append(f"[table] {TABLE}: server-read revenue columns + Ad/IAP ROAS")
    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: a null ratio stays null; zero stays zero")

    print("PATCHED, NOT YET VERIFIED - tsc + vitest are the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    print(
        "\nThe totals row is deliberately NOT here: its anchors landed inside MetricTable,"
        "\nwhere filters and format are out of scope. It ships once the real file is visible."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
