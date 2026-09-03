#!/usr/bin/env python3
"""Saved reports carry the category filter too - the drift guard caught this, correctly.

WHAT HAPPENED
-------------
category-filter.py added ``categories`` to MetricFilters. reports_service keeps its own
tuple of the narrowing dimensions a SAVED report round-trips, and an import-time assertion
holds the two in lockstep:

    assert set(_LIST_FILTER_FIELDS) | {"date_from", "date_to", "compare", "platform"} == set(
        MetricFilters.model_fields
    ), "reports_service._LIST_FILTER_FIELDS is out of sync with MetricFilters"

I added the field and not the tuple, so the module refused to import and the whole backend
suite failed at collection. That guard is exactly right and it did its job: without it, a
report saved with a category filter would have re-run WITHOUT it - quietly returning more
data than the person who saved it had chosen, which for a shared report means showing rows
the recipient's saved view never asked for. A loud import failure is much the better
outcome. Nothing reached the containers; ship.sh stops at the gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
SERVICE = ROOT / "backend/app/services/reports_service.py"
TEST = ROOT / "backend/tests/test_report_category_filter.py"

OLD = '    "apple_accounts",\n    "packages",\n    "bundles",\n)'
NEW = '    "apple_accounts",\n    "packages",\n    "bundles",\n    "categories",\n)'

TEST_SRC = '''"""A saved report keeps its category filter - it must never re-run wider than it was saved.

The import-time drift guard in reports_service is the mechanism; this is the behaviour that
guard exists to protect. A report saved with a category filter that came back without one
would return more data than the person who saved it chose - and for a SHARED report, more
than the recipient's own view ever asked for.
"""

from __future__ import annotations

from typing import Any

from app.services.reports_service import _LIST_FILTER_FIELDS, metric_filters_from_dict


def _saved(**extra: Any) -> dict[str, Any]:
    return {"date_from": "2026-01-01", "date_to": "2026-01-31", **extra}


def test_a_saved_category_filter_survives_the_round_trip() -> None:
    filters = metric_filters_from_dict(_saved(categories=["Puzzle", "Finance"]))
    assert filters.categories == ["Puzzle", "Finance"]


def test_a_report_saved_without_one_stays_unfiltered() -> None:
    assert metric_filters_from_dict(_saved()).categories == []


def test_categories_is_one_of_the_dimensions_reports_round_trip() -> None:
    # The tuple is what the builder iterates; a dimension missing from it is silently
    # dropped rather than rejected, which is the failure mode worth pinning.
    assert "categories" in _LIST_FILTER_FIELDS


def test_every_narrowing_dimension_round_trips_not_just_this_one() -> None:
    saved = _saved(**{field: [f"{field}-value"] for field in _LIST_FILTER_FIELDS})
    filters = metric_filters_from_dict(saved)
    for field in _LIST_FILTER_FIELDS:
        assert getattr(filters, field) == [f"{field}-value"], field
'''


def main() -> int:
    if not SERVICE.exists():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1
    text = SERVICE.read_text()
    if '"categories",\n)' in text:
        print("Already applied - left alone.")
        TEST.write_text(TEST_SRC)
        print(f"  - {TEST}: refreshed")
        return 0
    if text.count(OLD) != 1:
        print(
            "NOTHING WAS WRITTEN - expected exactly 1 match, found "
            f"{text.count(OLD)} for the _LIST_FILTER_FIELDS tail.",
            file=sys.stderr,
        )
        return 1
    SERVICE.write_text(text.replace(OLD, NEW, 1))
    TEST.write_text(TEST_SRC)
    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    print(f"  - {SERVICE}: categories joins _LIST_FILTER_FIELDS")
    print(f"  - {TEST}: four cases, incl. one covering EVERY dimension so the next")
    print("    new filter fails there rather than at import time")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
