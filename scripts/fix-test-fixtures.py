#!/usr/bin/env python3
"""Two test-side corrections, both recording an intentional change - not silencing one.

Stated plainly because "make the test green" is how real regressions get buried: neither
of these weakens an assertion. One records a table that genuinely exists now; the other
makes a fixture match the shape of real rows.

1. tests/test_models_metadata.py - add ``smtp_config`` to EXPECTED_TABLES.
   That test asserts the ORM metadata equals an explicit table list, which is exactly
   the guard you want against a model appearing by accident. The admin-editable SMTP
   settings table is deliberate, has its own migration, and is registered in
   app/models/__init__.py - so the list is what is out of date, and leaving it stale
   would mean the next accidental model slips in unnoticed behind an already-red test.

2. tests/conftest.py - seed ``rpt_gross_revenue_usd`` alongside ``total_revenue_usd``.
   pacing_service now reads the REPORTED figure (owner decision: YTD/MTD must reconcile
   with the Revenue KPI card, which has always shown rpt_gross_revenue_usd). The fixture
   seeds only total_revenue_usd, so pacing correctly computed 0 from rows that, in
   production, would carry both columns. The fix is to make the fixture realistic - NOT
   to assert 0, which would enshrine the fixture's gap as expected behaviour and blind
   the test to a genuine pacing failure. Values are mirrored, so the existing 1080
   assertion keeps its original meaning.

Anchored: every anchor must appear the expected number of times or nothing is written.
Idempotent. Affects tests only - no runtime behaviour, no migration.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

META_TEST = Path("backend/tests/test_models_metadata.py")
CONFTEST = Path("backend/tests/conftest.py")

TABLES_ANCHOR = '    "dynamic_columns",\n}\n'
TABLES_NEW = '    "dynamic_columns",\n    "smtp_config",\n}\n'

# Every seeded revenue value, so the mirrored column carries the same figure.
SEED_RE = re.compile(r'^(\s*)"total_revenue_usd": ([0-9.]+),$', re.M)


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    for path in (META_TEST, CONFTEST):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    meta = META_TEST.read_text()
    conf = CONFTEST.read_text()
    wrote = False

    if '"smtp_config"' in meta:
        print(f"{META_TEST}: already lists smtp_config")
    else:
        if meta.count(TABLES_ANCHOR) != 1:
            die(f"{META_TEST}: expected exactly one EXPECTED_TABLES terminator")
        META_TEST.write_text(meta.replace(TABLES_ANCHOR, TABLES_NEW, 1))
        print(f"patched {META_TEST}: smtp_config recorded as an expected table")
        wrote = True

    if "rpt_gross_revenue_usd" in conf:
        print(f"{CONFTEST}: already seeds the reported metric")
    else:
        matches = SEED_RE.findall(conf)
        if not matches:
            die(f"{CONFTEST}: found no seeded total_revenue_usd rows to mirror")
        conf = SEED_RE.sub(
            lambda m: f'{m.group(1)}"total_revenue_usd": {m.group(2)},\n'
            f'{m.group(1)}"rpt_gross_revenue_usd": {m.group(2)},',
            conf,
        )
        CONFTEST.write_text(conf)
        print(f"patched {CONFTEST}: mirrored {len(matches)} row(s) into rpt_gross_revenue_usd")
        wrote = True

    if not wrote:
        print("already corrected - nothing to do")


if __name__ == "__main__":
    main()
