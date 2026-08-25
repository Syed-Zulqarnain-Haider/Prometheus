#!/usr/bin/env python3
"""Make the dimension tables show every row, and scroll instead of truncating.

THE ACTUAL BUG
    MetricTable did `.slice(0, 10)` on every table that uses it - HOU Performance,
    Pod Owner Performance, Top Apps, Publisher, Revenue. Rows past the tenth were
    dropped before render, with nothing on screen to say so. A table showing ten
    rows is indistinguishable from a table that HAS ten rows, which is why this
    reads as "it needs a scrollbar" rather than as "it is hiding data".

THE CHANGE
    - `limit` becomes an opt-in prop. Omitted, every row is shown.
    - The table body scrolls past a height cap, with a sticky header so the
      column names stay put, and a scrollbar that is always visible rather than
      the OS default that only appears once you are already scrolling.
    - Done as one CSS class so it is genuinely generic: any table that opts in
      gets the behaviour without touching its own markup.

Nothing is written unless every anchor resolves exactly once. Re-running is a no-op.
Revert: git checkout -- frontend/
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"

TABLE = FE / "components" / "overview" / "revenue-table.tsx"
EXPLORE = FE / "components" / "explore" / "explore-client.tsx"
CSS = FE / "app" / "globals.css"

problems: list[str] = []
notes: list[str] = []
writes: dict[Path, str] = {}


def fail(message: str) -> None:
    problems.append(message)


def note(message: str) -> None:
    notes.append(message)


def swap(path: Path, source: str, old: str, new: str, what: str) -> str | None:
    count = source.count(old)
    if count != 1:
        fail(f"{path.relative_to(ROOT)}: {what} matched {count} times, expected 1")
        head = old.strip().splitlines()[0][:70]
        for number, line in enumerate(source.splitlines(), 1):
            if head and head in line:
                print(f"    on disk {path.relative_to(ROOT)}:{number}: {line}")
        return None
    note(f"  {path.relative_to(ROOT)}: {what}")
    return source.replace(old, new, 1)


# ── the CSS that makes it generic ────────────────────────────────────────────
STYLES = '''

/* ── scrollable data tables ───────────────────────────────────────────────────
   Applied to the wrapper AROUND a <table>. Everything here is deliberately in CSS
   rather than in each table's markup: any table that opts in gets a height cap, a
   sticky header and a visible scrollbar without a single change to its own JSX.

   A short table is untouched - max-height only bites past the cap - so a six-row
   table looks exactly as it did and a sixty-row one scrolls. */
.table-scroll {
  max-height: var(--table-max-height, 26rem);
  overflow: auto;
  /* Reserve the scrollbar's width always, so a table crossing the threshold does
     not shift its columns sideways the moment the bar appears. */
  scrollbar-gutter: stable;
  scrollbar-width: thin;
}

.table-scroll thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  /* Opaque on purpose: a transparent sticky header lets the rows scroll straight
     through the column names. */
  background-color: var(--color-bg-card);
  /* The rule under the header has to travel WITH the header. A border on <tr>
     does not stick - only the cells do - so it is drawn as an inset shadow here. */
  box-shadow: inset 0 -1px 0 var(--color-border, rgba(127, 127, 127, 0.25));
}

/* macOS and some Windows setups hide the scrollbar until you scroll - which is
   precisely when you cannot yet tell there is more to see. Draw it always. */
.table-scroll::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.table-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.table-scroll::-webkit-scrollbar-thumb {
  background-color: color-mix(in srgb, currentColor 22%, transparent);
  background-clip: content-box;
  border: 2px solid transparent;
  border-radius: 999px;
}

.table-scroll::-webkit-scrollbar-thumb:hover {
  background-color: color-mix(in srgb, currentColor 40%, transparent);
}
'''


def patch_css() -> None:
    source = CSS.read_text(encoding="utf-8") if CSS.exists() else None
    if source is None:
        fail(f"missing: {CSS.relative_to(ROOT)}")
        return
    if ".table-scroll" in source:
        note("globals.css already defines .table-scroll - left as is.")
        return
    if "--color-bg-card" not in source:
        fail("globals.css does not define --color-bg-card - the sticky header would be "
             "transparent and the rows would scroll through it.")
        return
    writes[CSS] = source.rstrip("\n") + "\n" + STYLES
    note("  globals.css: .table-scroll (height cap, sticky header, visible scrollbar)")


# ── MetricTable ──────────────────────────────────────────────────────────────
OLD_DOC = ''' *  to the first visible revenue/installs column), keeps the top 10, and renders the Swiss
 *  Ledger table with identical loading/empty/error states. Horizontally scrolls when tight. */'''

NEW_DOC = ''' *  to the first visible revenue/installs column) and renders the Swiss Ledger table with
 *  identical loading/empty/error states.
 *
 *  Scrolls in BOTH directions: horizontally when the columns are wider than the card, and
 *  vertically past a height cap, with the header stuck to the top. It used to keep only
 *  the top 10 rows and say nothing about the rest - see ``limit``. */'''

OLD_SORTID_TYPE = '''  /** Column deciding the top 10. Omitted, the historic Gross Rev preference applies. */
  sortId?: string;'''

NEW_SORTID_TYPE = '''  /** Column deciding the sort. Omitted, the historic Gross Rev preference applies. */
  sortId?: string;
  /** Cap on rows rendered. Omitted, EVERY row is shown and the body scrolls.
   *
   *  This was a hard-coded top 10 with nothing on screen to say rows had been dropped,
   *  which is indistinguishable from there only being ten. Pass a limit only where the
   *  cap is the point of the card, never merely to keep a list short - that is what the
   *  scroll container is for. */
  limit?: number;'''

OLD_DESTRUCTURE = '''  isLoading,
  isError,
  sortId,
  action,
}: {'''

NEW_DESTRUCTURE = '''  isLoading,
  isError,
  sortId,
  limit,
  action,
}: {'''

OLD_SLICE = ".slice(0, 10),"
NEW_SLICE = "// slice(0, undefined) keeps everything - the cap is opt-in.\n        .slice(0, limit),"

OLD_DEPS = "[rows, sortCol],"
NEW_DEPS = "[rows, sortCol, limit],"

OLD_WRAPPER = '<div className="overflow-x-auto" tabIndex={0}>'
NEW_WRAPPER = '<div className="table-scroll" tabIndex={0}>'


def patch_table() -> None:
    source = TABLE.read_text(encoding="utf-8") if TABLE.exists() else None
    if source is None:
        fail(f"missing: {TABLE.relative_to(ROOT)}")
        return
    if "table-scroll" in source:
        note("revenue-table.tsx already scrolls - left as is.")
        return
    out: str | None = source
    for old, new, what in (
        (OLD_DOC, NEW_DOC, "docstring no longer claims a top 10"),
        (OLD_SORTID_TYPE, NEW_SORTID_TYPE, "limit prop"),
        (OLD_DESTRUCTURE, NEW_DESTRUCTURE, "limit destructured"),
        (OLD_SLICE, NEW_SLICE, "every row rendered unless a limit is passed"),
        (OLD_DEPS, NEW_DEPS, "limit in the memo dependencies"),
        (OLD_WRAPPER, NEW_WRAPPER, "body scrolls with a sticky header"),
    ):
        if out is None:
            return
        out = swap(TABLE, out, old, new, what)
    if out is None:
        return
    if ".slice(0, 10)" in out:
        fail("a hard-coded top-10 slice survived in revenue-table.tsx")
        return
    writes[TABLE] = out


def patch_explore() -> None:
    source = EXPLORE.read_text(encoding="utf-8") if EXPLORE.exists() else None
    if source is None:
        fail(f"missing: {EXPLORE.relative_to(ROOT)}")
        return
    if "table-scroll" in source:
        note("explore-client.tsx already scrolls - left as is.")
        return
    out = swap(EXPLORE, source, OLD_WRAPPER, NEW_WRAPPER, "Explore's table scrolls too")
    if out is not None:
        writes[EXPLORE] = out


def main() -> int:
    patch_css()
    patch_table()
    patch_explore()
    if problems:
        report()
        return 1
    for path, text in writes.items():
        path.write_text(text, encoding="utf-8")
    report()
    return 0


def report() -> None:
    for line in notes:
        print(line)
    if problems:
        print("\nFAILED - nothing was written:")
        for line in problems:
            print(f"  - {line}")
    else:
        print(f"\nPATCHED {len(writes)} file(s). Verified only by:")
        print("  ./scripts/run-frontend-tests.sh")


if __name__ == "__main__":
    raise SystemExit(main())
