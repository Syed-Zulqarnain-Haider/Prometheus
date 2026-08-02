"""Budget pacing (target vs actual + projection) and linear forecasting — both RBAC-scoped."""

from __future__ import annotations

from app.services import forecast_service

from tests.conftest import MetricsEnv


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def _set_month_target(env: MetricsEnv, year: int, month: int, target: float) -> None:
    resp = await env.client.put(
        "/api/v1/admin/targets",
        json={
            "period_type": "month",
            "period_year": year,
            "period_month": month,
            "target_usd": target,
        },
        headers=_auth("admin"),
    )
    assert resp.status_code == 200, resp.text


# ── pacing ───────────────────────────────────────────────────────────────────
async def test_pacing_full_past_month(metrics_env: MetricsEnv) -> None:
    # June 2026 is fully in the past (today is 2026-08-02 in this repo), so pacing reflects the
    # complete month: actual = 600+400+70+10 = 1080 across the admin's (all-scope) June rows.
    await _set_month_target(metrics_env, 2026, 6, 2000.0)
    resp = await metrics_env.client.get(
        "/api/v1/metrics/pacing?year=2026&month=6", headers=_auth("admin")
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_usd"] == 2000.0
    assert body["actual_usd"] == 1080.0
    assert body["days_elapsed"] == 30 and body["days_in_month"] == 30
    assert body["projected_usd"] == 1080.0  # month complete → projection == actual
    assert abs(body["attainment_pct"] - 0.54) < 1e-6


async def test_pacing_target_only_when_revenue_not_permitted(metrics_env: MetricsEnv) -> None:
    # A viewer (store_installs only) can't see revenue → actual/projection are null, target shows.
    await _set_month_target(metrics_env, 2026, 6, 2000.0)
    resp = await metrics_env.client.get(
        "/api/v1/metrics/pacing?year=2026&month=6", headers=_auth("viewer")
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_usd"] == 2000.0
    assert body["actual_usd"] is None
    assert body["projected_usd"] is None


async def test_pacing_no_target_returns_nulls(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get(
        "/api/v1/metrics/pacing?year=2026&month=5", headers=_auth("admin")
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_usd"] is None
    assert body["attainment_pct"] is None


# ── forecast ─────────────────────────────────────────────────────────────────
async def test_forecast_returns_history_and_projection(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get(
        "/api/v1/metrics/forecast",
        params={
            "date_from": "2026-06-01",
            "date_to": "2026-06-02",
            "metric": "total_revenue_usd",
            "horizon": 3,
        },
        headers=_auth("admin"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] == "linear"
    assert len(body["history"]) == 2
    # June 1 total = 680 (600+70+10), June 2 = 400.
    assert body["history"][0]["value"] == 680.0
    assert len(body["forecast"]) == 3
    assert body["forecast"][0]["date"] == "2026-06-03"
    # Values are floored at zero (a steep downward trend can't project negative revenue).
    assert all(p["value"] >= 0 for p in body["forecast"])


async def test_forecast_forbidden_metric_is_400(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get(
        "/api/v1/metrics/forecast",
        params={
            "date_from": "2026-06-01",
            "date_to": "2026-06-02",
            "metric": "total_revenue_usd",  # not permitted for a viewer
            "horizon": 3,
        },
        headers=_auth("viewer"),
    )
    assert resp.status_code == 400


def test_linear_fit_recovers_a_known_line() -> None:
    # y = 2x + 1 → slope 2, intercept 1.
    slope, intercept = forecast_service._linear_fit([1.0, 3.0, 5.0, 7.0])
    assert abs(slope - 2.0) < 1e-9
    assert abs(intercept - 1.0) < 1e-9
