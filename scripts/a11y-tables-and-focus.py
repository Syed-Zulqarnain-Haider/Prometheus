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

SCOPE_ATTR = ' scope="col"'


def tag_end(text: str, start: int) -> int:
    """Index of the '>' that actually closes the JSX tag opening at `start`, or -1.

    A regex cannot do this and must not try. An attribute may hold an arrow function -
    onDragOver={(e) => reordering && e.preventDefault()} - whose '>' would end the tag
    early, and a className may hold a template literal full of braces. So: count brace
    depth, skip string and template literals, and take the first '>' seen at depth zero
    outside quotes. That is the real one.
    """
    index, depth, quote = start, 0, ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote and text[index - 1] != "\\":
                quote = ""
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == ">" and depth == 0:
            return index
        index += 1
    return -1

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
 * It finds the end of a tag by counting braces rather than by regex, because an attribute
 * can hold an arrow function whose ">" is not the end of the tag. The first version of the
 * patch script used a positional check instead and added a second scope to a header that
 * already had one; the duplicate-attribute test below is that bug, pinned.
 *
 * The count assertions matter as much as the offender lists: a source scanner whose regex
 * quietly stops matching passes every "no offenders" test while checking nothing at all.
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

/** Index of the ">" that really closes the tag opening at `start`, or -1. */
function tagEnd(text: string, start: number): number {
  let depth = 0;
  let quote = "";
  for (let i = start; i < text.length; i += 1) {
    const char = text[i];
    if (quote) {
      if (char === quote && text[i - 1] !== "\\\\") quote = "";
    } else if (char === '"' || char === "'" || char === "`") {
      quote = char;
    } else if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
    } else if (char === ">" && depth === 0) {
      return i;
    }
  }
  return -1;
}

/** Every <th ...> opening tag that sits inside a <thead>...</thead>. */
function headerTags(source: string): string[] {
  const tags: string[] = [];
  let at = 0;
  for (;;) {
    const open = source.indexOf("<thead", at);
    if (open === -1) break;
    const close = source.indexOf("</thead>", open);
    if (close === -1) break;
    for (const match of source.slice(open, close).matchAll(/<th(?=[\\s>])/g)) {
      const absolute = open + (match.index ?? 0);
      const end = tagEnd(source, absolute);
      if (end !== -1 && end < close) tags.push(source.slice(absolute, end + 1));
    }
    at = close + 1;
  }
  return tags;
}

describe("table accessibility, enforced against the source", () => {
  it("gives every column header exactly one scope", () => {
    const missing: string[] = [];
    const duplicated: string[] = [];
    let headers = 0;
    for (const file of FILES) {
      for (const tag of headerTags(readFileSync(file, "utf8"))) {
        headers += 1;
        const scopes = (tag.match(/\\bscope=/g) ?? []).length;
        if (scopes === 0) missing.push(`${relative(ROOT, file)}: <th without scope`);
        if (scopes > 1) duplicated.push(`${relative(ROOT, file)}: <th with two scopes`);
      }
    }
    expect(headers).toBeGreaterThan(20);
    expect(missing).toEqual([]);
    // A duplicate is not a style nit - react/jsx-no-duplicate-props fails the build.
    expect(duplicated).toEqual([]);
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
    expect(containers).toBeGreaterThan(3);
    expect(offenders).toEqual([]);
  });
});
'''


def add_scopes(source: str) -> tuple[str, int, int, list[str]]:
    """Give every <th> inside a <thead> a scope, exactly once.

    Three cases, and the middle one is what the first version of this script got wrong:
    a header with NO scope gets one; a header that ALREADY has one - anywhere in the tag,
    not merely straight after `<th` - is left alone; and a header carrying two, because an
    earlier run inserted a duplicate next to an existing attribute, is repaired by dropping
    the one this script added. That last case is why this is a repair, not just a guard:
    the broken output is already sitting in a working tree somewhere.
    """
    edits: list[tuple[int, int, str]] = []
    added = repaired = 0
    notes: list[str] = []
    at = 0
    while True:
        open_at = source.find(THEAD_OPEN, at)
        if open_at == -1:
            break
        close_at = source.find(THEAD_CLOSE, open_at)
        if close_at == -1:
            break
        for match in TH_OPEN.finditer(source, open_at, close_at):
            end_at = tag_end(source, match.start())
            if end_at == -1 or end_at > close_at:
                notes.append("unterminated <th tag - left untouched")
                continue
            tag = source[match.start():end_at + 1]
            count = tag.count("scope=")
            if count == 0:
                edits.append((match.start(), end_at + 1, "<th" + SCOPE_ATTR + tag[3:]))
                added += 1
            elif count > 1 and tag.startswith("<th" + SCOPE_ATTR):
                edits.append(
                    (match.start(), end_at + 1, "<th" + tag[3 + len(SCOPE_ATTR):])
                )
                repaired += 1
        at = close_at + len(THEAD_CLOSE)

    out, last = [], 0
    for begin, finish, replacement in edits:
        out.append(source[last:begin])
        out.append(replacement)
        last = finish
    out.append(source[last:])
    return "".join(out), added, repaired, notes


def duplicate_attributes(source: str) -> list[str]:
    """Tags carrying the same attribute twice - what ESLint's jsx-no-duplicate-props
    rejects, and what the previous version of this script silently produced. Checked on
    the OUTPUT before anything is written: a script that can corrupt a file must be the
    thing that notices, not the build twenty minutes later."""
    problems: list[str] = []
    for match in re.finditer(r"<[A-Za-z][A-Za-z0-9.]*", source):
        end_at = tag_end(source, match.start())
        if end_at == -1:
            continue
        tag = source[match.start():end_at + 1]
        for attribute in ("scope=", "tabIndex=", "role=", "aria-label="):
            if tag.count(attribute) > 1:
                line = source.count("\n", 0, match.start()) + 1
                problems.append(f"line {line}: {attribute.rstrip('=')} appears twice")
    return problems


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
    corrupt: list[str] = []
    scopes = focusables = repairs = 0
    for path in files:
        original = path.read_text()
        text, added, mended, notes = add_scopes(original)
        text, fixed = make_focusable(text, str(path), skipped)
        scopes += added
        focusables += fixed
        repairs += mended
        skipped.extend(f"{path}: {note}" for note in notes)
        # Verify the OUTPUT, not the input. The first version of this script emitted a
        # duplicate scope on a header that already had one and only found out when the
        # production build refused it - a failure the script itself should have caught.
        for problem in duplicate_attributes(text):
            corrupt.append(f"{path} {problem}")
        if text != original:
            planned[path] = text

    if corrupt:
        print("ABORTED - NOTHING was written. The patched output has duplicate JSX")
        print("attributes, which ESLint (react/jsx-no-duplicate-props) rejects:")
        print()
        for problem in corrupt:
            print(f"  {problem}")
        return 1

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
    if scopes == 0 and focusables == 0 and repairs == 0 and GUARD_TEST.exists() and ":focus-visible" in css:
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
    if repairs:
        print(f"repaired {repairs} header(s) that a previous run gave a duplicate scope")
    for note in skipped:
        print(f"note  {note}")
    print()
    print("Run: npx vitest run  and  npm run build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
