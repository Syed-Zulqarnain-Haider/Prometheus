#!/usr/bin/env python3
"""The Executive Overview opens in the order the owner asked for.

  1. the KPI strip
  2. Yearly Progress | Monthly Revenue Trend | Monthly Progress
  3. Pod Owner Performance
  4. everything else, in the order it is in now

WHY THE LAST CHANGE DID NOT SHOW UP
-----------------------------------
Moving the strip under the target cards changed the DEFAULT arrangement, and a saved
per-user arrangement beats the default - by design, so a release cannot undo work
somebody did by hand. Anyone who had ever opened the layout editor therefore saw no
change at all, which is exactly what happened.

So this does both halves. The default is rebuilt here, and a migration clears the SAVED
overview arrangements so the new default is what actually renders. That is a real cost,
stated plainly: anyone who had dragged their Overview into a shape of their own loses
that shape and has to drag it again. It is deliberate - the owner asked for a specific
arrangement to be THE arrangement, and a default nobody sees is not one.

Only the ``overview`` page is cleared. Saved arrangements for any other page are
untouched, and nothing else in dashboard_layouts is read or written.

HOW THE WIDGETS ARE IDENTIFIED
------------------------------
By the COMPONENT each grid slot renders, read out of overview-client.tsx - not by an id
spelled out here. The deployed widget set is not the one in this repository, and a
hardcoded "pod-owner" that turned out to be "pod_owner" would silently reorder nothing.
Rows move as rows, so a widget that shares its row with another keeps its neighbour.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(".")
LAYOUT = ROOT / "frontend/lib/overview-layout.ts"
CLIENT = ROOT / "frontend/components/overview/overview-client.tsx"
VERSIONS = ROOT / "backend/alembic/versions"
MIGRATION_ID = "f3b7c05a9e21"

report: list[str] = []
skipped: list[str] = []

ENTRY_RE = re.compile(
    r"\{\s*i:\s*\"(?P<id>[^\"]+)\"\s*,\s*x:\s*(?P<x>\d+)\s*,\s*y:\s*(?P<y>\d+)\s*,"
    r"\s*w:\s*(?P<w>\d+)\s*,\s*h:\s*(?P<h>\d+)(?P<rest>[^}]*)\}"
)
ITEM_RE = re.compile(
    r"^\s*(?:\"(?P<quoted>[^\"]+)\"|(?P<bare>[A-Za-z_$][\w$]*))\s*:\s*"
    r"<(?P<component>[A-Za-z_$][\w$]*)",
    re.M,
)


def window(text: str, needle: str, before: int = 2, after: int = 20) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(f"      | {ln}" for ln in lines[max(0, i - before) : i + after])
    return "      | (not found in this file)"


def braced_span(text: str, head: re.Match[str] | None, opener: str, closer: str) -> tuple[int, int] | None:
    """Range BETWEEN the delimiters of the literal that follows ``head``."""
    if head is None:
        return None
    open_at = text.find(opener, head.end() - 1)
    if open_at == -1:
        return None
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return open_at + 1, i
    return None


def array_span(text: str, header: re.Pattern[str]) -> tuple[int, int] | None:
    return braced_span(text, header.search(text), "[", "]")


def widget_ids_by_component() -> dict[str, str]:
    """{ComponentName: gridId}, read from the page's own items map."""
    if not CLIENT.exists():
        return {}
    text = CLIENT.read_text()
    head = re.search(r"const items\s*:\s*Record<OverviewItemId,\s*ReactNode>\s*=\s*", text)
    span = braced_span(text, head, "{", "}")
    if span is None:
        return {}
    out: dict[str, str] = {}
    for match in ITEM_RE.finditer(text[span[0] : span[1]]):
        out[match.group("component")] = match.group("quoted") or match.group("bare")
    return out


def pick(components: dict[str, str], pattern: str) -> str | None:
    matches = [gid for comp, gid in components.items() if re.search(pattern, comp)]
    return matches[0] if len(matches) == 1 else None


