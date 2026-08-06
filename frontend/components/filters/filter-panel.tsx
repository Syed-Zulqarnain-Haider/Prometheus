"use client";

import { Check, ChevronDown, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { DateRangePicker } from "@/components/filters/date-range-picker";
import type { FilterDimension } from "@/components/filters/dimensions";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  activeFilterCount,
  defaultFilters,
  type Filters,
  type ListFilterKey,
} from "@/lib/filters";
import type { Platform } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Lists longer than this get a search box inside the panel. */
const SEARCH_THRESHOLD = 8;

const PLATFORMS: { value: Platform | null; label: string }[] = [
  { value: null, label: "All" },
  { value: "ios", label: "iOS" },
  { value: "android", label: "Android" },
];

interface SectionProps {
  dimension: FilterDimension;
  selected: string[];
  onChange: (next: string[]) => void;
  defaultOpen: boolean;
}

/** One collapsible dimension: search, checkbox list, and bulk select/clear for what the
 *  search currently shows. Bulk actions deliberately act on the *filtered* list — "select
 *  all" after typing "puzzle" means all puzzle apps, not all 150. */
function Section({ dimension, selected, onChange, defaultOpen }: SectionProps) {
  const [expanded, setExpanded] = useState(defaultOpen);
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return dimension.options;
    return dimension.options.filter(
      (o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q),
    );
  }, [dimension.options, query]);

  const chosen = new Set(selected);
  const allVisibleChosen = visible.length > 0 && visible.every((o) => chosen.has(o.value));

  function toggle(value: string): void {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  }

  function toggleVisible(): void {
    const values = visible.map((o) => o.value);
    if (allVisibleChosen) {
      onChange(selected.filter((v) => !values.includes(v)));
    } else {
      onChange(Array.from(new Set([...selected, ...values])));
    }
  }

  return (
    <div className="border-b last:border-b-0">
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium hover:bg-accent/50"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="flex items-center gap-2">
          {dimension.label}
          {selected.length > 0 && (
            <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
              {selected.length}
            </span>
          )}
        </span>
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 opacity-60 transition-transform", expanded && "rotate-180")}
        />
      </button>

      {expanded && (
        <div className="px-4 pb-3">
          {dimension.options.length > SEARCH_THRESHOLD && (
            <div className="relative mb-2">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 opacity-50" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={`Search ${dimension.label.toLowerCase()}…`}
                aria-label={`Search ${dimension.label}`}
                className="h-8 pl-7 text-sm"
              />
            </div>
          )}

          {dimension.options.length === 0 ? (
            <p className="py-2 text-xs text-muted-foreground">
              No options for the current selection.
            </p>
          ) : (
            <>
              <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  Showing {visible.length} of {dimension.options.length}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="hover:text-foreground disabled:opacity-40"
                    disabled={visible.length === 0}
                    onClick={toggleVisible}
                  >
                    {allVisibleChosen ? "Deselect shown" : "Select shown"}
                  </button>
                  {selected.length > 0 && (
                    <button
                      type="button"
                      className="hover:text-foreground"
                      onClick={() => onChange([])}
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>
              <div className="max-h-56 overflow-y-auto rounded border">
                {visible.length === 0 ? (
                  <p className="px-2 py-3 text-xs text-muted-foreground">No matches.</p>
                ) : (
                  visible.map((o) => (
                    <label
                      key={o.value}
                      className="flex cursor-pointer items-center gap-2 px-2 py-1.5 text-sm hover:bg-accent"
                    >
                      <Checkbox
                        checked={chosen.has(o.value)}
                        onCheckedChange={() => toggle(o.value)}
                      />
                      <span className="truncate" title={o.label}>
                        {o.label}
                      </span>
                    </label>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

interface FilterPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filters: Filters;
  onApply: (next: Filters) => void;
  dimensions: FilterDimension[];
  loading?: boolean;
}

/** Split-screen filter panel: the dashboard stays visible on the left, every filter is on
 *  the right, and the whole selection is committed in one go.
 *
 *  The inline bar applies each change immediately, which means ten dropdown clicks are ten
 *  URL writes and ten refetches. Here the panel edits a private draft and **Apply** produces
 *  exactly one update — the difference between "set up my view" and "wait ten times".
 */
export function FilterPanel({
  open,
  onOpenChange,
  filters,
  onApply,
  dimensions,
  loading = false,
}: FilterPanelProps) {
  const [draft, setDraft] = useState<Filters>(filters);
  const panelRef = useRef<HTMLElement>(null);

  // Re-seed on open so an abandoned edit is discarded, never silently carried forward.
  useEffect(() => {
    if (open) setDraft(filters);
  }, [open, filters]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false);
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onOpenChange]);

  const draftCount = activeFilterCount(draft);
  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(filters),
    [draft, filters],
  );

  if (!open) return null;

  function setList(key: ListFilterKey, values: string[]): void {
    setDraft((current) => ({ ...current, [key]: values }));
  }

  return (
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label="Filters">
      <button
        type="button"
        aria-label="Close filters"
        className="flex-1 bg-black/40 backdrop-blur-[1px]"
        onClick={() => onOpenChange(false)}
      />
      <aside
        ref={panelRef}
        tabIndex={-1}
        className="flex h-full w-full flex-col border-l bg-card shadow-xl outline-none sm:w-[26rem]"
      >
        <header className="flex items-center justify-between border-b px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold">Filters</h2>
            <p className="text-xs text-muted-foreground">
              {draftCount === 0 ? "No filters applied" : `${draftCount} applied`}
            </p>
          </div>
          <button
            type="button"
            aria-label="Close filters"
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={() => onOpenChange(false)}
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="space-y-3 border-b px-4 py-3">
            <div className="space-y-1">
              <span className="text-xs font-medium text-muted-foreground">Date range</span>
              <div>
                <DateRangePicker
                  preset={draft.preset}
                  dateFrom={draft.dateFrom}
                  dateTo={draft.dateTo}
                  compare={draft.compare}
                  onChange={(value) => setDraft((current) => ({ ...current, ...value }))}
                />
              </div>
            </div>
            <div className="space-y-1">
              <span className="text-xs font-medium text-muted-foreground">Platform</span>
              <div className="flex gap-1">
                {PLATFORMS.map((p) => (
                  <Button
                    key={p.label}
                    size="sm"
                    variant={draft.platform === p.value ? "default" : "outline"}
                    onClick={() => setDraft((current) => ({ ...current, platform: p.value }))}
                  >
                    {draft.platform === p.value && <Check className="h-3 w-3" />}
                    {p.label}
                  </Button>
                ))}
              </div>
            </div>
          </div>

          {loading && dimensions.every((d) => d.options.length === 0) ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">Loading options…</p>
          ) : (
            dimensions.map((d, i) => (
              <Section
                key={d.key}
                dimension={d}
                selected={draft[d.key]}
                onChange={(values) => setList(d.key, values)}
                // Apps leads the list and is the one people open first.
                defaultOpen={i === 0 || draft[d.key].length > 0}
              />
            ))
          )}
        </div>

        <footer className="flex items-center gap-2 border-t px-4 py-3">
          <Button
            variant="ghost"
            size="sm"
            disabled={draftCount === 0}
            onClick={() => setDraft(defaultFilters())}
          >
            Clear all
          </Button>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={!dirty}
              onClick={() => {
                onApply(draft);
                onOpenChange(false);
              }}
            >
              Apply
            </Button>
          </div>
        </footer>
      </aside>
    </div>
  );
}
