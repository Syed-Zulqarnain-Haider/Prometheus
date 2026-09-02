#!/usr/bin/env python3
"""Unblock the image build: sync/requirements.txt still pins redis==5.*, the lock says 8.

WHAT HAPPENED
-------------
The build now installs against the lock (pin-dependencies.py), and the very first thing it
did was refuse:

    ERROR: Cannot install redis==5.* because these package versions have conflicting
    dependencies.
        The user requested redis==5.*
        The user requested (constraint) redis==8.0.0

That contradiction was ALREADY THERE. pyproject declares redis>=8.0 and every test runs
against 8.x; sync/requirements.txt pinned ==5.*; and because both were resolved in one
pass, pip quietly picked 5.x for the whole image - including the API. So the deployed
container has been running the rate limiter and the permission-keyed cache on a client
library no test has ever exercised, and one that `mypy --strict` rejects outright because
its from_url() carries no annotations.

Constraining the build did not create this. It made a silent wrong answer into a loud
refusal, which is the entire point - but it is blocking a deploy, so this fixes the cause.

THE FIX
-------
sync/requirements.txt moves to `redis>=8.0`, matching pyproject's floor, and is mirrored
byte-identical to backend/sync (the parity test enforces that). Nothing else moves: the
BigQuery and psycopg pins are untouched.

The comment in this repository's own Dockerfile already describes this exact incident from
the last time it happened. It was fixed there and in the canonical requirements file, and
the deployed copy never received it.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(".")
CANON = ROOT / "sync/requirements.txt"
VENDOR = ROOT / "backend/sync/requirements.txt"

NOTE = """\
# Kept in lockstep with the API's floor (backend/pyproject.toml: redis>=8.0). The production
# backend image installs THIS file and the package in one resolver pass, so a `==5.*` pin
# here silently decided the API's redis version too, landing on 5.x - whose from_url()
# carries no type annotations, so `mypy --strict` rejects it. The image therefore shipped a
# client the type checker refuses and CI never exercised. Constraining the build against the
# lock turned that silent downgrade into an honest build failure; this is its cause.
redis>=8.0
"""

PIN = re.compile(r"^(?:#[^\n]*\n)*redis\s*[=<>!~]=[^\n]*\n", re.M)


def main() -> int:
    if not CANON.exists():
        print(f"ABORTED: missing {CANON}", file=sys.stderr)
        return 1

    text = CANON.read_text()
    if re.search(r"^redis>=8\.0\s*$", text, re.M):
        print("Already correct - redis>=8.0 in the canonical copy.")
        if not VENDOR.exists() or VENDOR.read_bytes() != CANON.read_bytes():
            shutil.copyfile(CANON, VENDOR)
            print("  - re-mirrored the vendored copy (was out of parity)")
        return 0

    matches = PIN.findall(text)
    if len(matches) != 1:
        print(
            f"NOTHING WAS WRITTEN - expected exactly one redis pin, found {len(matches)}.\n"
            "This file decides the API's redis version too, so it is not a place to guess.\n"
            "On disk:\n",
            file=sys.stderr,
        )
        for number, line in enumerate(text.splitlines(), 1):
            print(f"  {number:>3}  {line}", file=sys.stderr)
        return 1

    CANON.write_text(PIN.sub(NOTE, text, count=1))
    shutil.copyfile(CANON, VENDOR)
    print("PATCHED - the image build is the verification for a dependency change.")
    print(f"  - {CANON}: redis pin -> >=8.0 (matching pyproject's floor)")
    print(f"  - {VENDOR}: mirrored byte-identical (parity test enforces this)")
    print(
        "\nThe API has been running on redis 5.x in the deployed image - a version no test\n"
        "exercises and mypy --strict rejects. This moves it onto the 8.x the whole suite\n"
        "actually runs against."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
