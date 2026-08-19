#!/usr/bin/env python3
"""Three shared-session bugs, plus one that made a panel permanently unusable.

All three backend bugs are the same mistake: a loop that promises "one failure never stops
the rest", wrapped around a try/except that catches the error but does NOT roll back. A
SQLAlchemy session is left in a FAILED TRANSACTION when a statement raises, and every later
statement on it raises until somebody rolls it back - so the first failure quietly takes
every later iteration with it, reporting an unrelated-looking error each time.

(The daily pass had the same bug; that one already shipped as fix-daily-pass-isolation.
This patch is the two places it did not cover, plus the annotations panel.)

Strict anchors: every anchor is checked in every file BEFORE a byte is written, so a
mismatch aborts having changed nothing. Each file carries its own marker, so re-running is
safe and a file that is already fixed is left alone.
"""

import sys
from pathlib import Path

EDITS: list[tuple[Path, str, list[tuple[str, str]]]] = []

# -- B. anomaly_service: "one bad account never stops the rest" was not true ------
EDITS.append((
    Path("backend/app/services/anomaly_service.py"),
    "could not roll back after user",
    [(
        '            log.exception("watchlist alert failed for user %s", user_id)\n',
        '            log.exception("watchlist alert failed for user %s", user_id)\n'
        '            # ROLL BACK, or the promise above is false: the session is left in a\n'
        '            # failed transaction and the first bad account poisons every user after it.\n'
        '            try:\n'
        '                await db.rollback()\n'
        '            except Exception:  # noqa: BLE001 - nothing useful is left to do\n'
        '                log.exception("could not roll back after user %s", user_id)\n',
    )],
))

# -- C. cache_warm: six producers share one session ------------------------------
EDITS.append((
    Path("backend/app/services/cache_warm.py"),
    "could not roll back the cache-warm session",
    [(
        '                log.exception("cache warm failed for %s", route)\n',
        '                log.exception("cache warm failed for %s", route)\n'
        '                # All six producers share the ONE session opened above; without this\n'
        '                # rollback the first failure silently takes the other five with it.\n'
        '                try:\n'
        '                    await db.rollback()\n'
        '                except Exception:  # noqa: BLE001 - nothing useful is left to do\n'
        '                    log.exception("could not roll back the cache-warm session")\n',
    )],
))

# -- D. annotations panel: a scoped user could never save a note -----------------
# scopeType starts as "all". A user whose scopes do not include "all" cannot write that,
# so the select rendered the first WRITABLE option while the state still said "all": the
# value field (gated on !== "all") stayed hidden, and every save 403'd, permanently.
EDITS.append((
    Path("frontend/components/overview/annotations-panel.tsx"),
    "effectiveScopeType",
    [
        (
            """  const suggestions = scopes
    .filter((s) => s.scope_type === scopeType && s.scope_value)""",
            """  // DERIVED, not trusted from state: scopeType starts as "all", which a scoped user
  // cannot write, so the select showed "Pod" while the state said "all", the value field
  // (gated on !== "all") stayed hidden, and every save 403'd with no way to recover.
  const effectiveScopeType = writableTypes.some((t) => t.id === scopeType)
    ? scopeType
    : (writableTypes[0]?.id ?? "all");

  const suggestions = scopes
    .filter((s) => s.scope_type === effectiveScopeType && s.scope_value)""",
        ),
        (
            '        scope_type: scopeType,\n'
            '        scope_value: scopeType === "all" ? null : scopeValue.trim() || null,',
            '        scope_type: effectiveScopeType,\n'
            '        scope_value: effectiveScopeType === "all" ? null : scopeValue.trim() || null,',
        ),
        (
            '                aria-label="Applies to"\n                value={scopeType}',
            '                aria-label="Applies to"\n                value={effectiveScopeType}',
        ),
        ('            {scopeType !== "all" && (', '            {effectiveScopeType !== "all" && ('),
    ],
))



# -- the regression tests these fixes exist for ----------------------------------
# Both fail without the rollbacks above (the cache warm drops from 8 entries to 0), which
# is the point: they are the reason the rollbacks stay.
TESTS = "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"


def write_tests() -> None:
    import base64
    import io
    import tarfile

    buffer = io.BytesIO(base64.b64decode(TESTS))
    with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
        names = tar.getnames()
        tar.extractall(Path("."))
    for name in names:
        print(f"wrote {name}")


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


plan: list[tuple[Path, str, list[tuple[str, str]]]] = []
for path, marker, pairs in EDITS:
    if not path.exists():
        die(f"{path} not found - run this from the repository root")
    text = path.read_text()
    if marker in text:
        print(f"{path.name}: already fixed")
        continue
    for anchor, _ in pairs:
        found = text.count(anchor)
        if found != 1:
            die(
                f"{path.name}: expected exactly 1 of {anchor.strip()[:50]!r}, found {found}"
            )
    plan.append((path, text, pairs))

if not plan:
    print("all three already fixed - nothing to do")
else:
    for path, text, pairs in plan:
        for anchor, replacement in pairs:
            text = text.replace(anchor, replacement, 1)
        path.write_text(text)
        print(f"fixed {path}")
write_tests()
print("done")
