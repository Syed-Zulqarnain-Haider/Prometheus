#!/usr/bin/env python3
"""Admin-only Pod Performance table on the Executive Overview.

The owner asked for "a table just like HOU, but pod level, and only admins can see it".
The second half is the part that needs care. This codebase has already decided how an
admin-only breakdown works - `pod_owner` is deliberately absent from the public breakdown
whitelist so there is no second door through /metrics/breakdown - and the route comment
says so in as many words. This follows that precedent for the TABLE: its data comes from
the admin router, which carries require_capability("admin_panel"), the 2FA gate and the
step-up gate. Row scope still applies on top, as everywhere.

WHAT THIS DOES NOT DO, DELIBERATELY. It does not remove "pod" from _GROUP_BY_COLUMN. That
token is load-bearing well beyond this table: the Pod donut on the Overview reads it,
chat_service._GROUP_BY offers it as a grouping, and SCOPE_TO_GROUP_BY resolves pod TARGETS
and budget pacing through it. Pulling it would break all three. So the honest position is
stated rather than glossed: this table is genuinely admin-gated, and pod totals remain
reachable by a non-admin holding an `all` row scope via the donut or chat. Closing those
doors is a separate, deliberate decision for the owner with a known cost - not something
to slip into a feature.

The table inherits METRIC_COLUMNS wholesale, exactly as the HOU and Pod Owner tables do,
so the three cannot drift into showing different things, and metric-group RBAC filters the
columns server-side. Only additive measures are summed; ROAS and Net are recomputed by the
shared column defs from those totals, because averaging a ratio across pods of different
sizes produces a number that is nobody's.

On the grid it is a normal widget with one difference: for a non-admin it is filtered out
through the SAME mechanism that handles user-hidden cards, so no empty cell is reserved
and - importantly - it never enters their saved `hidden` list, which would otherwise leave
the card hidden for them if they were later made an admin.

    python3 scripts/pod-table-widget.py
"""

from __future__ import annotations

import sys
from pathlib import Path

FOOTER = "Rebuild backend + frontend, then run both suites."

POD_TABLE_TSX = '''"use client";

import { useMemo, useState } from "react";

import {
  type ColumnDef,
  METRIC_COLUMNS,
  MetricTable,
  type Row,
  permittedMeasures,
} from "@/components/overview/revenue-table";
import { usePodPerformance, useMe } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";

const UNASSIGNED = "Unassigned";

/** A NULL or blank pod maps to a single "Unassigned" bucket, never dropped, so pod totals
 *  reconcile with the rest of the dashboard. */
function podKey(row: Row): string {
  const value = row.pod;
  return value == null || String(value).trim() === "" ? UNASSIGNED : String(value);
}

/** The identity column: the pod name. No link - unlike HOU there is no /pod/[pod] page,
 *  and linking to one that does not exist implies a drill-down we do not have. */
const POD_IDENTITY: ColumnDef = {
  id: "pod",
  label: "Pod",
  requires: [],
  align: "left",
  fmt: "text",
  value: podKey,
  render: (row) => {
    const key = podKey(row);
    return key === UNASSIGNED ? (
      <span className="text-muted-foreground">{UNASSIGNED}</span>
    ) : (
      <span className="font-medium">{key}</span>
    );
  },
};

/** Pod Performance - the HOU table grouped by pod. ADMIN ONLY.
 *
 *  The gate is server-side: the data comes from the admin router, which carries
 *  require_capability("admin_panel"). Returning null here is the cosmetic half and a
 *  second line of defence only - the query is also disabled for a non-admin, so no
 *  request is even made. */
export function PodTable({ filters }: { filters: Filters }) {
  const { data: me } = useMe();
  const isAdmin = Boolean(me?.capabilities.includes("admin_panel"));
  const permitted = useMemo(() => permittedMeasures(me?.metric_groups ?? []), [me]);

  const columns = useMemo(
    () =>
      [POD_IDENTITY, ...METRIC_COLUMNS].filter((c) =>
        c.requires.every((m) => permitted.has(m)),
      ),
    [permitted],
  );

  // Rank options are the visible metric columns themselves - RBAC-filtered for free, and
  // a future METRIC_COLUMNS addition becomes an option here with no edit.
  const rankOptions = columns.filter((c) => c.id !== POD_IDENTITY.id);
  const [rankBy, setRankBy] = useState<string>("gross");
  // A saved choice can outlive the role that could see it; fall back rather than sorting
  // by nothing.
  const activeRank = rankOptions.find((c) => c.id === rankBy) ?? rankOptions[0];

  const measures = useMemo(
    () => [...new Set(columns.flatMap((c) => c.requires))],
    [columns],
  );

  const query = usePodPerformance(filters, measures, isAdmin);
  const rows = useMemo<Row[]>(() => (query.data?.rows ?? []) as Row[], [query.data]);

  // Once /me has resolved and the caller is not an admin, render nothing at all. Checked
  // against `me` rather than bare isAdmin so the card does not flicker away and back
  // while the profile is still loading.
  if (me && !isAdmin) return null;

  return (
    <MetricTable
      title="Pod Performance"
      columns={columns}
      rows={rows}
      rowKey={podKey}
      isLoading={query.isLoading}
      isError={query.isError}
      sortId={activeRank?.id}
      action={
        rankOptions.length > 1 ? (
          <select
            aria-label="Rank pods by"
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
}
'''

