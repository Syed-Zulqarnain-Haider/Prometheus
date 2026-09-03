#!/usr/bin/env python3
"""The Schema diff now reflects the schema you actually adopted - "update the schema and it
should show the latest schema".

THE FINDING
-----------
The Integration page's Schema diff compares the live BigQuery view against
``expected_bq_schema()`` - and that function reads the STATIC registry only:

    return {c.name: c.bq_type for c in REGISTRY if c.source_expr is None}

Meanwhile "Match Database & BigQuery Schema" adopts new view columns into ``_DYNAMIC`` and
everything else - RBAC, response models, the query builder - reads ``effective_registry()``,
which is static + dynamic. So the moment you add a column to the view and reconcile it, the
diff STILL lists it as an extra, forever. Nothing is stale in BigQuery or in Redis: the
diff's idea of "expected" simply never learned about adoption. One line closes it.

The sync job's own copy of expected_bq_schema (backend/sync/) is deliberately untouched: the
loader only ever loads static columns, so static is the right expectation there.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
REGISTRY_FILE = ROOT / "backend/app/core/metric_registry.py"
TEST = ROOT / "backend/tests/test_schema_diff_expected.py"

OLD = "    return {c.name: c.bq_type for c in REGISTRY if c.source_expr is None}"
NEW = (
    "    # The EFFECTIVE registry - static plus adopted dynamic columns - so a column you\n"
    "    # reconcile from the view stops showing as an extra the moment it is adopted.\n"
    "    return {c.name: c.bq_type for c in effective_registry() if c.source_expr is None}"
)

TEST_SRC = '''"""The Schema diff's expectation follows adoption.

A column adopted through schema reconcile lives in the dynamic set. If the diff's expected
side reads only the static registry, that column is reported as an extra forever - which is
exactly what the owner saw. These pin the expectation to the effective registry.
"""

from __future__ import annotations

from app.core.metric_registry import (
    REGISTRY,
    Col,
    Group,
    expected_bq_schema,
    set_dynamic_columns,
)


def test_an_adopted_dynamic_column_is_expected_by_the_diff() -> None:
    try:
        set_dynamic_columns(
            [Col("adopted_metric", "FLOAT64", "NUMERIC(18,4)", Group.UNCLASSIFIED)]
        )
        assert expected_bq_schema()["adopted_metric"] == "FLOAT64"
    finally:
        set_dynamic_columns([])


def test_dropping_the_dynamic_column_drops_the_expectation() -> None:
    set_dynamic_columns([Col("gone_again", "INT64", "BIGINT", Group.UNCLASSIFIED)])
    set_dynamic_columns([])
    assert "gone_again" not in expected_bq_schema()


def test_static_pass_through_columns_are_still_expected() -> None:
    set_dynamic_columns([])
    expected = expected_bq_schema()
    for col in REGISTRY:
        if col.source_expr is None:
            assert expected[col.name] == col.bq_type


def test_computed_columns_are_still_never_expected_in_the_source() -> None:
    # Computed columns are produced by the sync, not read from the view; expecting them
    # would flag every one of them as missing.
    set_dynamic_columns([])
    expected = expected_bq_schema()
    for col in REGISTRY:
        if col.source_expr is not None:
            assert col.name not in expected
'''


def main() -> int:
    if not REGISTRY_FILE.exists():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1
    text = REGISTRY_FILE.read_text()
    if "for c in effective_registry() if c.source_expr is None" in text:
        print("Already applied - left alone.")
        TEST.write_text(TEST_SRC)
        print(f"  - {TEST}: refreshed")
        return 0
    if text.count(OLD) != 1:
        print(
            f"NOTHING WAS WRITTEN - expected exactly 1 match, found {text.count(OLD)}",
            file=sys.stderr,
        )
        return 1
    if "def effective_registry" not in text:
        print("NOTHING WAS WRITTEN - effective_registry() is not defined here.", file=sys.stderr)
        return 1
    REGISTRY_FILE.write_text(text.replace(OLD, NEW, 1))
    TEST.write_text(TEST_SRC)
    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    print(f"  - {REGISTRY_FILE}: expected_bq_schema reads the effective registry")
    print(f"  - {TEST}: four cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
