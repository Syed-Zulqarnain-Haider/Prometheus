import { format, subDays } from "date-fns";

import type { Platform } from "@/lib/types";

export type DatePreset = "7D" | "30D" | "90D" | "custom";

export interface Filters {
  preset: DatePreset;
  dateFrom: string; // yyyy-MM-dd
  dateTo: string; // yyyy-MM-dd
  compare: boolean;
  platform: Platform | null;
  pods: string[];
  publishers: string[];
  apps: string[];
}

const PRESET_DAYS: Record<Exclude<DatePreset, "custom">, number> = {
  "7D": 7,
  "30D": 30,
  "90D": 90,
};

const DEFAULT_PRESET: Exclude<DatePreset, "custom"> = "30D";

function isoDate(date: Date): string {
  return format(date, "yyyy-MM-dd");
}

/** Inclusive [from, to] range for a preset, ending today. */
export function presetRange(preset: Exclude<DatePreset, "custom">): {
  from: string;
  to: string;
} {
  const to = new Date();
  const from = subDays(to, PRESET_DAYS[preset] - 1);
  return { from: isoDate(from), to: isoDate(to) };
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
  };
}

function splitList(value: string | null): string[] {
  if (!value) return [];
  return value.split(",").filter(Boolean);
}

export function parseFilters(params: URLSearchParams): Filters {
  const base = defaultFilters();
  const preset = (params.get("preset") as DatePreset | null) ?? base.preset;
  const platformParam = params.get("platform");
  const platform: Platform | null =
    platformParam === "ios" || platformParam === "android" ? platformParam : null;

  return {
    preset: preset === "custom" || preset in PRESET_DAYS ? preset : base.preset,
    dateFrom: params.get("from") ?? base.dateFrom,
    dateTo: params.get("to") ?? base.dateTo,
    compare: params.get("compare") === "1",
    platform,
    pods: splitList(params.get("pods")),
    publishers: splitList(params.get("publishers")),
    apps: splitList(params.get("apps")),
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
  };
}
