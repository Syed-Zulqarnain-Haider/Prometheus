#!/usr/bin/env python3
"""Tests for /metrics/contribution - the endpoint ships with coverage, not after.

Three cases, chosen for what would actually break:

1. The shape and the arithmetic. Grouped by pod over the seeded June window, with the
   previous window empty, every entity is a gainer whose delta equals its current
   value. That pins BOTH the response shape and the current-vs-previous maths in one
   assertion - if previous_period ever drifts, the deltas stop matching and this fails.

2. covered_delta equals the sum of the returned rows. It is reported so the UI can say
   "these N explain X% of the move" honestly; if it silently became the overall total
   instead, that sentence would start lying and nothing else would notice.

3. RBAC: a viewer (store_installs only) asking for a revenue metric gets 400, not data.
   The gate is _validate_metrics inside the query builder, so this is really asserting
   that contribution inherits the same column RBAC as every other metrics route rather
   than having quietly opened a new door to the same numbers.

Anchored: the file must contain the breakdown test the new block is placed after, and
must not already contain these tests. Idempotent. Tests only.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS = Path("backend/tests/test_metrics_api.py")

ANCHOR = "async def test_breakdown_cache_respects_metric_order(metrics_env: MetricsEnv) -> None:\n"

ADDITION = '''async def test_contribution_reports_movers_and_arithmetic(metrics_env: MetricsEnv) -> None:
    """Deltas must reconcile with the seeded numbers, or the feature is decorative."""
    response = await metrics_env.client.get(
        "/api/v1/metrics/contribution",
        params={**RANGE, "group_by": "pod", "metric": "store_total_installs"},
        headers=_auth("admin"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metric"] == "store_total_installs"
    assert body["group_by"] == "pod"

    # The window before June 1-2 has no seeded rows, so every pod is a pure gain and
    # its delta IS its current value. This pins the current-vs-previous maths: if the
    # previous-period window ever drifts, these stop matching.
    gains = {row["key"]: row for row in body["gainers"]}
    assert gains["POD_A"]["current"] == 100.0
    assert gains["POD_A"]["previous"] == 0.0
    assert gains["POD_A"]["delta"] == 100.0
    # No growth from a zero base - a percentage there would be a division artefact.
    assert gains["POD_A"]["change_pct"] is None
    assert body["losers"] == []


async def test_contribution_covered_delta_sums_returned_rows(metrics_env: MetricsEnv) -> None:
    """covered_delta drives "these N explain X% of the move" - it must be exactly that."""
    response = await metrics_env.client.get(
        "/api/v1/metrics/contribution",
        params={**RANGE, "group_by": "pod", "metric": "store_total_installs"},
        headers=_auth("admin"),
    )
    body = response.json()
    returned = sum(row["delta"] for row in body["gainers"] + body["losers"])
    assert body["covered_delta"] == pytest.approx(returned)


async def test_contribution_enforces_metric_rbac(metrics_env: MetricsEnv) -> None:
    """A viewer has store_installs only; asking for revenue here must be refused.

    Contribution reaches the same numbers as /breakdown, so it has to inherit the same
    column RBAC - an endpoint that skipped it would be a new door to old data.
    """
    response = await metrics_env.client.get(
        "/api/v1/metrics/contribution",
        params={**RANGE, "group_by": "app", "metric": "total_revenue_usd"},
        headers=_auth("viewer"),
    )
    assert response.status_code == 400


'''


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not TESTS.exists():
        die(f"{TESTS} not found - run from the repository root")

    text = TESTS.read_text()
    if "test_contribution_reports_movers_and_arithmetic" in text:
        print("already tested - nothing to do")
        return
    if text.count(ANCHOR) != 1:
        die(f"{TESTS}: expected exactly one {ANCHOR.strip()!r}, found {text.count(ANCHOR)}")
    if "import pytest" not in text:
        die(f"{TESTS}: pytest is not imported - needed for approx")

    TESTS.write_text(text.replace(ANCHOR, ADDITION + ANCHOR, 1))
    print(f"patched {TESTS}: 3 contribution tests (shape+maths, coverage, RBAC)")


if __name__ == "__main__":
    main()
