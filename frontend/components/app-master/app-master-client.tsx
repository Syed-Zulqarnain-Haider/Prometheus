"use client";

import { RefreshCw, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api-client";
import {
  type AppMasterColumnMeta,
  type AppMasterFilters,
  useAppMaster,
  useMe,
  useRefreshAppMaster,
  useUpdateAppMaster,
} from "@/lib/api-hooks";

const PAGE_SIZE = 50;
const EMPTY_FILTERS: AppMasterFilters = { search: "", platform: "", hou: "", pod: "", needsReview: "" };

function formatCell(value: unknown, type: AppMasterColumnMeta["type"]): string {
  if (value === null || value === undefined || value === "") return "—";
  if (type === "boolean") return value ? "Yes" : "No";
  if (type === "timestamptz") return String(value).slice(0, 10);
  return String(value);
}

/** Coerce an edit-form field back to the value we send to the API. */
function parseField(raw: string | boolean, type: AppMasterColumnMeta["type"]): unknown {
  if (type === "boolean") return Boolean(raw);
  const text = String(raw).trim();
  if (text === "") return null;
  if (type === "bigint") return Number.parseInt(text, 10);
  if (type === "double") return Number.parseFloat(text);
  return text;
}

function EditDrawer({
  row,
  columns,
  primaryKey,
  onClose,
}: {
  row: Record<string, unknown>;
  columns: AppMasterColumnMeta[];
  primaryKey: string;
  onClose: () => void;
}) {
  const update = useUpdateAppMaster();
  const editable = useMemo(() => columns.filter((c) => c.editable), [columns]);
  const key = String(row[primaryKey] ?? "");

  // Local form state seeded from the row (strings for text/number inputs, booleans for checks).
  const [form, setForm] = useState<Record<string, string | boolean>>(() => {
    const seed: Record<string, string | boolean> = {};
    for (const c of editable) {
      const v = row[c.name];
      seed[c.name] = c.type === "boolean" ? Boolean(v) : v == null ? "" : String(v);
    }
    return seed;
  });

  function onSave() {
    // Only send columns whose value actually changed.
    const body: Record<string, unknown> = {};
    for (const c of editable) {
      const next = parseField(form[c.name], c.type);
      const original = c.type === "boolean" ? Boolean(row[c.name]) : (row[c.name] ?? null);
      const originalNorm = original === "" ? null : original;
      if (JSON.stringify(next) !== JSON.stringify(originalNorm)) body[c.name] = next;
    }
    if (Object.keys(body).length === 0) {
      onClose();
      return;
    }
    update.mutate({ key, body }, { onSuccess: onClose });
  }

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
      <button aria-label="Close" tabIndex={-1} onClick={onClose} className="absolute inset-0 bg-black/50" />
      <div className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l bg-card shadow-xl">
        <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{String(row.app_name ?? key)}</p>
            <p className="truncate text-xs text-muted-foreground">{key}</p>
          </div>
          <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {editable.map((c) => (
            <div key={c.name} className="space-y-1">
              <Label htmlFor={`f-${c.name}`} className="text-xs">
                {c.name}
              </Label>
              {c.type === "boolean" ? (
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <Checkbox
                    checked={Boolean(form[c.name])}
                    onCheckedChange={(v) => setForm((f) => ({ ...f, [c.name]: Boolean(v) }))}
                  />
                  {form[c.name] ? "Yes" : "No"}
                </label>
              ) : (
                <Input
                  id={`f-${c.name}`}
                  type={c.type === "bigint" || c.type === "double" ? "number" : "text"}
                  step={c.type === "double" ? "any" : undefined}
                  value={String(form[c.name] ?? "")}
                  onChange={(e) => setForm((f) => ({ ...f, [c.name]: e.target.value }))}
                />
              )}
            </div>
          ))}
        </div>

        <div className="shrink-0 space-y-2 border-t p-4">
          {update.isError && (
            <p className="text-xs text-destructive" role="alert">
              {update.error instanceof ApiError
                ? update.error.message
                : "Could not save — please try again."}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose} disabled={update.isPending}>
              Cancel
            </Button>
            <Button onClick={onSave} disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AppMasterClient() {
  const { data: me, isLoading: meLoading } = useMe();
  const [filters, setFilters] = useState<AppMasterFilters>(EMPTY_FILTERS);
  const [page, setPage] = useState(0);
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null);

  // Reset to the first page whenever a filter changes.
  useEffect(() => setPage(0), [filters]);

  const query = useAppMaster(filters, PAGE_SIZE, page * PAGE_SIZE);
  const refresh = useRefreshAppMaster();

  if (meLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!me?.capabilities.includes("admin_panel")) {
    return <p className="text-sm text-muted-foreground">You don&apos;t have access to App Master.</p>;
  }

  const data = query.data;
  const columns = data?.columns ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasFilters = Boolean(
    filters.search || filters.platform || filters.hou || filters.pod || filters.needsReview,
  );

  return (
    <div className="space-y-4">
      {/* Separate filter bar for this page only. */}
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Search</Label>
          <Input
            className="h-8 w-48"
            placeholder="app, key, publisher…"
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Platform</Label>
          <Select
            value={filters.platform || "all"}
            onValueChange={(v) => setFilters((f) => ({ ...f, platform: v === "all" ? "" : v }))}
          >
            <SelectTrigger className="h-8 w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="ios">iOS</SelectItem>
              <SelectItem value="android">Android</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">HOU</Label>
          <Input
            className="h-8 w-28"
            value={filters.hou}
            onChange={(e) => setFilters((f) => ({ ...f, hou: e.target.value }))}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Pod</Label>
          <Input
            className="h-8 w-20"
            type="number"
            value={filters.pod}
            onChange={(e) => setFilters((f) => ({ ...f, pod: e.target.value }))}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Needs review</Label>
          <Select
            value={filters.needsReview || "any"}
            onValueChange={(v) =>
              setFilters((f) => ({ ...f, needsReview: v === "any" ? "" : (v as "true" | "false") }))
            }
          >
            <SelectTrigger className="h-8 w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any</SelectItem>
              <SelectItem value="true">Yes</SelectItem>
              <SelectItem value="false">No</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" size="sm" onClick={() => setFilters(EMPTY_FILTERS)}>
          Clear
        </Button>
        <div className="ml-auto flex items-center gap-2">
          {refresh.isSuccess && (
            <span className="text-xs text-muted-foreground">
              Synced {refresh.data.synced}
              {refresh.data.skipped ? ` · skipped ${refresh.data.skipped}` : ""}
            </span>
          )}
          {refresh.isError && (
            <span className="text-xs text-destructive">
              {refresh.error instanceof ApiError ? refresh.error.message : "Refresh failed."}
            </span>
          )}
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
          >
            <RefreshCw className={`h-4 w-4 ${refresh.isPending ? "animate-spin" : ""}`} />
            {refresh.isPending ? "Refreshing…" : "Refresh from BigQuery"}
          </Button>
        </div>
      </div>

      {/* Wide, horizontally scrollable grid. */}
      <div className="rounded-lg border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="sticky left-0 z-10 bg-card px-3 py-2 text-left">Edit</th>
                {columns.map((c) => (
                  <th key={c.name} className="whitespace-nowrap px-3 py-2 text-left font-medium">
                    {c.name}
                    {c.editable && <span className="ml-1 text-[color:var(--color-accent)]">•</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {query.isLoading && (
                <tr>
                  <td className="px-3 py-6 text-center text-muted-foreground" colSpan={columns.length + 1}>
                    Loading…
                  </td>
                </tr>
              )}
              {query.isError && (
                <tr>
                  <td
                    className="px-3 py-6 text-center text-[color:var(--color-negative)]"
                    colSpan={columns.length + 1}
                  >
                    Couldn&apos;t load App Master — please retry.
                  </td>
                </tr>
              )}
              {!query.isLoading && !query.isError && (data?.rows.length ?? 0) === 0 && (
                <tr>
                  <td className="px-3 py-6 text-center text-muted-foreground" colSpan={columns.length + 1}>
                    {hasFilters
                      ? "No apps match these filters."
                      : "No apps loaded yet — click “Refresh from BigQuery” to pull the master list."}
                  </td>
                </tr>
              )}
              {data?.rows.map((row, i) => (
                <tr key={String(row[data.primary_key] ?? i)} className="border-b border-border-faint hover:bg-accent">
                  <td className="sticky left-0 z-10 bg-card px-3 py-1.5">
                    <Button variant="outline" size="sm" onClick={() => setEditing(row)}>
                      Edit
                    </Button>
                  </td>
                  {columns.map((c) => (
                    <td key={c.name} className="whitespace-nowrap px-3 py-1.5">
                      {formatCell(row[c.name], c.type)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between border-t px-3 py-2 text-xs text-muted-foreground">
          <span>
            {total} app{total === 1 ? "" : "s"} · editable columns marked{" "}
            <span className="text-[color:var(--color-accent)]">•</span>
          </span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              Prev
            </Button>
            <span>
              Page {page + 1} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page + 1 >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </div>

      {editing && data && (
        <EditDrawer
          row={editing}
          columns={columns}
          primaryKey={data.primary_key}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
