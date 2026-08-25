#!/usr/bin/env python3
"""Frontend batch 3: Explore reads Unassigned, and a shared rule for dimension labels.

Explore prints its dimension column straight from the row, so choosing Pod as the
dimension shows a bare -1 among the pod numbers. Rather than a fourth hand-rolled
`groupBy === "pod" ? ... : ...`, the rule moves into one helper - the fourth copy of a
conditional is the one that eventually disagrees with the other three.

Explore's table is not click-to-drill, so unlike the donut and the drill-down there is
no raw value to preserve here; the helper is display-only and says so.

Nothing is written unless every anchor resolves exactly once. Re-running is a no-op.
Revert: git checkout -- frontend/
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"

ATTRIBUTION = FE / "lib" / "attribution.ts"
EXPLORE = FE / "components" / "explore" / "explore-client.tsx"
TEST = FE / "tests" / "dimension-label.test.ts"

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
    note(f"{path.relative_to(ROOT)}: {what}")
    return source.replace(old, new, 1)


def add_import(source: str, statement: str) -> str:
    if statement in source:
        return source
    ends = [m.end() for m in re.finditer(r'^(?:import [^\n]*?;|\} from "[^"]+";)$', source, re.M)]
    if not ends:
        fail("no import block to extend")
        return source
    cut = max(ends)
    return source[:cut] + "\n" + statement + source[cut:]


# ── the shared rule ──────────────────────────────────────────────────────────
HELPER = '''

/** A dimension value as it should READ on screen.
 *
 *  Pod is the only dimension with a coded value: -1 is the bucket for apps nobody owns
 *  yet and apps that have just arrived in the feed. Everything else is shown as it comes.
 *
 *  DISPLAY ONLY. Never filter, group or drill with the result - the raw value is what the
 *  API groups by, and "Unassigned" is not a pod. Where a control is clickable, keep a map
 *  from the label back to the raw value (see the revenue donut and drill-down).
 */
export function dimensionLabel(dimension: string, value: unknown, fallback = "-"): string {
  if (dimension === "pod") return podLabel(value);
  if (value === null || value === undefined) return fallback;
  const text = String(value).trim();
  return text === "" ? fallback : text;
}
'''


def patch_attribution() -> None:
    source = ATTRIBUTION.read_text(encoding="utf-8") if ATTRIBUTION.exists() else None
    if source is None:
        fail(f"missing: {ATTRIBUTION.relative_to(ROOT)}")
        return
    if "dimensionLabel" in source:
        note("attribution.ts already exports dimensionLabel - left as is.")
        return
    # The new helper calls podLabel, and the new test imports all three. Check them here
    # rather than discovering it as a type error after the patch has already been written.
    required = ("podLabel", "UNASSIGNED_POD", "UNASSIGNED_LABEL")
    absent = [
        name
        for name in required
        if not re.search(rf"^export (?:function|const) {name}\b", source, re.M)
    ]
    if absent:
        # Built outside the f-string: 3.11 forbids a backslash inside one.
        pattern = "^export (?:function|const) " + r"(\w+)"
        found = re.findall(pattern, source, re.M)
        fail(f"attribution.ts does not export {absent} - the helper and its test "
             f"would not compile. Exports found: {found}")
        return
    writes[ATTRIBUTION] = source.rstrip("\n") + "\n" + HELPER
    note("attribution.ts: added dimensionLabel")


# ── Explore ──────────────────────────────────────────────────────────────────
OLD_CELL = '''                    <td className="whitespace-nowrap px-3 py-2 font-medium">
                      {String(
                        (dimension === "app" ? (row.app_name ?? row.app) : row[dimension]) ?? "-",
                      )}
                    </td>'''

NEW_CELL = '''                    <td className="whitespace-nowrap px-3 py-2 font-medium">
                      {dimensionLabel(
                        dimension,
                        dimension === "app" ? (row.app_name ?? row.app) : row[dimension],
                      )}
                    </td>'''


def patch_explore() -> None:
    source = EXPLORE.read_text(encoding="utf-8") if EXPLORE.exists() else None
    if source is None:
        fail(f"missing: {EXPLORE.relative_to(ROOT)}")
        return
    if "dimensionLabel" in source:
        note("explore-client.tsx already labels the unassigned pod - left as is.")
        return
    out = swap(EXPLORE, source, OLD_CELL, NEW_CELL, "dimension column reads Unassigned")
    if out is None:
        return
    writes[EXPLORE] = add_import(out, 'import { dimensionLabel } from "@/lib/attribution";')


TEST_SOURCE = '''/**
 * dimensionLabel: what a dimension value should READ as.
 *
 * The trap this guards is not the label itself - it is using the label to filter with.
 * Pod -1 has to read as "Unassigned" and still drill in as "-1"; a caller that passes the
 * label back to the API selects a pod that does not exist and gets an empty chart that
 * looks like missing data rather than a bug.
 */
import { describe, expect, it } from "vitest";

import { UNASSIGNED_LABEL, UNASSIGNED_POD, dimensionLabel, podLabel } from "@/lib/attribution";

describe("dimensionLabel", () => {
  it("names the unassigned pod", () => {
    expect(dimensionLabel("pod", UNASSIGNED_POD)).toBe(UNASSIGNED_LABEL);
    expect(dimensionLabel("pod", -1)).toBe(UNASSIGNED_LABEL);
  });

  it("leaves a real pod alone", () => {
    expect(dimensionLabel("pod", 3)).toBe("3");
    expect(dimensionLabel("pod", "3")).toBe("3");
  });

  it("treats an absent pod as unassigned, not as blank", () => {
    // A fact row with no pod IS unassigned - showing a dash would hide revenue that
    // belongs to nobody, which is the thing this bucket exists to make visible.
    expect(dimensionLabel("pod", null)).toBe(UNASSIGNED_LABEL);
    expect(dimensionLabel("pod", "")).toBe(UNASSIGNED_LABEL);
  });

  it("does not invent an Unassigned bucket for other dimensions", () => {
    // -1 is only meaningful for pod. A publisher literally named "-1" would be a data
    // problem, and relabelling it would hide that.
    expect(dimensionLabel("publisher", "-1")).toBe("-1");
    expect(dimensionLabel("hou", "-1")).toBe("-1");
  });

  it("falls back for an absent value on other dimensions", () => {
    expect(dimensionLabel("publisher", null)).toBe("-");
    expect(dimensionLabel("hou", undefined)).toBe("-");
    expect(dimensionLabel("app", "", "n/a")).toBe("n/a");
  });

  it("agrees with podLabel, so the two can never drift", () => {
    for (const value of [UNASSIGNED_POD, -1, 0, 3, "7", null, ""]) {
      expect(dimensionLabel("pod", value)).toBe(podLabel(value));
    }
  });
});
'''


# ── recon for batch 4 ────────────────────────────────────────────────────────
def recon() -> None:
    print("\n" + "=" * 78)
    print("== recon for batch 4: Apps Explorer cells, and Spotlight editing in place")
    print("=" * 78)

    def dump(path: Path, first: int, last: int, why: str) -> None:
        if not path.exists():
            print(f"\n--- {path}: missing")
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        last = min(last, len(lines))
        print(f"\n--- {path.relative_to(ROOT)} [{first}-{last} of {len(lines)}]  ({why})")
        for number in range(first, last + 1):
            print(f"{number:5}: {lines[number - 1]}")

    dump(FE / "components" / "apps" / "apps-explorer.tsx", 84, 118,
         "the cell renderer - where a text column becomes a string")
    dump(FE / "lib" / "api-hooks.ts", 1490, 1545,
         "AppMasterListResponse + AppMasterFilters, so Spotlight can load one row")
    dump(FE / "components" / "app-master" / "app-master-client.tsx", 736, 750,
         "how AppMasterClient mounts EditDrawer - the props Spotlight must supply")
    dump(FE / "lib" / "attribution.ts", 1, 60, "the current helper module")


def main() -> int:
    patch_attribution()
    patch_explore()

    current = TEST.read_text(encoding="utf-8") if TEST.exists() else ""
    if current != TEST_SOURCE:
        writes[TEST] = TEST_SOURCE
        note(("updated " if current else "wrote ") + str(TEST.relative_to(ROOT)))

    if problems:
        report()
        return 1
    for path, text in writes.items():
        path.write_text(text, encoding="utf-8")
    report()
    recon()
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
