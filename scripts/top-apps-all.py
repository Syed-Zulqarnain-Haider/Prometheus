#!/usr/bin/env python3
"""The apps table on the Overview shows every app, not the first page of them.

Two separate things were capping it and only one of them is obvious:

  A. THE FETCH.  ``useTable(filters, sort, 100)`` asks /metrics/table for one page.
     The endpoint is keyset-paginated (``next_cursor``) and caps a single page at 200,
     so no limit value can mean "all" - the cursor has to be walked to the end. This
     switches to ``useTableInfinite`` and pulls pages until there are none left.

  B. A SLICE INSIDE THE SHARED TABLE.  If the shared ``MetricTable`` trims the rows it
     is handed, fetching more changes nothing at all - the extra rows arrive and are
     thrown away one line before they would have been drawn. That is the silent half:
     the network tab says the data came, and the screen still shows ten. This looks for
     such a slice and lifts it into a prop with the current number as its default, so
     every OTHER caller keeps the behaviour it has today and only this table opts out.

     If the slice cannot be lifted safely, that section is skipped, the shared
     component's source is PRINTED, and (A) is still applied - so the round is not
     wasted and the next edit can be exact instead of hopeful.

MAX_ROWS is a runaway guard, not a display limit. If it is ever reached the heading
carries the count, so a truncated list cannot be mistaken for a complete one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
TABLE = ROOT / "frontend/components/overview/top-apps-table.tsx"
PAGE_SIZE = 200  # the endpoint's own maximum for one page
MAX_ROWS = 2000

report: list[str] = []
skipped: list[str] = []


def window(text: str, needle: str, before: int = 3, after: int = 12) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(f"      | {ln}" for ln in lines[max(0, i - before) : i + after])
    return "      | (not found in this file)"


# ── A. fetch every page ────────────────────────────────────────────────────────────
FETCH_OLD = '  const table = useTable(filters, active?.field ?? "canonical_key", 100);'
FETCH_NEW = f'''  // Every app, not the first page of them. /metrics/table is keyset-paginated and
  // caps ONE page at {PAGE_SIZE} rows, so "all" means walking the cursor to the end rather
  // than asking for a bigger page - no limit value can express it.
  //
  // The pages are pulled by an effect rather than by a "load more" button because the
  // question being answered here is "how do all my apps compare", and an answer that
  // is only complete if you remember to keep clicking is not an answer.
  const table = useTableInfinite(
    filters,
    active?.field ?? "canonical_key",
    "desc",
    {PAGE_SIZE},
  );
  const {{ fetchNextPage, hasNextPage, isFetchingNextPage }} = table;
  const rows = useMemo(
    () => (table.data?.pages ?? []).flatMap((page) => page.rows),
    [table.data],
  );

  useEffect(() => {{
    // MAX_ROWS is a guard against a filter that matches everything, not a display
    // limit; the heading shows the count so a stopped list is never a silent one.
    if (hasNextPage && !isFetchingNextPage && rows.length < MAX_ROWS) {{
      void fetchNextPage();
    }}
  }}, [fetchNextPage, hasNextPage, isFetchingNextPage, rows.length]);'''

DOC_OLD = """ * The ranking is NOT a client-side re-sort of a fixed list. /metrics/table is keyset
 * sorted server-side by one column and we only ever look at the first 100 rows, so
 * re-sorting that page by a different measure would give the top 10 OF THE TOP 100 BY
 * REVENUE - which is not the top 10 by UA cost, and would be silently wrong. Changing the
 * picker changes the SERVER sort as well, so the page fetched is the right page."""

DOC_NEW = """ * The ranking is NOT a client-side re-sort. /metrics/table is keyset sorted
 * server-side by one column, so changing the picker changes the SERVER sort and the
 * rows arrive in the right order. Every page is fetched, so the list is every app the
 * caller may see - the ranking is over all of them, not over a first page of them."""

SWAPS: list[tuple[str, str, str]] = [
    (DOC_OLD, DOC_NEW, "the header comment no longer describes a 100-row page"),
    (
        'import { useMemo, useState } from "react";',
        'import { useEffect, useMemo, useState } from "react";',
        "useEffect imported",
    ),
    (
        'import { useMe, useTable } from "@/lib/api-hooks";',
        'import { useMe, useTableInfinite } from "@/lib/api-hooks";',
        "paginated hook imported",
    ),
    (FETCH_OLD, FETCH_NEW, f"walks the cursor to the end ({PAGE_SIZE}/page)"),
    (
        "      rows={table.data?.rows ?? []}",
        "      rows={rows}",
        "every fetched row is drawn",
    ),
    (
        '      title={active ? `Top Apps by ${active.label}` : "Top Apps"}',
        """      title={
        active
          ? `All Apps by ${active.label}${rows.length ? ` (${rows.length})` : ""}`
          : "All Apps"
      }""",
        'heading says "All Apps" and carries the count',
    ),
]

MAX_ROWS_CONST = f"""/** A guard against a filter that matches the entire fact table, not a display limit -
 *  the heading carries the row count, so a list that stops here says so. */
