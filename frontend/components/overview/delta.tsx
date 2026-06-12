import { formatPercent } from "@/lib/format";

/** vs-previous delta chip. Renders nothing when a comparison isn't possible. */
export function Delta({
  current,
  previous,
}: {
  current: number | null | undefined;
  previous: number | null | undefined;
}) {
  if (current == null || previous == null || previous === 0) return null;
  const change = (current - previous) / Math.abs(previous);
  const up = change >= 0;
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-medium"
      style={{ color: up ? "var(--color-positive)" : "var(--color-negative)" }}
    >
      {up ? "▲" : "▼"} {formatPercent(Math.abs(change), 1)}
    </span>
  );
}
