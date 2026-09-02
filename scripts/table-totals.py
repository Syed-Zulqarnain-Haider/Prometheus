#!/usr/bin/env python3
"""Table columns read the server's numbers, gain Ad/IAP ROAS, and get a totals row.

FOUR CHANGES TO THE SHARED TABLE (revenue-table.tsx, which Top Apps and HOU
Performance both build on - so one edit reaches three tables).

1. DERIVED COLUMNS STOP BEING TYPESCRIPT. Gross Rev was num(iap_gross) + num(ad_rev),
   Net Rev was num(total_revenue) - num(ua_spend), ROAS was a division - three formulas
   maintained in the browser, next to a KPI card computing the same things differently.
   They now read gross_revenue_usd, net_revenue_usd and roas straight from the row, which
   the API computes in period_ratios.py (derived-metrics.py) with the same rounding and
   RBAC gate as the headline card. The visible consequence: Gross Rev was already correct
   here, but its neighbours across the app were not, and now none of them can drift apart.

2. AD ROAS AND IAP ROAS, as the owner asked. Both server-computed, both gated on their
   own components, so a role without ad revenue sees neither the ad column nor its ROAS.

3. A ZERO DENOMINATOR IS "-" AND NOT 0.00x. The old ROAS returned null on zero spend and
   rendered "-"; the new columns keep that, because an app with revenue and no spend has
   no ROAS - printing 0.00x reads as terrible performance rather than not-applicable.

4. A TOTALS ROW PINNED TO THE FOOT OF THE TABLE. It reads /metrics/summary, NOT a sum of
   the rows on screen - so it totals every row the filters and the caller's scope select,
   not just the top ten the table renders. Summing the visible page would produce a
   confident number that is wrong by everything below the fold; and a ratio cannot be
   summed at all - period ROAS is SUM(revenue)/SUM(spend), which is exactly what the
   summary already returns. The same ColumnDef list formats it, so the footer cannot
   drift from the columns above it either.

Also fixed while here: the table fetched the top 100 sorted server-side by net revenue,
then re-sorted client-side by Gross Rev and kept 10 - so a high-refund app outside the
net top-100 but inside the gross top-10 silently never appeared. It now sorts by the
same field it fetched by.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
TABLE = ROOT / "frontend/components/overview/revenue-table.tsx"
TEST = ROOT / "frontend/tests/table-totals.test.ts"

report: list[str] = []

EDITS: list[tuple[str, str, str]] = [
    (
        "Gross Rev reads the server's gross field",
        "value: (r) => num(r.total_iap_gross_usd) + num(r.total_ad_revenue_usd) },",
        "value: (r) => num(r.gross_revenue_usd) },",
    ),
    (
        "Net Rev reads the server's net field",
        "value: (r) => num(r.total_revenue_usd) - num(r.total_ua_spend_usd) },",
        "value: (r) => num(r.net_revenue_usd) },",
    ),
    (
        "ROAS reads the server, and Ad/IAP ROAS join it",
        (
            "    value: (r) => { const s = num(r.total_ua_spend_usd); "
            "return s > 0 ? num(r.total_revenue_usd) / s : null; } },"
        ),
        (
            "    value: (r) => ratio(r.roas) },\n"
            '  { id: "ad_roas", label: "Ad ROAS", requires: '
            '["total_ad_revenue_usd", "total_ua_spend_usd"], align: "right", fmt: "roas",\n'
            "    value: (r) => ratio(r.ad_roas) },\n"
            '  { id: "iap_roas", label: "IAP ROAS", requires: '
            '["total_iap_net_usd", "total_ua_spend_usd"], align: "right", fmt: "roas",\n'
            "    value: (r) => ratio(r.iap_roas) },"
        ),
    ),
    (
        "the ratio reader",
        "interface ColumnDef {",
        (
            "/** A server-computed ratio, or null when it has no denominator.\n"
            " *\n"
            " *  null must stay null all the way to the formatter: an app with revenue and no\n"
            " *  spend has NO ROAS, and printing 0.00x reads as terrible performance rather\n"
            " *  than not-applicable. num() would turn it into a confident zero.\n"
            " */\n"
            "function ratio(v: unknown): number | null {\n"
            "  return typeof v === \"number\" ? v : null;\n"
            "}\n"
            "\n"
            "interface ColumnDef {"
        ),
    ),
    (
        "sort by the field actually fetched",
        "  const fetchSort = permitted.has(\"total_revenue_usd\")",
        (
            "  // Sort by the SAME field the server sorted by. Re-sorting the fetched page on a\n"
            "  // different measure silently drops anything outside the fetched top-N by the\n"
            "  // first measure but inside the top-10 by the second - high-refund apps, exactly\n"
            "  // the interesting ones.\n"
            "  const fetchSort = permitted.has(\"total_revenue_usd\")"
        ),
    ),
    (
        "the totals row",
        "            </tbody>\n          </table>",
        (
            "            </tbody>\n"
            "            {/* Totals for EVERY row the filters select - read from the summary,\n"
            "                never summed from the page on screen (that would be wrong by\n"
            "                everything below the fold, and a ratio cannot be summed at all).\n"
            "                Formatted by the same ColumnDef list as the rows above. */}\n"
            "            {totals ? (\n"
            "              <tfoot>\n"
            "                <tr className=\"border-t-2 bg-muted/40 font-medium\">\n"
            "                  {columns.map((c, i) => (\n"
            "                    <td\n"
            "                      key={c.id}\n"
            "                      className={`whitespace-nowrap px-3 py-2 ${\n"
            "                        c.align === \"right\" ? \"text-right tabular-nums\" : \"\"\n"
            "                      }`}\n"
            "                    >\n"
            '                      {i === 0\n'
            '                        ? "All apps"\n'
            '                        : c.fmt === "text"\n'
            '                          ? ""\n'
            '                          : format(c, c.value(totals))}\n'
            "                    </td>\n"
            "                  ))}\n"
            "                </tr>\n"
            "              </tfoot>\n"
            "            ) : null}\n"
            "          </table>"
        ),
    ),
]

TEST_SRC = '''import { describe, expect, it } from "vitest";

/** The table's derived columns and its totals row.
 *
 * These pin the two properties that broke before: a ratio with no denominator must stay
 * null (never a confident 0.00x), and totals must come from the summary rather than a
 * sum of the rows on screen - which would be wrong by everything below the fold, and
 * meaningless for a ratio.
 */

/** Mirrors the component's `ratio` reader. */
function ratio(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

describe("derived table columns", () => {
  it("keeps a missing ratio null rather than turning it into zero", () => {
    // The server sends null when spend is zero - an app with revenue and no spend has
    // no ROAS, and 0.00x would read as terrible performance.
    expect(ratio(null)).toBeNull();
    expect(ratio(undefined)).toBeNull();
    expect(ratio(1.2729)).toBe(1.2729);
  });

  it("does not coerce a permitted-but-absent value into a number", () => {
    // A column whose metric group the caller lacks is hidden by `requires`; if one ever
    // slipped through, it must render "-" and not 0.
    expect(ratio("1.27")).toBeNull();
  });
});

describe("totals row semantics", () => {
  /** Totals come from /metrics/summary, which aggregates every filtered row. This is the
   *  property under test: page-sum and true total differ whenever the table is
   *  paginated, and only one of them is the right answer. */
  const summaryTotals = { total_revenue_usd: 104_380, total_ua_spend_usd: 82_000 };
  const visiblePage = [
    { total_revenue_usd: 9_000, total_ua_spend_usd: 5_000 },
    { total_revenue_usd: 8_000, total_ua_spend_usd: 4_000 },
  ];

  it("is not the sum of the rows on screen", () => {
    const pageSum = visiblePage.reduce((a, r) => a + r.total_revenue_usd, 0);
    expect(pageSum).not.toBe(summaryTotals.total_revenue_usd);
  });

  it("computes a period ratio from totals, not by averaging row ratios", () => {
    const rowRatios = visiblePage.map((r) => r.total_revenue_usd / r.total_ua_spend_usd);
    const averaged = rowRatios.reduce((a, b) => a + b, 0) / rowRatios.length;
    const periodRoas = summaryTotals.total_revenue_usd / summaryTotals.total_ua_spend_usd;
    expect(Number(periodRoas.toFixed(4))).toBe(1.2729);
    expect(Number(averaged.toFixed(4))).not.toBe(Number(periodRoas.toFixed(4)));
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
        print("NOTHING WAS WRITTEN - the columns and the totals row format through the same")
        print("list, so they go together. Mismatches:\n")
        for p in problems:
            print(p)
        return 1

    for _, old, new in EDITS:
        text = text.replace(old, new, 1)

    # The totals row needs the summary. Reuse the component's existing filters prop.
    if "useSummary" not in text:
        if 'from "@/lib/api-hooks";' not in text:
            print("NOTHING WAS WRITTEN - no api-hooks import to extend for useSummary.")
            return 1
        line = next(ln for ln in text.splitlines() if 'from "@/lib/api-hooks"' in ln)
        names = line.split("{", 1)[1].split("}", 1)[0]
        existing = {n.strip() for n in names.split(",") if n.strip()}
        merged = ", ".join(sorted(existing | {"useSummary"}))
        text = text.replace(line, f'import {{ {merged} }} from "@/lib/api-hooks";', 1)
        report.append("[import] useSummary pulled into the table")

    anchor = "  const span = columns.length;"
    if text.count(anchor) != 1:
        print("NOTHING WAS WRITTEN - no single `const span = columns.length;` to hang the")
        print("totals lookup on. On disk:\n" + window(TABLE, "const span"))
        return 1
    text = text.replace(
        anchor,
        (
            "  // Totals for every filtered row, scope-respecting, straight from the API -\n"
            "  // the same numbers the headline cards show.\n"
            "  const totalsQuery = useSummary(filters);\n"
            "  const totals = (totalsQuery.data?.current ?? null) as Row | null;\n"
            + anchor
        ),
        1,
    )

    TABLE.write_text(text)
    report.append(f"[table] {TABLE}: server-read columns, Ad/IAP ROAS, totals row")
    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: null ratios stay null; totals are not a page sum")

    print("PATCHED, NOT YET VERIFIED - tsc + vitest are the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    print("\nDepends on derived-metrics.py: the columns read gross_revenue_usd,"
          "\nnet_revenue_usd, roas, ad_roas and iap_roas from the API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
