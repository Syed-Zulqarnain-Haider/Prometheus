#!/usr/bin/env python3
"""Add ``python-multipart`` to the backend's runtime dependencies.

FastAPI parses multipart form data (``UploadFile`` / ``File``) through python-multipart, and
it is NOT pulled in by fastapi itself. Without it, importing any module that declares a file
upload raises at import time - which is exactly how the avatar endpoint was caught, before
anything restarted.

Written as a script rather than a whole pyproject.toml because that file carries security
floors and comments this tree does not have. Verifies the result still parses as TOML, and
restores the original if it does not.

Run from the repository root:  python3 scripts/add-multipart-dep.py
"""

from __future__ import annotations

import shutil
import sys
import time
import tomllib
from pathlib import Path

TARGET = Path("backend/pyproject.toml")
PACKAGE = "python-multipart"
ANCHOR = "dependencies = [\n"
ENTRY = (
    "    # Runtime dependency (NOT optional): FastAPI parses multipart form data through\n"
    "    # python-multipart, and does not depend on it itself. The avatar upload endpoint\n"
    "    # fails at IMPORT time without it, so it belongs here, not in a dev extra.\n"
    '    "python-multipart>=0.0.9",\n'
)


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not TARGET.exists():
        die(f"{TARGET} not found - run from the repository root")

    text = TARGET.read_text()
    if PACKAGE in text:
        print(f"skipped  {TARGET} ({PACKAGE} already declared)")
        return

    count = text.count(ANCHOR)
    if count != 1:
        die(f"expected one 'dependencies = [' in {TARGET}, found {count}")

    backup = TARGET.with_suffix(f".toml.bak.{int(time.time())}")
    shutil.copy2(TARGET, backup)
    patched = text.replace(ANCHOR, ANCHOR + ENTRY, 1)

    # Prove it is still valid TOML before leaving it in place; a broken pyproject.toml
    # breaks every build, not just this feature.
    try:
        parsed = tomllib.loads(patched)
    except tomllib.TOMLDecodeError as exc:
        shutil.copy2(backup, TARGET)
        die(f"patched file is not valid TOML ({exc}); the original has been restored")

    deps = parsed.get("project", {}).get("dependencies", [])
    if not any(dep.startswith(PACKAGE) for dep in deps):
        shutil.copy2(backup, TARGET)
        die(f"{PACKAGE} did not land in project.dependencies; the original has been restored")

    TARGET.write_text(patched)
    print(f"patched  {TARGET}  ({PACKAGE} added to project.dependencies)")
    print(f"backup   {backup}")


if __name__ == "__main__":
    main()
