#!/usr/bin/env python3
"""Let MetricTable be ranked by a chosen column, and carry a control in its header.

Three small, backwards-compatible additions to
``frontend/components/overview/revenue-table.tsx``. Nothing about the existing tables
changes: both new props are optional and default to today's behaviour.

  * ``sortId``  - which column decides the top 10. MetricTable has always sorted by Gross
                  Rev (falling back through Net, IAP, Installs); that stays the default,
                  but the Top Apps widget now passes the column the user picked.
  * ``action``  - a node rendered on the right of the card header, for the picker.
  * ``PUBLISHER_IDENTITY`` becomes exported, so the Top Apps widget reuses the Publisher +
    Game identity columns - including the store links and the drill-down link - instead of
    duplicating them and letting the two drift apart.

Why this file and not a new one: the shared metric columns and the table renderer live
here by design, and every dimension table inherits them. A second copy of the renderer
with its own sort is exactly the divergence that rule exists to prevent.

Anchored: every anchor must appear EXACTLY once or nothing is written. Idempotent.
Frontend rebuild required; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

TABLE = Path("frontend/components/overview/revenue-table.tsx")

EXPORT_ANCHOR = "const PUBLISHER_IDENTITY: ColumnDef[] = [\n"
EXPORT_NEW = "export const PUBLISHER_IDENTITY: ColumnDef[] = [\n"

PROPS_ANCHOR = """export function MetricTable({
  title,
  columns,
  rows,
  rowKey,
  isLoading,
  isError,
}: {
  title: string;
  columns: ColumnDef[];
  rows: Row[];
  rowKey: (row: Row) => string;
  isLoading: boolean;
  isError: boolean;
}) {
  const sortCol =
    columns.find((c) => c.id === "gross") ??
"""

PROPS_NEW = """export function MetricTable({
  title,
  columns,
  rows,
  rowKey,
  isLoading,
  isError,
  sortId,
  action,
}: {
  title: string;
  columns: ColumnDef[];
  rows: Row[];
  rowKey: (row: Row) => string;
  isLoading: boolean;
  isError: boolean;
  /** Column deciding the top 10. Omitted, the historic Gross Rev preference applies. */
  sortId?: string;
  /** Rendered at the right of the card header - e.g. a "rank by" picker. */
  action?: ReactNode;
}) {
  const sortCol =
    (sortId ? columns.find((c) => c.id === sortId) : undefined) ??
    columns.find((c) => c.id === "gross") ??
"""

HEADER_ANCHOR = """    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
"""

HEADER_NEW = """    <Card>
      {/* flex-row only when there is something to sit beside the title, so every other
          table keeps the header it has always had. */}
      <CardHeader
        className={action ? "flex-row items-center justify-between gap-3 space-y-0" : undefined}
      >
        <CardTitle>{title}</CardTitle>
        {action}
      </CardHeader>
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not TABLE.exists():
        die(f"{TABLE} not found - run from the repository root")

    text = TABLE.read_text()

    if "sortId?: string" in text:
        print("already extended - nothing to do")
        return

    for anchor in (EXPORT_ANCHOR, PROPS_ANCHOR, HEADER_ANCHOR):
        if text.count(anchor) != 1:
            die(
                f"{TABLE}: expected exactly one {anchor.splitlines()[0].strip()!r}, "
                f"found {text.count(anchor)} - the component has changed shape"
            )
    # ReactNode is needed for the `action` prop; it is already imported for ColumnDef's
    # optional `render`, but check rather than assume.
    if "type ReactNode" not in text:
        die(f"{TABLE}: ReactNode is not imported - add it before running this")

    text = text.replace(EXPORT_ANCHOR, EXPORT_NEW, 1)
    text = text.replace(PROPS_ANCHOR, PROPS_NEW, 1)
    text = text.replace(HEADER_ANCHOR, HEADER_NEW, 1)
    TABLE.write_text(text)

    print(f"patched {TABLE}: MetricTable takes sortId + action; PUBLISHER_IDENTITY exported")
    print("\nExisting tables are unchanged - both props are optional.")


if __name__ == "__main__":
    main()
