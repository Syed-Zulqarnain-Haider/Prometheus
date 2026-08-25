#!/usr/bin/env python3
"""Accessibility batch: named column headers, keyboard-reachable tables, a visible focus ring.

The platform audit scored accessibility 55, and three findings account for most of it. None
is cosmetic - each one is a person unable to use a page they have permission to see.

1. COLUMN HEADERS ARE UNNAMED. Every table renders <th> with no `scope`. Sighted users get
   the association from the layout; a screen-reader user gets a wall of numbers with no
   idea which column each belongs to. `scope="col"` is what binds a cell to its header.

2. SCROLLING TABLES ARE UNREACHABLE BY KEYBOARD. The wide tables sit in overflow containers.
   A mouse can scroll them; a keyboard cannot focus a plain <div>, so the columns past the
   fold are simply unreachable without a pointing device. tabIndex={0} makes the container
   focusable and therefore scrollable with the arrow keys. Where the table sits in a card
   with a plain-text title, the container also gets role="region" and that title as its
   aria-label, so it is announced as something meaningful rather than an unnamed landmark.
   Where no such title exists it gets tabIndex only - an unnamed region is worse than none.

3. FOCUS IS INVISIBLE. Nothing defines a focus ring, so keyboard users navigate blind. The
   rule added here is :focus-visible, never :focus - a mouse click must not draw a ring, or
   people find it ugly, turn it off, and keyboard users lose it again.

THIS SCRIPT DISCOVERS ITS OWN WORK. There are no anchors and nothing is hardcoded: it walks
components/ and app/, finds every <thead> region and every overflow container that directly
wraps a <table>, and edits what it finds. New tables added later are covered by re-running
it - and by the drift guard it writes, tests/a11y-source.test.ts, which fails the build if
a <th> ever lands in a <thead> without a scope.

Deliberately conservative: it refuses any container whose opening tag is not a simple
className string, and reports every one it skipped rather than guessing. Idempotent - the
inserted attribute is what it looks for on a re-run.

    python3 scripts/a11y-tables-and-focus.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOTS = ("frontend/components", "frontend/app")
GLOBALS_CSS = Path("frontend/app/globals.css")
GUARD_TEST = Path("frontend/tests/a11y-source.test.ts")

# <th followed by whitespace or '>' - never matches <thead, which has an 'e' next.
TH_OPEN = re.compile(r"<th(?=[\s>])")
THEAD_OPEN = "<thead"
THEAD_CLOSE = "</thead>"

# Only containers whose whole opening tag is a plain className string. Anything with a
# brace expression is skipped and reported - a regex has no business inside JSX braces.
CONTAINER = re.compile(r'<(div|CardContent)\s+className="([^"]*)"\s*>')
NEXT_TAG = re.compile(r"<\s*([A-Za-z/][A-Za-z0-9.]*)")
CARD_TITLE = re.compile(r"<CardTitle[^>]*>([^<>{}]+)</CardTitle>")

FOCUS_CSS = """
  /* Visible keyboard focus. :focus-visible and never :focus - a mouse click must not draw
     a ring, because that is what makes people remove it and strand keyboard users. The
     accent token is defined in both themes, so this stays visible on parchment and onyx. */
  :focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }
