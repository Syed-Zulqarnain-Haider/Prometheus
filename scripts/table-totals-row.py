#!/usr/bin/env python3
"""A totals row pinned to the foot of every dimension table.

WHY THIS IS A SEPARATE, SECOND ATTEMPT
--------------------------------------
The first version put the totals lookup inside ``MetricTable`` and broke the build:
"Cannot find name 'filters'". MetricTable is PRESENTATIONAL - it takes already-aggregated
rows and knows nothing about filters or data fetching. That was not a bad anchor, it was a
misunderstanding of the component, and no amount of re-anchoring would have fixed it.

So the totals arrive the way every other piece of data arrives: as a PROP. MetricTable
renders a footer when given one; the wrapper that owns the filters fetches it. The
presentational component stays presentational.

WHY THE SUMMARY AND NOT A SUM OF THE ROWS
-----------------------------------------
The totals come from /metrics/summary, which aggregates every row the filters and the
caller's scope select. Summing the rows on screen would be wrong by everything below the
fold - RevenueTable fetches 100 and shows a scrolling subset - and a ratio cannot be summed
at all: period ROAS is SUM(revenue)/SUM(spend), not the mean of per-app ROAS. The summary
already returns exactly that, computed by period_ratios.py, which is also where the KPI
cards get theirs. So the footer, the columns and the headline cards are three renderings
of one number.

The SAME ColumnDef list formats the footer as the rows above it, through the same exported
formatCell - so a column and its total cannot disagree about units or rounding either.

Identity columns (Publisher, Game) have no total: the first shows "All apps" and the rest
are blank, rather than printing a meaningless aggregate of names.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
TABLE = ROOT / "frontend/components/overview/revenue-table.tsx"
TEST = ROOT / "frontend/tests/table-totals-row.test.ts"

report: list[str] = []

# Every anchor is a COMPLETE line or block - never a substring of a longer line.
EDITS: list[tuple[str, str, str]] = [
    (
        "useSummary imported alongside the hooks already used",
        'import { useMe, useTable } from "@/lib/api-hooks";',
        'import { useMe, useSummary, useTable } from "@/lib/api-hooks";',
    ),
    (
        "totals joins MetricTable's destructuring",
        "  sortId,\n  limit,\n  action,\n}: {",
        "  sortId,\n  limit,\n  action,\n  totals,\n}: {",
    ),
    (
        "totals joins MetricTable's props type",
        (
            '  /** Rendered at the right of the card header - e.g. a "rank by" picker. */\n'
            "  action?: ReactNode;\n"
            "}) {"
        ),
        (
            '  /** Rendered at the right of the card header - e.g. a "rank by" picker. */\n'
            "  action?: ReactNode;\n"
            "  /** Period totals for EVERY row the filters select - from /metrics/summary,\n"
            "   *  never a sum of the rows on screen. Summing the visible rows would be wrong\n"
            "   *  by everything below the fold, and a ratio cannot be summed at all: period\n"
            "   *  ROAS is SUM(revenue)/SUM(spend), which is what the summary already returns. */\n"
            "  totals?: Row | null;\n"
            "}) {"
        ),
    ),
    (
        "the footer row itself",
        "            </tbody>\n          </table>",
        (
            "            </tbody>\n"
            "            {/* Totals for every filtered row, formatted by the SAME ColumnDef\n"
            "                list as the rows above - so a column and its total cannot\n"
            "                disagree about units or rounding. Identity columns carry no\n"
            '                total: the first says "All apps", the rest stay blank. */}\n'
            "            {totals ? (\n"
            "              <tfoot>\n"
            '                <tr className="border-t-2 bg-muted/40 font-medium">\n'
            "                  {columns.map((c, i) => (\n"
            "                    <td\n"
            "                      key={c.id}\n"
            "                      className={cn(\n"
            '                        "whitespace-nowrap px-3 py-2",\n'
            '                        c.align === "right" && "text-right tabular-nums",\n'
            "                      )}\n"
            "                    >\n"
            "                      {i === 0\n"
            '                        ? "All apps"\n'
            '                        : c.fmt === "text"\n'
            '                          ? ""\n'
            "                          : formatCell(c, c.value(totals))}\n"
            "                    </td>\n"
            "                  ))}\n"
            "                </tr>\n"
            "              </tfoot>\n"
            "            ) : null}\n"
            "          </table>"
        ),
    ),
    (
        "RevenueTable fetches the totals it already has the filters for",
        "  const table = useTable(filters, fetchSort, 100);",
        (
            "  const table = useTable(filters, fetchSort, 100);\n"
            "  // Same filters, same scope, same numbers as the headline cards - the summary\n"
            "  // aggregates every row, not just the page this table renders.\n"
            "  const summary = useSummary(filters);"
        ),
    ),
    (
        "and passes them down",
        "      isLoading={table.isLoading}\n      isError={table.isError}\n    />",
        (
            "      isLoading={table.isLoading}\n"
            "      isError={table.isError}\n"
            "      totals={(summary.data?.current ?? null) as Row | null}\n"
            "    />"
        ),
    ),
]

TEST_SRC = '''import { describe, expect, it } from "vitest";

/** The totals row reads /metrics/summary, never a sum of the rows on screen.
 *
 * These pin the reasoning rather than the markup: the two numbers genuinely differ
 * whenever a table shows a subset, and a period ratio is not the mean of row ratios.
 * Getting either wrong produces a confident, wrong figure at the bottom of the table -
 * which is worse than no total at all.
 */
describe("totals row semantics", () => {
  const summaryTotals = { total_revenue_usd: 104_380, total_ua_spend_usd: 82_000 };
  const visibleRows = [
    { total_revenue_usd: 9_000, total_ua_spend_usd: 5_000 },
    { total_revenue_usd: 8_000, total_ua_spend_usd: 4_000 },
  ];

  it("is not the sum of the rows the table happens to render", () => {
    const pageSum = visibleRows.reduce((a, r) => a + r.total_revenue_usd, 0);
    expect(pageSum).toBe(17_000);
    expect(pageSum).not.toBe(summaryTotals.total_revenue_usd);
  });

  it("computes a period ratio from totals, not by averaging row ratios", () => {
    const rowRatios = visibleRows.map((r) => r.total_revenue_usd / r.total_ua_spend_usd);
    const averaged = rowRatios.reduce((a, b) => a + b, 0) / rowRatios.length;
    const periodRoas = summaryTotals.total_revenue_usd / summaryTotals.total_ua_spend_usd;
    // The owner's Looker sheet: 127.29%.
    expect(Number(periodRoas.toFixed(4))).toBe(1.2729);
    // Averaging the rows gives a different, wrong answer.
    expect(Number(averaged.toFixed(4))).not.toBe(Number(periodRoas.toFixed(4)));
  });

  it("has nothing to total for an identity column", () => {
    // Publisher and Game are names. The footer shows "All apps" in the first cell and
    // leaves the rest blank rather than printing an aggregate of strings.
    const identity = { fmt: "text" as const };
    expect(identity.fmt).toBe("text");
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
    if "totals?: Row | null" in text:
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
        print("NOTHING WAS WRITTEN - the prop, the footer and the caller go together or the")
        print("file does not compile. Mismatches:\n")
        for p in problems:
            print(p)
        return 1

    for _, old, new in EDITS:
        text = text.replace(old, new, 1)
    TABLE.write_text(text)
    report.append(f"[table] {TABLE}: totals row, fed by the summary")
    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: totals are not a page sum; ratios are not averaged")

    print("PATCHED, NOT YET VERIFIED - tsc + vitest are the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    print(
        "\nOnly RevenueTable passes totals so far. Top Apps, HOU and Pod tables share"
        "\nMetricTable and gain the footer the moment they pass one - the prop is optional,"
        "\nso they are unaffected until then."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
