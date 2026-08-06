"use client";

import type { Option } from "@/components/filters/multi-select";
import { useFilterOptions } from "@/lib/api-hooks";
import type { ListFilterKey } from "@/lib/filters";

/** The shape `/meta/filter-options` returns, taken from the hook rather than re-declared, so
 *  a change to the endpoint's schema surfaces here as a type error instead of drifting. */
export type FilterOptionsData = NonNullable<ReturnType<typeof useFilterOptions>["data"]>;

export interface FilterDimension {
  /** The `Filters` key this dimension narrows. */
  key: ListFilterKey;
  label: string;
  options: Option[];
}

function toOptions(values: string[] | undefined): Option[] {
  return [...(values ?? [])].sort().map((v) => ({ value: v, label: v }));
}

/** Single definition of the filter bar's dimensions — their order, their labels and where
 *  their options come from. The inline bar and the slide-over panel both render from this,
 *  so the two can't disagree about what's filterable.
 *
 *  Apps leads: it is by far the most-used dimension and, at 150+ entries, the one people go
 *  looking for first. */
export function buildDimensions(data: FilterOptionsData | undefined): FilterDimension[] {
  const apps = [...(data?.apps ?? [])]
    .map((a) => ({ value: a.value, label: a.label ?? a.value }))
    .sort((x, y) => x.label.localeCompare(y.label));

  return [
    { key: "apps", label: "Apps", options: apps },
    { key: "consoles", label: "Console", options: toOptions(data?.consoles) },
    { key: "hou", label: "HOU", options: toOptions(data?.hous) },
    { key: "podOwners", label: "Pod Owner", options: toOptions(data?.pod_owners) },
    { key: "publishers", label: "Publisher", options: toOptions(data?.publishers) },
    { key: "developers", label: "Developer", options: toOptions(data?.developers) },
    {
      key: "googlePlayAccounts",
      label: "Google account",
      options: toOptions(data?.google_play_accounts),
    },
    { key: "appleAccounts", label: "Apple account", options: toOptions(data?.apple_accounts) },
    { key: "packages", label: "Google package", options: toOptions(data?.packages) },
    { key: "bundles", label: "iOS bundle", options: toOptions(data?.bundles) },
  ];
}
