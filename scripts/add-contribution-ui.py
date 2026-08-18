#!/usr/bin/env python3
"""The "What moved" panel - features 1 and 2 of the roadmap, on one surface.

Feature 1 (contribution analysis) shipped its backend in ``add-contribution-analysis.py``:
GET /api/v1/metrics/contribution returns, per entity, the current and previous totals,
the delta and the change percent, biggest movers first, using the SAME previous-period
window the KPI cards use. This is the UI for it, and it carries feature 2 (narrative
insights) in the same card because the two answer one question:

    Revenue is down 34%.  Why?

  * The sentence at the top is WRITTEN FROM THE NUMBERS BELOW IT - deterministic, no
    LLM. A generated summary must never be able to invent a figure that contradicts the
    table under it, and this one arithmetically cannot. It is also instant, free and
    unit-testable. The AI assistant stays for open-ended questions; this is arithmetic.
  * The movers themselves, declines first (that is what people are looking for), each
    with a bar showing its size RELATIVE TO THE LARGEST MOVER. Deliberately not a share
    of the net total: when gains and losses roughly cancel - the exact case this panel
    exists to explain - shares of a near-zero net are nonsense.
  * Coverage is stated honestly. The list is a top N, so the card says how much of the
    move those N explain rather than implying they are the whole story.

Metric and dimension pickers are filtered through the caller's permitted measures, so a
marketing user sees UA cost and a viewer sees the panel say there is nothing it can show
- the same RBAC the endpoint enforces, mirrored so the UI never asks for a 400.

Files:
  frontend/lib/types.ts                              ContributionRow/Response
  frontend/lib/api-hooks.ts                          useContribution
  frontend/components/overview/what-moved.tsx        the panel (NEW)
  frontend/lib/overview-layout.ts                    widget id + default placement
  frontend/components/overview/overview-client.tsx   import + registry entry

Anchored: every anchor must appear EXACTLY once or NOTHING is written - all files
validate before any is touched. Idempotent. Frontend rebuild; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

TYPES = Path("frontend/lib/types.ts")
HOOKS = Path("frontend/lib/api-hooks.ts")
PANEL = Path("frontend/components/overview/what-moved.tsx")
LAYOUT = Path("frontend/lib/overview-layout.ts")
CLIENT = Path("frontend/components/overview/overview-client.tsx")

# ── types.ts ──────────────────────────────────────────────────────────────────
TYPES_ANCHOR = "export interface TableResponse {\n"
TYPES_ADD = """/** One entity's movement between the selected window and the previous one.
 *  ``change_pct`` is null - never 0 - when the previous window was zero: a percentage
 *  off nothing is a division artefact, not a fact about the business. */
export interface ContributionRow {
  key: string | null;
  label: string | null;
  current: number;
  previous: number;
  delta: number;
  change_pct: number | null;
}

export interface ContributionResponse {
  metric: string;
  group_by: string;
  gainers: ContributionRow[];
  losers: ContributionRow[];
  /** Sum of the RETURNED rows' deltas - how much of the move this list explains. */
  covered_delta: number;
}

