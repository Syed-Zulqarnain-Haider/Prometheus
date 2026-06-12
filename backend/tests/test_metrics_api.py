"""Integration tests for the metrics/apps/meta API, per role (RBAC matrix).

Covers: auth required, per-role column RBAC, period-ratio recomputation (incl.
zero-denominator → null), scope narrowing, /apps scoping, /apps/{key} 404,
/meta/freshness, caching, and the rate limiter.
"""

from typing import Any

import pytest
from app.models import AuditLog
from sqlalchemy import func, select

from tests.conftest import MetricsEnv

RANGE = {"date_from": "2026-06-01", "date_to": "2026-06-02"}


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


# Representative keys that MUST / MUST NOT appear in summary.current, per role.
ROLE_EXPECTATIONS: dict[str, tuple[set[str], set[str]]] = {
    "admin": ({"store_total_installs", "total_revenue_usd", "roas", "adjust_installs"}, set()),
    "executive": ({"store_total_installs", "total_revenue_usd", "roas", "adjust_installs"}, set()),
    "pod_owner": ({"store_total_installs", "total_revenue_usd", "roas", "adjust_installs"}, set()),
    "marketing": ({"store_total_installs", "total_revenue_usd", "roas"}, {"adjust_installs"}),
    "finance": ({"store_total_installs", "total_revenue_usd", "roas"}, {"adjust_installs"}),
    "viewer": ({"store_total_installs"}, {"total_revenue_usd", "roas", "adjust_installs"}),
}


async def test_unauthenticated_rejected(metrics_env: MetricsEnv) -> None:
    response = await metrics_env.client.get("/api/v1/metrics/summary", params=RANGE)
    assert response.status_code == 401


@pytest.mark.parametrize("role", list(ROLE_EXPECTATIONS))
async def test_summary_columns_per_role(metrics_env: MetricsEnv, role: str) -> None:
    response = await metrics_env.client.get(
        "/api/v1/metrics/summary", params=RANGE, headers=_auth(role)
    )
    assert response.status_code == 200
    current = response.json()["current"]
    present, absent = ROLE_EXPECTATIONS[role]
    assert present <= set(current), f"{role} missing {present - set(current)}"
    assert set(current).isdisjoint(absent), f"{role} leaked {set(current) & absent}"


async def test_summary_ratio_recomputed_from_totals(metrics_env: MetricsEnv) -> None:
    # appA only: totals rev=1000, spend=250, paid=100 -> roas 4.0, cpi 2.5.
    # (Averaging daily roas would give ~4.33 — proving period recompute.)
    response = await metrics_env.client.get(
        "/api/v1/metrics/summary",
        params={**RANGE, "apps": "appA"},
        headers=_auth("admin"),
    )
    current = response.json()["current"]
    assert current["total_revenue_usd"] == 1000.0
    assert current["roas"] == 4.0
    assert current["cpi"] == 2.5


async def test_summary_zero_denominator_is_null(metrics_env: MetricsEnv) -> None:
    response = await metrics_env.client.get(
        "/api/v1/metrics/summary",
        params={**RANGE, "apps": "appZ"},
        headers=_auth("admin"),
    )
    current = response.json()["current"]
    assert current["roas"] is None  # revenue but zero spend
    assert current["cpi"] is None  # zero installs


async def test_scope_narrows_rows(metrics_env: MetricsEnv) -> None:
    admin = await metrics_env.client.get(
        "/api/v1/metrics/summary", params=RANGE, headers=_auth("admin")
    )
    scoped = await metrics_env.client.get(
        "/api/v1/metrics/summary", params=RANGE, headers=_auth("pod_owner_scoped")
    )
    assert admin.json()["current"]["store_total_installs"] == 107  # all pods
    assert scoped.json()["current"]["store_total_installs"] == 100  # POD_A only


async def test_apps_list_scoped(metrics_env: MetricsEnv) -> None:
    admin = await metrics_env.client.get("/api/v1/apps", headers=_auth("admin"))
    scoped = await metrics_env.client.get("/api/v1/apps", headers=_auth("pod_owner_scoped"))
    admin_keys = {a["canonical_key"] for a in admin.json()["apps"]}
    scoped_keys = {a["canonical_key"] for a in scoped.json()["apps"]}
    assert admin_keys == {"appA", "appB", "appZ"}
    assert scoped_keys == {"appA", "appZ"}  # POD_B's appB excluded


