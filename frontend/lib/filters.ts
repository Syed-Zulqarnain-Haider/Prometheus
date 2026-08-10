import { endOfMonth, format, startOfMonth, subDays, subMonths } from "date-fns";

import type { Platform } from "@/lib/types";

export type DatePreset =
  | "today"
  | "yesterday"
  | "7D"
  | "30D"
  | "mtd" // this month so far
  | "lastmonth"
  | "all"
  | "custom";

/** Preset menu, in display order (labels match the AdMob/Looker date picker). */
export const PRESET_LABELS: { key: Exclude<DatePreset, "custom">; label: string }[] = [
  { key: "today", label: "Today so far" },
  { key: "yesterday", label: "Yesterday" },
  { key: "7D", label: "Last 7 days" },
  { key: "30D", label: "Last 30 days" },
  { key: "mtd", label: "This month so far" },
  { key: "lastmonth", label: "Last month" },
  { key: "all", label: "All time" },
];

const VALID_PRESETS = new Set<string>([...PRESET_LABELS.map((p) => p.key), "custom"]);

export interface Filters {
  preset: DatePreset;
  dateFrom: string; // yyyy-MM-dd
  dateTo: string; // yyyy-MM-dd
  compare: boolean;
  platform: Platform | null;
  pods: string[]; // legacy - kept for saved views; the bar now uses podOwners
  publishers: string[];
  apps: string[];
  hou: string[];
  // Additional narrowing dimensions surfaced in the global filter bar.
  podOwners: string[];
  consoles: string[];
  developers: string[];
  googlePlayAccounts: string[];
  appleAccounts: string[];
  packages: string[]; // android_package
  bundles: string[]; // ios_bundle_id
}

/** Every list-valued filter key, in one place. Used by "Clear filters" to count what's
 *  applied without hand-listing the keys at each call site - adding a dimension to
 *  ``Filters`` and forgetting it here would otherwise leave a filter uncounted. */
export const LIST_FILTER_KEYS = [
  "pods",
  "publishers",
  "apps",
  "hou",
  "podOwners",
  "consoles",
  "developers",
  "googlePlayAccounts",
  "appleAccounts",
  "packages",
  "bundles",
] as const;

export type ListFilterKey = (typeof LIST_FILTER_KEYS)[number];

const DEFAULT_PRESET: Exclude<DatePreset, "custom"> = "30D";
// Earliest date "All time" reaches back to (well before any data).
export const ALL_TIME_START = "2020-01-01";

function isoDate(date: Date): string {
  return format(date, "yyyy-MM-dd");
}

/** Inclusive [from, to] range for a preset. */
export function presetRange(preset: Exclude<DatePreset, "custom">): {
  from: string;
  to: string;
} {
  const today = new Date();
  switch (preset) {
    case "today":
      return { from: isoDate(today), to: isoDate(today) };
    case "yesterday": {
      const y = subDays(today, 1);
      return { from: isoDate(y), to: isoDate(y) };
    }
    case "7D":
      return { from: isoDate(subDays(today, 6)), to: isoDate(today) };
    case "30D":
      return { from: isoDate(subDays(today, 29)), to: isoDate(today) };
    case "mtd":
      return { from: isoDate(startOfMonth(today)), to: isoDate(today) };
    case "lastmonth": {
      const prev = subMonths(today, 1);
      return { from: isoDate(startOfMonth(prev)), to: isoDate(endOfMonth(prev)) };
    }
    case "all":
      return { from: ALL_TIME_START, to: isoDate(today) };
  }
}

export function defaultFilters(): Filters {
  const { from, to } = presetRange(DEFAULT_PRESET);
  return {
    preset: DEFAULT_PRESET,
    dateFrom: from,
    dateTo: to,
    compare: false,
    platform: null,
    pods: [],
    publishers: [],
    apps: [],
    hou: [],
    podOwners: [],
    consoles: [],
    developers: [],
    googlePlayAccounts: [],
    appleAccounts: [],
    packages: [],
    bundles: [],
  };
}

/** How many distinct filters the viewer has applied, counting the whole date range as one.
 *  Drives the count on the "Clear filters" button and whether it is shown at all. */
