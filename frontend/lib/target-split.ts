/** Splitting an annual revenue target across twelve months.
 *
 *  All arithmetic is in integer cents. Splitting dollars with floating point leaves the
 *  months summing to something like 11,999,999.99 against a 12,000,000 annual, and the whole
 *  point of the targets panel is that the two agree exactly.
 */

export const MONTH_NUMBERS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

/** Parse a user-typed amount ("12,000,000", " 1200 ", "") to a number, or null. */
export function numberOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed.replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

export function toCents(value: string): number | null {
  const parsed = numberOrNull(value);
  return parsed === null ? null : Math.round(parsed * 100);
}

/** Render cents back to the input: whole dollars stay whole, otherwise two decimals. */
export function fromCents(cents: number): string {
  return cents % 100 === 0 ? String(cents / 100) : (cents / 100).toFixed(2);
}

export function sumCents(months: Record<number, string>): number {
  return MONTH_NUMBERS.reduce((total, m) => total + (toCents(months[m] ?? "") ?? 0), 0);
}

/** Spread whatever the annual target has left over the months the user has NOT typed into.
 *
 *  Manual months are taken as given; the remainder is split evenly across the rest, with the
 *  indivisible cents handed out one at a time from January so the total lands exactly on the
 *  annual figure rather than a cent or two below it.
 *
 *  Returns the input unchanged when there is nothing to do: no annual target yet, or every
 *  month pinned manually. When the manual months already meet or exceed the annual target the
 *  rest are zeroed rather than shown as negative targets - the caller surfaces the overshoot.
 */
export function redistribute(
  annual: string,
  months: Record<number, string>,
  manual: Set<number>,
): Record<number, string> {
  const annualCents = toCents(annual);
  if (annualCents === null) return months;

  const auto = MONTH_NUMBERS.filter((m) => !manual.has(m));
  if (auto.length === 0) return months;

  const manualCents = MONTH_NUMBERS.filter((m) => manual.has(m)).reduce(
    (total, m) => total + (toCents(months[m] ?? "") ?? 0),
    0,
  );
  const remainder = annualCents - manualCents;
  const next = { ...months };

  if (remainder <= 0) {
    for (const m of auto) next[m] = "0";
    return next;
  }

  const base = Math.floor(remainder / auto.length);
  let extra = remainder - base * auto.length;
  for (const m of auto) {
    next[m] = fromCents(base + (extra > 0 ? 1 : 0));
    if (extra > 0) extra -= 1;
  }
  return next;
}
