/** The immediately-preceding window of equal length (mirrors the backend's
 *  previous-period logic) for Compare-mode "ghost" overlays. */

function parseLocal(d: string): Date {
  const [y, m, day] = d.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, day);
}

function iso(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function previousWindow(
  dateFrom: string,
  dateTo: string,
): { from: string; to: string } {
  const from = parseLocal(dateFrom);
  const to = parseLocal(dateTo);
  const dayMs = 24 * 60 * 60 * 1000;
  const length = Math.round((to.getTime() - from.getTime()) / dayMs) + 1;
  const prevTo = new Date(from.getTime() - dayMs);
  const prevFrom = new Date(prevTo.getTime() - (length - 1) * dayMs);
  return { from: iso(prevFrom), to: iso(prevTo) };
}
