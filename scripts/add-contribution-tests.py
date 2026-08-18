#!/usr/bin/env python3
"""Tests for /metrics/contribution - the endpoint ships with coverage, not after.

Three cases, chosen for what would actually break:

1. The arithmetic. Grouped by pod over the seeded June window, the window BEFORE it has
   no rows, so every entity is a pure gain whose delta equals its current value and whose
   change percent is null. That pins the current-vs-previous maths without hard-coding a
   single seeded total - if previous_period ever drifts, the deltas stop matching and this
   fails, and it keeps failing for the right reason if someone adds a row to the fixture.

2. covered_delta equals the sum of the returned rows. It is reported so the UI can say
   "these N explain X% of the move" honestly; if it silently became the overall total
   instead, that sentence would start lying and nothing else would notice.

3. RBAC: a viewer (store_installs only) asking for a revenue metric gets 400, not data.
   The gate is _validate_metrics inside the query builder, so this really asserts that
   contribution inherits the same column RBAC as every other metrics route rather than
   having quietly opened a new door to the same numbers.

APPENDED at end of file, on purpose. An earlier version of this script anchored on a
neighbouring test function and aborted on a tree that did not have it - test files are
exactly the files that differ most between branches, and pytest does not care about
order. The block is also self-contained: its own date range, its own auth helper, and a
plain float comparison instead of pytest.approx, so it depends on nothing in the file
above it except the MetricsEnv fixture type that every test there already uses.

Idempotent. Tests only - no runtime code, nothing to migrate.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS = Path("backend/tests/test_metrics_api.py")

ADDITION = '''

# ── /metrics/contribution ─────────────────────────────────────────────────────
# Self-contained on purpose (own range, own auth helper): appended blocks must not
# depend on names defined above them, which differ between branches.
_CONTRIB_RANGE = {"from": "2026-06-01", "to": "2026-06-30"}


def _contrib_auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def test_contribution_reports_movers_and_arithmetic(metrics_env: MetricsEnv) -> None:
    """Deltas must reconcile with the previous window, or the feature is decorative."""
    response = await metrics_env.client.get(
        "/api/v1/metrics/contribution",
        params={**_CONTRIB_RANGE, "group_by": "pod", "metric": "store_total_installs"},
        headers=_contrib_auth("admin"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["metric"] == "store_total_installs"
    assert body["group_by"] == "pod"

    # The window before the seeded June rows is empty, so every pod is a pure gain:
    # delta IS current, and there is nothing to have fallen. Asserted as a RELATION
    # rather than against a hard-coded total, so adding a fixture row cannot make this
    # fail for the wrong reason - but drifting the previous-period window still does.
    assert body["gainers"], "expected at least one pod to have moved"
    assert body["losers"] == []
    for row in body["gainers"]:
        assert row["previous"] == 0.0
        assert row["delta"] == row["current"]
        # No growth from a zero base - a percentage there is a division artefact.
        assert row["change_pct"] is None


async def test_contribution_covered_delta_sums_returned_rows(metrics_env: MetricsEnv) -> None:
    """covered_delta drives "these N explain X% of the move" - it must be exactly that."""
    response = await metrics_env.client.get(
        "/api/v1/metrics/contribution",
        params={**_CONTRIB_RANGE, "group_by": "pod", "metric": "store_total_installs"},
        headers=_contrib_auth("admin"),
    )
    body = response.json()
    returned = sum(row["delta"] for row in body["gainers"] + body["losers"])
    assert abs(body["covered_delta"] - returned) < 1e-9


async def test_contribution_enforces_metric_rbac(metrics_env: MetricsEnv) -> None:
    """A viewer has store_installs only; asking for revenue here must be refused.

    Contribution reaches the same numbers as /breakdown, so it has to inherit the same
    column RBAC - an endpoint that skipped it would be a new door to old data.
    """
    response = await metrics_env.client.get(
        "/api/v1/metrics/contribution",
        params={**_CONTRIB_RANGE, "group_by": "app", "metric": "total_revenue_usd"},
        headers=_contrib_auth("viewer"),
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

    # The ONLY thing the appended block borrows from the file above it.
    if "MetricsEnv" not in text:
        die(f"{TESTS}: MetricsEnv is not imported - this is not the metrics API test module")

    TESTS.write_text(text.rstrip("\n") + "\n" + ADDITION)
    print(f"patched {TESTS}: 3 contribution tests appended (maths, coverage, RBAC)")


if __name__ == "__main__":
    main()
