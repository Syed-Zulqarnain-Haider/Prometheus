#!/usr/bin/env python3
"""Hovering a KPI sparkline shows that day's date and value.

The sparklines were drawn as pure decoration - tooltip off, x-axis data just index
numbers - so the daily shape was visible but no day was readable. Now each card's
sparkline carries the real daily dates from the same timeseries that draws it, and
hover shows "Aug 14 · $5,135.21".

  frontend/components/overview/kpi-row.tsx
      Derives the shared daily date axis once (every card's sparkline is a column of
      the SAME timeseries response, so one axis serves all ten cards) and passes it to
      each KpiCard.

  frontend/components/overview/kpi-card.tsx
      sparklineOption takes the dates + a value formatter and turns the tooltip on:
      axis-triggered, confined so it never clips at the card or viewport edge. The
      date label is built from the Y-M-D PARTS, not new Date(iso-string) - an ISO date
      parses as UTC midnight, which toLocaleDateString renders as the PREVIOUS day in
      any timezone west of UTC. Values format as USD by default; every sparked card is
      a dollar figure today, and the prop exists for the day one is not.

Anchored: every anchor must appear EXACTLY the expected number of times or nothing is
written. Idempotent. Frontend rebuild required; no migration.

Run AFTER scripts/beautify-overview-motion.py - the kpi-row anchors include the
cascade wrappers that script writes.
"""

from __future__ import annotations

import sys
from pathlib import Path

KPI_ROW = Path("frontend/components/overview/kpi-row.tsx")
KPI_CARD = Path("frontend/components/overview/kpi-card.tsx")

# ── kpi-row.tsx ───────────────────────────────────────────────────────────────
ROW_DATES_ANCHOR = '  const timeseries = useTimeseries(filters, SPARK_METRICS, "day");\n'
ROW_DATES_ADD = """  // One daily axis serves every card: each sparkline is a column of this same
  // response. The bucket is an ISO timestamp; the date part is all the tooltip needs.
  const sparkDates = (timeseries.data?.series ?? []).map((row) =>
    String(row.bucket ?? "").slice(0, 10),
  );
"""

# Written by beautify-overview-motion.py's cascade wrappers - once per surviving row
# (the ladder row was removed from the deployed Overview, so 1 there, 2 elsewhere).
ROW_SPARK_ANCHOR = "              spark={kpi.spark}\n"
ROW_SPARK_NEW = "              spark={kpi.spark}\n              sparkDates={sparkDates}\n"

# ── kpi-card.tsx ──────────────────────────────────────────────────────────────
CARD_IMPORT_ANCHOR = 'import { formatPercent } from "@/lib/format";\n'
CARD_IMPORT_NEW = 'import { formatPercent, formatUSD } from "@/lib/format";\n'

CARD_SIG_ANCHOR = "function sparklineOption(values: number[], color: string): EChartsOption {\n"
CARD_SIG_NEW = """function sparklineOption(
  values: number[],
  color: string,
  dates?: string[],
  format?: (value: number) => string,
): EChartsOption {
"""

CARD_AXIS_ANCHOR = "    xAxis: { type: \"category\", show: false, boundaryGap: false, data: values.map((_, i) => i) },\n"
CARD_AXIS_NEW = """    xAxis: {
      type: "category",
      show: false,
      boundaryGap: false,
      // Real dates when the row supplies them (hover shows the day); index fallback
      // keeps a mismatched length from silently mislabelling points.
      data:
        dates && dates.length === values.length ? dates : values.map((_, i) => String(i)),
    },
"""

CARD_TOOLTIP_ANCHOR = "    tooltip: { show: false },\n"
CARD_TOOLTIP_NEW = """    tooltip: {
      show: true,
      trigger: "axis",
      confine: true,
      axisPointer: { type: "line", lineStyle: { width: 1 } },
      formatter: (params: unknown) => {
        const point = (Array.isArray(params) ? params[0] : params) as {
          axisValue?: string | number;
          data?: number | null;
        };
        // Build the label from the Y-M-D parts: new Date("2026-08-14") is UTC
        // midnight, which toLocaleDateString shows as the PREVIOUS day west of UTC.
        const [y, m, d] = String(point.axisValue ?? "").split("-").map(Number);
        const label =
          y && m && d
            ? new Date(y, m - 1, d).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })
            : String(point.axisValue ?? "");
        return `${label} · ${(format ?? formatUSD)(Number(point.data ?? 0))}`;
      },
    },
"""

