"use client";

import { useMemo, useState } from "react";

import {
  type ColumnDef,
  METRIC_COLUMNS,
  MetricTable,
  PUBLISHER_IDENTITY,
  permittedMeasures,
} from "@/components/overview/revenue-table";
import { useMe, useTable } from "@/lib/api-hooks";
import { num } from "@/lib/chart-helpers";
import type { Filters } from "@/lib/filters";

/* Top Apps, ranked by whichever measure the user picks.
 *
 * The ranking is NOT a client-side re-sort of a fixed list. /metrics/table is keyset
 * sorted server-side by one column and we only ever look at the first 100 rows, so
 * re-sorting that page by a different measure would give the top 10 OF THE TOP 100 BY
 * REVENUE - which is not the top 10 by UA cost, and would be silently wrong. Changing the
 * picker changes the SERVER sort as well, so the page fetched is the right page.
 *
 * Options are filtered by the caller's metric groups, so a role without spend is never
 * offered "UA Cost". That is cosmetic - the API refuses a sort on a measure the caller
 * cannot see - but being offered a choice that then errors is worse than not seeing it. */

/** Measures the reported ladder exposes that the shared columns do not. Deliberately
 *  local: adding them to METRIC_COLUMNS would push them into every dimension table. */
const EXTRA_COLUMNS: ColumnDef[] = [
  {
    id: "revenue",
    label: "Total Rev",
    requires: ["total_revenue_usd"],
    align: "right",
    fmt: "usd",
    value: (r) => num(r.total_revenue_usd),
  },
  {
    id: "partner-share",
    label: "Partner Share",
    requires: ["rpt_shares_fees_taxes_usd"],
    align: "right",
    fmt: "usd",
    value: (r) => num(r.rpt_shares_fees_taxes_usd),
  },
  {
    id: "gross-profit",
    label: "Gross Profit",
    requires: ["rpt_tf_profit_usd"],
    align: "right",
    fmt: "usd",
    value: (r) => num(r.rpt_tf_profit_usd),
  },
];

interface RankOption {
  /** Column id the table sorts by client-side. */
  id: string;
  label: string;
  /** The measure the SERVER sorts by - must be the same underlying number as the column,
   *  or the fetched page and the displayed ranking disagree. */
  field: string;
}

const RANK_OPTIONS: RankOption[] = [
  { id: "revenue", label: "Revenue", field: "total_revenue_usd" },
  { id: "ua", label: "UA Cost", field: "total_ua_spend_usd" },
  { id: "partner-share", label: "Partner Share", field: "rpt_shares_fees_taxes_usd" },
  { id: "gross-profit", label: "Gross Profit", field: "rpt_tf_profit_usd" },
  { id: "installs", label: "Total Installs", field: "store_total_installs" },
  { id: "paid", label: "Paid Installs", field: "total_paid_installs" },
  { id: "organic", label: "Organic Installs", field: "store_organic_installs" },
];

export function TopAppsTable({ filters }: { filters: Filters }) {
  const { data: me } = useMe();
  const permitted = useMemo(() => permittedMeasures(me?.metric_groups ?? []), [me]);

  const options = useMemo(
    () => RANK_OPTIONS.filter((option) => permitted.has(option.field)),
    [permitted],
  );

  const [choice, setChoice] = useState<string>(RANK_OPTIONS[0].id);
  // The chosen option may be one this role cannot see (a saved choice, or a role change
  // mid-session), so fall back to the first permitted one rather than sorting by nothing.
  const active = options.find((option) => option.id === choice) ?? options[0] ?? null;

  const columns = useMemo(
    () =>
      [...PUBLISHER_IDENTITY, ...METRIC_COLUMNS, ...EXTRA_COLUMNS].filter((column) =>
        column.requires.every((measure) => permitted.has(measure)),
      ),
    [permitted],
  );

  // canonical_key is always sortable, so a role with no permitted measure at all still
  // gets a table (unranked) instead of a failed request.
  const table = useTable(filters, active?.field ?? "canonical_key", 100);

  return (
    <MetricTable
      title={active ? `Top Apps by ${active.label}` : "Top Apps"}
      columns={columns}
      rows={table.data?.rows ?? []}
      rowKey={(r) => String(r.canonical_key ?? r.app_name ?? "")}
      isLoading={table.isLoading}
      isError={table.isError}
      sortId={active?.id}
      action={
        options.length > 1 ? (
          <select
            aria-label="Rank apps by"
            value={active?.id ?? ""}
            onChange={(event) => setChoice(event.target.value)}
            className="h-8 rounded-[var(--radius-inner)] border border-input bg-background px-2 text-xs outline-none focus:ring-1 focus:ring-ring"
          >
            {options.map((option) => (
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
