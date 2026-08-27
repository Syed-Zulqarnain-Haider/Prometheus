#!/usr/bin/env python3
"""UX batch 1: presence keep-alive, retire the Magnetic dot cursor, put the Overview
widgets in the order the owner asked for, and dump what the next batch needs to see.

Three fixes and one recon, all in one run:

  1. PRESENCE KEEP-ALIVE.  Presence is refreshed by any authenticated request, which
     stops being true the moment somebody just *reads* a page: the dashboard caches
     hard, an idle tab issues no requests, the 120s Redis key lapses and a person who
     is sitting right there is shown as "away". A deliberate 45s ping (visible tabs
     only) replaces the accidental traffic we were relying on.

  2. MAGNETIC DOT.  Removed from the cursor picker on Profile, and de-selected for
     anyone who had already chosen it. The implementation is left in place and still
     referenced - ripping the component out would orphan `INTERACTIVE` and the shared
     spring, which is a bigger change than "take the button away" asked for.

  3. OVERVIEW ORDER.  Pod Owner Performance, then HOU, then Top Apps by Revenue, at the
     top of the draggable grid. Done STRUCTURALLY: the LG_LAYOUT rows are parsed, the
     rows are reordered, and `y` is recomputed by stacking - so every widget keeps its
     own width, height and column position and only the row order moves. The widget ids
     are DISCOVERED from the code (the id -> component map in overview-client.tsx), not
     guessed, and the run aborts with that map printed if any of the three is ambiguous.

     A saved per-user layout beats the default, so the reorder is invisible to anyone
     who has ever pressed "Customize layout". A one-time migration clears the saved
     Overview layouts so everybody actually gets the new order; re-customizing is a
     drag away, and "Reset to default" does the same thing by hand.

  4. RECON for the next batch - the sidebar's order persistence and the glossary page.

All or nothing: every anchor must match exactly once. If any section fails, NOTHING is
written and every failure is reported in this one run, with the on-disk region printed
so the next attempt is not another guess. Re-running is safe - each section detects its
own marker and skips.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(".")
LAYOUT_TS = ROOT / "frontend/lib/overview-layout.ts"
OVERVIEW_CLIENT = ROOT / "frontend/components/overview/overview-client.tsx"
APP_LAYOUT = ROOT / "frontend/app/(app)/layout.tsx"
CURSOR = ROOT / "frontend/components/effects/custom-cursor.tsx"
HEARTBEAT = ROOT / "frontend/lib/use-presence-heartbeat.ts"
SIDEBAR = ROOT / "frontend/components/layout/sidebar.tsx"
VERSIONS = ROOT / "backend/alembic/versions"

# Globally NEW id. A reused id makes the "already there?" glob succeed against somebody
# else's file and the migration silently never runs.
MIGRATION_ID = "c4d9e17b6a02"

failures: list[str] = []
notes: list[str] = []
pending: dict[Path, str] = {}


def fail(section: str, message: str, region: str = "") -> None:
    failures.append(
        f"[{section}] {message}" + (f"\n{indent(region)}" if region else "")
    )


def indent(text: str) -> str:
    return "\n".join(f"    | {line}" for line in text.rstrip("\n").splitlines())


def read(path: Path, section: str) -> str | None:
    if not path.exists():
        fail(section, f"missing file: {path}")
        return None
    return path.read_text()


def window(text: str, needle: str, before: int = 4, after: int = 12) -> str:
    """The on-disk region around `needle`, so a failure report shows the real text."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(lines[max(0, i - before) : i + after])
    return "(needle not found anywhere in the file)"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Presence keep-alive
# ─────────────────────────────────────────────────────────────────────────────

