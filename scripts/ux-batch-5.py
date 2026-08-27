#!/usr/bin/env python3
"""UX batch 5: the Spotlight board gets an Edit button that opens the full app record.

Spotlight already edits in place, but only the six fields it grades completeness on -
publisher, HOU, pod, pod owner, partner name, net revenue share. Anything else still
meant leaving the board for App Master and losing your place on it.

This adds one control to the open card, next to Save and Close: "Edit all fields", which
opens the app editor from batch 4 over the top of the board. Same app, every editable
column, and closing the drawer puts you back exactly where you were - the board does not
reload and your filter and page are untouched.

`card.key` is App Master's own primary key, which is precisely what the drawer looks the
row up by, so nothing has to be translated between the two.

The anchor is the Close button's CODE - the `setOpenKey(null)` handler - not its label or
the prose around it. If the board has been rewritten and that element is not there, the
run writes nothing and prints the file so the next attempt is aimed rather than guessed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
PORTAL = ROOT / "frontend/components/apps/app-edit-portal.tsx"
IMPORT_LINE = 'import { openAppEditor } from "@/components/apps/app-edit-portal";'

# <Button ... onClick={() => setOpenKey(null)} ...>Close</Button>, however it is
# attributed and whatever the label reads.
CLOSE_BUTTON_RE = re.compile(
    r"(?P<indent>[ \t]*)<Button\b(?P<before>[^>]*?)onClick=\{\(\)\s*=>\s*setOpenKey\(null\)\}"
    r"(?P<after>[^>]*?)>\s*(?P<label>[^<]{0,40}?)\s*</Button>",
    re.S,
)

EDIT_BUTTON = """{indent}<Button
{indent}  size="sm"
{indent}  variant="outline"
{indent}  onClick={{() => openAppEditor(card.key)}}
{indent}  title="Open this app's full App Master record, without leaving the board"
{indent}>
{indent}  Edit all fields
{indent}</Button>"""


def indent_block(text: str) -> str:
    return "\n".join(f"      | {line}" for line in text.rstrip("\n").splitlines())


def add_import(text: str) -> str:
    if IMPORT_LINE in text:
        return text
    imports = list(re.finditer(r"^import [^\n]*;$", text, re.M))
    if not imports:
        return IMPORT_LINE + "\n" + text
    end = imports[-1].end()
    return text[:end] + "\n" + IMPORT_LINE + text[end:]


def spotlight_files() -> list[Path]:
    found = sorted(ROOT.glob("frontend/components/spotlight/*.tsx"))
    found += sorted(ROOT.glob("frontend/app/(app)/spotlight/*.tsx"))
    return [p for p in found if "node_modules" not in p.parts]


def dump(path: Path) -> None:
    print(f"\n--- {path}", file=sys.stderr)
    for i, line in enumerate(path.read_text().splitlines(), 1):
        print(f"  {i:>4}  {line}", file=sys.stderr)


def main() -> int:
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    if not PORTAL.exists():
        print(
            f"ABORTED - nothing was written.\n\n{PORTAL} is not there yet. Run "
            "ux-batch-4.py first; it creates the editor this button opens.",
            file=sys.stderr,
        )
        return 1

    files = spotlight_files()
    if not files:
        print(
            "ABORTED - nothing was written.\n\nNo Spotlight component found under "
            "frontend/components/spotlight/ or frontend/app/(app)/spotlight/.",
            file=sys.stderr,
        )
        return 1

    already = [p for p in files if "openAppEditor(" in p.read_text()]
    if already:
        print("Already applied - left alone:")
        for path in already:
            print(f"  - {path}")
        return 0

    # The card editor lives in exactly one of these files; the others are the page
    # wrapper and any helpers.
    hits: list[tuple[Path, re.Match[str]]] = []
    for path in files:
        for match in CLOSE_BUTTON_RE.finditer(path.read_text()):
            hits.append((path, match))

    if len(hits) != 1:
        print(
            f"ABORTED - nothing was written.\n\nExpected exactly one Close button "
            f"handled by `setOpenKey(null)` across the Spotlight files; found "
            f"{len(hits)}. The files on disk, in full:",
            file=sys.stderr,
        )
        for path in files:
            dump(path)
        return 1

    path, match = hits[0]
    text = path.read_text()
    if "card.key" not in text:
        print(
            "ABORTED - nothing was written.\n\nThe open card does not expose `card.key`, "
            "so there is no app id to hand the editor. The file, in full:",
            file=sys.stderr,
        )
        dump(path)
        return 1

    block = EDIT_BUTTON.format(indent=match.group("indent"))
    text = text[: match.end()] + "\n" + block + text[match.end() :]
    text = add_import(text)
    path.write_text(text)

    print(
        "PATCHED, NOT YET VERIFIED - the test run is the verification, not this script."
    )
    print(f"  - {path}: 'Edit all fields' added next to {match.group('label')!r}")
    print(
        "  - opens the batch-4 drawer over the board; the board keeps its page and filters"
    )
    print("\nThe inserted control:")
    print(indent_block(block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