def section_order() -> bool:
    label = "order"
    if not LAYOUT.exists() or not CLIENT.exists():
        skipped.append(f"[{label}] {LAYOUT} or {CLIENT} is missing - nothing changed.")
        return False

    components = widget_ids_by_component()
    if not components:
        skipped.append(
            f"[{label}] could not read the widget map out of {CLIENT}, so which grid slot\n"
            "  is which component is unknown. Nothing changed."
        )
        return False

    kpis = pick(components, r"^KpiRow$")
    trend = pick(components, r"MonthlyTrend")
    pod_owner = pick(components, r"PodOwner")
    missing = [
        name
        for name, value in (
            ("the KPI strip", kpis),
            ("the trend chart", trend),
            ("Pod Owner Performance", pod_owner),
        )
        if value is None
    ]
    if missing:
        skipped.append(
            f"[{label}] could not identify {', '.join(missing)} in {CLIENT} - reordering\n"
            "  around a widget that might be the wrong one is worse than not reordering.\n"
            "  What the page renders:\n"
            + "\n".join(f"      | {comp} -> {gid}" for comp, gid in sorted(components.items()))
        )
        return False

    text = LAYOUT.read_text()
    span = array_span(text, re.compile(r"const LG_LAYOUT\s*:\s*Layout\[\]\s*="))
    if span is None:
        skipped.append(f"[{label}] no LG_LAYOUT array in {LAYOUT}. Nothing changed.")
        return False

    entries = list(ENTRY_RE.finditer(text[span[0] : span[1]]))
    if not entries:
        skipped.append(
            f"[{label}] LG_LAYOUT holds no recognisable entries. Nothing changed.\n"
            + window(text, "LG_LAYOUT")
        )
        return False

    # Rows, in the order they appear. A widget sharing a row keeps its neighbour.
    rows: list[list[re.Match[str]]] = []
    by_y: dict[int, list[re.Match[str]]] = {}
    for entry in entries:
        y = int(entry.group("y"))
        if y not in by_y:
            by_y[y] = []
            rows.append(by_y[y])
        by_y[y].append(entry)

    def row_of(widget: str) -> list[re.Match[str]] | None:
        return next((r for r in rows if any(e.group("id") == widget for e in r)), None)

    wanted = [(kpis, row_of(kpis)), (trend, row_of(trend)), (pod_owner, row_of(pod_owner))]
    absent = [name for name, row in wanted if row is None]
    if absent:
        skipped.append(
            f"[{label}] {LAYOUT} has no row for {', '.join(absent)}. Nothing changed.\n"
            + window(text, "LG_LAYOUT")
        )
        return False

    lead: list[list[re.Match[str]]] = []
    for _, row in wanted:
        if row is not None and row not in lead:  # a shared row is placed once
            lead.append(row)
    ordered = lead + [r for r in rows if r not in lead]

    if ordered == rows:
        report.append(f"[{label}] the default is already in this order - left alone")
        return True

    lines: list[str] = []
    y = 0
    for row in ordered:
        for entry in row:
            lines.append(
                f'  {{ i: "{entry.group("id")}", x: {entry.group("x")}, y: {y}, '
                f'w: {entry.group("w")}, h: {entry.group("h")}{entry.group("rest").rstrip()} }},'
            )
        y += max(int(e.group("h")) for e in row)

    text = text[: span[0]] + "\n" + "\n".join(lines) + "\n" + text[span[1] :]

    # The id list is the MOBILE order (stacked() reads it), so it follows the same shape.
    ids_span = array_span(text, re.compile(r"export const OVERVIEW_ITEM_IDS\s*="))
    if ids_span is None:
        skipped.append(
            f"[{label}] LG_LAYOUT was reordered but OVERVIEW_ITEM_IDS could not be found,\n"
            "  so desktop and mobile would disagree. Nothing was written."
        )
        return False
    ordered_ids = [e.group("id") for row in ordered for e in row]
    listed = re.findall(r'"([^"]+)"', text[ids_span[0] : ids_span[1]])
    # An id with no layout entry keeps its place at the end rather than being dropped:
    # silently losing a widget here would be a far bigger change than a reorder.
    tail = [i for i in listed if i not in ordered_ids]
    text = (
        text[: ids_span[0]]
        + "\n"
        + "".join(f'  "{i}",\n' for i in ordered_ids + tail)
        + text[ids_span[1] :]
    )

    LAYOUT.write_text(text)
    report.append(
        f"[{label}] {LAYOUT}: default order is now {kpis} -> the target row -> "
        f"{pod_owner} -> the rest, on desktop and stacked alike"
    )
    return True


