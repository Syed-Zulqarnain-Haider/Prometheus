/** Visible marker required on every demo (non-real-data) widget. */
export function DemoBadge() {
  return (
    <span
      className="inline-flex items-center rounded-sm border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
      style={{
        borderColor: "var(--color-amber)",
        color: "var(--color-amber)",
        backgroundColor: "var(--color-amber-soft)",
      }}
      title="Placeholder data — not from the live API (see docs/DESIGN.md)"
    >
      Demo data
    </span>
  );
}
