"use client";

import { AlertCircle, Check, ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { TextScramble } from "@/components/effects/text-scramble";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  type AppMasterFilters,
  useAppMaster,
  useUpdateAppMaster,
} from "@/lib/api-hooks";
import { cn } from "@/lib/utils";

/* App Spotlight: the incomplete-records worklist, as a card deck.
 *
 * Source is the BigQuery app_master_v2 table through the existing admin App Master API -
 * the same endpoint the App Master page uses, so reads, RBAC and writes all go through
 * one already-audited path. A card appears ONLY when at least one of the six fields the
 * owner named is blank; the missing ones are flagged, each is editable in place, and
 * saving PATCHes just those fields back to app_master_v2. Fill them all and the app
 * leaves the deck. */

const REQUIRED_FIELDS = [
  { key: "publisher", label: "Publisher" },
  { key: "hou", label: "HOU" },
  { key: "pod", label: "Pod" },
  { key: "pod_owner", label: "Pod owner" },
  { key: "partner_name", label: "Partner name" },
  { key: "net_revenue_share", label: "Net revenue share" },
] as const;

/** Pull a generous page: the deck filters client-side for blanks across six columns,
 *  which the list endpoint cannot express as a single query parameter. */
const PAGE = 200;

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

export function SpotlightClient() {
  const list = useAppMaster(EMPTY_FILTERS, PAGE, 0);
  const update = useUpdateAppMaster();

  const rows = useMemo(() => list.data?.rows ?? [], [list.data]);
  const primaryKey = list.data?.primary_key ?? "canonical_key";

  // Only apps missing at least one of the six fields reach the deck.
  const incomplete = useMemo(
    () => rows.filter((row) => REQUIRED_FIELDS.some((field) => isBlank(row[field.key]))),
    [rows],
  );

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

  const [index, setIndex] = useState(0);
  const clamped = incomplete.length ? Math.min(index, incomplete.length - 1) : 0;
  const current = incomplete[clamped];

  // Draft edits for the visible card, seeded blank and reset whenever the card changes.
  const [draft, setDraft] = useState<Record<string, string>>({});
  const seededFor = useRef<string | null>(null);
  const currentKey = current ? String(current[primaryKey] ?? "") : null;
  useEffect(() => {
    if (seededFor.current === currentKey) return;
    seededFor.current = currentKey;
    setDraft({});
  }, [currentKey]);

  const go = useCallback(
    (dir: -1 | 1) => {
      setIndex((value) => {
        const base = incomplete.length ? Math.min(value, incomplete.length - 1) : 0;
        return Math.min(Math.max(base + dir, 0), Math.max(incomplete.length - 1, 0));
      });
    },
    [incomplete.length],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLElement) {
        const tag = event.target.tagName;
        if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return; // typing, not paging
      }
      if (event.key === "ArrowRight") go(1);
      if (event.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  function save(): void {
    if (!current || !currentKey) return;
    // Send ONLY the fields actually filled in, so a PATCH never blanks something else.
    const body: Record<string, unknown> = {};
    for (const field of REQUIRED_FIELDS) {
      const value = (draft[field.key] ?? "").trim();
      if (!value) continue;
      body[field.key] =
        field.key === "net_revenue_share" && Number.isFinite(Number(value))
          ? Number(value)
          : value;
    }
    if (Object.keys(body).length === 0) return;
    update.mutate({ key: currentKey, body });
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
  if (!current) {
    return (
      <div className="mx-auto max-w-xl rounded-[var(--radius-card)] border bg-card p-10 text-center">
        <Check className="mx-auto h-10 w-10 text-[color:var(--color-positive)]" />
        <p className="mt-3 font-display text-xl">Everything is filled in</p>
        <p className="mt-1 text-sm text-muted-foreground">
          No app is missing publisher, HOU, pod, pod owner, partner name or net revenue share.
        </p>
      </div>
    );
  }

  const missing = REQUIRED_FIELDS.filter((field) => isBlank(current[field.key]));
  const name = String(current.app_name ?? current[primaryKey] ?? "-");

  return (
    <div className="mx-auto max-w-xl">
      <div className="mb-3 flex items-center justify-between text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <AlertCircle className="h-3.5 w-3.5 text-[color:var(--color-amber)]" />
          <span className="font-semibold text-foreground">{incomplete.length}</span> apps need
          attention
        </span>
        <span className="tabular-nums">
          {clamped + 1} / {incomplete.length}
        </span>
      </div>

      <div className="rounded-[var(--radius-card)] border bg-card p-6 shadow-lg">
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          Incomplete record
        </p>
        <h3 className="mt-1 truncate font-display text-2xl" title={name}>
          <TextScramble text={name} />
        </h3>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{String(current[primaryKey] ?? "")}</p>

        <div className="mt-5 space-y-3">
          {REQUIRED_FIELDS.map((field) => {
            const existing = display(current[field.key]);
            const isMissing = isBlank(current[field.key]);
            const choices = options[field.key] ?? [];
            return (
              <div key={field.key} className="grid grid-cols-[9rem_1fr] items-center gap-3">
                <span
                  className={cn(
                    "text-xs font-medium",
                    isMissing ? "text-[color:var(--color-negative)]" : "text-muted-foreground",
                  )}
                >
                  {field.label}
                  {isMissing && " *"}
                </span>
                {isMissing ? (
                  <div className="flex gap-1">
                    {choices.length > 0 && field.key !== "net_revenue_share" && (
                      <select
                        aria-label={`${field.label} (existing values)`}
                        value={draft[field.key] ?? ""}
                        onChange={(event) =>
                          setDraft((value) => ({ ...value, [field.key]: event.target.value }))
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
                        setDraft((value) => ({ ...value, [field.key]: event.target.value }))
                      }
                      placeholder={
                        field.key === "net_revenue_share" ? "e.g. 0.7" : "or type a new value"
                      }
                      inputMode={field.key === "net_revenue_share" ? "decimal" : undefined}
                      className="h-9 min-w-0 flex-1"
                    />
                  </div>
                ) : (
                  <span className="truncate text-sm">{existing}</span>
                )}
              </div>
            );
          })}
        </div>

        <div className="mt-5 flex items-center gap-2">
          <Button
            size="sm"
            className="flex-1"
            disabled={update.isPending || Object.values(draft).every((value) => !value.trim())}
            onClick={save}
          >
            {update.isPending ? "Saving..." : `Save ${missing.length} missing field(s)`}
          </Button>
          <Button size="sm" variant="outline" onClick={() => go(1)}>
            Skip
          </Button>
        </div>
        {update.isError && (
          <p className="mt-2 text-xs text-destructive">
            Could not save: {(update.error as Error).message}
          </p>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between">
        <button
          type="button"
          aria-label="Previous app"
          disabled={clamped === 0}
          onClick={() => go(-1)}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-[color:var(--color-bg-elevated)] text-muted-foreground transition-all duration-[var(--dur-fast)] hover:scale-110 hover:text-foreground disabled:opacity-30"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <span className="hidden text-xs text-muted-foreground sm:inline">
          arrow keys to move between apps
        </span>
        <button
          type="button"
          aria-label="Next app"
          disabled={clamped >= incomplete.length - 1}
          onClick={() => go(1)}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-[color:var(--color-accent)] text-[color:var(--color-accent-foreground)] transition-all duration-[var(--dur-fast)] hover:scale-110 disabled:opacity-30"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}