MIGRATION = '''"""reset saved Executive Overview arrangements

The default arrangement changed (KPI strip, then the progress-to-target row, then Pod
Owner Performance). A saved per-user arrangement beats the default - by design, so a
release cannot undo work somebody did by hand - which means the new default would never
render for anyone who had ever opened the layout editor.

So the saved OVERVIEW arrangements are cleared and everyone starts from the new default.
The cost is stated rather than hidden: anyone who had dragged their Overview into a shape
of their own loses it and drags it again. Only ``page = 'overview'`` is affected.

Revision ID: {rev}
Revises: {down}
Create Date: {created}
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "{rev}"
down_revision: str | tuple[str, ...] | None = "{down}"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Parameterised, and scoped to one page by an exact match on a literal - nothing here
# comes from user input, and nothing outside the Overview is reachable from it.
_RESET = sa.text("DELETE FROM dashboard_layouts WHERE page = :page")


def upgrade() -> None:
    op.get_bind().execute(_RESET, {{"page": "overview"}})


def downgrade() -> None:
    """Nothing to restore. The rows are gone, and inventing arrangements to put back
    would be worse than leaving people on the default they are already looking at."""
'''


def detect_heads() -> list[str]:
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        rev = re.search(r'^revision(?::\s*[^=\n]+)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        if rev:
            revisions.add(rev.group(1))
        down = re.search(r"^down_revision(?::[^=\n]+)?\s*=\s*(.+)$", text, re.M)
        if down:
            parents.update(re.findall(r'["\']([^"\']+)["\']', down.group(1)))
    return sorted(revisions - parents)


def section_migration() -> None:
    label = "reset saved layouts"
    if not VERSIONS.is_dir():
        skipped.append(f"[{label}] {VERSIONS} is missing - saved arrangements still win.")
        return
    if list(VERSIONS.glob(f"*{MIGRATION_ID}*.py")):
        report.append(f"[{label}] {MIGRATION_ID} already present - left alone")
        return

    heads = detect_heads()
    if len(heads) != 1:
        skipped.append(
            f"[{label}] expected exactly one alembic head, found {heads or 'none'} - a\n"
            "  revision on top of a forked history would fork it again. Nothing written."
        )
        return

    stamp = datetime.now(UTC)
    path = VERSIONS / f"{stamp:%Y%m%d_%H%M}_{MIGRATION_ID}_reset_overview_layouts.py"
    path.write_text(MIGRATION.format(rev=MIGRATION_ID, down=heads[0], created=stamp.isoformat()))
    report.append(
        f"[{label}] {path.name}: clears saved OVERVIEW arrangements so the new default "
        f"is what renders (down_revision={heads[0]})"
    )


def main() -> int:
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    # No point clearing anyone's arrangement if the default they fall back to has not
    # actually changed.
    if section_order():
        section_migration()
    else:
        skipped.append(
            "[reset saved layouts] not written: the default order was not changed, so\n"
            "  clearing saved arrangements would cost people their layouts for nothing."
        )

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    if skipped:
        print("\nSKIPPED (nothing written for these):")
        for entry in skipped:
            print(f"\n  {entry}")
    print(
        "\nEveryone's Overview goes back to the default arrangement on the next load.\n"
        "'Customize layout' still works exactly as before for anyone who wants their own."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