EDITS = [
    # ---------------------------------------------------------------- backend service
    {
        "path": "backend/app/services/admin_service.py",
        "anchor": '''        bucket = merged.setdefault(key, {"pod_owner": key, **dict.fromkeys(metrics, 0.0)})
        for measure in metrics:
            bucket[measure] += float(row[measure] or 0)

    sort_key = "total_revenue_usd" if "total_revenue_usd" in metrics else metrics[0]
    rows = sorted(merged.values(), key=lambda r: float(r.get(sort_key, 0) or 0), reverse=True)
    return {"measures": metrics, "rows": rows}
''',
        "replacement": '''        bucket = merged.setdefault(key, {"pod_owner": key, **dict.fromkeys(metrics, 0.0)})
        for measure in metrics:
            bucket[measure] += float(row[measure] or 0)

    sort_key = "total_revenue_usd" if "total_revenue_usd" in metrics else metrics[0]
    rows = sorted(merged.values(), key=lambda r: float(r.get(sort_key, 0) or 0), reverse=True)
    return {"measures": metrics, "rows": rows}


# A pod list is a short list. The cap exists so a mis-set filter cannot turn this into an
# unbounded scan, not because anyone is expected to approach it.
_POD_LIMIT = 500


async def pod_performance(
    db: AsyncSession, qb: QueryBuilder, params: MetricFilters, metrics: list[str]
) -> dict[str, Any]:
    """Per-pod totals. ADMIN ONLY - enforced by the route's capability check.

    Unlike ``pod_owner``, ``pod`` IS a public breakdown token: the Pod donut, the chat
    tool and pod TARGETS all resolve through it, so it cannot be removed without breaking
    them. This route is therefore the gate on THIS TABLE, and that is stated plainly
    rather than implied: a non-admin with an `all` row scope can still reach pod totals
    through those other paths. Closing them is a separate decision.

    Only ADDITIVE measures are summed. Net revenue and ROAS are recomputed by the
    frontend's shared column definitions from these totals - averaging a ratio across pods
    of different sizes produces a number that is nobody's.
    """
    result = (
        (await db.execute(qb.breakdown(params, "pod", metrics, limit=_POD_LIMIT)))
        .mappings()
        .all()
    )

    merged: dict[str, dict[str, Any]] = {}
    for row in result:
        raw = row["pod"]
        key = UNASSIGNED if raw is None or str(raw).strip() == "" else str(raw)
        bucket = merged.setdefault(key, {"pod": key, **dict.fromkeys(metrics, 0.0)})
        for measure in metrics:
            bucket[measure] += float(row[measure] or 0)

    sort_key = "total_revenue_usd" if "total_revenue_usd" in metrics else metrics[0]
    rows = sorted(merged.values(), key=lambda r: float(r.get(sort_key, 0) or 0), reverse=True)
    return {"measures": metrics, "rows": rows}
''',
        "marker": "async def pod_performance(",
    },
    # ------------------------------------------------------------------ backend route
    {
        "path": "backend/app/api/v1/admin.py",
        "anchor": '''        return await admin_service.pod_owner_performance(db, QueryBuilder(context), params, metrics)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
''',
        "replacement": '''        return await admin_service.pod_owner_performance(db, QueryBuilder(context), params, metrics)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/pod-performance")
async def pod_performance(
    context: CurrentUser,
    db: DbSession,
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
    metrics: Annotated[list[str], Query(min_length=1)],
) -> dict[str, Any]:
    """Per-pod totals - ADMIN ONLY.

    The gate is this router's ``require_capability("admin_panel")``, not the widget that
    calls it, so hiding the card is cosmetic and this is the real control. Row scope still
    applies on top, as everywhere else.

    Note the difference from ``pod-owner-performance`` above: ``pod_owner`` is absent from
    the public breakdown whitelist, so that route is the ONLY door to its data. ``pod`` is
    not - the Pod donut, the chat tool and pod targets all resolve through it. This route
    gates the TABLE; it does not claim to be the only way to reach a pod total.
    """
    try:
        params = MetricFilters(date_from=date_from, date_to=date_to)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid date range") from exc
    try:
        return await admin_service.pod_performance(db, QueryBuilder(context), params, metrics)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
''',
        "marker": '@router.get("/pod-performance")',
    },
    # ----------------------------------------------------------------- frontend hook
    {
        "path": "frontend/lib/api-hooks.ts",
        "anchor": '''    enabled: Boolean(user) && enabled && metrics.length > 0,
    staleTime: AGG_STALE,
  });
}

export function useSpotlight() {''',
        "replacement": '''    enabled: Boolean(user) && enabled && metrics.length > 0,
    staleTime: AGG_STALE,
  });
}

/** Per-pod totals for the admin-only Pod Performance table. `enabled` carries the caller's
 *  admin capability: a non-admin never issues the request at all, so the 403 the server
 *  would return is never generated in the first place. */
export function usePodPerformance(filters: Filters, metrics: string[], enabled: boolean) {
  const { user } = useAuth();
  const params = { ...filtersToApiQuery(filters), metrics };
  return useQuery({
    queryKey: ["pod-performance", params],
    queryFn: () =>
      apiFetch<{ measures: string[]; rows: Record<string, unknown>[] }>(
        `/api/v1/admin/pod-performance${buildQuery(params)}`,
      ),
    enabled: Boolean(user) && enabled && metrics.length > 0,
    staleTime: AGG_STALE,
  });
}

export function useSpotlight() {''',
        "marker": "export function usePodPerformance(",
    },
    # ------------------------------------------------------------- grid registration
    {
        "path": "frontend/lib/overview-layout.ts",
        "anchor": '''  "hou",
  "top-apps",''',
        "replacement": '''  "hou",
  "pod-table",
  "top-apps",''',
        "marker": '"pod-table",',
    },
    {
        "path": "frontend/lib/overview-layout.ts",
        "anchor": '''  { i: "hou", x: 0, y: 34, w: 12, h: 18, minW: 4, minH: 10 },''',
        "replacement": '''  { i: "hou", x: 0, y: 34, w: 12, h: 18, minW: 4, minH: 10 },
  { i: "pod-table", x: 0, y: 34, w: 12, h: 18, minW: 4, minH: 10 },''',
        "marker": '{ i: "pod-table",',
    },
    {
        "path": "frontend/lib/overview-layout.ts",
        "anchor": '''export type OverviewItemId = (typeof OVERVIEW_ITEM_IDS)[number];''',
        "replacement": '''export type OverviewItemId = (typeof OVERVIEW_ITEM_IDS)[number];

/** Widgets only an admin may see. Kept HERE, next to the id list, so adding a privileged
 *  widget and forgetting to gate it means editing this file and walking past the line
 *  that would have gated it. The real enforcement is server-side; this decides whether a
 *  cell is rendered at all, which is what keeps the grid from reserving an empty slot. */
export const ADMIN_ONLY_ITEMS: readonly OverviewItemId[] = ["pod-table"];''',
        "marker": "ADMIN_ONLY_ITEMS",
    },
    # ------------------------------------------------------------- overview client
    {
        "path": "frontend/components/overview/overview-client.tsx",
        "anchor": '''import { HouTable } from "@/components/overview/hou-table";''',
        "replacement": '''import { HouTable } from "@/components/overview/hou-table";
import { PodTable } from "@/components/overview/pod-table";''',
        "marker": 'import { PodTable }',
    },
    {
        "path": "frontend/components/overview/overview-client.tsx",
        "anchor": '''import {
  useClientSettings,
  useDashboardLayout,
  useResetDashboardLayout,
  useSaveDashboardLayout,
} from "@/lib/api-hooks";''',
        "replacement": '''import {
  useClientSettings,
  useDashboardLayout,
  useMe,
  useResetDashboardLayout,
  useSaveDashboardLayout,
} from "@/lib/api-hooks";''',
        "marker": "  useMe,\n  useResetDashboardLayout,",
    },
    {
        "path": "frontend/components/overview/overview-client.tsx",
        "anchor": '''import {
  defaultLayouts,
  normalizeLayouts,
  readHidden,
  visibleLayouts,
  withHidden,
  type OverviewItemId,
} from "@/lib/overview-layout";''',
        "replacement": '''import {
  ADMIN_ONLY_ITEMS,
  defaultLayouts,
  normalizeLayouts,
  readHidden,
  visibleLayouts,
  withHidden,
  type OverviewItemId,
} from "@/lib/overview-layout";''',
        "marker": "  ADMIN_ONLY_ITEMS,",
    },
    {
        "path": "frontend/components/overview/overview-client.tsx",
        "anchor": '''export function OverviewClient() {
  const { filters } = useFilters();
  const [editMode, setEditMode] = useState(false);''',
        "replacement": '''export function OverviewClient() {
  const { filters } = useFilters();
  const [editMode, setEditMode] = useState(false);
  const { data: me } = useMe();
  const isAdmin = Boolean(me?.capabilities.includes("admin_panel"));''',
        "marker": "const isAdmin = Boolean(me?.capabilities",
    },
    {
        "path": "frontend/components/overview/overview-client.tsx",
        "anchor": '''    hou: <HouTable filters={filters} />,''',
        "replacement": '''    hou: <HouTable filters={filters} />,
    "pod-table": <PodTable filters={filters} />,''',
        "marker": '"pod-table": <PodTable',
    },
    {
        "path": "frontend/components/overview/overview-client.tsx",
        "anchor": '''  const visibleItems = Object.fromEntries(
    (Object.keys(items) as OverviewItemId[])
      .filter((id) => !hidden.includes(id))
      .map((id) => [id, items[id]]),
  ) as Record<OverviewItemId, ReactNode>;''',
        "replacement": '''  // Hidden-by-choice PLUS not-permitted. Kept separate from `hidden` on purpose: an
  // admin-only card must never be written into a user's saved hidden list, or the day
  // they are made an admin the card stays invisible and nobody can explain why.
  const suppressed = useMemo(
    () => (isAdmin ? hidden : [...hidden, ...ADMIN_ONLY_ITEMS]),
    [hidden, isAdmin],
  );

  const visibleItems = Object.fromEntries(
    (Object.keys(items) as OverviewItemId[])
      .filter((id) => !suppressed.includes(id))
      .map((id) => [id, items[id]]),
  ) as Record<OverviewItemId, ReactNode>;''',
        "marker": "const suppressed = useMemo(",
    },
    {
        "path": "frontend/components/overview/overview-client.tsx",
        "anchor": '''        layouts={visibleLayouts(layouts, hidden)}''',
        "replacement": '''        layouts={visibleLayouts(layouts, suppressed)}''',
        "marker": "visibleLayouts(layouts, suppressed)",
    },
]

