"use client";

import { Check, ChevronDown, RefreshCw, Search as SearchIcon, Undo2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
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
  useAppMasterFilterValues,
  useAppMasterSchemaDiff,
  useAppMasterSchemaSync,
  useMe,
  useRefreshAppMaster,
  useSetAppMasterColumnOrder,
  useUndoAppMaster,
  useUpdateAppMaster,
} from "@/lib/api-hooks";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;

/** Lists longer than this get a search box instead of a plain dropdown. */
const SEARCHABLE_THRESHOLD = 12;

const EMPTY_FILTERS: AppMasterFilters = {
  search: "",
  platform: "",
  hou: "",
  publisher: "",
  pod: "",
  podOwner: "",
  appName: "",
  partnerName: "",
  needsReview: "",
  package: "",
  appId: "",
  syncedFrom: "",
  syncedTo: "",
};

function formatCell(value: unknown, type: AppMasterColumnMeta["type"]): string {
  if (value === null || value === undefined || value === "") return "";
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
  const undo = useUndoAppMaster();
  const filterValues = useAppMasterFilterValues();
  const editable = useMemo(() => columns.filter((c) => c.editable), [columns]);
  const key = String(row[primaryKey] ?? "");
  const [localError, setLocalError] = useState<string | null>(null);

  // Column name -> existing values, so these edit fields render as dropdowns (pick a known
  // value, or type a new one). Keeps HOU / pod owner / publisher / partner consistent.
  const OPTIONS: Record<string, string[] | undefined> = {
    publisher: filterValues.data?.publishers,
    pod_owner: filterValues.data?.pod_owners,
    hou: filterValues.data?.hou,
    partner_name: filterValues.data?.partner_names,
  };

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
    setLocalError(null);
    // Client-side guards matching the backend: pod > 0, net_revenue_share in [0.0, 1.0].
    const podRaw = String(form["pod"] ?? "").trim();
    if (podRaw !== "") {
      const n = Number(podRaw);
      if (!Number.isInteger(n) || n <= 0) {
        setLocalError("Pod must be a whole number greater than 0.");
        return;
      }
    }
    const nrsRaw = String(form["net_revenue_share"] ?? "").trim();
    if (nrsRaw !== "") {
      const n = Number(nrsRaw);
      if (Number.isNaN(n) || n < 0 || n > 1) {
        setLocalError("Net revenue share must be a number between 0.0 and 1.0.");
        return;
      }
    }
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

  const busy = update.isPending || undo.isPending;

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
      <button
        aria-label="Close"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 bg-black/50"
      />
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
              ) : OPTIONS[c.name] ? (
                <>
                  {/* Dropdown of existing values - you can also type a new one. */}
                  <Input
                    id={`f-${c.name}`}
                    list={`dl-${c.name}`}
                    value={String(form[c.name] ?? "")}
                    onChange={(e) => setForm((f) => ({ ...f, [c.name]: e.target.value }))}
                    placeholder="Select or type…"
                  />
                  <datalist id={`dl-${c.name}`}>
                    {(OPTIONS[c.name] ?? []).map((o) => (
                      <option key={o} value={o} />
                    ))}
                  </datalist>
                </>
              ) : c.name === "pod" ? (
                <Input
                  id={`f-${c.name}`}
                  type="number"
                  min={1}
                  step={1}
                  value={String(form[c.name] ?? "")}
                  onChange={(e) => setForm((f) => ({ ...f, [c.name]: e.target.value }))}
                  placeholder="Pod number (> 0)"
                />
              ) : c.name === "net_revenue_share" ? (
                <Input
                  id={`f-${c.name}`}
                  type="number"
                  min={0}
                  max={1}
                  step="0.01"
                  value={String(form[c.name] ?? "")}
                  onChange={(e) => setForm((f) => ({ ...f, [c.name]: e.target.value }))}
                  placeholder="0.0 - 1.0"
                />
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
          {localError && (
            <p className="text-xs text-destructive" role="alert">
              {localError}
            </p>
          )}
          {update.isError && (
            <p className="text-xs text-destructive" role="alert">
              {update.error instanceof ApiError
                ? update.error.message
                : "Could not save - please try again."}
            </p>
          )}
          {undo.isError && (
            <p className="text-xs text-destructive" role="alert">
              {undo.error instanceof ApiError ? undo.error.message : "Nothing to undo."}
            </p>
          )}
          <div className="flex items-center justify-between gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="gap-1 text-muted-foreground"
              disabled={busy}
              title="Revert the most recent edit on this app"
              onClick={() => undo.mutate(key, { onSuccess: onClose })}
            >
              <Undo2 className="h-4 w-4" />
              Undo last edit
            </Button>
            <div className="flex gap-2">
              <Button variant="outline" onClick={onClose} disabled={busy}>
                Cancel
              </Button>
              <Button onClick={onSave} disabled={busy}>
                {update.isPending ? "Saving…" : "Save changes"}
              </Button>
            </div>
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

  // Column-reorder mode (admin): drag headers, then Save applies it globally.
  const [reordering, setReordering] = useState(false);
  const [localOrder, setLocalOrder] = useState<string[]>([]);
  const dragCol = useRef<string | null>(null);

  useEffect(() => setPage(0), [filters]);

  const query = useAppMaster(filters, PAGE_SIZE, page * PAGE_SIZE);
  const values = useAppMasterFilterValues();
  const refresh = useRefreshAppMaster();
  const schema = useAppMasterSchemaDiff();
  const schemaSync = useAppMasterSchemaSync();
  const saveOrder = useSetAppMasterColumnOrder();

  if (meLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!me?.capabilities.includes("admin_panel")) {
    return <p className="text-sm text-muted-foreground">You don&apos;t have access to App Master.</p>;
  }

  const data = query.data;
  const columns = data?.columns ?? [];
  const colByName = new Map(columns.map((c) => [c.name, c]));
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasFilters = Object.values(filters).some(Boolean);

  // Columns to render: the dragged local order while reordering, else the server order.
  const shownColumns = reordering
    ? localOrder.map((n) => colByName.get(n)).filter((c): c is AppMasterColumnMeta => Boolean(c))
    : columns;

  function startReorder() {
    setLocalOrder(columns.map((c) => c.name));
    setReordering(true);
  }
  function dropOn(target: string) {
    const from = dragCol.current;
    dragCol.current = null;
    if (!from || from === target) return;
    setLocalOrder((prev) => {
      const next = prev.filter((n) => n !== from);
      next.splice(next.indexOf(target), 0, from);
      return next;
    });
  }

  const platformOpts = values.data?.platforms ?? ["ios", "android"];
  const houOpts = values.data?.hou ?? [];
  const publisherOpts = values.data?.publishers ?? [];
  const podOwnerOpts = values.data?.pod_owners ?? [];
  const partnerOpts = values.data?.partner_names ?? [];
  const appNameOpts = values.data?.app_names ?? [];
  // Pods are integers server-side; the control speaks strings and the hook casts back.
  const podOpts = (values.data?.pods ?? []).map(String);

  return (
    <div className="space-y-4">
      {/* Filter bar (this page only). */}
      <div className="flex flex-wrap items-end gap-2">
        <FilterText
          label="Search"
          width="w-44"
          placeholder="app, key, publisher…"
          value={filters.search}
          onChange={(v) => setFilters((f) => ({ ...f, search: v }))}
        />
        <FilterPicker
          label="App name"
          width="w-52"
          value={filters.appName}
          options={appNameOpts}
          onChange={(v) => setFilters((f) => ({ ...f, appName: v }))}
        />
        <FilterSelect
          label="Platform"
          value={filters.platform}
          options={platformOpts}
          onChange={(v) => setFilters((f) => ({ ...f, platform: v }))}
        />
        <FilterPicker
          label="Publisher"
          value={filters.publisher}
          options={publisherOpts}
          onChange={(v) => setFilters((f) => ({ ...f, publisher: v }))}
        />
        <FilterSelect
          label="HOU"
          value={filters.hou}
          options={houOpts}
          onChange={(v) => setFilters((f) => ({ ...f, hou: v }))}
        />
        <FilterPicker
          label="Pod owner"
          value={filters.podOwner}
          options={podOwnerOpts}
          onChange={(v) => setFilters((f) => ({ ...f, podOwner: v }))}
        />
        <FilterSelect
          label="Pod"
          width="w-24"
          value={filters.pod}
          options={podOpts}
          onChange={(v) => setFilters((f) => ({ ...f, pod: v }))}
        />
        <FilterPicker
          label="Partner"
          value={filters.partnerName}
          options={partnerOpts}
          onChange={(v) => setFilters((f) => ({ ...f, partnerName: v }))}
        />
        <FilterText
          label="Package"
          width="w-40"
          value={filters.package}
          onChange={(v) => setFilters((f) => ({ ...f, package: v }))}
        />
        <FilterText
          label="App ID"
          width="w-32"
          value={filters.appId}
          onChange={(v) => setFilters((f) => ({ ...f, appId: v }))}
        />
        <div className="space-y-1">
          <Label className="text-xs">Needs review</Label>
          <Select
            value={filters.needsReview || "any"}
            onValueChange={(v) =>
              setFilters((f) => ({ ...f, needsReview: v === "any" ? "" : (v as "true" | "false") }))
            }
          >
            <SelectTrigger className="h-8 w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any</SelectItem>
              <SelectItem value="true">Yes</SelectItem>
              <SelectItem value="false">No</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Last synced from</Label>
          <Input
            className="h-8 w-36"
            type="date"
            value={filters.syncedFrom}
            max={filters.syncedTo || undefined}
            onChange={(e) => setFilters((f) => ({ ...f, syncedFrom: e.target.value }))}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Last synced to</Label>
          <Input
            className="h-8 w-36"
            type="date"
            value={filters.syncedTo}
            min={filters.syncedFrom || undefined}
            onChange={(e) => setFilters((f) => ({ ...f, syncedTo: e.target.value }))}
          />
        </div>
        <Button variant="outline" size="sm" onClick={() => setFilters(EMPTY_FILTERS)}>
          Clear
        </Button>
        <div className="ml-auto flex items-center gap-2">
          {refresh.isSuccess && (
            <span className="text-xs text-positive">
              ✓ Synced {refresh.data.synced}
              {refresh.data.skipped ? ` · skipped ${refresh.data.skipped}` : ""}
            </span>
          )}
          {refresh.isError && (
            <span className="text-xs text-destructive">
              {refresh.error instanceof ApiError ? refresh.error.message : "Refresh failed."}
            </span>
          )}
          <Button variant="outline" size="sm" onClick={() => schema.mutate()} disabled={schema.isPending}>
            {schema.isPending ? "Checking…" : "Check schema"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => schemaSync.mutate()}
            disabled={schemaSync.isPending}
            title="Add any new BigQuery columns to Postgres (read-only) and flag removed ones. Never drops data."
          >
            {schemaSync.isPending ? "Matching…" : "Match DB & BigQuery Schema"}
          </Button>
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

      {/* Schema-sync (Match DB & BigQuery) result. */}
      {(schemaSync.data || schemaSync.isError) && (
        <div className="rounded-lg border bg-card p-3 text-sm">
          {schemaSync.isError ? (
            <p className="text-destructive">
              {schemaSync.error instanceof ApiError
                ? schemaSync.error.message
                : "Schema match failed."}
            </p>
          ) : schemaSync.data && !schemaSync.data.configured ? (
            <p className="text-muted-foreground">{schemaSync.data.message}</p>
          ) : schemaSync.data && !schemaSync.data.ok ? (
            <p className="text-destructive">{schemaSync.data.message}</p>
          ) : schemaSync.data ? (
            <div className="space-y-1">
              <p className="font-medium text-[color:var(--color-positive)]">
                ✓ Schema matched to BigQuery.
              </p>
              {schemaSync.data.added.length > 0 && (
                <p>
                  <span className="text-muted-foreground">Added (read-only):</span>{" "}
                  {schemaSync.data.added.map((c) => `${c.name} (${c.type})`).join(", ")}
                </p>
              )}
              {schemaSync.data.healed_static.length > 0 && (
                <p>
                  <span className="text-muted-foreground">Restored missing:</span>{" "}
                  {schemaSync.data.healed_static.join(", ")}
                </p>
              )}
              {schemaSync.data.deactivated.length > 0 && (
                <p>
                  <span className="text-muted-foreground">
                    Removed from BigQuery (kept + flagged):
                  </span>{" "}
                  {schemaSync.data.deactivated.join(", ")}
                </p>
              )}
              {schemaSync.data.missing_in_bigquery.length > 0 && (
                <p className="text-muted-foreground">
                  Not in BigQuery: {schemaSync.data.missing_in_bigquery.join(", ")}
                </p>
              )}
              {schemaSync.data.unsupported_types.length > 0 && (
                <p className="text-muted-foreground">
                  Skipped (unsupported):{" "}
                  {schemaSync.data.unsupported_types.map((c) => `${c.name} (${c.type})`).join(", ")}
                </p>
              )}
              {schemaSync.data.added.length === 0 &&
                schemaSync.data.deactivated.length === 0 &&
                schemaSync.data.healed_static.length === 0 && (
                  <p className="text-muted-foreground">Already in sync - no changes.</p>
                )}
            </div>
          ) : null}
        </div>
      )}

      {/* Schema-match result. */}
      {(schema.data || schema.isError) && (
        <div className="rounded-lg border bg-card p-3 text-sm">
          {schema.isError ? (
            <p className="text-destructive">
              {schema.error instanceof ApiError ? schema.error.message : "Schema check failed."}
            </p>
          ) : schema.data && !schema.data.configured ? (
            <p className="text-muted-foreground">{schema.data.message}</p>
          ) : schema.data?.message ? (
            <p className="text-destructive">{schema.data.message}</p>
          ) : schema.data?.in_sync ? (
            <p className="font-medium text-[color:var(--color-positive)]">
              ✓ Schema matches - all {columns.length} columns present with the expected types.
            </p>
          ) : (
            <div className="space-y-1">
              <p className="font-medium text-[color:var(--color-negative)]">
                Schema mismatch - fix before syncing/editing:
              </p>
              {(schema.data?.missing_in_view.length ?? 0) > 0 && (
                <p>
                  <span className="text-muted-foreground">Missing:</span>{" "}
                  {schema.data?.missing_in_view.join(", ")}
                </p>
              )}
              {(schema.data?.type_mismatches.length ?? 0) > 0 && (
                <p>
                  <span className="text-muted-foreground">Type mismatches:</span>{" "}
                  {schema.data?.type_mismatches
                    .map((m) => `${m.column} (expected ${m.expected}, got ${m.actual})`)
                    .join(", ")}
                </p>
              )}
              {(schema.data?.unregistered_in_view.length ?? 0) > 0 && (
                <p className="text-muted-foreground">
                  Extra in BigQuery (ignored):{" "}
                  {schema.data?.unregistered_in_view.map((u) => u.column).join(", ")}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Reorder controls. */}
      <div className="flex items-center gap-2 text-sm">
        {reordering ? (
          <>
            <span className="text-xs text-muted-foreground">
              Drag column headers to reorder - this applies to <strong>all users</strong>.
            </span>
            <Button
              size="sm"
              disabled={saveOrder.isPending}
              onClick={() => saveOrder.mutate(localOrder, { onSuccess: () => setReordering(false) })}
            >
              {saveOrder.isPending ? "Saving…" : "Save order"}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setReordering(false)}>
              Cancel
            </Button>
          </>
        ) : (
          <Button variant="outline" size="sm" onClick={startReorder} disabled={columns.length === 0}>
            Reorder columns
          </Button>
        )}
      </div>

      {/* Grid - sticky header (top) + sticky Edit column (left). */}
      <div className="rounded-lg border bg-card">
        <div className="max-h-[68vh] overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="sticky left-0 top-0 z-30 border-b bg-card px-3 py-2 text-left">
                  Edit
                </th>
                {shownColumns.map((c) => (
                  <th
                    key={c.name}
                    draggable={reordering}
                    onDragStart={() => (dragCol.current = c.name)}
                    onDragOver={(e) => reordering && e.preventDefault()}
                    onDrop={() => dropOn(c.name)}
                    className={`sticky top-0 z-20 whitespace-nowrap border-b bg-card px-3 py-2 text-left font-medium ${
                      reordering ? "cursor-move hover:bg-accent" : ""
                    }`}
                  >
                    {c.name}
                    {c.editable && <span className="ml-1 text-[color:var(--color-accent)]">•</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {query.isLoading && (
                <tr>
                  <td className="px-3 py-6 text-center text-muted-foreground" colSpan={shownColumns.length + 1}>
                    Loading…
                  </td>
                </tr>
              )}
              {query.isError && (
                <tr>
                  <td
                    className="px-3 py-6 text-center text-[color:var(--color-negative)]"
                    colSpan={shownColumns.length + 1}
                  >
                    Couldn&apos;t load App Master - please retry.
                  </td>
                </tr>
              )}
              {!query.isLoading && !query.isError && (data?.rows.length ?? 0) === 0 && (
                <tr>
                  <td className="px-3 py-6 text-center text-muted-foreground" colSpan={shownColumns.length + 1}>
                    {hasFilters
                      ? "No apps match these filters."
                      : "No apps loaded yet - click “Refresh from BigQuery” to pull the master list."}
                  </td>
                </tr>
              )}
              {data?.rows.map((row, i) => (
                <tr
                  key={String(row[data.primary_key] ?? i)}
                  className="border-b border-border-faint hover:bg-accent"
                >
                  <td className="sticky left-0 z-10 bg-card px-3 py-1.5">
                    <Button variant="outline" size="sm" onClick={() => setEditing(row)}>
                      Edit
                    </Button>
                  </td>
                  {shownColumns.map((c) => (
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

function FilterText({
  label,
  value,
  onChange,
  width,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  width: string;
  placeholder?: string;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input
        className={`h-8 ${width}`}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

/** Single-select dropdown populated from real values ("" = All). */
function FilterSelect({
  label,
  value,
  options,
  onChange,
  width = "w-36",
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  width?: string;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Select value={value || "all"} onValueChange={(v) => onChange(v === "all" ? "" : v)}>
        <SelectTrigger className={`h-8 ${width}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All</SelectItem>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** Single-select with a search box, for lists too long to scroll ("" = All).
 *
 *  App names run to 150+, and pod owners / publishers grow with the org, so a plain
 *  dropdown becomes a scrolling exercise. Below `SEARCHABLE_THRESHOLD` this falls back to
 *  the plain `FilterSelect` so short lists don't gain a search box they don't need.
 */
function FilterPicker({
  label,
  value,
  options,
  onChange,
  width = "w-44",
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  width?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => o.toLowerCase().includes(q));
  }, [options, query]);

  if (options.length <= SEARCHABLE_THRESHOLD) {
    return (
      <FilterSelect
        label={label}
        value={value}
        options={options}
        onChange={onChange}
        width={width}
      />
    );
  }

  function pick(next: string): void {
    onChange(next);
    setQuery("");
    setOpen(false);
  }

  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Popover
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setQuery("");
        }}
      >
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            role="combobox"
            aria-expanded={open}
            aria-label={label}
            className={`h-8 ${width} justify-between gap-2 font-normal`}
          >
            <span className={cn("truncate", !value && "text-muted-foreground")}>
              {value || "All"}
            </span>
            <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-72 p-2"
          align="start"
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          <div className="relative mb-2">
            <SearchIcon className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 opacity-50" />
            <Input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Search ${label.toLowerCase()}…`}
              aria-label={`Search ${label}`}
              className="h-8 pl-7 text-sm"
            />
          </div>
          <div className="max-h-56 overflow-y-auto">
            <button
              type="button"
              onClick={() => pick("")}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
            >
              <Check className={cn("h-3.5 w-3.5 shrink-0", value === "" ? "" : "invisible")} />
              <span className="text-muted-foreground">All</span>
            </button>
            {visible.length === 0 ? (
              <p className="px-2 py-3 text-xs text-muted-foreground">No matches.</p>
            ) : (
              visible.map((o) => (
                <button
                  key={o}
                  type="button"
                  onClick={() => pick(o)}
                  title={o}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
                >
                  <Check className={cn("h-3.5 w-3.5 shrink-0", o === value ? "" : "invisible")} />
                  <span className="truncate">{o}</span>
                </button>
              ))
            )}
          </div>
          <p className="mt-1 border-t px-2 pt-1.5 text-[10px] text-muted-foreground">
            Showing {visible.length} of {options.length}
          </p>
        </PopoverContent>
      </Popover>
    </div>
  );
}
