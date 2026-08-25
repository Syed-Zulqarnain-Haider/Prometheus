#!/usr/bin/env python3
"""Let an admin un-assign an app: accept pod = -1, keep rejecting nonsense.

The schema declares ``pod: int | None = Field(default=None, gt=0)``. The owner has since
confirmed what -1 means in this data: apps nobody has been assigned yet, and new apps
arriving in the feed. So the feed produces a value the API forbids anyone from setting -
un-assigning an app was simply impossible, and the UI and the data disagreed about what a
valid pod is. That is not a strict validator; it is a validator that is wrong about its
own domain.

gt=0 cannot express "positive, or exactly -1", so the constraint moves to a field
validator that says it in words. The guard keeps doing its real job: 0 is still rejected,
-2 is still rejected, a typo is still rejected. Exactly one negative value has a meaning
and exactly that one is allowed.

THE IMPORT IS DISCOVERED, NOT ASSUMED. This script does not know how app_master.py spells
its pydantic import, so it reads the existing ``from pydantic import ...`` line, adds
``field_validator`` only if it is missing, and rewrites the names in order. Guessing that
line is how a patch turns a working module into an ImportError.

THIS IS THE BACKEND HALF. The README says pod > 0 is validated on the client too, so the
edit drawer will still refuse -1 until its own check is changed and the pod dropdown gets
an explicit "Unassigned" option. Stated here rather than left as a surprise.

    python3 scripts/allow-unassigned-pod.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

SCHEMA = Path("backend/app/schemas/app_master.py")

OLD_FIELD = """    # pod is a positive pod NUMBER (must be > 0).
    pod: int | None = Field(default=None, gt=0)"""

NEW_FIELD = '''    # A pod is a positive NUMBER, or -1: the bucket for apps nobody has been assigned
    # yet and for new apps arriving in the feed. gt=0 rejected -1, so the feed could
    # produce a value an admin was forbidden from setting - un-assigning an app was
    # impossible, and the UI disagreed with the data about what a valid pod is.
    pod: int | None = None

    @field_validator("pod")
    @classmethod
    def _pod_assigned_or_unassigned(cls, value: int | None) -> int | None:
        """Positive, or the -1 sentinel. Everything else is still a typo.

        Deliberately NOT loosened to "any integer": 0 and -2 mean nothing here, and a
        validator that accepts anything negative would let a fat-fingered -5 become a pod
        that silently matches no app and quietly drops rows out of every split.
        """
        if value is None or value > 0 or value == UNASSIGNED_POD:
            return value
        raise ValueError(
            f"pod must be a positive number, or {UNASSIGNED_POD} for unassigned"
        )'''

CONSTANT = '''
# The pod value meaning "nobody owns this app yet" - unassigned apps, and new apps that
# have just appeared in the feed. It is a real bucket carrying real revenue, not a null.
UNASSIGNED_POD = -1

'''


def add_import(text: str) -> tuple[str, str | None]:
    """Ensure ``field_validator`` is imported from pydantic. Returns (text, error)."""
    if re.search(r"\bfield_validator\b", text):
        return text, None
    match = re.search(r"^from pydantic import (.+)$", text, re.MULTILINE)
    if not match:
        return text, "no 'from pydantic import ...' line found - cannot add field_validator"
    if match.group(1).lstrip().startswith("("):
        return text, "the pydantic import is parenthesised; re-anchor by hand"
    names = [n.strip() for n in match.group(1).split(",") if n.strip()]
    names = sorted({*names, "field_validator"}, key=str.lower)
    return text[: match.start()] + f"from pydantic import {', '.join(names)}" + text[match.end() :], None


def main() -> int:
    if not SCHEMA.exists():
        print(f"ABORTED: {SCHEMA} not found - run from the repository root")
        return 1
    text = SCHEMA.read_text()

    if "_pod_assigned_or_unassigned" in text:
        print("nothing to do - already applied")
        return 0

    found = text.count(OLD_FIELD)
    if found != 1:
        print(f"ABORTED - NOTHING was written: expected 1 match for the pod field, found {found}.")
        print()
        lines = text.splitlines()
        for n, line in enumerate(lines, start=1):
            if "pod" in line and (":" in line or "#" in line):
                lo, hi = max(0, n - 4), min(len(lines), n + 3)
                print(f"----- {SCHEMA} lines {lo + 1}-{hi} -----")
                for m, l in enumerate(lines[lo:hi], start=lo + 1):
                    print(f"{m:6d}\t{l}")
                break
        return 1

    patched, error = add_import(text)
    if error:
        print(f"ABORTED - NOTHING was written: {error}")
        return 1
    patched = patched.replace(OLD_FIELD, NEW_FIELD, 1)

    # The constant goes after the imports, before the first class.
    first_class = re.search(r"^class ", patched, re.MULTILINE)
    if not first_class:
        print("ABORTED - NOTHING was written: no class definition found in the schema")
        return 1
    patched = patched[: first_class.start()] + CONSTANT.lstrip("\n") + patched[first_class.start() :]

    # Verify the OUTPUT parses and actually carries the validator. A schema module that
    # fails to import takes the whole API down, so this is not a formality.
    try:
        tree = ast.parse(patched)
    except SyntaxError as exc:
        print(f"ABORTED - NOTHING was written: the patched file does not parse: {exc}")
        return 1
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if "_pod_assigned_or_unassigned" not in names:
        print("ABORTED - NOTHING was written: the validator is not in the patched module")
        return 1
    if not re.search(r"^from pydantic import .*\bfield_validator\b", patched, re.MULTILINE):
        print("ABORTED - NOTHING was written: field_validator was never imported")
        return 1

    SCHEMA.write_text(patched)
    print(f"wrote {SCHEMA}")
    print()
    print("Backend now accepts pod = -1 (and still rejects 0, -2 and anything else).")
    print("STILL TO DO - the client half: the edit drawer validates pod > 0 too, and the")
    print("pod dropdown needs an explicit 'Unassigned' option so nobody types a sentinel.")
    print()
    print("Rebuild the backend, then run its suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
