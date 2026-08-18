"use client";

import { AlertCircle, Check, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  type AppMasterFilters,
  useAppMaster,
  useUpdateAppMaster,
} from "@/lib/api-hooks";
import { cn } from "@/lib/utils";

/* App Spotlight: the completeness board for app_master_v2.
 *
 * EVERY app is on the board, shaded by state - red where one of the six required fields
 * is blank, green where the record is complete - so the work left is readable at a glance
 * instead of one card at a time. Red tiles sort to the front and carry the count of what
 * is missing; each field is a chip that says either its value or "Missing".
 *
 * Click a tile to edit it in place. Saving PATCHes only the fields you actually changed
 * back to app_master_v2 through the existing admin App Master API - the same endpoint the
 * App Master page uses, so reads, RBAC and writes all go through one already-audited path.
 * Fill the blanks and the tile turns green on the next refetch. */

const REQUIRED_FIELDS = [
  { key: "publisher", label: "Publisher" },
  { key: "hou", label: "HOU" },
  { key: "pod", label: "Pod" },
  { key: "pod_owner", label: "Pod owner" },
  { key: "partner_name", label: "Partner name" },
  { key: "net_revenue_share", label: "Net revenue share" },
] as const;

/** The API caps a page at 200. Completeness spans six columns and cannot be expressed as
 *  a list filter, so the split is computed here over whatever page is loaded. */
const PAGE = 200;

/* Tints as inline styles rather than Tailwind classes: color-mix against the theme's own
 * positive/negative tokens means the shading follows whatever background is in force
 * instead of being a hardcoded light- or dark-mode colour. */
const SHADE = {
  incomplete: {
    backgroundColor: "color-mix(in srgb, var(--color-negative) 7%, transparent)",
    borderColor: "color-mix(in srgb, var(--color-negative) 38%, transparent)",
  },
  complete: {
    backgroundColor: "color-mix(in srgb, var(--color-positive) 7%, transparent)",
    borderColor: "color-mix(in srgb, var(--color-positive) 32%, transparent)",
  },
} as const;

const CHIP = {
  missing: {
    backgroundColor: "color-mix(in srgb, var(--color-negative) 14%, transparent)",
    color: "var(--color-negative)",
  },
  filled: {
    backgroundColor: "color-mix(in srgb, var(--color-positive) 12%, transparent)",
    color: "var(--color-positive)",
  },
} as const;

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

type Mode = "all" | "incomplete" | "complete";

/** Blank means blank: null, undefined, empty string, or whitespace. A numeric 0 is a
 *  real value (a 0% revenue share is a decision), so it must NOT count as missing. */
function isBlank(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim() === "";
  return false;
}

function display(value: unknown): string {
  if (isBlank(value)) return "";
  return String(value);
}

interface Card {
  key: string;
  name: string;
  row: Record<string, unknown>;
  missing: readonly { key: string; label: string }[];
}