HEARTBEAT_SOURCE = """"use client";

import { useEffect } from "react";

import { apiFetch } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";

/** How often to tell the server we are still here. The presence key expires after 120s
 *  server-side, so this has to leave room for one lost ping. */
const HEARTBEAT_MS = 45_000;

/**
 * Keep this user's presence alive for as long as their tab is open and visible.
 *
 * Presence is refreshed by ANY authenticated request, and for a while that was enough.
 * It stops being enough the moment somebody is READING rather than clicking: the
 * dashboard caches aggressively, an idle tab issues no requests at all, the heartbeat
 * lapses, and a person sitting in front of the screen is shown to everyone else as
 * "away". This sends a deliberate ping instead of depending on incidental traffic.
 *
 * A hidden tab is deliberately NOT a heartbeat - a dashboard buried behind twelve other
 * tabs is not someone you can reach - but coming back to the window pings immediately,
 * so returning is reflected at once rather than up to 45 seconds later.
 *
 * Failures are swallowed. Presence is a nicety; it must never put an error in front of
 * a user or break the page it is mounted in.
 */
export function usePresenceHeartbeat(): void {
  const { user } = useAuth();

  useEffect(() => {
    if (!user) return;
    let cancelled = false;

    const ping = () => {
      if (cancelled || document.visibilityState !== "visible") return;
      void apiFetch<unknown>("/api/v1/auth/me").catch(() => {
        /* best effort - presence is never worth an error */
      });
    };

    ping();
    const timer = window.setInterval(ping, HEARTBEAT_MS);
    document.addEventListener("visibilitychange", ping);
    window.addEventListener("focus", ping);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", ping);
      window.removeEventListener("focus", ping);
    };
  }, [user]);
}
"""

IMPORT_LINE = 'import { usePresenceHeartbeat } from "@/lib/use-presence-heartbeat";'
IMPORT_RE = re.compile(r"^import [^\n]*;$", re.M)
APP_LAYOUT_FN_RE = re.compile(r"(export default function AppLayout\([^)]*\)\s*\{\n)")


