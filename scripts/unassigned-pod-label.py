#!/usr/bin/env python3
"""Label pod -1 as Unassigned instead of showing a raw sentinel.

The owner confirmed what -1 means: apps nobody has been assigned yet, plus new apps that
have just appeared in the feed. It is a real bucket carrying real revenue - the live table
shows it with $270 gross and a negative net - so it is LABELLED, never hidden. Dropping it
would make real money vanish from a split that is supposed to reconcile with the totals.

The rule lives in one exported place rather than inline in the table, because pod values
are rendered in more than one spot (the pod donut, Explore, the filter dropdowns) and a
sentinel decoded differently in two of them is worse than one decoded nowhere: the numbers
stop agreeing and nothing says why. This patch applies it to the Pod Performance table;
the remaining sites are listed for the owner rather than changed blind.

Note what is NOT assumed here: that -1 is the only such value, or that it is numeric in
every column. The check is written against the string form of the cell, so a pod arriving
as -1 or "-1" both resolve, and anything else is left exactly as it came.

    python3 scripts/unassigned-pod-label.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ATTRIBUTION_TS = '''/** How unassigned attribution is spelled in the source data.
 *
 * Pods arrive from BigQuery as numbers, and -1 is the bucket for "nobody owns this yet":
 * apps that have never been assigned, and new apps that have appeared in the feed since
 * the last triage. It is not missing data - it carries real installs and real revenue -
 * so everything here LABELS it rather than filtering it out. A split that silently drops
 * a bucket stops reconciling with the totals above it, and nothing announces that.
 *
 * This is deliberately the only place the sentinel is spelled out. It is rendered in the
 * pod table, the pod donut, Explore and the filter dropdowns; a sentinel decoded in three
 * of those and missed in the fourth produces two different answers to the same question.
 */

/** The raw value the feed uses for "unassigned". */
export const UNASSIGNED_POD = "-1";

/** What a person should see instead. */
export const UNASSIGNED_LABEL = "Unassigned";

/** True for a pod that nobody owns: the -1 sentinel, or an absent/blank value.
 *
 * Compared as a string so a pod arriving as the number -1 and as "-1" both resolve, which
 * they do depending on whether the value came through JSON as numeric or text. */
export function isUnassignedPod(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  const text = String(value).trim();
  return text === "" || text === UNASSIGNED_POD;
}

/** The pod as it should be displayed. Anything that is not the sentinel is returned
 *  untouched - inventing a friendlier name for a real pod is not this function's job. */
export function podLabel(value: unknown): string {
  return isUnassignedPod(value) ? UNASSIGNED_LABEL : String(value).trim();
}
'''

ATTRIBUTION_TEST = '''/**
 * The unassigned-pod sentinel.
 *
 * -1 means "nobody owns this yet" - unassigned apps plus new arrivals in the feed. The
 * tests that matter here are the ones that stop it being treated as missing data: it
 * carries real revenue, so it must survive as a labelled bucket rather than being
 * filtered away, and a real pod must never be relabelled by accident.
 */
import { describe, expect, it } from "vitest";

import {
  UNASSIGNED_LABEL,
  UNASSIGNED_POD,
  isUnassignedPod,
  podLabel,
} from "@/lib/attribution";

describe("isUnassignedPod", () => {
  it("recognises the sentinel as a number and as a string", () => {
    // Which one arrives depends on whether the column came back numeric or text; a check
    // that only handles one of them works until the day the serialization changes.
    expect(isUnassignedPod(-1)).toBe(true);
    expect(isUnassignedPod("-1")).toBe(true);
    expect(isUnassignedPod(" -1 ")).toBe(true);
  });

  it("treats absent and blank as unassigned too", () => {
    expect(isUnassignedPod(null)).toBe(true);
    expect(isUnassignedPod(undefined)).toBe(true);
    expect(isUnassignedPod("")).toBe(true);
  });

  it("does not swallow a real pod", () => {
    // Pod 1 is a real pod with real revenue. The failure this guards against is a loose
    // check - a falsy test, or a bare `< 0` on a parsed number - quietly eating it.
    for (const pod of [1, 2, 3, "5", 0, "10", "-10"]) {
      expect(isUnassignedPod(pod), `${JSON.stringify(pod)} was treated as unassigned`).toBe(
        false,
      );
    }
  });
});

describe("podLabel", () => {
  it("names the unassigned bucket", () => {
    expect(podLabel(-1)).toBe(UNASSIGNED_LABEL);
    expect(podLabel(null)).toBe(UNASSIGNED_LABEL);
  });

  it("leaves a real pod exactly as it came", () => {
    expect(podLabel(3)).toBe("3");
    expect(podLabel("north")).toBe("north");
  });

  it("keeps the sentinel and the label in step", () => {
    // If someone changes UNASSIGNED_POD without changing the check, this is what fails.
    expect(podLabel(UNASSIGNED_POD)).toBe(UNASSIGNED_LABEL);
  });
});
'''

EDITS = [
    {
        "path": "frontend/components/overview/pod-table.tsx",
        "anchor": '''import { usePodPerformance, useMe } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";

const UNASSIGNED = "Unassigned";

/** A NULL or blank pod maps to a single "Unassigned" bucket, never dropped, so pod totals
 *  reconcile with the rest of the dashboard. */
function podKey(row: Row): string {
  const value = row.pod;
  return value == null || String(value).trim() === "" ? UNASSIGNED : String(value);
}''',
        "replacement": '''import { usePodPerformance, useMe } from "@/lib/api-hooks";
import { UNASSIGNED_LABEL, isUnassignedPod, podLabel } from "@/lib/attribution";
import type { Filters } from "@/lib/filters";

const UNASSIGNED = UNASSIGNED_LABEL;

/** The pod, with -1 resolved to its meaning. -1 is the bucket for apps nobody owns yet and
 *  for new apps just arrived in the feed - it carries real revenue, so it is named rather
 *  than dropped, and pod totals still reconcile with the rest of the dashboard. */
function podKey(row: Row): string {
  return podLabel(row.pod);
}''',
        "marker": 'from "@/lib/attribution"',
    },
    {
        "path": "frontend/components/overview/pod-table.tsx",
        "anchor": '''  render: (row) => {
    const key = podKey(row);
    return key === UNASSIGNED ? (
      <span className="text-muted-foreground">{UNASSIGNED}</span>
    ) : (
      <span className="font-medium">{key}</span>
    );
  },
};''',
        "replacement": '''  render: (row) => {
    const key = podKey(row);
    // Muted, not hidden: an admin should see at a glance that this row is work waiting to
    // be done - unassigned apps and new arrivals - without it competing with real pods.
    return isUnassignedPod(row.pod) ? (
      <span className="text-muted-foreground" title="Apps not assigned to anyone yet, and new apps from the feed">
        {UNASSIGNED}
      </span>
    ) : (
      <span className="font-medium">{key}</span>
    );
  },
};''',
        "marker": "title=\"Apps not assigned to anyone yet",
    },
]

NEW_FILES = {
    "frontend/lib/attribution.ts": ATTRIBUTION_TS,
    "frontend/tests/attribution.test.ts": ATTRIBUTION_TEST,
}


def resolve(text, anchor, replacement, marker):
    if anchor in text:
        return anchor, replacement, marker
    flat = anchor.replace("—", "-")
    if flat != anchor and flat in text:
        return flat, replacement.replace("—", "-"), marker.replace("—", "-")
    return anchor, replacement, marker


def main() -> int:
    if not Path("frontend/lib").is_dir():
        print("ABORTED: run this from the repository root")
        return 1
    target = Path("frontend/components/overview/pod-table.tsx")
    if not target.exists():
        print("ABORTED: pod-table.tsx is not present - run scripts/pod-table-widget.py first")
        return 1

    planned: dict[str, str] = {}
    skipped: list[str] = []
    problems: list[str] = []

    for rel, content in NEW_FILES.items():
        path = Path(rel)
        if path.exists() and path.read_text() == content:
            skipped.append(f"{rel}: already present")
            continue
        planned[rel] = content

    for index, edit in enumerate(EDITS, start=1):
        rel = edit["path"]
        path = Path(rel)
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
            continue
        planned[rel] = text.replace(anchor, replacement, 1)

    if problems:
        print("ABORTED - NOTHING was written:")
        print()
        for problem in problems:
            print(problem)
        print()
        lines = target.read_text().splitlines()
        print(f"----- {target} lines 1-60 of {len(lines)} -----")
        for n, line in enumerate(lines[:60], start=1):
            print(f"{n:6d}\t{line}")
        return 1

    if not planned:
        print("nothing to do - already applied")
        return 0

    table = planned.get(str(target), target.read_text())
    if "podLabel(row.pod)" not in table:
        print("ABORTED - NOTHING was written: the table still decodes the pod itself,")
        print("so the shared rule and the table can disagree.")
        return 1

    for rel, content in sorted(planned.items()):
        Path(rel).parent.mkdir(parents=True, exist_ok=True)
        Path(rel).write_text(content)
        print(f"wrote {rel}")
    for note in skipped:
        print(f"skip  {note}")
    print()
    print("STILL SHOWING A RAW -1, and not changed here - each needs its own look:")
    print("  * the Pod donut (components/overview/splits.tsx)")
    print("  * Explore, when the dimension is Pod")
    print("  * the Pod filter dropdown (options come from the fact table)")
    print()
    print("Rebuild the frontend, then run the frontend suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
