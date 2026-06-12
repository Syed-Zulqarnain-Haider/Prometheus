"use client";

import {
  type ColumnDef,
  type SortingState,
  type VisibilityState,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, Settings2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { useTableInfinite } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";
import { formatNumber, formatUSD } from "@/lib/format";

type AppRow = Record<string, number | string | null>;

interface Candidate {
  key: string;
  label: string;
  kind: "app" | "usd" | "number" | "text";
  sortable: boolean;
}

// Order + presentation of candidate columns. Measures only appear when the row
// includes them (RBAC-filtered server-side); dimensions always appear.
const CANDIDATES: Candidate[] = [
  { key: "app_name", label: "App", kind: "app", sortable: true },
  { key: "total_revenue_usd", label: "Revenue", kind: "usd", sortable: true },
  { key: "total_ua_spend_usd", label: "Spend", kind: "usd", sortable: true },
  { key: "profit_usd", label: "Profit", kind: "usd", sortable: true },
  { key: "total_iap_net_usd", label: "IAP Net", kind: "usd", sortable: true },
  { key: "total_ad_revenue_usd", label: "Ad Rev", kind: "usd", sortable: true },
  { key: "store_total_installs", label: "Installs", kind: "number", sortable: true },
  { key: "total_paid_installs", label: "Paid", kind: "number", sortable: true },
  { key: "store_organic_installs", label: "Organic", kind: "number", sortable: true },
  { key: "publisher", label: "Publisher", kind: "text", sortable: false },
  { key: "pod", label: "Pod", kind: "text", sortable: false },
  { key: "hou", label: "HoU", kind: "text", sortable: false },
];

const ALWAYS = new Set(["app_name", "publisher", "pod", "hou"]);

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function buildColumns(available: Set<string>): ColumnDef<AppRow>[] {
  return CANDIDATES.filter((c) => ALWAYS.has(c.key) || available.has(c.key)).map((c) => ({
    id: c.key,
    accessorKey: c.key,
    header: c.label,
    enableSorting: c.sortable,
    enableHiding: c.key !== "app_name",
    cell: ({ getValue }) => {
      const value = getValue() as number | string | null;
      if (c.kind === "usd") return formatUSD(typeof value === "number" ? value : null);
      if (c.kind === "number") return formatNumber(typeof value === "number" ? value : null);
      if (c.kind === "app") {
        return (
          <span className="font-medium text-[color:var(--color-accent)]">
            {String(value ?? "—")}
          </span>
        );
      }
      return String(value ?? "—");
    },
  }));
}

export function AppsExplorer({ filters }: { filters: Filters }) {
  const router = useRouter();
  const [sorting, setSorting] = useState<SortingState>([{ id: "app_name", desc: false }]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search, 250);

  const sort = sorting[0]?.id ?? "app_name";
  const direction = sorting[0]?.desc ? "desc" : "asc";
  const query = useTableInfinite(filters, sort, direction);

  const allRows = useMemo<AppRow[]>(
    () => query.data?.pages.flatMap((p) => p.rows as AppRow[]) ?? [],
    [query.data],
  );
  const available = useMemo(() => {
    const keys = new Set<string>();
    for (const row of allRows) for (const k of Object.keys(row)) keys.add(k);
    return keys;
  }, [allRows]);
  const columns = useMemo(() => buildColumns(available), [available]);

  const q = debouncedSearch.trim().toLowerCase();
  const rows = useMemo(
    () =>
      q
        ? allRows.filter((r) =>
            [r.app_name, r.publisher, r.pod].some((x) =>
              String(x ?? "").toLowerCase().includes(q),
            ),
          )
        : allRows,
    [allRows, q],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting, columnVisibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    manualSorting: true,
    enableSortingRemoval: false,
    enableMultiSort: false,
    getCoreRowModel: getCoreRowModel(),
  });

  const visibleColumns = table.getVisibleLeafColumns();
  const gridTemplate = visibleColumns
    .map((col) =>
      col.id === "app_name"
        ? "minmax(180px, 1.6fr)"
        : ALWAYS.has(col.id)
          ? "minmax(110px, 1fr)"
          : "110px",
    )
    .join(" ");

  const scrollRef = useRef<HTMLDivElement>(null);
  const tableRows = table.getRowModel().rows;
  const virtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 44,
    overscan: 12,
  });
  const virtualItems = virtualizer.getVirtualItems();

  // Auto-load the next keyset page when scrolled near the bottom (not while filtering).
  useEffect(() => {
    const last = virtualItems[virtualItems.length - 1];
    if (!last) return;
    if (
      !q &&
      last.index >= tableRows.length - 1 &&
      query.hasNextPage &&
      !query.isFetchingNextPage
    ) {
      void query.fetchNextPage();
    }
  }, [virtualItems, tableRows.length, q, query]);

  return (
    <div className="space-y-4">
      <PageHeader title="Apps Explorer" />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <Input
          placeholder="Search app, publisher, pod…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              <Settings2 className="h-4 w-4" /> Columns
            </Button>
          </PopoverTrigger>
          <PopoverContent className="max-h-72 overflow-auto">
            <div className="space-y-1">
              {table
                .getAllLeafColumns()
                .filter((col) => col.getCanHide())
                .map((col) => {
                  const label = CANDIDATES.find((c) => c.key === col.id)?.label ?? col.id;
                  return (
                    <label
                      key={col.id}
                      className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm hover:bg-accent"
                    >
                      <Checkbox
                        checked={col.getIsVisible()}
                        onCheckedChange={(v) => col.toggleVisibility(Boolean(v))}
                      />
                      {label}
                    </label>
                  );
                })}
            </div>
          </PopoverContent>
        </Popover>
      </div>

      <div className="rounded-lg border bg-card">
        {/* header */}
        <div
          className="grid border-b text-[11px] uppercase tracking-wider text-muted-foreground"
          style={{ gridTemplateColumns: gridTemplate }}
        >
          {table.getHeaderGroups()[0]?.headers.map((header) => {
            const canSort = header.column.getCanSort();
            const sorted = header.column.getIsSorted();
            return (
              <button
                key={header.id}
                type="button"
                disabled={!canSort}
                onClick={header.column.getToggleSortingHandler()}
                className={`flex items-center gap-1 px-3 py-2 text-left ${
                  canSort ? "hover:text-foreground" : "cursor-default"
                } ${ALWAYS.has(header.column.id) && header.column.id !== "app_name" ? "" : "justify-start"}`}
              >
                {flexRender(header.column.columnDef.header, header.getContext())}
                {sorted === "asc" && <ArrowUp className="h-3 w-3" />}
                {sorted === "desc" && <ArrowDown className="h-3 w-3" />}
              </button>
            );
          })}
        </div>

        {/* virtualized body */}
        <div ref={scrollRef} className="relative h-[600px] overflow-auto">
          {query.isLoading ? (
            <div className="space-y-2 p-3">
              {Array.from({ length: 10 }).map((_, i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : tableRows.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              No apps for the selected filters
            </div>
          ) : (
            <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
              {virtualItems.map((vi) => {
                const row = tableRows[vi.index];
                const key = String(row.original.canonical_key);
                return (
                  <div
                    key={row.id}
                    onClick={() => router.push(`/apps/${encodeURIComponent(key)}`)}
                    className="absolute left-0 grid w-full cursor-pointer items-center border-b border-border-faint text-sm hover:bg-accent"
                    style={{
                      gridTemplateColumns: gridTemplate,
                      height: vi.size,
                      transform: `translateY(${vi.start}px)`,
                    }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <div
                        key={cell.id}
                        className={`truncate px-3 ${
                          cell.column.id === "app_name" || ALWAYS.has(cell.column.id)
                            ? "text-left"
                            : "text-right tabular-nums"
                        }`}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t px-3 py-2 text-xs text-muted-foreground">
          <span>{rows.length} apps loaded</span>
          {query.isFetchingNextPage && <span>Loading more…</span>}
        </div>
      </div>
    </div>
  );
}
