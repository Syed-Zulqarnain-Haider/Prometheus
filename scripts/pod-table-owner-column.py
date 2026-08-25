#!/usr/bin/env python3
"""Show the pod OWNER next to the pod on the Pod Performance table.

The table shipped grouping by pod, and pod ids are bare numbers - the live table reads
"1, 3, 2, 5, 4, -1". That tells an executive nothing about who owns the number, which is
the entire reason to look at a pod table.

The owner name is not fetched with a new hand-written query. QueryBuilder already has
``distinct_values(params, column, self_key, label=...)``, whose whole job is pairing a
dimension with a label column under the caller's row scope and date window - it is what
makes the filter dropdowns show a name against an id. Reusing it means the pairing here
cannot drift from the pairing the filters use, and no new SQL enters the codebase.

One consequence worth knowing: distinct_values deliberately clears the dimension's OWN
filter (so a dropdown never filters itself out of existence), which means the lookup map
can contain pods outside the current pod filter. That is harmless - it is only ever read
by key for pods the breakdown actually returned - and it stays inside the caller's row
scope either way.

NOT CHANGED, deliberately: the pod value "-1". It looks like a sentinel for unassigned,
but I have not confirmed that, and silently relabelling a value that might mean something
real is how a dashboard starts lying. It is raised for the owner instead.

    python3 scripts/pod-table-owner-column.py
"""

from __future__ import annotations

import sys
from pathlib import Path

EDITS = [
    {
        "path": "backend/app/services/admin_service.py",
        "anchor": '''    result = (
        (await db.execute(qb.breakdown(params, "pod", metrics, limit=_POD_LIMIT)))
        .mappings()
        .all()
    )

    merged: dict[str, dict[str, Any]] = {}
    for row in result:
        raw = row["pod"]
        key = UNASSIGNED if raw is None or str(raw).strip() == "" else str(raw)
        bucket = merged.setdefault(key, {"pod": key, **dict.fromkeys(metrics, 0.0)})''',
        "replacement": '''    result = (
        (await db.execute(qb.breakdown(params, "pod", metrics, limit=_POD_LIMIT)))
        .mappings()
        .all()
    )

    # Pod ids are bare numbers, so a table of "1, 3, -1" says nothing about who owns the
    # number. distinct_values already knows how to pair a dimension with a label column
    # under this caller's row scope - it is what puts names against ids in the filter
    # dropdowns - so the mapping comes from there rather than a second hand-written query,
    # and the two can never disagree. It clears the pod filter by design, so this map may
    # cover more pods than the breakdown returned; it is only ever read by key.
    owners = {
        str(row["value"]): row["label"]
        for row in (
            await db.execute(qb.distinct_values(params, "pod", "pod", label="pod_owner"))
        )
        .mappings()
        .all()
        if row["value"] is not None
    }

    merged: dict[str, dict[str, Any]] = {}
    for row in result:
        raw = row["pod"]
        key = UNASSIGNED if raw is None or str(raw).strip() == "" else str(raw)
        bucket = merged.setdefault(
            key, {"pod": key, "pod_owner": owners.get(key), **dict.fromkeys(metrics, 0.0)}
        )''',
        "marker": "owners = {",
    },
    {
        "path": "frontend/components/overview/pod-table.tsx",
        "anchor": '''/** Pod Performance - the HOU table grouped by pod. ADMIN ONLY.''',
        "replacement": '''/** Who owns the pod. Comes back on the row beside the metrics; blank when the pod has no
 *  owner recorded, which is a real state and is shown as such rather than as a guess. */
const OWNER_COLUMN: ColumnDef = {
  id: "pod_owner",
  label: "Pod Owner",
  requires: [],
  align: "left",
  fmt: "text",
  value: (row) => {
    const value = row.pod_owner;
    return value == null || String(value).trim() === "" ? UNASSIGNED : String(value);
  },
  render: (row) => {
    const value = row.pod_owner;
    const name = value == null || String(value).trim() === "" ? "" : String(value);
    return name ? (
      <span>{name}</span>
    ) : (
      <span className="text-muted-foreground">{UNASSIGNED}</span>
    );
  },
};

/** Pod Performance - the HOU table grouped by pod. ADMIN ONLY.''',
        "marker": "const OWNER_COLUMN: ColumnDef",
    },
    {
        "path": "frontend/components/overview/pod-table.tsx",
        "anchor": '''      [POD_IDENTITY, ...METRIC_COLUMNS].filter((c) =>
        c.requires.every((m) => permitted.has(m)),
      ),''',
        "replacement": '''      [POD_IDENTITY, OWNER_COLUMN, ...METRIC_COLUMNS].filter((c) =>
        c.requires.every((m) => permitted.has(m)),
      ),''',
        "marker": "[POD_IDENTITY, OWNER_COLUMN,",
    },
    {
        "path": "frontend/components/overview/pod-table.tsx",
        "anchor": '''  const rankOptions = columns.filter((c) => c.id !== POD_IDENTITY.id);''',
        "replacement": '''  // Both identity columns are excluded: ranking pods alphabetically by their owner's name
  // is not a ranking anyone wants, and neither column carries a measure to sort on.
  const rankOptions = columns.filter(
    (c) => c.id !== POD_IDENTITY.id && c.id !== OWNER_COLUMN.id,
  );''',
        "marker": "c.id !== OWNER_COLUMN.id",
    },
]


