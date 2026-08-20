#!/usr/bin/env python3
"""Remove the stale App Master editable-set assertion that spotlight.py left behind.

WHAT WENT WRONG. Making `type` the seventh editable column needed the owner-approved
set widened. The patch INSERTED the new comment, `_EXPECTED_EDITABLE` and assertion
above `BY_NAME` - and never removed the six-column pair already sitting between REGISTRY
and BY_NAME. Two assertions over the same registry, the six-column one first, so import
died on it and alembic could not even load the models:

    AssertionError: App Master editable set drifted from the owner-approved 6 columns

The registry itself is right: `type` is editable, seven columns are editable, and that is
the owner's decision of 2026-08-20. Only the stale copy of the guard is wrong.

WHY THIS IS NOT JUST A TEXT DELETION. That assertion exists so the editable set can never
widen by accident, and deleting the wrong one would quietly widen it. So this does not
match on comment text. It reads the registry, works out which columns are ACTUALLY
editable, keeps the block that agrees with it, and removes the ones that do not - and if
no block agrees, it changes nothing and prints both sets. Then it imports the module for
real, because the only convincing proof that an assertion passes is running it.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

TARGET = Path("backend/app/core/app_master_columns.py")


def registry_editable(tree: ast.Module) -> set[str]:
    """The set the REGISTRY literal actually declares editable."""
    for node in ast.walk(tree):
        # REGISTRY carries a type annotation, so it is an AnnAssign, not an Assign.
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "REGISTRY" for t in targets):
            continue
        if node.value is None:
            continue
        editable: set[str] = set()
        for call in ast.walk(node.value):
            if not isinstance(call, ast.Call):
                continue
            if not (isinstance(call.func, ast.Name) and call.func.id == "_c"):
                continue
            is_editable = any(
                kw.arg == "editable" and isinstance(kw.value, ast.Constant) and kw.value.value
                for kw in call.keywords
            )
            if is_editable and call.args and isinstance(call.args[0], ast.Constant):
                editable.add(call.args[0].value)
        return editable
    raise SystemExit("ABORTED: no REGISTRY assignment found")


def blocks(tree: ast.Module) -> list[tuple[set[str], int, int]]:
    """Every (set, first line, last line) pair of _EXPECTED_EDITABLE + its assertion."""
    body = tree.body
    found = []
    for index, node in enumerate(body):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "_EXPECTED_EDITABLE" for t in node.targets):
            continue
        try:
            value = set(ast.literal_eval(node.value))
        except ValueError:
            raise SystemExit(f"ABORTED: _EXPECTED_EDITABLE at line {node.lineno} is not a literal")
        end = node.end_lineno or node.lineno
        following = body[index + 1] if index + 1 < len(body) else None
        if isinstance(following, ast.Assert) and "_EXPECTED_EDITABLE" in ast.dump(following.test):
            end = following.end_lineno or end
        found.append((value, node.lineno, end))
    return found


def main() -> int:
    if not TARGET.exists():
        print(f"ABORTED: {TARGET} not found - run this from the repository root")
        return 1

    text = TARGET.read_text()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)

    actual = registry_editable(tree)
    found = blocks(tree)
    print(f"registry declares {len(actual)} editable columns: {', '.join(sorted(actual))}")
    for value, start, end in found:
        verdict = "agrees" if value == actual else "STALE"
        print(f"  lines {start}-{end}: {len(value)}-column guard, {verdict}")

    if len(found) < 2:
        print("nothing to do - a single guard, already consistent")
        return 0

    keep = [b for b in found if b[0] == actual]
    drop = [b for b in found if b[0] != actual]
    if not keep:
        print()
        print("ABORTED - NOTHING was written: no guard matches the registry, so removing")
        print("either one would silently widen the owner-approved set. Decide first.")
        return 1

    # Take the leading comment run with the block, otherwise the explanation for a guard
    # that no longer exists is left stranded above the one that does.
    cut: set[int] = set()
    for _, start, end in drop:
        first = start
        while first > 1 and lines[first - 2].lstrip().startswith("#"):
            first -= 1
        last = end
        while last < len(lines) and not lines[last].strip():
            last += 1
        cut.update(range(first, last + 1))
        print(f"removing lines {first}-{last}")

    TARGET.write_text("".join(l for n, l in enumerate(lines, 1) if n not in cut))

    # The only convincing proof that an assertion passes is running it.
    proof = subprocess.run(
        [sys.executable, "-c", "import app.core.app_master_columns as m; print(len(m.REGISTRY))"],
        cwd="backend",
        capture_output=True,
        text=True,
    )
    if proof.returncode != 0:
        print()
        print("WROTE THE FILE, but importing it still fails:")
        print(proof.stderr.strip()[-2000:])
        return 1
    print(f"import clean - {proof.stdout.strip()} columns in the registry")
    print()
    print("Re-run the migration, the test gate and the restart.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
