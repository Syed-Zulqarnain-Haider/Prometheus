"use client";

import { Check, ChevronDown, Plus, Search, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApps } from "@/lib/api-hooks";
import type { AppListItem, Scope, ScopeType } from "@/lib/types";
import { cn } from "@/lib/utils";

const SCOPE_TYPES: ScopeType[] = ["all", "hou", "pod", "publisher", "app"];

/** Scope types that carry a value. `all` is the whole org and takes none. */
type ValuedScopeType = Exclude<ScopeType, "all">;

interface ValueOption {
  value: string;
  label: string;
}

const TYPE_LABELS: Record<ScopeType, string> = {
  all: "all",
  hou: "hou",
  pod: "pod",
  publisher: "publisher",
  app: "app",
};

/** Real values for each scope type, taken from `/apps` — the dimension table, so a pod or
 *  publisher with no rows in the current date window still appears. A scope grant is about
 *  the org chart, not about who happened to have revenue last month. */
function useScopeOptions(): {
  options: Record<ValuedScopeType, ValueOption[]>;
  loading: boolean;
} {
  const { data, isLoading } = useApps();

  const options = useMemo(() => {
    const apps: AppListItem[] = data?.apps ?? [];
    const distinct = (pick: (a: AppListItem) => string | null): ValueOption[] =>
      Array.from(new Set(apps.map(pick).filter((v): v is string => Boolean(v))))
        .sort((a, b) => a.localeCompare(b))
        .map((v) => ({ value: v, label: v }));

    return {
      hou: distinct((a) => a.hou),
      pod: distinct((a) => a.pod),
      publisher: distinct((a) => a.publisher),
      app: apps
        .map((a) => ({ value: a.canonical_key, label: a.app_name ?? a.canonical_key }))
        .sort((x, y) => x.label.localeCompare(y.label)),
    };
  }, [data]);

  return { options, loading: isLoading };
}

/** Searchable single-value picker for a scope's value.
 *
 *  It stays typeable on purpose. The list is the fast path — an admin should not have to
 *  remember a canonical key — but a grant may legitimately name a pod or publisher that has
 *  no apps mapped to it yet, and the old free-text field could express that. Typing a value
 *  the list doesn't contain offers it explicitly rather than silently dropping it.
 */
function ScopeValuePicker({
  scopeType,
  value,
  options,
  loading,
  onChange,
}: {
  scopeType: ValuedScopeType;
  value: string;
  options: ValueOption[];
  loading: boolean;
  onChange: (next: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q),
    );
  }, [options, query]);

  const selected = options.find((o) => o.value === value);
  // A value the list doesn't know (typed by hand, or mapped since the grant was made) is
  // still shown — never blank out what an admin actually granted.
  const triggerLabel = selected?.label ?? (value || `Select ${TYPE_LABELS[scopeType]}…`);
  const typed = query.trim();
  const exact = options.some((o) => o.value === typed);

  function pick(next: string): void {
    onChange(next);
    setQuery("");
    setOpen(false);
  }

  return (
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
          aria-label={`${TYPE_LABELS[scopeType]} value`}
          className="h-8 flex-1 justify-between gap-2 font-normal"
        >
          <span className={cn("truncate", !value && "text-muted-foreground")}>
            {triggerLabel}
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-2" align="start" onOpenAutoFocus={(e) => e.preventDefault()}>
        <div className="relative mb-2">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 opacity-50" />
          <Input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search ${TYPE_LABELS[scopeType]}…`}
            aria-label={`Search ${TYPE_LABELS[scopeType]}`}
            className="h-8 pl-7 text-sm"
          />
        </div>

        <div className="max-h-56 overflow-y-auto">
          {loading && options.length === 0 ? (
            <p className="px-2 py-3 text-xs text-muted-foreground">Loading…</p>
          ) : visible.length === 0 ? (
            <p className="px-2 py-3 text-xs text-muted-foreground">
              {options.length === 0
                ? `No ${TYPE_LABELS[scopeType]} values found.`
                : "No matches."}
            </p>
          ) : (
            visible.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => pick(o.value)}
                title={o.value}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
              >
                <Check
                  className={cn("h-3.5 w-3.5 shrink-0", o.value === value ? "" : "invisible")}
                />
                <span className="truncate">{o.label}</span>
              </button>
            ))
          )}
        </div>

        {typed.length > 0 && !exact && (
          <button
            type="button"
            onClick={() => pick(typed)}
            className="mt-1 w-full rounded border-t px-2 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Use “{typed}” anyway
          </button>
        )}
      </PopoverContent>
    </Popover>
  );
}

/** Edit a user's row-scope grants. Effective access is the UNION of these rows;
 *  an "all" grant needs no value, every other type requires one. */
export function ScopeEditor({
  scopes,
  onChange,
}: {
  scopes: Scope[];
  onChange: (next: Scope[]) => void;
}) {
  const { options, loading } = useScopeOptions();

  function update(index: number, patch: Partial<Scope>) {
    onChange(scopes.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  return (
    <div className="space-y-2">
      {scopes.length === 0 && (
        <p className="text-xs text-muted-foreground">
          No scopes — this user sees nothing until a scope is added.
        </p>
      )}
      {scopes.map((scope, index) => (
        <div key={index} className="flex items-center gap-2">
          <Select
            value={scope.scope_type}
            onValueChange={(value) =>
              update(index, {
                scope_type: value as ScopeType,
                // Values don't carry across types — a pod name is not a publisher name, and
                // silently keeping it would grant something nobody chose.
                scope_value: value === "all" ? null : "",
              })
            }
          >
            <SelectTrigger className="h-8 w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SCOPE_TYPES.map((type) => (
                <SelectItem key={type} value={type}>
                  {TYPE_LABELS[type]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {scope.scope_type === "all" ? (
            <div className="flex h-8 flex-1 items-center rounded-md border border-input bg-muted/40 px-3 text-sm text-muted-foreground">
              — whole org
            </div>
          ) : (
            <ScopeValuePicker
              scopeType={scope.scope_type}
              value={scope.scope_value ?? ""}
              options={options[scope.scope_type]}
              loading={loading}
              onChange={(next) => update(index, { scope_value: next })}
            />
          )}

          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={() => onChange(scopes.filter((_, i) => i !== index))}
            aria-label="Remove scope"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        className="gap-1"
        onClick={() => onChange([...scopes, { scope_type: "all", scope_value: null }])}
      >
        <Plus className="h-4 w-4" />
        Add scope
      </Button>
    </div>
  );
}
