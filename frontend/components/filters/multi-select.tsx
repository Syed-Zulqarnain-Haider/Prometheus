"use client";

import { ChevronDown, Search } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

export interface Option {
  value: string;
  label: string;
}

interface MultiSelectProps {
  label: string;
  options: Option[];
  selected: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

/** Only long lists get a search box — Apps is 150+ and painful to scroll, while
 *  Console/HOU are a handful of values and stay uncluttered without one. */
const SEARCH_THRESHOLD = 8;

export function MultiSelect({
  label,
  options,
  selected,
  onChange,
  disabled,
}: MultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  // Snapshot of what was selected when the popover opened. Sorting by THIS rather than
  // by the live selection keeps already-chosen items at the top without rows jumping
  // out from under the cursor as you tick boxes.
  const [pinned, setPinned] = useState<string[]>([]);
  const searchRef = useRef<HTMLInputElement>(null);

  const searchable = options.length > SEARCH_THRESHOLD;

  function handleOpenChange(next: boolean) {
    if (next) {
      setPinned(selected);
      setQuery(""); // always reopen on a clean list
    }
    setOpen(next);
  }

  function toggle(value: string) {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  }

  /** Options after the search filter, previously-selected ones first. Matches the
   *  label OR the underlying value, so an app can be found by name or by key. */
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matched = needle
      ? options.filter(
          (o) =>
            o.label.toLowerCase().includes(needle) ||
            o.value.toLowerCase().includes(needle),
        )
      : options;
    const pinnedSet = new Set(pinned);
    return [
      ...matched.filter((o) => pinnedSet.has(o.value)),
      ...matched.filter((o) => !pinnedSet.has(o.value)),
    ];
  }, [options, query, pinned]);

  const summary =
    selected.length === 0 ? `All ${label.toLowerCase()}` : `${selected.length} selected`;

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          className="min-w-[9rem] justify-between gap-2"
        >
          <span className="truncate">{summary}</span>
          <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-72"
        // Land the caret in the search box so you can type immediately on open.
        onOpenAutoFocus={(event: Event) => {
          if (searchable && searchRef.current) {
            event.preventDefault();
            searchRef.current.focus();
          }
        }}
      >
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium">{label}</span>
          {selected.length > 0 && (
            <button
              type="button"
              className="text-xs text-muted-foreground hover:underline"
              onClick={() => onChange([])}
            >
              Clear
            </button>
          )}
        </div>

        {searchable && (
          <div className="relative mb-2">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 opacity-50" />
            <input
              ref={searchRef}
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`Search ${label.toLowerCase()}…`}
              aria-label={`Search ${label}`}
              className="h-8 w-full rounded-md border bg-background pl-7 pr-2 text-sm outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        )}

        {/* Only the list scrolls, so the search box and Clear stay put while you browse. */}
        <div className="max-h-60 space-y-1 overflow-auto">
          {options.length === 0 && (
            <p className="text-xs text-muted-foreground">No options</p>
          )}
          {options.length > 0 && visible.length === 0 && (
            <p className="text-xs text-muted-foreground">No matches for “{query.trim()}”</p>
          )}
          {visible.map((option) => (
            <div
              key={option.value}
              className="group flex items-center gap-2 rounded px-1 py-1 text-sm hover:bg-accent"
            >
              <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2">
                <Checkbox
                  checked={selected.includes(option.value)}
                  onCheckedChange={() => toggle(option.value)}
                />
                <span className="truncate">{option.label}</span>
              </label>
              {/* "only" quick-pick: select just this one (like Looker/Tableau). */}
              <button
                type="button"
                className="shrink-0 rounded px-1 text-xs text-muted-foreground opacity-0 hover:underline group-hover:opacity-100"
                onClick={() => onChange([option.value])}
              >
                only
              </button>
            </div>
          ))}
        </div>

        {searchable && options.length > 0 && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            Showing {visible.length} of {options.length}
            {selected.length > 0 ? ` · ${selected.length} selected` : ""}
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
}