async def test_app_detail_404_when_out_of_scope(metrics_env: MetricsEnv) -> None:
    ok = await metrics_env.client.get("/api/v1/apps/appA", headers=_auth("pod_owner_scoped"))
    assert ok.status_code == 200
    out = await metrics_env.client.get("/api/v1/apps/appB", headers=_auth("pod_owner_scoped"))
    assert out.status_code == 404
    assert out.json()["error"]["code"] == "not_found"
    missing = await metrics_env.client.get("/api/v1/apps/nope", headers=_auth("admin"))
    assert missing.status_code == 404


async def test_freshness(metrics_env: MetricsEnv) -> None:
    response = await metrics_env.client.get("/api/v1/meta/freshness", headers=_auth("admin"))
    assert response.status_code == 200
    body = response.json()
    assert body["last_status"] == "success"
    assert body["bq_built_at"] is not None
    assert body["rows_loaded"] == 100


async def test_timeseries(metrics_env: MetricsEnv) -> None:
    response = await metrics_env.client.get(
        "/api/v1/metrics/timeseries",
        params={**RANGE, "metrics": "store_total_installs", "bucket": "day"},
        headers=_auth("admin"),
    )
    assert response.status_code == 200
    series = response.json()["series"]
    by_day = {r["bucket"][:10]: r["store_total_installs"] for r in series}
    assert by_day == {"2026-06-01": 47.0, "2026-06-02": 60.0}


async def test_breakdown_by_pod(metrics_env: MetricsEnv) -> None:
    response = await metrics_env.client.get(
        "/api/v1/metrics/breakdown",
        params={**RANGE, "group_by": "pod", "metrics": "store_total_installs"},
        headers=_auth("admin"),
    )
    rows = response.json()["rows"]
    assert [(r["pod"], r["store_total_installs"]) for r in rows] == [
        ("POD_A", 100.0),
        ("POD_B", 7.0),
    ]


async def test_table_keyset_pagination(metrics_env: MetricsEnv) -> None:
    page1 = await metrics_env.client.get(
        "/api/v1/metrics/table",
        params={**RANGE, "sort": "store_total_installs", "limit": 2},
        headers=_auth("admin"),
    )
    body1 = page1.json()
    assert [r["canonical_key"] for r in body1["rows"]] == ["appA", "appB"]
    assert body1["next_cursor"] is not None

    page2 = await metrics_env.client.get(
        "/api/v1/metrics/table",
        params={
            **RANGE,
            "sort": "store_total_installs",
            "limit": 2,
            "cursor": body1["next_cursor"],
        },
        headers=_auth("admin"),
    )
    assert [r["canonical_key"] for r in page2.json()["rows"]] == ["appZ"]


async def test_forbidden_metric_returns_400(metrics_env: MetricsEnv) -> None:
    response = await metrics_env.client.get(
        "/api/v1/metrics/timeseries",
        params={**RANGE, "metrics": "total_revenue_usd"},
        headers=_auth("viewer"),
    )
    assert response.status_code == 400


async def test_invalid_date_range_returns_400(metrics_env: MetricsEnv) -> None:
    response = await metrics_env.client.get(
        "/api/v1/metrics/summary",
        params={"date_from": "2026-06-30", "date_to": "2026-06-01"},
        headers=_auth("admin"),
    )
    assert response.status_code == 400


async def test_aggregate_result_is_cached(metrics_env: MetricsEnv) -> None:
    await metrics_env.client.get("/api/v1/metrics/summary", params=RANGE, headers=_auth("admin"))
    keys = [k async for k in metrics_env.redis.scan_iter(match="agg:*")]
    assert keys, "expected an agg:* cache entry after a summary request"


async def test_api_query_is_audited(metrics_env: MetricsEnv) -> None:
    await metrics_env.client.get("/api/v1/metrics/summary", params=RANGE, headers=_auth("admin"))
    async with metrics_env.sessionmaker() as session:
        count = await session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "api_query")
        )
    assert count and count >= 1


async def test_rate_limit_returns_429_with_retry_after(
    metrics_env: MetricsEnv, monkeypatch: Any
) -> None:
    monkeypatch.setattr("app.core.rate_limit.RATE_LIMIT", 3)
    for _ in range(3):
        ok = await metrics_env.client.get("/api/v1/meta/freshness", headers=_auth("admin"))
        assert ok.status_code == 200
    blocked = await metrics_env.client.get("/api/v1/meta/freshness", headers=_auth("admin"))
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers}