NEW_FILES = {"frontend/components/overview/pod-table.tsx": POD_TABLE_TSX}


def resolve(text, anchor, replacement, marker):
    """The deployment normalises em-dashes; flatten anchor, replacement and marker together
    or the patch reintroduces the character the file was cleaned of."""
    if anchor in text:
        return anchor, replacement, marker
    flat = anchor.replace("—", "-")
    if flat != anchor and flat in text:
        return flat, replacement.replace("—", "-"), marker.replace("—", "-")
    return anchor, replacement, marker


def locate(lines, anchor):
    """Line index where the longest present run of the anchor's own lines begins."""
    wanted = anchor.splitlines()
    joined = "\n".join(lines)
    for take in range(len(wanted), 0, -1):
        for start in (0, len(wanted) - take):
            probe = "\n".join(wanted[start : start + take])
            if not probe.strip():
                continue
            index = joined.find(probe)
            if index != -1:
                return joined.count("\n", 0, index) - start
    for offset, line in sorted(
        enumerate(wanted), key=lambda p: len(p[1].strip()), reverse=True
    ):
        if len(line.strip()) < 12:
            break
        index = joined.find(line)
        if index != -1:
            return joined.count("\n", 0, index) - offset
    return None


def main() -> int:
    if not Path("backend/app").is_dir() or not Path("frontend/lib").is_dir():
        print("ABORTED: run this from the repository root")
        return 1

    planned: dict[str, str] = {}
    problems: list[str] = []
    failures: list[tuple[str, str]] = []
    skipped: list[str] = []

    for rel, content in NEW_FILES.items():
        path = Path(rel)
        if path.exists() and path.read_text() == content:
            skipped.append(f"{rel}: already present")
            continue
        planned[rel] = content

    for index, edit in enumerate(EDITS, start=1):
        rel = edit["path"]
        path = Path(rel)
        if not path.exists():
            problems.append(f"  [{index}] {rel}: file not found")
            continue
        text = planned.get(rel, path.read_text())
        anchor, replacement, marker = resolve(
            text, edit["anchor"], edit["replacement"], edit["marker"]
        )
        if marker in text:
            skipped.append(f"{rel} [{index}]: already applied")
            continue
        found = text.count(anchor)
        if found != 1:
            problems.append(
                f"  [{index}] {rel}: expected exactly 1 match, found {found}\n"
                f"        anchor starts: {anchor.splitlines()[0][:76]!r}"
            )
            failures.append((rel, anchor))
            continue
        planned[rel] = text.replace(anchor, replacement, 1)

    if problems:
        print("ABORTED - NOTHING was written. Every problem, so one round-trip fixes all:")
        print()
        for problem in problems:
            print(problem)
        shown: dict[str, list[tuple[int, int]]] = {}
        for rel, anchor in failures:
            lines = Path(rel).read_text().splitlines()
            hit = locate(lines, anchor)
            if hit is None:
                lo, hi = 0, min(len(lines), 120)
                note = "nothing from this anchor is on disk - head of file"
            else:
                lo, hi = max(0, hit - 30), min(len(lines), hit + 30)
                note = f"nearest partial match at line {hit + 1}"
            if any(lo >= a and hi <= b for a, b in shown.get(rel, [])):
                continue
            shown.setdefault(rel, []).append((lo, hi))
            print()
            print(f"----- {rel} lines {lo + 1}-{hi} of {len(lines)} ({note}) -----")
            for n, line in enumerate(lines[lo:hi], start=lo + 1):
                print(f"{n:6d}\t{line}")
        print()
        print("The regions above are what is actually on disk; I re-anchor from them.")
        return 1

    # Verify the OUTPUT, not the inputs. The failure that matters here is a privileged
    # widget rendered for everyone, so check the gate is actually wired rather than
    # trusting that thirteen anchors happened to land in the right order.
    client = planned.get(
        "frontend/components/overview/overview-client.tsx",
        Path("frontend/components/overview/overview-client.tsx").read_text(),
    )
    layout = planned.get(
        "frontend/lib/overview-layout.ts", Path("frontend/lib/overview-layout.ts").read_text()
    )
    checks = [
        ('"pod-table"' in layout, "pod-table is not in OVERVIEW_ITEM_IDS"),
        ("ADMIN_ONLY_ITEMS" in layout, "ADMIN_ONLY_ITEMS was not created"),
        ("suppressed" in client, "the admin filter was never added to the client"),
        (
            "visibleLayouts(layouts, suppressed)" in client,
            "the grid still lays out by `hidden`, so a non-admin gets an empty cell",
        ),
        (
            ".filter((id) => !suppressed.includes(id))" in client,
            "visibleItems still filters by `hidden`, so a non-admin renders the card",
        ),
        (
            "withHidden(layouts, hidden)" in client,
            "saving must persist `hidden`, never `suppressed` - otherwise the admin-only"
            " id is written into a user's saved hidden list",
        ),
    ]
    broken = [message for ok, message in checks if not ok]
    if broken:
        print("ABORTED - NOTHING was written. The gate is not correctly wired:")
        print()
        for message in broken:
            print(f"  {message}")
        return 1

    for rel, content in sorted(planned.items()):
        path = Path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"wrote {rel}")
    for note in skipped:
        print(f"skip  {note}")
    if not planned:
        print("nothing to do - already applied")
        return 0
    print()
    print(FOOTER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