CARD_PROPS_ANCHOR = "  spark?: number[];\n"
CARD_PROPS_NEW = """  spark?: number[];
  /** Daily dates aligned with ``spark`` - hovering shows that day's value. */
  sparkDates?: string[];
  /** Formats the hovered value; USD by default (every sparked card is a dollar figure). */
  sparkFormat?: (value: number) => string;
"""

CARD_DESTRUCTURE_ANCHOR = "  spark,\n"
CARD_DESTRUCTURE_NEW = "  spark,\n  sparkDates,\n  sparkFormat,\n"

CARD_MOUNT_ANCHOR = "          <Chart option={sparklineOption(spark, sparkColor)} height={48} adjustable={false} />\n"
CARD_MOUNT_NEW = """          <Chart
            option={sparklineOption(spark, sparkColor, sparkDates, sparkFormat)}
            height={48}
            adjustable={false}
          />
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def require(path: Path, text: str, anchor: str, expected: int = 1) -> None:
    if text.count(anchor) != expected:
        first = anchor.splitlines()[0].strip()
        die(f"{path}: expected {expected} of {first!r}, found {text.count(anchor)}")


def main() -> None:
    for path in (KPI_ROW, KPI_CARD):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    row = KPI_ROW.read_text()
    card = KPI_CARD.read_text()

    todo: dict[Path, str] = {}

    if "sparkDates" in row:
        print(f"{KPI_ROW}: already dated")
    else:
        require(KPI_ROW, row, ROW_DATES_ANCHOR)
        spark_count = row.count(ROW_SPARK_ANCHOR)
        if spark_count not in (1, 2):
            die(
                f"{KPI_ROW}: expected 1 or 2 cascade spark props, found {spark_count} - "
                "run beautify-overview-motion.py first"
            )
        text = row.replace(ROW_DATES_ANCHOR, ROW_DATES_ANCHOR + ROW_DATES_ADD, 1)
        text = text.replace(ROW_SPARK_ANCHOR, ROW_SPARK_NEW)
        todo[KPI_ROW] = text

    if "sparkDates" in card:
        print(f"{KPI_CARD}: already dated")
    else:
        for anchor in (
            CARD_IMPORT_ANCHOR,
            CARD_SIG_ANCHOR,
            CARD_AXIS_ANCHOR,
            CARD_TOOLTIP_ANCHOR,
            CARD_PROPS_ANCHOR,
            CARD_DESTRUCTURE_ANCHOR,
            CARD_MOUNT_ANCHOR,
        ):
            require(KPI_CARD, card, anchor)
        text = card
        text = text.replace(CARD_IMPORT_ANCHOR, CARD_IMPORT_NEW, 1)
        text = text.replace(CARD_SIG_ANCHOR, CARD_SIG_NEW, 1)
        text = text.replace(CARD_AXIS_ANCHOR, CARD_AXIS_NEW, 1)
        text = text.replace(CARD_TOOLTIP_ANCHOR, CARD_TOOLTIP_NEW, 1)
        text = text.replace(CARD_PROPS_ANCHOR, CARD_PROPS_NEW, 1)
        text = text.replace(CARD_DESTRUCTURE_ANCHOR, CARD_DESTRUCTURE_NEW, 1)
        text = text.replace(CARD_MOUNT_ANCHOR, CARD_MOUNT_NEW, 1)
        todo[KPI_CARD] = text

    if not todo:
        print("already dated - nothing to do")
        return

    for path, text in todo.items():
        path.write_text(text)
        print(f"patched {path}")

    print("\nHover any KPI sparkline to read that day's date and value.")
    print("Rebuild the frontend: docker compose -f docker-compose.prod.yml up -d --build frontend")


if __name__ == "__main__":
    main()
