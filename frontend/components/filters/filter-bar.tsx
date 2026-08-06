"use client";

import { FilterX, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";

import { DateRangePicker } from "@/components/filters/date-range-picker";
import { buildDimensions } from "@/components/filters/dimensions";
import { FilterPanel } from "@/components/filters/filter-panel";
import { MultiSelect } from "@/components/filters/multi-select";
import { SavedViewsMenu } from "@/components/reports/saved-views-menu";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useFilterOptions } from "@/lib/api-hooks";
import { activeFilterCount, defaultFilters } from "@/lib/filters";
import type { Platform } from "@/lib/types";
import { useFilters } from "@/lib/use-filters";
import { cn } from "@/lib/utils";

const PLATFORM_ALL = "all";

export function FilterBar() {
  const { filters, setFilters } = useFilters();
  const { data, isFetching } = useFilterOptions(filters);
  const [panelOpen, setPanelOpen] = useState(false);

  const dimensions = useMemo(() => buildDimensions(data), [data]);

  // Disabled only until the first set of options lands. Keying this off `isFetching` meant
  // every background refresh greyed out all ten dropdowns mid-click, which is most of why
  // the filters felt unreliable — a refetch is not a reason to take the controls away.
  const busy = !data;
  const refreshing = isFetching && Boolean(data);
  // Counted here rather than inside the button so the button is simply absent when there is
  // nothing to clear — a permanently-visible "Clear" on an unfiltered page reads as broken.
  const activeCount = activeFilterCount(filters);

  return (
    <div
      className="flex flex-wrap items-center gap-2 border-b bg-card px-3 py-2 sm:px-4"
      data-tour="filters"
    >
      <DateRangePicker
        preset={filters.preset}
        dateFrom={filters.dateFrom}
        dateTo={filters.dateTo}
        compare={filters.compare}
        onChange={(value) => setFilters({ ...filters, ...value })}
      />

      {/* The panel is the primary way in on anything narrower than a desktop, where the
          inline dropdowns below are hidden rather than wrapped into five unusable rows. */}
      <Button
        variant={activeCount > 0 ? "secondary" : "outline"}
        size="sm"
        className="gap-1.5"
        aria-busy={refreshing}
        onClick={() => setPanelOpen(true)}
      >
        <SlidersHorizontal className={cn("h-4 w-4", refreshing && "animate-pulse")} />
        Filters
        {activeCount > 0 && (
          <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
            {activeCount}
          </span>
        )}
      </Button>

      <Select
        value={filters.platform ?? PLATFORM_ALL}
        onValueChange={(value) =>
          setFilters({
            ...filters,
            platform: value === PLATFORM_ALL ? null : (value as Platform),
          })
        }
      >
        <SelectTrigger className="h-8 w-[7.5rem]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={PLATFORM_ALL}>All platforms</SelectItem>
          <SelectItem value="ios">iOS</SelectItem>
          <SelectItem value="android">Android</SelectItem>
        </SelectContent>
      </Select>

      {/* Inline dropdowns: convenient on a wide screen, hidden below it. Ten of them wrapped
          onto a phone is not a filter bar, it's a wall. */}
      <div className="hidden flex-wrap items-center gap-2 xl:flex">
        {dimensions.map((d) => (
          <MultiSelect
            key={d.key}
            label={d.label}
            options={d.options}
            selected={filters[d.key]}
            onChange={(values) => setFilters({ ...filters, [d.key]: values })}
            disabled={busy}
          />
        ))}
      </div>

      <div className="ml-auto flex items-center gap-2">
        {activeCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-muted-foreground hover:text-foreground"
            title="Reset the date range and every dimension to their defaults"
            onClick={() => setFilters(defaultFilters())}
          >
            <FilterX className="h-4 w-4" />
            <span className="hidden sm:inline">Clear filters ({activeCount})</span>
            <span className="sm:hidden">Clear</span>
          </Button>
        )}
        <SavedViewsMenu />
      </div>

      <FilterPanel
        open={panelOpen}
        onOpenChange={setPanelOpen}
        filters={filters}
        onApply={setFilters}
        dimensions={dimensions}
        loading={busy}
      />
    </div>
  );
}