"""

# ── api-hooks.ts ──────────────────────────────────────────────────────────────
HOOKS_IMPORT_ANCHOR = "  BreakdownResponse,\n  Bucket,\n"
HOOKS_IMPORT_ADD = "  ContributionResponse,\n"

HOOKS_ANCHOR = "/** Keyset-paginated table for the Apps Explorer (server-side sort + cursor). */\n"
HOOKS_ADD = '''/** Which entities moved ONE metric between this window and the previous one.
 *  The server does the diff in a single query against the same comparison window the
 *  KPI cards use, so these deltas reconcile with the headline. */
export function useContribution(
  filters: Filters,
  groupBy: string,
  metric: string,
  limit = 10,
) {
  const { user } = useAuth();
  const params = { ...filtersToApiQuery(filters), group_by: groupBy, metric, limit };
  return useQuery({
    queryKey: ["contribution", params],
    queryFn: () =>
      apiFetch<ContributionResponse>(`/api/v1/metrics/contribution${buildQuery(params)}`),
    enabled: Boolean(user) && metric.length > 0,
    staleTime: AGG_STALE,
  });
}

'''

# ── overview-layout.ts ────────────────────────────────────────────────────────
LAYOUT_ID_ANCHOR = '  "top-apps",\n'
LAYOUT_ID_ADD = '  "what-moved",\n'

# Placed directly below Top Apps at the same y as `ratios`; compactType="vertical"
# pushes everything after it down, so no other line has to be rewritten.
LAYOUT_GRID_ANCHOR = '  { i: "ratios", x: 0, y: 52, w: 12, h: 5, minW: 6, minH: 4 },\n'
LAYOUT_GRID_ADD = '  { i: "what-moved", x: 0, y: 52, w: 12, h: 24, minW: 4, minH: 14 },\n'

# ── overview-client.tsx ───────────────────────────────────────────────────────
CLIENT_IMPORT_ANCHOR = 'import { TopAppsTable } from "@/components/overview/top-apps-table";\n'
CLIENT_IMPORT_ADD = 'import { WhatMoved } from "@/components/overview/what-moved";\n'

CLIENT_ITEM_ANCHOR = '    "top-apps": <TopAppsTable filters={filters} />,\n'
CLIENT_ITEM_ADD = '    "what-moved": <WhatMoved filters={filters} />,\n'

PANEL_SOURCE = r'''"use client";

import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { useMemo, useState } from "react";

import { ChartCard } from "@/components/charts/chart-card";
import { permittedMeasures } from "@/components/overview/revenue-table";
import { Skeleton } from "@/components/ui/skeleton";
import { useContribution, useMe } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";
import { formatPercent, formatUSD } from "@/lib/format";
import type { ContributionRow } from "@/lib/types";

/* "What moved the number" - the question every KPI card raises and none of them answer.
 *
 * Revenue is down 34%: WHICH apps? Until now that meant opening Apps Explorer and
 * diffing two periods by hand. The server does the diff (/metrics/contribution - one
 * query, the SAME previous-period window the KPI cards use, so these deltas reconcile
 * with the headline) and this renders it two ways:
 *
 *   * A sentence, written FROM the numbers - no LLM. A generated summary must never be
 *     able to invent a figure that contradicts the list under it, and a deterministic
 *     sentence is also instant, free and testable. The AI assistant is for open
 *     questions; this is arithmetic.
 *   * The movers themselves, declines first, each with its size relative to the biggest.
 *
 * Coverage is stated honestly: the list is a top N, so the panel says how much of the
 * move those N explain instead of implying they are the whole story. */

const DIMENSIONS = [
  { id: "app", label: "App" },
  { id: "pod", label: "Pod" },
  { id: "publisher", label: "Publisher" },
  { id: "hou", label: "HOU" },
  { id: "platform", label: "Platform" },
] as const;

/** The reported ladder first (the finance-authoritative figures the KPI row shows),
 *  then the raw measures. Filtered against the caller's permitted measures at render. */
const METRICS = [
  { field: "rpt_gross_revenue_usd", label: "Revenue" },
  { field: "rpt_tf_profit_usd", label: "Gross Profit" },
  { field: "rpt_ua_cost_usd", label: "UA Cost" },
  { field: "total_revenue_usd", label: "Total Revenue" },
  { field: "store_total_installs", label: "Installs" },
] as const;

const SELECT_CLASS =
  "h-8 rounded-[var(--radius-inner)] border border-input bg-background px-2 text-xs outline-none focus:ring-1 focus:ring-ring";

function fmt(field: string, value: number): string {
  return field.endsWith("_usd")
    ? formatUSD(value, { compact: true })
    : Math.round(value).toLocaleString();
}

/** The sentence. Built from the same rows rendered below it, so the two can never
 *  disagree - the failure mode of every AI-written summary. */
function narrative(
  metricLabel: string,
  field: string,
  gainers: ContributionRow[],
  losers: ContributionRow[],
  coveredDelta: number,
): string {
  if (gainers.length === 0 && losers.length === 0) {
    return `No movement in ${metricLabel} against the previous period.`;
  }
  const parts: string[] = [
    `${metricLabel} ${coveredDelta >= 0 ? "rose" : "fell"} by ` +
      `${fmt(field, Math.abs(coveredDelta))} across the movers below.`,
  ];
  const worst = losers[0];
  const best = gainers[0];
  if (worst) {
    const pct = worst.change_pct != null ? `, ${formatPercent(worst.change_pct)}` : "";
    parts.push(`${worst.label ?? "Unattributed"} fell the most (${fmt(field, worst.delta)}${pct}).`);
  }
  if (best) {
    const pct = best.change_pct != null ? `, ${formatPercent(best.change_pct)}` : "";
    parts.push(`${best.label ?? "Unattributed"} gained the most (+${fmt(field, best.delta)}${pct}).`);
  }
  return parts.join(" ");
}

function MoverRow({
  row,
  field,
  share,
}: {
  row: ContributionRow;
  field: string;
  share: number;
}) {
  const up = row.delta >= 0;
  const color = up ? "var(--color-positive)" : "var(--color-negative)";
  const label = row.label ?? "Unattributed";
  return (
    <li className="flex items-center gap-3 py-1.5">
      {up ? (
        <ArrowUpRight className="h-3.5 w-3.5 shrink-0" style={{ color }} />
      ) : (
        <ArrowDownRight className="h-3.5 w-3.5 shrink-0" style={{ color }} />
      )}
      <span className="min-w-0 flex-1 truncate text-sm" title={label}>
        {label}
      </span>
      {/* Size relative to the BIGGEST mover, not a share of the net total: when gains
          and losses roughly cancel, shares of a near-zero net are meaningless. */}
      <span className="hidden h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-[var(--color-bg-elevated)] sm:block">
        <span
          className="block h-full rounded-full"
          style={{ width: `${Math.min(100, share * 100)}%`, backgroundColor: color }}
        />
      </span>
      <span className="shrink-0 text-sm font-semibold tabular-nums" style={{ color }}>
        {up ? "+" : "−"}
        {fmt(field, Math.abs(row.delta))}
      </span>
      <span className="hidden w-14 shrink-0 text-right text-xs tabular-nums text-[var(--color-text-muted)] sm:block">
        {row.change_pct != null ? formatPercent(row.change_pct) : "—"}
      </span>
    </li>
  );
}

function MoverList({
  title,
  rows,
  field,
  largest,
  prefix,
}: {
  title: string;
  rows: ContributionRow[];
  field: string;
  largest: number;
  prefix: string;
}) {
  if (rows.length === 0) return null;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
        {title}
      </p>
      <ul className="divide-y">
        {rows.map((row, index) => (
          <MoverRow
            key={`${prefix}-${row.key ?? index}`}
            row={row}
            field={field}
            share={Math.abs(row.delta) / largest}
          />
        ))}
      </ul>
    </div>
  );
}

export function WhatMoved({ filters }: { filters: Filters }) {
  const { data: me } = useMe();
  const permitted = useMemo(() => permittedMeasures(me?.metric_groups ?? []), [me]);
  const metrics = useMemo(() => METRICS.filter((m) => permitted.has(m.field)), [permitted]);

  const [metricField, setMetricField] = useState<string>(METRICS[0].field);
  const [dimension, setDimension] = useState<string>("app");

  // A chosen metric can outlive the permission that allowed it (role change, shared
  // link); fall back rather than asking the API for something it will refuse.
  const active = metrics.find((m) => m.field === metricField) ?? metrics[0];

  const query = useContribution(filters, dimension, active?.field ?? "", 8);
  const gainers = query.data?.gainers ?? [];
  const losers = query.data?.losers ?? [];
  const covered = query.data?.covered_delta ?? 0;
  const largest = Math.max(...[...gainers, ...losers].map((r) => Math.abs(r.delta)), 1);

  if (!active) {
    return (
      <ChartCard title="What moved">
        <p className="text-sm text-[var(--color-text-muted)]">
          None of the metrics this panel explains are visible to your role.
        </p>
      </ChartCard>
    );
  }

  const controls = (
    <div className="flex items-center gap-1.5">
      <select
        aria-label="Metric"
        value={active.field}
        onChange={(event) => setMetricField(event.target.value)}
        className={SELECT_CLASS}
      >
        {metrics.map((m) => (
          <option key={m.field} value={m.field}>
            {m.label}
          </option>
        ))}
      </select>
      <select
        aria-label="Group by"
        value={dimension}
        onChange={(event) => setDimension(event.target.value)}
        className={SELECT_CLASS}
      >
        {DIMENSIONS.map((d) => (
          <option key={d.id} value={d.id}>
            {d.label}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <ChartCard title="What moved" action={controls}>
      {query.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : query.isError ? (
        <p className="text-sm text-[var(--color-negative)]">
          Could not load movers: {(query.error as Error).message}
        </p>
      ) : gainers.length === 0 && losers.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">
          Nothing moved materially against the previous period.
        </p>
      ) : (
        <div className="space-y-3">
          <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
            {narrative(active.label, active.field, gainers, losers, covered)}
          </p>
          <MoverList
            title="Biggest declines"
            rows={losers}
            field={active.field}
            largest={largest}
            prefix="down"
          />
          <MoverList
            title="Biggest gains"
            rows={gainers}
            field={active.field}
            largest={largest}
            prefix="up"
          />
        </div>
      )}
    </ChartCard>
  );
}
'''


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def require_once(path: Path, text: str, anchor: str) -> None:
    if text.count(anchor) != 1:
        first = anchor.splitlines()[0].strip()
        die(f"{path}: expected exactly one {first!r}, found {text.count(anchor)}")


def main() -> None:
    for path in (TYPES, HOOKS, LAYOUT, CLIENT):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    texts = {path: path.read_text() for path in (TYPES, HOOKS, LAYOUT, CLIENT)}

    # permittedMeasures is imported from the revenue table; if that export ever moved,
    # the panel would fail at BUILD time, so check it here where the message is useful.
    table = Path("frontend/components/overview/revenue-table.tsx")
    if not table.exists() or "export function permittedMeasures" not in table.read_text():
        die(f"{table}: permittedMeasures is not exported there - the panel imports it")

    # Anchors: validate EVERY file before writing ANY. A registered widget whose
    # component does not compile takes the whole Overview down.
    plan: dict[Path, list[tuple[str, str, bool]]] = {}

    if "ContributionRow" in texts[TYPES]:
        print(f"{TYPES}: already has the types")
    else:
        require_once(TYPES, texts[TYPES], TYPES_ANCHOR)
        plan[TYPES] = [(TYPES_ANCHOR, TYPES_ADD, True)]

    if "useContribution" in texts[HOOKS]:
        print(f"{HOOKS}: already has the hook")
    else:
        require_once(HOOKS, texts[HOOKS], HOOKS_IMPORT_ANCHOR)
        require_once(HOOKS, texts[HOOKS], HOOKS_ANCHOR)
        plan[HOOKS] = [
            (HOOKS_IMPORT_ANCHOR, HOOKS_IMPORT_ADD, False),
            (HOOKS_ANCHOR, HOOKS_ADD, True),
        ]

    # The EXACT array line, not a bare quoted word: a bare '"what-moved"' could match a
    # comment or another literal and silently skip both edits, leaving the id out of
    # OVERVIEW_ITEM_IDS while the registry entry still expects it.
    if '  "what-moved",\n' in texts[LAYOUT]:
        print(f"{LAYOUT}: already registered")
    else:
        require_once(LAYOUT, texts[LAYOUT], LAYOUT_ID_ANCHOR)
        require_once(LAYOUT, texts[LAYOUT], LAYOUT_GRID_ANCHOR)
        plan[LAYOUT] = [
            (LAYOUT_ID_ANCHOR, LAYOUT_ID_ADD, False),
            (LAYOUT_GRID_ANCHOR, LAYOUT_GRID_ADD, True),
        ]

    if "WhatMoved" in texts[CLIENT]:
        print(f"{CLIENT}: already registered")
    else:
        require_once(CLIENT, texts[CLIENT], CLIENT_IMPORT_ANCHOR)
        require_once(CLIENT, texts[CLIENT], CLIENT_ITEM_ANCHOR)
        plan[CLIENT] = [
            (CLIENT_IMPORT_ANCHOR, CLIENT_IMPORT_ADD, False),
            (CLIENT_ITEM_ANCHOR, CLIENT_ITEM_ADD, False),
        ]

    panel_stale = not PANEL.exists() or PANEL.read_text() != PANEL_SOURCE

    if not plan and not panel_stale:
        print("already wired - nothing to do")
        return

    if panel_stale:
        PANEL.parent.mkdir(parents=True, exist_ok=True)
        PANEL.write_text(PANEL_SOURCE)
        print(f"wrote {PANEL}")

    for path, edits in plan.items():
        text = texts[path]
        for anchor, addition, before in edits:
            text = text.replace(anchor, (addition + anchor) if before else (anchor + addition), 1)
        path.write_text(text)
        print(f"patched {path}")

    print("\nWhat moved appears on Executive Overview below Top Apps.")
    print("Users with a SAVED layout keep theirs - normalizeLayouts adds the new widget")
    print("from the default, so it shows up for them too without a reset.")


if __name__ == "__main__":
    main()
