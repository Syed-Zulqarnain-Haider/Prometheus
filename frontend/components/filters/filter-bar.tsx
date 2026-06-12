"use client";

import { useMemo } from "react";

import { DateRangePicker } from "@/components/filters/date-range-picker";
import { MultiSelect, type Option } from "@/components/filters/multi-select";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApps } from "@/lib/api-hooks";
import type { Platform } from "@/lib/types";
import { useFilters } from "@/lib/use-filters";

const PLATFORM_ALL = "all";

function uniqueOptions(values: (string | null)[]): Option[] {
  const set = Array.from(
    new Set(values.filter((v): v is string => Boolean(v))),
  ).sort();
  return set.map((v) => ({ value: v, label: v }));
}

export function FilterBar() {
  const { filters, setFilters } = useFilters();
  const { data, isLoading } = useApps();
  const apps = useMemo(() => data?.apps ?? [], [data]);

  const podOptions = useMemo(() => uniqueOptions(apps.map((a) => a.pod)), [apps]);
  const publisherOptions = useMemo(
    () => uniqueOptions(apps.map((a) => a.publisher)),
    [apps],
  );
  const appOptions = useMemo<Option[]>(
    () =>
      apps
        .map((a) => ({ value: a.canonical_key, label: a.app_name ?? a.canonical_key }))
        .sort((x, y) => x.label.localeCompare(y.label)),
    [apps],
  );

  return (
    <div className="flex flex-wrap items-center gap-2 border-b bg-card px-4 py-2">
      <DateRangePicker
        preset={filters.preset}
        dateFrom={filters.dateFrom}
        dateTo={filters.dateTo}
        onChange={(value) => setFilters({ ...filters, ...value })}
      />
      <Button
        variant={filters.compare ? "default" : "outline"}
        size="sm"
        onClick={() => setFilters({ ...filters, compare: !filters.compare })}
      >
        Compare
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
      <MultiSelect
        label="Pods"
        options={podOptions}
        selected={filters.pods}
        onChange={(pods) => setFilters({ ...filters, pods })}
        disabled={isLoading}
      />
      <MultiSelect
        label="Publishers"
        options={publisherOptions}
        selected={filters.publishers}
        onChange={(publishers) => setFilters({ ...filters, publishers })}
        disabled={isLoading}
      />
      <MultiSelect
        label="Apps"
        options={appOptions}
        selected={filters.apps}
        onChange={(appsSelected) => setFilters({ ...filters, apps: appsSelected })}
        disabled={isLoading}
      />
    </div>
  );
}