export function SpotlightClient() {
  const [offset, setOffset] = useState(0);
  const list = useAppMaster(EMPTY_FILTERS, PAGE, offset);
  const update = useUpdateAppMaster();

  const [mode, setMode] = useState<Mode>("all");
  const [search, setSearch] = useState("");
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  // What the card looked like WHEN IT WAS OPENED. save() diffs the draft against this,
  // not the live row: the query can refetch while a card sits open (another admin
  // saving, a background refresh), and diffing against the refreshed row would treat
  // the untouched seeded values as "changes" - silently reverting the other admin's
  // edit. Against the snapshot, an untouched field is never sent.
  const [seedRow, setSeedRow] = useState<Record<string, unknown>>({});

  const rows = useMemo(() => list.data?.rows ?? [], [list.data]);
  const primaryKey = list.data?.primary_key ?? "canonical_key";
  const total = list.data?.total ?? rows.length;

  const cards: Card[] = useMemo(
    () =>
      rows.map((row) => ({
        key: String(row[primaryKey] ?? ""),
        name: String(row.app_name ?? row[primaryKey] ?? "-"),
        row,
        missing: REQUIRED_FIELDS.filter((field) => isBlank(row[field.key])),
      })),
    [rows, primaryKey],
  );

  const incompleteCount = cards.filter((card) => card.missing.length > 0).length;
  const completeCount = cards.length - incompleteCount;

  // Dropdown options per field, built from the values already present across the whole
  // page - these repeat heavily (the same pods, publishers, owners), so picking beats
  // retyping and cannot introduce a near-duplicate through a typo.
  const options = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const field of REQUIRED_FIELDS) {
      const seen = new Set<string>();
      for (const row of rows) {
        const value = row[field.key];
        if (!isBlank(value)) seen.add(String(value));
      }
      map[field.key] = [...seen].sort((a, b) => a.localeCompare(b));
    }
    return map;
  }, [rows]);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return cards
      .filter((card) =>
        mode === "all"
          ? true
          : mode === "incomplete"
            ? card.missing.length > 0
            : card.missing.length === 0,
      )
      .filter(
        (card) =>
          !query ||
          card.name.toLowerCase().includes(query) ||
          card.key.toLowerCase().includes(query),
      )
      .sort(
        (a, b) =>
          // Work first: anything red outranks anything green, then most-missing, then name.
          Number(b.missing.length > 0) - Number(a.missing.length > 0) ||
          b.missing.length - a.missing.length ||
          a.name.localeCompare(b.name),
      );
  }, [cards, mode, search]);

  /** Open a tile, seeding the draft from what is already stored so an existing value can
   *  be corrected as easily as a blank one can be filled. Seeding happens OUTSIDE any
   *  state updater - updaters must be pure (StrictMode double-invokes them), so the
   *  toggle check reads the rendered openKey instead. */
  function openCard(card: Card): void {
    if (openKey === card.key) {
      setOpenKey(null); // clicking the open tile closes it
      return;
    }
    const seed: Record<string, string> = {};
    for (const field of REQUIRED_FIELDS) seed[field.key] = display(card.row[field.key]);
    setDraft(seed);
    setSeedRow(card.row);
    setOpenKey(card.key);
  }

  /** Inline validation for the one numeric field: the API takes 0-1, and "70%" or "70"
   *  would bounce off it as a raw 422 - catch it before the request with a usable hint. */
  function badShare(value: string): boolean {
    return !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 1;
  }
  const shareDraft = (draft.net_revenue_share ?? "").trim();
  const shareSeed = display(seedRow.net_revenue_share);
  const shareInvalid = shareDraft !== "" && shareDraft !== shareSeed && badShare(shareDraft);
  // A legacy STORED value can itself be out of range ("70" meant as 70%). It sits in
  // the box looking accepted, and the unchanged-field rule silently drops it from every
  // save - so say so, rather than letting the admin believe Save covered it.
  const shareSeedInvalid = shareSeed !== "" && shareDraft === shareSeed && badShare(shareSeed);

  /** The PATCH body save() would send: only fields CHANGED vs the SNAPSHOT taken at
   *  open - never the live row, which may have been refetched with another admin's
   *  newer values (diffing against those would re-send the stale seed and revert their
   *  edit). And never a change to blank: clearing a box here is far more likely to be
   *  a slip than an intent to erase a value in BigQuery. */
  function pendingBody(): Record<string, unknown> {
    const body: Record<string, unknown> = {};
    for (const field of REQUIRED_FIELDS) {
      const next = (draft[field.key] ?? "").trim();
      if (!next || next === display(seedRow[field.key])) continue;
      body[field.key] =
        field.key === "net_revenue_share" && Number.isFinite(Number(next))
          ? Number(next)
          : next;
    }
    return body;
  }
  const hasChanges = Object.keys(pendingBody()).length > 0;

  function save(card: Card): void {
    if (!card.key || shareInvalid) return;
    const body = pendingBody();
    if (Object.keys(body).length === 0) return;
    update.mutate({ key: card.key, body });
  }

  if (list.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading app master...</p>;
  }
  if (list.isError) {
    return (
      <p className="text-sm text-destructive">
        Could not load app master: {(list.error as Error).message}
      </p>
    );
  }

  const pageStart = rows.length ? offset + 1 : 0;
  const pageEnd = offset + rows.length;
  const paged = total > rows.length;

  return (
    <div className="space-y-4">
      {/* Tally + controls. The counts describe the loaded page, which is said plainly
          when there is more than one - a total that silently covered a fraction of the
          table would be worse than no total. */}
      <div className="flex flex-wrap items-center gap-3">
        <Legend
          tone="incomplete"
          count={incompleteCount}
          label={paged ? "need updating on this page" : "need updating"}
        />
        <Legend
          tone="complete"
          count={completeCount}
          label={paged ? "complete on this page" : "complete"}
        />
        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Find an app"
              aria-label="Find an app"
              className="h-9 w-52 pl-8"
            />
          </div>
          <div className="flex rounded-[var(--radius-inner)] border p-0.5">
            {(
              [
                ["all", "All"],
                ["incomplete", "Needs update"],
                ["complete", "Complete"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={mode === value}
                onClick={() => setMode(value)}
                className={cn(
                  "rounded-[calc(var(--radius-inner)-2px)] px-2.5 py-1 text-xs font-medium transition-colors",
                  mode === value
                    ? "bg-[color:var(--color-accent)] text-[color:var(--color-accent-foreground)]"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {visible.length === 0 ? (
        <div className="rounded-[var(--radius-card)] border bg-card p-10 text-center">
          <Check className="mx-auto h-10 w-10 text-[color:var(--color-positive)]" />
          <p className="mt-3 font-display text-xl">Nothing to show</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {mode === "incomplete"
              ? "No app on this page is missing publisher, HOU, pod, pod owner, partner name or net revenue share."
              : "No app matches the current filter."}
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((card) => {
            const needsWork = card.missing.length > 0;
            const isOpen = openKey === card.key;
            return (
              <div
                key={card.key}
                style={needsWork ? SHADE.incomplete : SHADE.complete}
                className={cn(
                  "rounded-[var(--radius-card)] border transition-shadow",
                  isOpen && "shadow-lg sm:col-span-2 xl:col-span-3",
                )}
              >
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => openCard(card)}
                  className="w-full rounded-[var(--radius-card)] p-4 text-left outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h3 className="truncate font-display text-base" title={card.name}>
                        {card.name}
                      </h3>
                      <p className="truncate text-xs text-muted-foreground">{card.key}</p>
                    </div>
                    <span
                      className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                      style={needsWork ? CHIP.missing : CHIP.filled}
                    >
                      {needsWork ? `${card.missing.length} missing` : "Complete"}
                    </span>
                  </div>

                  {/* One chip per required field: the value when it is there, "Missing"
                      when it is not, so the tile says WHAT to fix, not just that it needs
                      fixing. */}
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {REQUIRED_FIELDS.map((field) => {
                      const blank = isBlank(card.row[field.key]);
                      return (
                        <span
                          key={field.key}
                          style={blank ? CHIP.missing : CHIP.filled}
                          className="max-w-full truncate rounded-[var(--radius-inner)] px-1.5 py-0.5 text-[11px]"
                          title={`${field.label}: ${blank ? "missing" : display(card.row[field.key])}`}
                        >
                          {field.label}: {blank ? "Missing" : display(card.row[field.key])}
                        </span>
                      );
                    })}
                  </div>
                </button>

                {isOpen && (
                  <div className="border-t px-4 pb-4 pt-3">
                    <div className="space-y-3">
                      {REQUIRED_FIELDS.map((field) => {
                        const blank = isBlank(card.row[field.key]);
                        const choices = options[field.key] ?? [];
                        return (
                          <div
                            key={field.key}
                            className="grid grid-cols-[9rem_1fr] items-center gap-3"
                          >
                            <span
                              className={cn(
                                "text-xs font-medium",
                                blank
                                  ? "text-[color:var(--color-negative)]"
                                  : "text-muted-foreground",
                              )}
                            >
                              {field.label}
                              {blank && " *"}
                            </span>
                            <div className="flex gap-1">
                              {choices.length > 0 && field.key !== "net_revenue_share" && (
                                <select
                                  aria-label={`${field.label} (existing values)`}
                                  value={choices.includes(draft[field.key] ?? "") ? draft[field.key] : ""}
                                  onChange={(event) =>
                                    setDraft((value) => ({
                                      ...value,
                                      [field.key]: event.target.value,
                                    }))
                                  }
                                  className="min-w-0 flex-1 rounded-[var(--radius-inner)] border border-input bg-background px-2 py-1.5 text-sm outline-none focus:ring-1 focus:ring-ring"
                                >
                                  <option value="">Select...</option>
                                  {choices.map((choice) => (
                                    <option key={choice} value={choice}>
                                      {choice}
                                    </option>
                                  ))}
                                </select>
                              )}
                              <Input
                                value={draft[field.key] ?? ""}
                                onChange={(event) =>
                                  setDraft((value) => ({
                                    ...value,
                                    [field.key]: event.target.value,
                                  }))
                                }
                                placeholder={
                                  field.key === "net_revenue_share"
                                    ? "e.g. 0.7"
                                    : "or type a new value"
                                }
                                inputMode={
                                  field.key === "net_revenue_share" ? "decimal" : undefined
                                }
                                className="h-9 min-w-0 flex-1"
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {shareInvalid && (
                      <p className="mt-2 text-xs text-destructive">
                        Net revenue share must be a number between 0 and 1 (e.g. 0.7 for
                        70%).
                      </p>
                    )}
                    {shareSeedInvalid && (
                      <p className="mt-2 text-xs text-[color:var(--color-amber)]">
                        The stored net revenue share ({shareSeed}) is outside 0-1 and will
                        NOT be saved until corrected - enter the share as a fraction
                        (e.g. 0.7 for 70%).
                      </p>
                    )}
                    <div className="mt-4 flex items-center gap-2">
                      <Button
                        size="sm"
                        disabled={update.isPending || shareInvalid || !hasChanges}
                        onClick={() => save(card)}
                      >
                        {update.isPending && update.variables?.key === card.key
                          ? "Saving..."
                          : hasChanges
                            ? "Save changes"
                            : "No changes yet"}
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setOpenKey(null)}>
                        Close
                      </Button>
                      <span className="text-xs text-muted-foreground">
                        Only changed fields are written back.
                      </span>
                    </div>
                    {update.isError && update.variables?.key === card.key && (
                      <p className="mt-2 text-xs text-destructive">
                        Could not save: {(update.error as Error).message}
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {paged && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="tabular-nums">
            {pageStart}-{pageEnd} of {total}
          </span>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={offset === 0}
              onClick={() => {
                setOpenKey(null);
                setOffset((value) => Math.max(value - PAGE, 0));
              }}
            >
              <ChevronLeft className="mr-1 h-3.5 w-3.5" />
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={pageEnd >= total}
              onClick={() => {
                setOpenKey(null);
                setOffset((value) => value + PAGE);
              }}
            >
              Next
              <ChevronRight className="ml-1 h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Legend({
  tone,
  count,
  label,
}: {
  tone: "incomplete" | "complete";
  count: number;
  label: string;
}) {
  return (
    <span
      className="flex items-center gap-1.5 rounded-[var(--radius-inner)] border px-2.5 py-1 text-xs"
      style={tone === "incomplete" ? SHADE.incomplete : SHADE.complete}
    >
      {tone === "incomplete" ? (
        <AlertCircle
          className="h-3.5 w-3.5"
          style={{ color: "var(--color-negative)" }}
          aria-hidden
        />
      ) : (
        <Check className="h-3.5 w-3.5" style={{ color: "var(--color-positive)" }} aria-hidden />
      )}
      <span className="font-semibold tabular-nums text-foreground">{count}</span>
      <span className="text-muted-foreground">{label}</span>
    </span>
  );
}
