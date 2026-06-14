/** Series/value formatting helpers shared by charts, KPIs, and tables. */

const EMPTY = "—";

function isNil(value: number | null | undefined): value is null | undefined {
  return value === null || value === undefined || Number.isNaN(value);
}

/** Currency, e.g. "$1,234,850" or compact "$1.23M". */
export function formatUSD(
  value: number | null | undefined,
  options: { compact?: boolean; digits?: number } = {},
): string {
  if (isNil(value)) return EMPTY;
  const { compact = false, digits } = options;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: digits ?? (compact ? 2 : 0),
  }).format(value);
}

/** A fraction (0.704) rendered as a percentage ("70.4%"). */
export function formatPercent(
  fraction: number | null | undefined,
  digits = 1,
): string {
  if (isNil(fraction)) return EMPTY;
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** Compact number, e.g. "1.2K", "3.4M". */
export function formatCompact(
  value: number | null | undefined,
  digits = 1,
): string {
  if (isNil(value)) return EMPTY;
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: digits,
  }).format(value);
}

/** Grouped integer, e.g. "1,234,567". */
export function formatNumber(value: number | null | undefined): string {
  if (isNil(value)) return EMPTY;
  return new Intl.NumberFormat("en-US").format(value);
}

/** A multiplier ratio (ROAS), e.g. "2.45×". */
export function formatMultiplier(
  value: number | null | undefined,
  digits = 2,
): string {
  if (isNil(value)) return EMPTY;
  return `${value.toFixed(digits)}×`;
}

/** Localized date-time, e.g. "Jun 14, 2026, 09:40". */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
