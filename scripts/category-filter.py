#!/usr/bin/env python3
"""The app-category filter - the one item from the owner's list that is genuinely unbuilt.

Recon against the deployed tree found app_category everywhere EXCEPT where it would let
anyone filter by it: it is in the metric registry, the Postgres DDL, the BigQuery view,
dim_app, App Detail and the glossary - but not in MetricFilters, not in get_filters, not
in the query builder's narrowing conditions, and not in the filter-options endpoint. So
the column exists on every row and no one can ask a question with it.

This adds it the same way every other narrowing dimension is added, end to end:
  schema field -> input cap -> query parameter -> SQL condition -> options dropdown -> UI.

It is a NARROWING filter only. Row scope is applied first and independently, exactly as
the MetricFilters docstring promises; a category the caller cannot see stays invisible.

Anchors are taken verbatim from the deployed files (recon passes one and two), not from
memory. Every anchor must match exactly once or NOTHING is written.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
TEST = ROOT / "backend/tests/test_category_filter.py"

report: list[str] = []

# (path, label, old, new, expected occurrences)
EDITS: list[tuple[str, str, str, str, int]] = [
    # ── the filter model ──────────────────────────────────────────────────────────
    (
        "backend/app/schemas/metrics.py",
        "categories joins the filter model",
        "    bundles: list[str] = []  # ios_bundle_id",
        "    bundles: list[str] = []  # ios_bundle_id\n"
        "    categories: list[str] = []  # app_category (store category, e.g. Puzzle)",
        1,
    ),
    (
        "backend/app/schemas/metrics.py",
        "and is capped like every other dimension",
        '            ("bundles", self.bundles),\n        )',
        '            ("bundles", self.bundles),\n'
        '            ("categories", self.categories),\n        )',
        1,
    ),
    # ── the query parameter ───────────────────────────────────────────────────────
    (
        "backend/app/api/v1/metrics.py",
        "accepted as a query parameter",
        "    bundles: Annotated[list[str] | None, Query()] = None,\n) -> MetricFilters:",
        "    bundles: Annotated[list[str] | None, Query()] = None,\n"
        "    categories: Annotated[list[str] | None, Query()] = None,\n) -> MetricFilters:",
        1,
    ),
    (
        "backend/app/api/v1/metrics.py",
        "passed through to the model",
        "            bundles=bundles or [],\n        )",
        "            bundles=bundles or [],\n            categories=categories or [],\n        )",
        1,
    ),
    # ── saved reports round-trip it too ──────────────────────────────────────────
    # reports_service holds its own tuple of narrowing dimensions and asserts at import
    # that it matches MetricFilters exactly. Miss it and a saved report re-runs WITHOUT
    # the filter - wider than the person who saved it chose. (Learned the hard way: the
    # guard failed the whole suite at collection, which is the right way to find out.)
    (
        "backend/app/services/reports_service.py",
        "categories joins the dimensions a saved report keeps",
        '    "apple_accounts",\n    "packages",\n    "bundles",\n)',
        '    "apple_accounts",\n    "packages",\n    "bundles",\n    "categories",\n)',
        1,
    ),
    # ── the options dropdown ──────────────────────────────────────────────────────
    (
        "backend/app/api/v1/meta.py",
        "offered as a dropdown, cascading like the rest",
        '    ("hous", "hou", "hou"),\n]',
        '    ("hous", "hou", "hou"),\n    ("categories", "app_category", "categories"),\n]',
        1,
    ),
    # ── the frontend ──────────────────────────────────────────────────────────────
    (
        "frontend/components/filters/dimensions.ts",
        "a Category control beside the others",
        '    { key: "podOwners", label: "Pod Owner", options: toOptions(data?.pod_owners) },',
        '    { key: "podOwners", label: "Pod Owner", options: toOptions(data?.pod_owners) },\n'
        '    { key: "categories", label: "Category", options: toOptions(data?.categories) },',
        1,
    ),
    (
        "frontend/lib/filters.ts",
        "the filter state carries it",
        "  podOwners: string[];",
        "  podOwners: string[];\n  categories: string[];",
        1,
    ),
    (
        "frontend/lib/filters.ts",
        "it counts as an active filter",
        '  "podOwners",',
        '  "podOwners",\n  "categories",',
        1,
    ),
    (
        "frontend/lib/filters.ts",
        "it defaults to unfiltered",
        "    podOwners: [],",
        "    podOwners: [],\n    categories: [],",
        1,
    ),
    (
        "frontend/lib/filters.ts",
        "it survives a page reload (URL state)",
        '    podOwners: splitList(params.get("podOwners")),',
        '    podOwners: splitList(params.get("podOwners")),\n'
        '    categories: splitList(params.get("categories")),',
        1,
    ),
    (
        "frontend/lib/filters.ts",
        "and is written back to the URL",
        '  if (filters.podOwners.length) params.set("podOwners", filters.podOwners.join(","));',
        '  if (filters.podOwners.length) params.set("podOwners", filters.podOwners.join(","));\n'
        '  if (filters.categories.length) params.set("categories", filters.categories.join(","));',
        1,
    ),
    (
        "frontend/lib/filters.ts",
        "and reaches the API under the name the backend accepts",
        "    pod_owners: filters.podOwners,",
        "    pod_owners: filters.podOwners,\n    categories: filters.categories,",
        1,
    ),
    (
        "frontend/lib/api-hooks.ts",
        "the options payload may carry categories (optional: an older backend simply omits it)",
        "  pod_owners: string[];",
        "  pod_owners: string[];\n  categories?: string[];",
        2,
    ),
]

TEST_SRC = '''"""The app-category filter: plumbed end to end, capped, and actually applied.

