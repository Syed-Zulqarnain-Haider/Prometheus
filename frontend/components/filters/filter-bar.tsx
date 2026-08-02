"use client";

import { useMemo } from "react";

import { DateRangePicker } from "@/components/filters/date-range-picker";
import { MultiSelect, type Option } from "@/components/filters/multi-select";
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
import type { Platform } from "@/lib/types";
import { useFilters } from "@/lib/use-filters";

const PLATFORM_ALL = "all";

/** Plain string values → sorted MultiSelect options. */
function toOptions(values: string[]): Option[] {
  return [...values].sort().map((v) => ({ value: v, label: v }));
}

export function FilterBar() {
  const { filters, setFilters } = useFilters();
  const { data, isFetching } = useFilterOptions(filters);

  const consoleOptions = useMemo(() => toOptions(data?.consoles ?? []), [data]);
  const podOwnerOptions = useMemo(() => toOptions(data?.pod_owners ?? []), [data]);
  const houOptions = useMemo(() => toOptions(data?.hous ?? []), [data]);
  const publisherOptions = useMemo(() => toOptions(data?.publishers ?? []), [data]);
  const developerOptions = useMemo(() => toOptions(data?.developers ?? []), [data]);
  const googleAcctOptions = useMemo(() => toOptions(data?.google_play_accounts ?? []), [data]);
  const appleAcctOptions = useMemo(() => toOptions(data?.apple_accounts ?? []), [data]);
  const packageOptions = useMemo(() => toOptions(data?.packages ?? []), [data]);
  const bundleOptions = useMemo(() => toOptions(data?.bundles ?? []), [data]);
  const appOptions = useMemo<Option[]>(
    () =>
      (data?.apps ?? [])
        .map((a) => ({ value: a.value, label: a.label ?? a.value }))
        .sort((x, y) => x.label.localeCompare(y.label)),
    [data],
  );

  const busy = isFetching;

  return (
    <div
      className="flex flex-wrap items-center gap-2 border-b bg-card px-4 py-2"
      data-tour="filters"
    >
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
        label="Console"
        options={consoleOptions}
        selected={filters.consoles}
        onChange={(consoles) => setFilters({ ...filters, consoles })}
        disabled={busy}
      />
      <MultiSelect
        label="HOU"
        options={houOptions}
        selected={filters.hou}
        onChange={(hou) => setFilters({ ...filters, hou })}
        disabled={busy}
      />
      <MultiSelect
        label="Pod Owner"
        options={podOwnerOptions}
        selected={filters.podOwners}
        onChange={(podOwners) => setFilters({ ...filters, podOwners })}
        disabled={busy}
      />
      <MultiSelect
        label="Publisher"
        options={publisherOptions}
        selected={filters.publishers}
        onChange={(publishers) => setFilters({ ...filters, publishers })}
        disabled={busy}
      />
      <MultiSelect
        label="Developer"
        options={developerOptions}
        selected={filters.developers}
        onChange={(developers) => setFilters({ ...filters, developers })}
        disabled={busy}
      />
      <MultiSelect
        label="Google account"
        options={googleAcctOptions}
        selected={filters.googlePlayAccounts}
        onChange={(googlePlayAccounts) => setFilters({ ...filters, googlePlayAccounts })}
        disabled={busy}
      />
      <MultiSelect
        label="Apple account"
        options={appleAcctOptions}
        selected={filters.appleAccounts}
        onChange={(appleAccounts) => setFilters({ ...filters, appleAccounts })}
        disabled={busy}
      />
      <MultiSelect
        label="Google package"
        options={packageOptions}
        selected={filters.packages}
        onChange={(packages) => setFilters({ ...filters, packages })}
        disabled={busy}
      />
      <MultiSelect
        label="iOS bundle"
        options={bundleOptions}
        selected={filters.bundles}
        onChange={(bundles) => setFilters({ ...filters, bundles })}
        disabled={busy}
      />
      <MultiSelect
        label="Apps"
        options={appOptions}
        selected={filters.apps}
        onChange={(appsSelected) => setFilters({ ...filters, apps: appsSelected })}
        disabled={busy}
      />
      <div className="ml-auto">
        <SavedViewsMenu />
      </div>
    </div>
  );
}
