#!/usr/bin/env python3
"""Frontend batch 2: the rest of the bare -1s, and the assistant panel.

  1. Pod -1 reads as "Unassigned" in the revenue donut and the revenue drill-down.
     Both are click-to-drill, so the LABEL and the VALUE have to part company: the
     legend says Unassigned, the filter it applies still says -1. Getting that
     wrong would look right and silently filter on a pod that does not exist.

  2. The assistant opens with grouped, tappable starters and its own identity
     instead of three dashed lines under a greeting. The commonest reason a box
     like this goes unused is that nobody knows what it will answer.

Nothing is written unless every anchor resolves exactly once. Re-running is a no-op.
Revert: git checkout -- frontend/
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"

SPLITS = FE / "components" / "overview" / "splits.tsx"
DRILL = FE / "components" / "revenue" / "revenue-drill.tsx"
CHAT = FE / "components" / "chat" / "chat-widget.tsx"

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


# ── 1. the pod donut ─────────────────────────────────────────────────────────
OLD_PIE_DATA = '''  const rows = breakdown.data?.rows ?? [];
  const data = rows.map((row, i) => ({
    name: String(row[groupBy] ?? ""),
    value: num(row.total_revenue_usd),
    itemStyle: { color: token(PALETTE[i % PALETTE.length]) },
  }));'''

NEW_PIE_DATA = '''  const rows = breakdown.data?.rows ?? [];
  // A slice's name is a LABEL; the click handler needs the value the API grouped by.
  // Pod -1 has to read as "Unassigned" in the legend and still drill in as -1 - showing
  // the label and then filtering on it would look right and quietly select nothing.
  const rawByLabel = new Map<string, string>();
  const data = rows.map((row, i) => {
    const rawValue = String(row[groupBy] ?? "");
    const shown = groupBy === "pod" ? podLabel(rawValue) : rawValue;
    rawByLabel.set(shown, rawValue);
    return {
      name: shown,
      value: num(row.total_revenue_usd),
      itemStyle: { color: token(PALETTE[i % PALETTE.length]) },
    };
  });'''

OLD_PIE_CLICK = '''          click: (p) => {
            const next = drillInto(filters, groupBy, String(p.name));
            if (next) setFilters(next);
          },'''

NEW_PIE_CLICK = '''          click: (p) => {
            const clicked = rawByLabel.get(String(p.name)) ?? String(p.name);
            const next = drillInto(filters, groupBy, clicked);
            if (next) setFilters(next);
          },'''


def patch_splits() -> None:
    source = SPLITS.read_text(encoding="utf-8") if SPLITS.exists() else None
    if source is None:
        fail(f"missing: {SPLITS.relative_to(ROOT)}")
        return
    if "podLabel" in source:
        note("splits.tsx already labels the unassigned pod - left as is.")
        return
    out = swap(SPLITS, source, OLD_PIE_DATA, NEW_PIE_DATA, "donut slices carry a label and a value")
    if out is None:
        return
    out = swap(SPLITS, out, OLD_PIE_CLICK, NEW_PIE_CLICK, "drill-down uses the raw pod value")
    if out is None:
        return
    writes[SPLITS] = add_import(out, 'import { podLabel } from "@/lib/attribution";')


# ── 2. the revenue drill-down ────────────────────────────────────────────────
OLD_DRILL_LABELS = '''  const labels = rows.map((r) => String(r[labelKey] ?? r[groupBy] ?? ""));'''

NEW_DRILL_LABELS = '''  // Same split as the donut: the axis shows a label, the drill-down uses the raw value.
  const rawByLabel = new Map<string, string>();
  const labels = rows.map((r) => {
    const rawValue = String(r[labelKey] ?? r[groupBy] ?? "");
    const shown = level === "pod" ? podLabel(rawValue) : rawValue;
    rawByLabel.set(shown, rawValue);
    return shown;
  });'''

OLD_DRILL_CLICK = '''      if (level === "hou") setHou(params.name);
      else if (level === "pod") setPod(params.name);'''

NEW_DRILL_CLICK = '''      const clicked = rawByLabel.get(params.name) ?? params.name;
      if (level === "hou") setHou(clicked);
      else if (level === "pod") setPod(clicked);'''

OLD_CRUMB = '''        <Breadcrumb
          hou={hou}
          pod={pod}'''

NEW_CRUMB = '''        <Breadcrumb
          hou={hou}
          // Display only - `pod` itself stays raw, because it is what the query filters on.
          pod={pod === null ? null : podLabel(pod)}'''


def patch_drill() -> None:
    source = DRILL.read_text(encoding="utf-8") if DRILL.exists() else None
    if source is None:
        fail(f"missing: {DRILL.relative_to(ROOT)}")
        return
    if "podLabel" in source:
        note("revenue-drill.tsx already labels the unassigned pod - left as is.")
        return
    out = swap(DRILL, source, OLD_DRILL_LABELS, NEW_DRILL_LABELS, "axis labels carry a label and a value")
    if out is None:
        return
    out = swap(DRILL, out, OLD_DRILL_CLICK, NEW_DRILL_CLICK, "drill-down uses the raw pod value")
    if out is None:
        return
    out = swap(DRILL, out, OLD_CRUMB, NEW_CRUMB, "breadcrumb shows Unassigned")
    if out is None:
        return
    writes[DRILL] = add_import(out, 'import { podLabel } from "@/lib/attribution";')


# ── 3. the assistant panel ───────────────────────────────────────────────────
OLD_SUGGESTIONS = '''const SUGGESTIONS = [
  "What was total revenue last 30 days?",
  "Top 5 apps by profit this month",
  "How did UA spend change vs the prior period?",
];'''

NEW_SUGGESTIONS = '''/** Tappable starters, grouped.
 *
 *  An assistant goes unused for one reason more than any other: an empty box gives no
 *  clue what it will actually answer. Three dashed lines were a hint; a short menu of
 *  what this thing is FOR is an invitation. Grouped rather than a flat list so the
 *  headings themselves say what it can be asked about.
 *
 *  Every one of these is answered through the caller's own access, like any other
 *  query - a starter cannot ask for more than the person tapping it can see. */
const STARTERS: { group: string; prompts: string[] }[] = [
  {
    group: "Revenue",
    prompts: [
      "What was total revenue last 30 days?",
      "Which apps grew revenue most this month?",
      "Split revenue by pod this quarter",
    ],
  },
  {
    group: "Spend and returns",
    prompts: [
      "How did UA spend change vs the prior period?",
      "Top 5 apps by profit this month",
      "Which apps are below 100% ROAS?",
    ],
  },
  {
    group: "Portfolio",
    prompts: ["Which apps have no pod assigned?", "How fresh is the data right now?"],
  },
];'''

OLD_HEADER = '''            <div className="flex min-w-0 items-center gap-2">
              <Sparkles className="h-4 w-4 shrink-0 text-primary" />
              <div className="min-w-0">
                <p className="text-sm font-semibold leading-none">Ask your data</p>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Answers respect your access
                </p>
              </div>
            </div>'''

NEW_HEADER = '''            <div className="flex min-w-0 items-center gap-2.5">
              <span
                aria-hidden
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                style={{
                  background: "color-mix(in srgb, var(--color-accent) 14%, transparent)",
                }}
              >
                <Sparkles className="h-4 w-4 text-[color:var(--color-accent)]" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold leading-none">Ask Prometheus</p>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Your data, your access
                </p>
              </div>
            </div>'''

OLD_CHIPS = '''            {messages.length === 1 && !send.isPending && (
              <div className="space-y-1.5 pt-1">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void submit(s)}
                    className="block w-full rounded-md border border-dashed px-3 py-1.5 text-left text-xs text-muted-foreground hover:border-solid hover:bg-muted hover:text-foreground"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}'''

NEW_CHIPS = '''            {messages.length === 1 && !send.isPending && (
              <div className="space-y-3 pt-1">
                {STARTERS.map((section) => (
                  <div key={section.group} className="space-y-1.5">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                      {section.group}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {section.prompts.map((prompt) => (
                        <button
                          key={prompt}
                          type="button"
                          onClick={() => void submit(prompt)}
                          className="rounded-full border px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-[color:var(--color-accent)] hover:bg-[color:var(--color-accent)] hover:text-[color:var(--color-accent-foreground)]"
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}'''


def patch_chat() -> None:
    source = CHAT.read_text(encoding="utf-8") if CHAT.exists() else None
    if source is None:
        fail(f"missing: {CHAT.relative_to(ROOT)}")
        return
    if "STARTERS" in source:
        note("chat-widget.tsx already has the grouped starters - left as is.")
        return
    out = swap(CHAT, source, OLD_SUGGESTIONS, NEW_SUGGESTIONS, "grouped starter prompts")
    if out is None:
        return
    out = swap(CHAT, out, OLD_HEADER, NEW_HEADER, "branded panel header")
    if out is None:
        return
    out = swap(CHAT, out, OLD_CHIPS, NEW_CHIPS, "starters render as tappable chips")
    if out is None:
        return
    if "SUGGESTIONS" in out:
        fail("chat-widget.tsx still references SUGGESTIONS after the swap - "
             "an unused or undefined name would fail the type check")
        return
    writes[CHAT] = out


# ── recon for batch 3 (Spotlight inline editing) ─────────────────────────────
def recon() -> None:
    print("\n" + "=" * 78)
    print("== recon: what Spotlight needs to mount the App Master editor in place")
    print("=" * 78)

    print("\n--- the App Master hooks (rows, columns, update, undo)")
    hooks = FE / "lib" / "api-hooks.ts"
    if hooks.exists():
        lines = hooks.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            if re.search(r"AppMaster|app-master|app_master", line):
                print(f"{number:5}: {line}")

    print("\n--- AppMasterClient: how it loads rows/columns and opens the drawer")
    client = FE / "components" / "app-master" / "app-master-client.tsx"
    if client.exists():
        lines = client.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            if re.search(r"use[A-Z]\w*\(|EditDrawer|setEditing|editing", line):
                print(f"{number:5}: {line.rstrip()}")

    print("\n--- Explore: where the dimension value is rendered")
    explore = FE / "components" / "explore" / "explore-client.tsx"
    if explore.exists():
        lines = explore.read_text(encoding="utf-8").splitlines()
        for number in range(130, min(266, len(lines)) + 1):
            print(f"{number:5}: {lines[number - 1]}")

    print("\n--- Apps Explorer: how a text cell is rendered")
    explorer = FE / "components" / "apps" / "apps-explorer.tsx"
    if explorer.exists():
        lines = explorer.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            if re.search(r"row\[|c\.key|col\.key|kind|<td|cell", line):
                print(f"{number:5}: {line.rstrip()}")


def main() -> int:
    patch_splits()
    patch_drill()
    patch_chat()

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