The cap tests are the important ones - a new dimension that skips the input cap is a
free way to send a query with ten thousand IN values. The last test reads the query
builder's own source: the field can exist, be accepted, and reach the builder while the
SQL quietly ignores it, and that failure looks exactly like success from the outside.
"""

from __future__ import annotations

import inspect
from datetime import date

import pytest
from app.schemas.metrics import MAX_FILTER_VALUES, MetricFilters
from app.services import query_builder
from pydantic import ValidationError


def _filters(**kw: object) -> MetricFilters:
    return MetricFilters(  # type: ignore[arg-type]
        date_from=date(2026, 1, 1), date_to=date(2026, 1, 7), **kw
    )


def test_no_category_filter_means_unfiltered() -> None:
    assert _filters().categories == []


def test_categories_are_accepted_as_a_narrowing_filter() -> None:
    assert _filters(categories=["Puzzle", "Finance"]).categories == ["Puzzle", "Finance"]


def test_categories_are_capped_like_every_other_dimension() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _filters(categories=[f"c{i}" for i in range(MAX_FILTER_VALUES + 1)])
    assert "categories" in str(excinfo.value)


def test_the_category_condition_is_actually_in_the_sql() -> None:
    source = inspect.getsource(query_builder.QueryBuilder._base_filters)
    assert "params.categories" in source
    assert "app_category" in source
'''


def window(path: Path, needle: str) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - 4), min(len(lines), i + 10)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: anchor not found"


def category_column() -> str:
    """Filter on the App-Master-corrected column when there is one, else the raw fact column.

    hou and pod_owner go through live_column so an App Master edit re-attributes history;
    developer and the account columns do not, because they are not App Master's to correct.
    Which group app_category is in is a fact about the deployed live_attribution module, so
    it is read rather than assumed.
    """
    live = ROOT / "backend/app/services/live_attribution.py"
    if live.exists() and "app_category" in live.read_text():
        return 'live_column("app_category")'
    return "FACT_TABLE.c.app_category"


def patch_filter_options(text: str) -> tuple[str, str] | None:
    """Add ``categories`` to FilterOptions, matching whatever default style it already uses.

    Anchored structurally, not literally: the class is a long list of near-identical
    ``x: list[str]`` lines and picking one by hand is how an anchor ends up ambiguous.
    """
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("class FilterOptions")), None)
    if start is None:
        return None
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith(("class ", "def "))),
        len(lines),
    )
    last = None
    for i in range(start + 1, end):
        if re.match(r"^\s+\w+: list\[str\]", lines[i]):
            last = i
    if last is None:
        return None
    tail = lines[last].split("list[str]", 1)[1]  # reuse " = []" or " = Field(...)" verbatim
    lines.insert(last + 1, f"    categories: list[str]{tail}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), lines[last + 1]


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    if "categories: Annotated[" in (ROOT / "backend/app/api/v1/metrics.py").read_text():
        print("Already applied - left alone.")
        if TEST.parent.is_dir():
            TEST.write_text(TEST_SRC)
            print(f"  - {TEST}: refreshed")
        return 0

    column = category_column()
    edits = list(EDITS)
    edits.append(
        (
            "backend/app/services/query_builder.py",
            f"the SQL condition, on {column}",
            "        if params.bundles:\n"
            "            conditions.append(FACT_TABLE.c.ios_bundle_id.in_(params.bundles))\n"
            "        return conditions",
            "        if params.bundles:\n"
            "            conditions.append(FACT_TABLE.c.ios_bundle_id.in_(params.bundles))\n"
            "        if params.categories:\n"
            f"            conditions.append({column}.in_(params.categories))\n"
            "        return conditions",
            1,
        )
    )

    planned: dict[Path, str] = {}
    problems: list[str] = []
    for rel, label, old, new, expected in edits:
        path = ROOT / rel
        if not path.exists():
            problems.append(f"  [{label}] {rel}: file missing")
            continue
        text = planned.get(path, path.read_text())
        found = text.count(old)
        if found != expected:
            problems.append(
                f"  [{label}] {rel}: expected {expected} match(es), found {found}\n"
                + window(path, old.splitlines()[0].strip()[:56])
            )
            continue
        planned[path] = text.replace(old, new, expected)

    schema = ROOT / "backend/app/schemas/metrics.py"
    result = patch_filter_options(planned.get(schema, schema.read_text()))
    if result is None:
        problems.append(
            "  [FilterOptions] backend/app/schemas/metrics.py: could not find the class,"
            " or it has no list[str] fields to sit beside"
        )
    else:
        planned[schema], added = result

    if problems:
        print("NOTHING WAS WRITTEN - a filter half-applied is worse than absent: the bar")
        print("would show an active filter over unfiltered numbers. Mismatches:\n")
        for p in problems:
            print(p)
        return 1

    for path, text in planned.items():
        path.write_text(text)
        report.append(f"[filter] {path}")
    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: four cases incl. proof the SQL condition exists")

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    print(f"\n  SQL condition uses: {column}")
    print(f"  FilterOptions gained: {added.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
