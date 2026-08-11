/** The immediately-preceding window of equal length (mirrors the backend's
 *  previous-period logic) for Compare-mode "ghost" overlays. */

import { differenceInCalendarDays, format, parseISO, subDays } from "date-fns";

export function previousWindow(
  dateFrom: string,
  dateTo: string,
): { from: string; to: string } {
  // Calendar-day arithmetic, NOT raw *86400000 millisecond math: subtracting 24h
  // across a DST change lands at 23:00 or 01:00 of the WRONG calendar day, which
  // shifted the whole comparison window by one day for viewers in DST timezones.
  const from = parseISO(dateFrom.slice(0, 10));
  const to = parseISO(dateTo.slice(0, 10));
  const length = differenceInCalendarDays(to, from) + 1;
  const prevTo = subDays(from, 1);
  const prevFrom = subDays(prevTo, length - 1);
  return { from: format(prevFrom, "yyyy-MM-dd"), to: format(prevTo, "yyyy-MM-dd") };
}