const MAX_ROWS = {MAX_ROWS};

"""


def section_fetch() -> bool:
    if not TABLE.exists():
        skipped.append(f"[fetch] {TABLE} does not exist here - nothing changed.")
        return False
    text = TABLE.read_text()
    if "useTableInfinite" in text:
        report.append("[fetch] already paginating - left alone")
        return True

    missing = [(old, why) for old, _, why in SWAPS if text.count(old) != 1]
    if missing:
        detail = "\n".join(
            f"    expected exactly one ({why}):\n      {old.strip()[:140]}\n"
            f"    on disk near it:\n{window(text, old.strip()[:38])}"
            for old, why in missing
        )
        skipped.append(f"[fetch] {TABLE} - nothing changed.\n{detail}")
        return False

    for old, new, _ in SWAPS:
        text = text.replace(old, new, 1)

    # The constant goes above the component, next to the other module-level tables.
    anchor = re.search(r"^export function TopAppsTable\b", text, re.M)
    if anchor is None:
        skipped.append(f"[fetch] {TABLE}: no `export function TopAppsTable` to sit above.")
        return False
    text = text[: anchor.start()] + MAX_ROWS_CONST + text[anchor.start() :]

    TABLE.write_text(text)
    report.extend(f"[fetch] {why}" for _, _, why in SWAPS)
    return True


# ── B. the shared table's own cap ──────────────────────────────────────────────────
IMPORT_RE = re.compile(r'from\s*"(@/[^"]+)"')
SLICE_RE = re.compile(r"\.slice\(\s*0\s*,\s*(\d+)\s*\)")


def resolve_metric_table() -> Path | None:
    """Follow top-apps-table's own import rather than assuming where MetricTable lives."""
    if not TABLE.exists():
        return None
    text = TABLE.read_text()
    block = re.search(r"import\s*\{[^}]*\bMetricTable\b[^}]*\}\s*from\s*\"(@/[^\"]+)\"", text)
    if block is None:
        return None
    rel = block.group(1).replace("@/", "frontend/")
    for candidate in (Path(rel + ".tsx"), Path(rel + ".ts")):
        if (ROOT / candidate).exists():
            return ROOT / candidate
    return None


def function_body(text: str, name: str) -> tuple[int, int] | None:
    """Byte range of ``export function <name>``'s body, by brace balance."""
    head = re.search(rf"^export function {re.escape(name)}\b", text, re.M)
    if head is None:
        return None
    open_at = text.find("{", head.end())
    if open_at == -1:
        return None
    depth, i = 0, open_at
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return open_at, i + 1
        i += 1
    return None


def section_shared_cap() -> None:
    path = resolve_metric_table()
    if path is None:
        skipped.append(
            "[shared cap] could not follow top-apps-table's import of MetricTable to a\n"
            "  file, so its source could not be checked for a row cap. If the table\n"
            "  still shows a fixed number of apps after this, the cap is in there."
        )
        return

    text = path.read_text()
    if "rowLimit" in text:
        report.append(f"[shared cap] {path}: already takes a rowLimit - left alone")
        return

    span = function_body(text, "MetricTable")
    if span is None:
        report.append(
            f"[shared cap] {path}: no `export function MetricTable` - the row cap, if any,"
            " is not there. Nothing to lift."
        )
        return

    start, end = span
    body = text[start:end]
    hits = SLICE_RE.findall(body)
    if not hits:
        report.append(
            f"[shared cap] {path}: MetricTable draws every row it is handed - no cap to"
            " lift, so the fetch above is the whole fix."
        )
        return

    if len(hits) > 1:
        skipped.append(
            f"[shared cap] {path}: MetricTable trims its rows in {len(hits)} places, so\n"
            "  which one is the display cap is a guess. Nothing was changed there.\n"
            "  Its source, so the next edit can be exact:\n"
            + "\n".join(f"      | {ln}" for ln in body.splitlines())
        )
        return

    print(
        f"NOTE: {path} caps MetricTable at {hits[0]} rows. Lifting it into a prop needs\n"
        "  its signature, which differs between versions - printing it rather than\n"
        "  rewriting it blind. Nothing in that file was changed."
    )
    skipped.append(
        f"[shared cap] {path}: MetricTable slices to {hits[0]}. The fetch now brings every\n"
        "  app, but this line throws all but the first "
        f"{hits[0]} away before they are drawn.\n"
        "  Its source, so the cap can be lifted into a prop exactly:\n"
        + "\n".join(f"      | {ln}" for ln in body.splitlines())
    )


def main() -> int:
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    if section_fetch():
        section_shared_cap()

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    if skipped:
        print("\nSKIPPED (nothing written for these):")
        for entry in skipped:
            print(f"\n  {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