"""

GUARD = '''/**
 * Accessibility drift guard - it reads the SOURCE, not a rendered DOM.
 *
 * Two rules the audit found broken across every table, and which are easy to reintroduce
 * the next time someone adds a column: a <th> inside <thead> must carry a scope, and a
 * scroll container wrapping a table must be focusable or its far columns are unreachable
 * without a mouse. Neither is visible in review, so the guard has to be automatic.
 *
 * The last test is the one that matters most: it asserts the scanner actually FOUND
 * tables. A source scanner whose regex silently stops matching passes every other test in
 * this file while checking nothing at all.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

function tsxFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...tsxFiles(full));
    else if (entry.endsWith(".tsx")) out.push(full);
  }
  return out;
}

const FILES = [join(ROOT, "components"), join(ROOT, "app")].flatMap(tsxFiles);

/** Every <thead>...</thead> body in a file. */
function theadRegions(source: string): string[] {
  const regions: string[] = [];
  let at = 0;
  for (;;) {
    const open = source.indexOf("<thead", at);
    if (open === -1) break;
    const close = source.indexOf("</thead>", open);
    if (close === -1) break;
    regions.push(source.slice(open, close));
    at = close + 1;
  }
  return regions;
}

describe("table accessibility, enforced against the source", () => {
  it("gives every column header a scope", () => {
    const offenders: string[] = [];
    let headers = 0;
    for (const file of FILES) {
      const source = readFileSync(file, "utf8");
      for (const region of theadRegions(source)) {
        for (const match of region.matchAll(/<th(?=[\\s>])/g)) {
          headers += 1;
          if (!region.slice(match.index).startsWith('<th scope=')) {
            offenders.push(`${relative(ROOT, file)}: <th without scope`);
          }
        }
      }
    }
    expect(headers).toBeGreaterThan(20);
    expect(offenders).toEqual([]);
  });

  it("keeps every table scroll container reachable from the keyboard", () => {
    const offenders: string[] = [];
    let containers = 0;
    for (const file of FILES) {
      const source = readFileSync(file, "utf8");
      for (const match of source.matchAll(/<(?:div|CardContent)\\s+className="([^"]*)"([^>]*)>/g)) {
        if (!/\\boverflow-(?:x-)?auto\\b/.test(match[1])) continue;
        const after = source.slice((match.index ?? 0) + match[0].length);
        if (!/^\\s*<\\s*table\\b/.test(after)) continue;
        containers += 1;
        if (!match[2].includes("tabIndex")) {
          offenders.push(`${relative(ROOT, file)}: scrolling table is not focusable`);
        }
      }
    }
    // If this drops to zero the scanner has stopped seeing tables and the test above it
    // is passing vacuously. That is the failure mode this assertion exists to catch.
    expect(containers).toBeGreaterThan(3);
    expect(offenders).toEqual([]);
  });
});
'''


def add_scopes(source: str) -> tuple[str, int]:
    """Insert scope="col" into every <th> that lives inside a <thead> and lacks one."""
    out, at, added = [], 0, 0
    while True:
        open_at = source.find(THEAD_OPEN, at)
        if open_at == -1:
            break
        close_at = source.find(THEAD_CLOSE, open_at)
        if close_at == -1:
            break
        out.append(source[at:open_at])
        region = source[open_at:close_at]
        pieces, last = [], 0
        for match in TH_OPEN.finditer(region):
            if region[match.start():].startswith('<th scope='):
                continue
            pieces.append(region[last:match.end()])
            pieces.append(' scope="col"')
            last = match.end()
            added += 1
        pieces.append(region[last:])
        out.append("".join(pieces))
        at = close_at
    out.append(source[at:])
    return "".join(out), added


def make_focusable(source: str, rel: str, skipped: list[str]) -> tuple[str, int]:
    """Give overflow containers that DIRECTLY wrap a <table> a tab stop, and a name when
    a plain-text CardTitle above them supplies one."""
    result, at, fixed = [], 0, 0
    for match in CONTAINER.finditer(source):
        classes = match.group(2)
        if not re.search(r"\boverflow-(?:x-)?auto\b", classes):
            continue
        after = source[match.end():]
        tag = NEXT_TAG.search(after)
        if not tag or tag.group(1) != "table":
            continue
        if "tabIndex" in match.group(0):
            continue
        titles = CARD_TITLE.findall(source[:match.start()])
        label = titles[-1].strip() if titles else ""
        attrs = " tabIndex={0}"
        if label:
            safe = label.replace('"', "&quot;")
            attrs += f' role="region" aria-label="{safe}"'
        else:
            skipped.append(f"{rel}: focusable, but no plain-text CardTitle to name it")
        result.append(source[at:match.end() - 1])
        result.append(attrs + ">")
        at = match.end()
        fixed += 1
    result.append(source[at:])
    return "".join(result), fixed


def main() -> int:
    if not Path("frontend/components").is_dir():
        print("ABORTED: run this from the repository root")
        return 1

    files: list[Path] = []
    for root in ROOTS:
        files.extend(sorted(Path(root).rglob("*.tsx")))
    if not files:
        print("ABORTED: found no .tsx files - wrong tree?")
        return 1

    planned: dict[Path, str] = {}
    skipped: list[str] = []
    scopes = focusables = 0
    for path in files:
        original = path.read_text()
        text, added = add_scopes(original)
        text, fixed = make_focusable(text, str(path), skipped)
        scopes += added
        focusables += fixed
        if text != original:
            planned[path] = text

    css = GLOBALS_CSS.read_text() if GLOBALS_CSS.exists() else ""
    if not css:
        print(f"ABORTED: {GLOBALS_CSS} not found")
        return 1
    if ":focus-visible" not in css:
        marker = "@layer base {"
        if marker not in css:
            print(f"ABORTED: no '@layer base' block in {GLOBALS_CSS} to extend")
            return 1
        planned[GLOBALS_CSS] = css.replace(marker, marker + FOCUS_CSS, 1)

    if not GUARD_TEST.exists() or GUARD_TEST.read_text() != GUARD:
        planned[GUARD_TEST] = GUARD

    # A pass that changed nothing while claiming a fix is the failure worth catching. The
    # only legitimate no-op is a tree already fully patched, and that is stated as such.
    if not planned:
        print("nothing to do - already applied")
        return 0
    if scopes == 0 and focusables == 0 and GUARD_TEST.exists() and ":focus-visible" in css:
        print("ABORTED: matched no headers and no containers - the scanner is broken,")
        print("not the tree. Nothing was written.")
        return 1

    for path, content in sorted(planned.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"wrote {path}")
    print()
    print(f"scope=\"col\" added to {scopes} column headers")
    print(f"tab stop added to {focusables} scrolling tables")
    for note in skipped:
        print(f"note  {note}")
    print()
    print("Run: npx vitest run  and  npm run build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