def section_heartbeat() -> None:
    section = "presence-heartbeat"
    text = read(APP_LAYOUT, section)
    if text is None:
        return

    if HEARTBEAT.exists() and HEARTBEAT.read_text() != HEARTBEAT_SOURCE:
        notes.append(f"{section}: rewriting {HEARTBEAT} (contents differed)")
    pending[HEARTBEAT] = HEARTBEAT_SOURCE

    if "usePresenceHeartbeat" in text:
        notes.append(f"{section}: already mounted in {APP_LAYOUT} - left alone")
        return

    imports = list(IMPORT_RE.finditer(text))
    if not imports:
        fail(section, f"no import statements found in {APP_LAYOUT}", text[:400])
        return

    matches = list(APP_LAYOUT_FN_RE.finditer(text))
    if len(matches) != 1:
        fail(
            section,
            f"expected exactly one `export default function AppLayout(...)` in "
            f"{APP_LAYOUT}, found {len(matches)}",
            window(text, "export default function AppLayout"),
        )
        return

    last_import = imports[-1]
    text = text[: last_import.end()] + "\n" + IMPORT_LINE + text[last_import.end() :]

    # Re-find after the import shifted the offsets. The hook goes FIRST in the body:
    # this component early-returns while auth resolves, and a hook after a conditional
    # return is a hooks-order violation.
    match = APP_LAYOUT_FN_RE.search(text)
    assert match is not None  # the count was checked above; the import cannot remove it
    body = (
        "  // Presence is a fact about the last two minutes, and a reading user makes\n"
    )
    body += "  // no requests. Ping deliberately so they stay visibly online.\n"
    body += "  usePresenceHeartbeat();\n"
    text = text[: match.end()] + body + text[match.end() :]

    pending[APP_LAYOUT] = text
    notes.append(f"{section}: hook written, mounted in {APP_LAYOUT}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Retire the Magnetic dot cursor
# ─────────────────────────────────────────────────────────────────────────────

MAGNETIC_OPTION_RE = re.compile(
    r'\n[ \t]*\{\s*id:\s*"magnetic"\s*,\s*label:\s*"[^"]*"\s*\}\s*,'
)
MAGNETIC_PARSE_RE = re.compile(
    r'if \(raw === "smooth" \|\| raw === "magnetic"\) return raw;'
)
MAGNETIC_PARSE_NEW = (
    '// "magnetic" was retired from the picker (owner decision). Anyone who had it\n'
    "    // selected falls through to the system cursor rather than keeping a style they\n"
    "    // can no longer choose.\n"
    '    if (raw === "smooth") return raw;'
)


def section_magnetic() -> None:
    section = "magnetic-dot"
    text = read(CURSOR, section)
    if text is None:
        return

    done: list[str] = []

    # Each edit is checked for on its own. `"magnetic"` still appears in the type union
    # and in the `[data-magnetic]` selector after this runs, so "is the word present?"
    # is not a usable did-this-already test - the SPECIFIC construct is.
    option_hits = MAGNETIC_OPTION_RE.findall(text)
    if option_hits:
        if len(option_hits) != 1:
            fail(
                section,
                f"expected at most one magnetic entry in CURSOR_STYLES, found "
                f"{len(option_hits)}",
                window(text, "CURSOR_STYLES"),
            )
            return
        text = MAGNETIC_OPTION_RE.sub("", text, count=1)
        done.append("removed from the picker")
    elif '{ id: "smooth"' not in text:
        fail(
            section,
            "CURSOR_STYLES no longer looks like the expected list of options",
            window(text, "CURSOR_STYLES"),
        )
        return

    parse_hits = MAGNETIC_PARSE_RE.findall(text)
    if parse_hits:
        if len(parse_hits) != 1:
            fail(
                section,
                f"expected at most one magnetic branch in readCursorPreference, found "
                f"{len(parse_hits)}",
                window(text, "readCursorPreference"),
            )
            return
        text = MAGNETIC_PARSE_RE.sub(MAGNETIC_PARSE_NEW, text, count=1)
        done.append("de-selected for anyone who had chosen it")
    elif 'if (raw === "smooth") return raw;' not in text:
        fail(
            section,
            "readCursorPreference does not parse the stored style the way this patch "
            "expects - refusing to guess",
            window(text, "readCursorPreference"),
        )
        return

    if '{ id: "magnetic"' in text:
        fail(
            section,
            "the magnetic option survived the edit",
            window(text, "CURSOR_STYLES"),
        )
        return

    if not done:
        notes.append(f"{section}: already applied - left alone")
        return
    pending[CURSOR] = text
    notes.append(f"{section}: {', '.join(done)}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Overview widget order: Pod Owner -> HOU -> Top Apps
# ─────────────────────────────────────────────────────────────────────────────

BLOCK_RE = re.compile(r"(const LG_LAYOUT: Layout\[\] = \[)(.*?)(\n\];)", re.S)
ENTRY_RE = re.compile(
    r'\{\s*i:\s*"(?P<id>[^"]+)"\s*,\s*x:\s*(?P<x>-?\d+)\s*,\s*y:\s*(?P<y>-?\d+)\s*,'
    r"\s*w:\s*(?P<w>\d+)\s*,\s*h:\s*(?P<h>\d+)(?P<rest>[^}]*)\}"
)
IDS_BLOCK_RE = re.compile(
    r"(export const OVERVIEW_ITEM_IDS = \[)(.*?)(\n\] as const;)", re.S
)
ITEMS_DECL_RE = re.compile(r"items\s*:\s*Record<\s*OverviewItemId\s*,[^>]*>\s*=\s*")
# Object keys come in both flavours here - `"top-apps":` has to be quoted, `trend:` does
# not - and a regex that only knows the quoted form silently sees half the widgets.
ITEM_MAP_RE = re.compile(
    r'(?:"([A-Za-z0-9_-]+)"|([A-Za-z_][A-Za-z0-9_]*))\s*:\s*<([A-Za-z0-9_]+)'
)
LEAD_COMMENT_RE = re.compile(
    r"(?:^[ \t]*//[^\n]*\n)+(?=const LG_LAYOUT: Layout\[\] = \[)", re.M
)

# What each leading widget must be, and how to recognise its component. Matched against
# the id -> component map in overview-client.tsx, so a rename in either place shows up as
# an abort with the real map printed rather than as a silently wrong order.
LEADERS: list[tuple[str, re.Pattern[str]]] = [
    ("Pod Owner Performance", re.compile(r"^Pod[A-Za-z]*Table$|^PodOwner[A-Za-z]*$")),
    ("HOU Performance", re.compile(r"^[Hh][Oo][Uu][A-Za-z]*$")),
    ("Top Apps by Revenue", re.compile(r"^TopApps[A-Za-z]*$")),
]


def extract_items_block(text: str) -> str | None:
    """The body of the `items: Record<OverviewItemId, ReactNode> = { ... }` object.

    Scanned with a brace counter rather than a regex: the values are JSX and carry their
    own braces (`<Foo filters={filters} />`), so `{...}` is not a delimiter you can match
    non-greedily. String and template literals are skipped so a brace inside one cannot
    unbalance the count.
    """
    decl = ITEMS_DECL_RE.search(text)
    if decl is None:
        return None
    start = text.find("{", decl.end())
    if start == -1:
        return None

    depth = 0
    quote: str | None = None
    i = start
    while i < len(text):
        char = text[i]
        if quote is not None:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
        i += 1
    return None


def section_overview_order() -> list[str]:
    """Returns the new visual id order (empty on failure)."""
    section = "overview-order"
    layout_text = read(LAYOUT_TS, section)
    client_text = read(OVERVIEW_CLIENT, section)
    if layout_text is None or client_text is None:
        return []

    items_block = extract_items_block(client_text)
    if items_block is None:
        fail(
            section,
            f"could not locate the `items: Record<OverviewItemId, ReactNode>` object in "
            f"{OVERVIEW_CLIENT}",
            window(client_text, "OverviewItemId"),
        )
        return []

    id_to_component: dict[str, str] = {}
    for quoted, bare, component in ITEM_MAP_RE.findall(items_block):
        id_to_component[quoted or bare] = component
    if not id_to_component:
        fail(section, "the items object parsed to zero widgets", items_block)
        return []

    printable = "\n".join(f"{k:>16} -> <{v} />" for k, v in id_to_component.items())

    lead_ids: list[str] = []
    for label, pattern in LEADERS:
        hits = [i for i, comp in id_to_component.items() if pattern.match(comp)]
        if len(hits) != 1:
            fail(
                section,
                f'could not pin down the "{label}" widget: {len(hits)} components matched '
                f"{pattern.pattern!r}. The id -> component map on disk is:",
                printable,
            )
            return []
        lead_ids.append(hits[0])

    block = BLOCK_RE.search(layout_text)
    if block is None:
        fail(
            section,
            f"LG_LAYOUT block not found in {LAYOUT_TS}",
            window(layout_text, "LG_LAYOUT"),
        )
        return []

    body = block.group(2)
    entries = [m.groupdict() for m in ENTRY_RE.finditer(body)]
    declared = body.count("{ i:")
    if len(entries) != declared:
        fail(
            section,
            f"parsed {len(entries)} layout entries but the block declares {declared} - "
            "the entry shape has changed, refusing to rewrite it",
            body,
        )
        return []
    if not entries:
        fail(section, "LG_LAYOUT is empty", body)
        return []

    missing = [i for i in lead_ids if i not in {e["id"] for e in entries}]
    if missing:
        fail(
            section,
            f"widgets present in the client but absent from LG_LAYOUT: {missing}",
            body,
        )
        return []

    # Group into rows by the CURRENT y, preserving first-seen order within a row. Moving
    # whole rows (rather than individual widgets) is what keeps the three-across top row
    # three-across instead of scattering its members.
    rows: dict[int, list[dict[str, str]]] = {}
    for entry in entries:
        rows.setdefault(int(entry["y"]), []).append(entry)
    ordered_keys = sorted(rows)

    row_of = {e["id"]: int(e["y"]) for e in entries}
    new_order: list[int] = []
    for lead in lead_ids:
        key = row_of[lead]
        if key not in new_order:
            new_order.append(key)
    new_order += [k for k in ordered_keys if k not in new_order]

    lines: list[str] = []
    visual: list[str] = []
    y = 0
    for key in new_order:
        row = rows[key]
        for entry in row:
            rest = entry["rest"].rstrip()
            lines.append(
                f'  {{ i: "{entry["id"]}", x: {entry["x"]}, y: {y}, '
                f"w: {entry['w']}, h: {entry['h']}{rest} }},"
            )
            visual.append(entry["id"])
        y += max(int(e["h"]) for e in row)

    new_block = block.group(1) + "\n" + "\n".join(lines) + block.group(3)
    if visual == [e["id"] for e in entries]:
        notes.append(f"{section}: already in the requested order - left alone")
        return visual
    layout_text = layout_text[: block.start()] + new_block + layout_text[block.end() :]

    # OVERVIEW_ITEM_IDS documents itself as "in default visual order", and `stacked()`
    # builds the phone layout from LG_LAYOUT's array order - both have to follow.
    ids_block = IDS_BLOCK_RE.search(layout_text)
    if ids_block is None:
        fail(
            section,
            "OVERVIEW_ITEM_IDS block not found",
            window(layout_text, "OVERVIEW_ITEM_IDS"),
        )
        return []
    declared_ids = re.findall(r'"([^"]+)"', ids_block.group(2))
    if set(declared_ids) != set(visual):
        fail(
            section,
            "OVERVIEW_ITEM_IDS and LG_LAYOUT disagree about which widgets exist "
            f"(only in ids: {sorted(set(declared_ids) - set(visual))}, "
            f"only in layout: {sorted(set(visual) - set(declared_ids))})",
            ids_block.group(2),
        )
        return []
    rebuilt = (
        ids_block.group(1)
        + "\n"
        + "\n".join(f'  "{i}",' for i in visual)
        + ids_block.group(3)
    )
    layout_text = (
        layout_text[: ids_block.start()] + rebuilt + layout_text[ids_block.end() :]
    )

    # The comment above LG_LAYOUT describes the rows. Regenerate it - a stale map of the
    # layout is worse than none, because it is read as if it were true.
    labels = {i: id_to_component.get(i, i) for i in visual}
    described: list[str] = []
    row_no = 0
    for key in new_order:
        row_no += 1
        members = " | ".join(labels[e["id"]] for e in rows[key])
        described.append(f"//   row {row_no}: {members}")
    comment = (
        "// The default desktop arrangement for the DRAGGABLE area (everything below the\n"
        "// fixed KPI header), top to bottom. Pod Owner, HOU and Top Apps lead by owner\n"
        "// decision; the rest keep the order they had.\n"
        + "\n".join(described)
        + "\n// Heights are tuned per widget, and the runtime auto-height (per-widget minH from\n"
        "// a ResizeObserver) grows any cell whose content reflows taller, so a saved\n"
        "// arrangement never clips. Below lg the grid stacks in this same order.\n"
    )
    if LEAD_COMMENT_RE.search(layout_text):
        layout_text = LEAD_COMMENT_RE.sub(comment, layout_text, count=1)
    else:
        notes.append(f"{section}: no comment block above LG_LAYOUT to refresh")

    pending[LAYOUT_TS] = layout_text
    notes.append(f"{section}: new order -> {', '.join(visual)}")
    return visual


# ─────────────────────────────────────────────────────────────────────────────
# 3b. One-time migration: clear saved Overview layouts so the new order is seen
# ─────────────────────────────────────────────────────────────────────────────

MIGRATION_TEMPLATE = '''"""reset saved overview layouts

A saved per-user layout wins over the default arrangement (that is the whole point of
"Customize layout"), which means changing the default is invisible to anyone who has
ever dragged a widget. The owner asked for Pod Owner, then HOU, then Top Apps at the
top of the Overview, so the saved arrangements are cleared once here and everybody
picks up the new default.

Nothing is lost that cannot be redone by dragging: this only drops the stored
positions, and "Customize layout -> Reset to default" does exactly the same thing by
hand. Rows for other pages are untouched.

Revision ID: {rev}
Revises: {down}
Create Date: {created}
"""

from __future__ import annotations

from alembic import op

revision: str = "{rev}"
down_revision: str | None = "{down}"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.execute("DELETE FROM dashboard_layouts WHERE page = 'overview'")


def downgrade() -> None:
    # Deleted positions cannot be reconstructed, and re-creating them empty would be a
    # lie. Downgrading simply leaves everyone on the default arrangement.
    pass
'''


def detect_head(section: str) -> str | None:
    """Find the single revision nothing points at. Detected, never assumed."""
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        rev = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        down = re.search(
            r'^down_revision(?::[^=]+)?\s*=\s*["\']([^"\']+)["\']', text, re.M
        )
        if rev:
            revisions.add(rev.group(1))
        if down:
            parents.add(down.group(1))
    heads = revisions - parents
    if len(heads) != 1:
        fail(section, f"expected exactly one alembic head, found {sorted(heads)}")
        return None
    return heads.pop()


def section_migration() -> None:
    section = "layout-reset-migration"
    if not VERSIONS.is_dir():
        fail(section, f"missing directory: {VERSIONS}")
        return
    if list(VERSIONS.glob(f"*{MIGRATION_ID}*.py")):
        notes.append(
            f"{section}: migration {MIGRATION_ID} already present - left alone"
        )
        return
    head = detect_head(section)
    if head is None:
        return
    stamp = datetime.now(UTC)
    path = VERSIONS / f"{stamp:%Y%m%d_%H%M}_{MIGRATION_ID}_reset_overview_layouts.py"
    pending[path] = MIGRATION_TEMPLATE.format(
        rev=MIGRATION_ID, down=head, created=stamp.isoformat()
    )
    notes.append(f"{section}: {path.name} (down_revision={head})")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Recon for the next batch (read-only, never fails the run)
# ─────────────────────────────────────────────────────────────────────────────


def recon() -> None:
    print()
    print("=" * 72)
    print("RECON (read-only) - input for the next batch")
    print("=" * 72)

    print("\n--- sidebar: how the nav order is persisted -------------------------")
    if SIDEBAR.exists():
        text = SIDEBAR.read_text()
        lines = text.splitlines()
        wanted = [
            i
            for i, line in enumerate(lines)
            if "ORDER_KEY" in line or "localStorage" in line or "setOrder" in line
        ]
        shown: set[int] = set()
        for i in wanted:
            for j in range(max(0, i - 3), min(len(lines), i + 6)):
                shown.add(j)
        last = -2
        for j in sorted(shown):
            if j != last + 1:
                print("       ...")
            print(f"  {j + 1:>4}  {lines[j]}")
            last = j
        if not wanted:
            print("  (no ORDER_KEY / localStorage references found)")
    else:
        print(f"  missing: {SIDEBAR}")

    print("\n--- glossary page ---------------------------------------------------")
    hits = [
        p
        for p in ROOT.glob("frontend/**/*")
        if "glossary" in p.name.lower() and "node_modules" not in str(p) and p.is_file()
    ]
    for path in hits:
        print(f"  {path}  ({len(path.read_text().splitlines())} lines)")
    if not hits:
        print("  (no glossary file found)")

    print("\n--- mutations with no cache invalidation ----------------------------")
    print(
        "  (a useMutation without invalidateQueries is a 'only updates when I refresh')"
    )
    for path in sorted(ROOT.glob("frontend/lib/*.ts")) + sorted(
        ROOT.glob("frontend/lib/*.tsx")
    ):
        text = path.read_text()
        for match in re.finditer(r"export function (use[A-Za-z0-9_]+)\(", text):
            start = match.start()
            end = text.find("\nexport function ", start + 1)
            body = text[start : end if end != -1 else len(text)]
            if "useMutation" in body and "invalidateQueries" not in body:
                print(f"  {path}:{text[:start].count(chr(10)) + 1}  {match.group(1)}")


# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    if not LAYOUT_TS.parent.exists():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    section_heartbeat()
    section_magnetic()
    order = section_overview_order()
    if order:
        section_migration()

    if failures:
        print("ABORTED - nothing was written.\n", file=sys.stderr)
        for item in failures:
            print(item + "\n", file=sys.stderr)
        if notes:
            print("Sections that WOULD have applied:", file=sys.stderr)
            for note in notes:
                print(f"  - {note}", file=sys.stderr)
        return 1

    for path, text in pending.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    print(
        "PATCHED, NOT YET VERIFIED - the test run is the verification, not this script."
    )
    for note in notes:
        print(f"  - {note}")
    if not pending:
        print("  (nothing to write - every section was already applied)")

    recon()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