export function activeFilterCount(filters: Filters): number {
  const base = defaultFilters();
  let count = 0;
  for (const key of LIST_FILTER_KEYS) {
    if (filters[key].length > 0) count += 1;
  }
  if (filters.platform !== null) count += 1;
  if (filters.compare) count += 1;
  if (
    filters.preset !== base.preset ||
    filters.dateFrom !== base.dateFrom ||
    filters.dateTo !== base.dateTo
  ) {
    count += 1;
  }
  return count;
}

/** Is anything narrowed away from the defaults? */
export function isFiltered(filters: Filters): boolean {
  return activeFilterCount(filters) > 0;
}

function splitList(value: string | null): string[] {
  if (!value) return [];
  return value.split(",").filter(Boolean);
}

export function parseFilters(params: URLSearchParams): Filters {
  const base = defaultFilters();
  const raw = (params.get("preset") as DatePreset | null) ?? base.preset;
  const preset: DatePreset = VALID_PRESETS.has(raw) ? raw : base.preset;
  const platformParam = params.get("platform");
  const platform: Platform | null =
    platformParam === "ios" || platformParam === "android" ? platformParam : null;

  // A named preset is RECOMPUTED, never read back from the URL. A bookmark, saved view or
  // shared link carrying `preset=today&from=2026-08-05` must not render yesterday's numbers
  // under a "Today so far" label - the label is the intent, the dates are just its cache.
  // Only `preset=custom` trusts the stored dates.
  const stored =
    preset === "custom"
      ? { from: params.get("from") ?? base.dateFrom, to: params.get("to") ?? base.dateTo }
      : presetRange(preset);

  return {
    preset,
    dateFrom: stored.from,
    dateTo: stored.to,
    compare: params.get("compare") === "1",
    platform,
    pods: splitList(params.get("pods")),
    publishers: splitList(params.get("publishers")),
    apps: splitList(params.get("apps")),
    hou: splitList(params.get("hou")),
    podOwners: splitList(params.get("podOwners")),
    consoles: splitList(params.get("consoles")),
    developers: splitList(params.get("developers")),
    googlePlayAccounts: splitList(params.get("googlePlayAccounts")),
    appleAccounts: splitList(params.get("appleAccounts")),
    packages: splitList(params.get("packages")),
    bundles: splitList(params.get("bundles")),
  };
}

export function filtersToParams(filters: Filters): URLSearchParams {
  const params = new URLSearchParams();
  params.set("preset", filters.preset);
  params.set("from", filters.dateFrom);
  params.set("to", filters.dateTo);
  if (filters.compare) params.set("compare", "1");
  if (filters.platform) params.set("platform", filters.platform);
  if (filters.pods.length) params.set("pods", filters.pods.join(","));
  if (filters.publishers.length) params.set("publishers", filters.publishers.join(","));
  if (filters.apps.length) params.set("apps", filters.apps.join(","));
  if (filters.hou.length) params.set("hou", filters.hou.join(","));
  if (filters.podOwners.length) params.set("podOwners", filters.podOwners.join(","));
  if (filters.consoles.length) params.set("consoles", filters.consoles.join(","));
  if (filters.developers.length) params.set("developers", filters.developers.join(","));
  if (filters.googlePlayAccounts.length)
    params.set("googlePlayAccounts", filters.googlePlayAccounts.join(","));
  if (filters.appleAccounts.length) params.set("appleAccounts", filters.appleAccounts.join(","));
  if (filters.packages.length) params.set("packages", filters.packages.join(","));
  if (filters.bundles.length) params.set("bundles", filters.bundles.join(","));
  return params;
}

/** Shape the filters for the metrics API query string. */
export function filtersToApiQuery(filters: Filters): Record<string, string | boolean | string[]> {
  return {
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    compare: filters.compare,
    ...(filters.platform ? { platform: filters.platform } : {}),
    pods: filters.pods,
    publishers: filters.publishers,
    apps: filters.apps,
    ...(filters.hou.length ? { hou: filters.hou } : {}),
    pod_owners: filters.podOwners,
    consoles: filters.consoles,
    developers: filters.developers,
    google_play_accounts: filters.googlePlayAccounts,
    apple_accounts: filters.appleAccounts,
    packages: filters.packages,
    bundles: filters.bundles,
  };
}