def resolve(text, anchor, replacement, marker):
    if anchor in text:
        return anchor, replacement, marker
    flat = anchor.replace("—", "-")
    if flat != anchor and flat in text:
        return flat, replacement.replace("—", "-"), marker.replace("—", "-")
    return anchor, replacement, marker


def locate(lines, anchor):
    wanted = anchor.splitlines()
    joined = "\n".join(lines)
    for take in range(len(wanted), 0, -1):
        for start in (0, len(wanted) - take):
            probe = "\n".join(wanted[start : start + take])
            if not probe.strip():
                continue
            index = joined.find(probe)
            if index != -1:
                return joined.count("\n", 0, index) - start
    return None


def main() -> int:
    if not Path("backend/app").is_dir():
        print("ABORTED: run this from the repository root")
        return 1
    if not Path("frontend/components/overview/pod-table.tsx").exists():
        print("ABORTED: pod-table.tsx is not present - run scripts/pod-table-widget.py first")
        return 1

    planned: dict[str, str] = {}
    problems: list[str] = []
    failures: list[tuple[str, str]] = []
    skipped: list[str] = []
    for index, edit in enumerate(EDITS, start=1):
        rel = edit["path"]
        path = Path(rel)
        if not path.exists():
            problems.append(f"  [{index}] {rel}: file not found")
            continue
        text = planned.get(rel, path.read_text())
        anchor, replacement, marker = resolve(
            text, edit["anchor"], edit["replacement"], edit["marker"]
        )
        if marker in text:
            skipped.append(f"{rel} [{index}]: already applied")
            continue
        found = text.count(anchor)
        if found != 1:
            problems.append(
                f"  [{index}] {rel}: expected exactly 1 match, found {found}\n"
                f"        anchor starts: {anchor.splitlines()[0][:76]!r}"
            )
            failures.append((rel, anchor))
            continue
        planned[rel] = text.replace(anchor, replacement, 1)

    if problems:
        print("ABORTED - NOTHING was written:")
        print()
        for problem in problems:
            print(problem)
        for rel, anchor in failures:
            lines = Path(rel).read_text().splitlines()
            hit = locate(lines, anchor)
            lo, hi = (0, min(len(lines), 80)) if hit is None else (max(0, hit - 25), min(len(lines), hit + 25))
            print()
            print(f"----- {rel} lines {lo + 1}-{hi} of {len(lines)} -----")
            for n, line in enumerate(lines[lo:hi], start=lo + 1):
                print(f"{n:6d}\t{line}")
        return 1

    if not planned:
        print("nothing to do - already applied")
        return 0

    # The point of this change is that the owner reaches the table. Verify BOTH halves in
    # the output: the column exists on the frontend AND the backend actually puts the field
    # on the row. A column bound to a field nobody sends renders an empty stripe.
    service = planned.get(
        "backend/app/services/admin_service.py",
        Path("backend/app/services/admin_service.py").read_text(),
    )
    table = planned.get(
        "frontend/components/overview/pod-table.tsx",
        Path("frontend/components/overview/pod-table.tsx").read_text(),
    )
    checks = [
        ('"pod_owner": owners.get(key)' in service, "the row never carries pod_owner"),
        ('label="pod_owner"' in service, "the owner lookup was never issued"),
        ("OWNER_COLUMN" in table, "the Pod Owner column was not created"),
        ("[POD_IDENTITY, OWNER_COLUMN," in table, "the column is defined but never shown"),
    ]
    broken = [message for ok, message in checks if not ok]
    if broken:
        print("ABORTED - NOTHING was written:")
        for message in broken:
            print(f"  {message}")
        return 1

    for rel, content in sorted(planned.items()):
        Path(rel).write_text(content)
        print(f"wrote {rel}")
    for note in skipped:
        print(f"skip  {note}")
    print()
    print("Rebuild backend + frontend, then run the backend suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
