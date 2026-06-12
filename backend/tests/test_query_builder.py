"""Query builder tests against seeded fact data.

Covers scope-first filtering, client filters narrowing only, previous-period math,
timeseries bucketing, breakdown grouping, and keyset-paginated table with a sort
whitelist.
"""

import uuid
from datetime import date
from typing import Any

import pytest
from app.core.fact_table import FACT_TABLE
from app.schemas.auth import ScopeOut, UserContext
from app.schemas.metrics import MetricFilters
from app.services.query_builder import QueryBuilder
from sqlalchemy import insert
from sqlalchemy.engine import Row

ALL_GROUPS = [
    "store_installs",
    "ua_spend",
    "ad_revenue",
    "iap_revenue",
    "attribution",
    "profitability",
]


def _context(*, groups: list[str], scopes: list[tuple[str, str | None]]) -> UserContext:
    return UserContext(
        user_id=uuid.uuid4(),
        firebase_uid="uid",
        email="u@terafort.org",
        display_name=None,
        is_active=True,
        roles=[],
        metric_groups=groups,
        capabilities=[],
        scopes=[ScopeOut(scope_type=t, scope_value=v) for t, v in scopes],
    )


async def _insert_fact(session: Any, **overrides: Any) -> None:
    row: dict[str, Any] = {
        "date": date(2026, 1, 8),
        "platform": "ios",
        "canonical_key": "appA",
        "app_name": "App A",
        "publisher": "PubA",
        "pod": "POD_A",
        "hou": "HOU_A",
        "store_total_installs": 0,
        "total_ua_spend_usd": 0,
        "total_revenue_usd": 0,
    }
    row.update(overrides)
    await session.execute(insert(FACT_TABLE).values(**row))


async def _rows(session: Any, stmt: Any) -> list[Row[Any]]:
    return list((await session.execute(stmt)).all())


async def _one(session: Any, stmt: Any) -> Any:
    return (await session.execute(stmt)).mappings().one()


# ── scope is applied first; client filters can only narrow ───────────────────
async def test_scope_filter_limits_rows(fact_session: Any) -> None:
    await _insert_fact(fact_session, pod="POD_A", store_total_installs=10)
    await _insert_fact(fact_session, pod="POD_B", store_total_installs=99)
    await fact_session.commit()

    qb = QueryBuilder(_context(groups=ALL_GROUPS, scopes=[("pod", "POD_A")]))
    params = MetricFilters(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    result = await _one(fact_session, qb.summary(params))
    assert int(result["store_total_installs"]) == 10  # POD_B excluded by scope


async def test_client_filter_can_only_narrow(fact_session: Any) -> None:
    await _insert_fact(fact_session, pod="POD_A", store_total_installs=10)
    await _insert_fact(fact_session, pod="POD_B", store_total_installs=99)
    await fact_session.commit()

    ctx = _context(groups=ALL_GROUPS, scopes=[("pod", "POD_A")])
    qb = QueryBuilder(ctx)

    # Filtering to the in-scope pod: still 10.
    in_scope = MetricFilters(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31), pods=["POD_A"])
    assert int((await _one(fact_session, qb.summary(in_scope)))["store_total_installs"]) == 10

    # Asking for an out-of-scope pod cannot widen access: intersection is empty.
    out_of_scope = MetricFilters(
        date_from=date(2026, 1, 1), date_to=date(2026, 1, 31), pods=["POD_B"]
    )
    assert int((await _one(fact_session, qb.summary(out_of_scope)))["store_total_installs"]) == 0


async def test_scope_all_sees_everything(fact_session: Any) -> None:
    await _insert_fact(fact_session, pod="POD_A", store_total_installs=10)
    await _insert_fact(fact_session, pod="POD_B", store_total_installs=99)
    await fact_session.commit()

    qb = QueryBuilder(_context(groups=ALL_GROUPS, scopes=[("all", None)]))
    params = MetricFilters(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    assert int((await _one(fact_session, qb.summary(params)))["store_total_installs"]) == 109


# ── previous-period comparison math ──────────────────────────────────────────
async def test_summary_previous_period_math(fact_session: Any) -> None:
    # current window: Jan 8–14 (7 days); previous: Jan 1–7.
    await _insert_fact(fact_session, date=date(2026, 1, 9), store_total_installs=100)
    await _insert_fact(fact_session, date=date(2026, 1, 12), store_total_installs=50)
    await _insert_fact(fact_session, date=date(2026, 1, 3), store_total_installs=30)
    await _insert_fact(fact_session, date=date(2026, 1, 5), store_total_installs=20)
    # outside both windows — must be ignored
    await _insert_fact(fact_session, date=date(2025, 12, 30), store_total_installs=999)
    await fact_session.commit()

    qb = QueryBuilder(_context(groups=ALL_GROUPS, scopes=[("all", None)]))
    params = MetricFilters(date_from=date(2026, 1, 8), date_to=date(2026, 1, 14), compare=True)
    result = await _one(fact_session, qb.summary(params))
    assert int(result["store_total_installs"]) == 150
    assert int(result["store_total_installs__previous"]) == 50


# ── timeseries ───────────────────────────────────────────────────────────────
async def test_timeseries_day_buckets(fact_session: Any) -> None:
    await _insert_fact(fact_session, date=date(2026, 1, 8), store_total_installs=10)
    await _insert_fact(fact_session, date=date(2026, 1, 8), store_total_installs=5)
    await _insert_fact(fact_session, date=date(2026, 1, 9), store_total_installs=7)
    await fact_session.commit()

    qb = QueryBuilder(_context(groups=ALL_GROUPS, scopes=[("all", None)]))
    params = MetricFilters(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    rows = (
        (await fact_session.execute(qb.timeseries(params, ["store_total_installs"], "day")))
        .mappings()
        .all()
    )
    by_day = {r["bucket"].date(): int(r["store_total_installs"]) for r in rows}
    assert by_day == {date(2026, 1, 8): 15, date(2026, 1, 9): 7}


# ── breakdown ────────────────────────────────────────────────────────────────
async def test_breakdown_by_pod_ordered_desc(fact_session: Any) -> None:
    await _insert_fact(fact_session, pod="POD_A", store_total_installs=10)
    await _insert_fact(fact_session, pod="POD_B", store_total_installs=40)
    await _insert_fact(fact_session, pod="POD_B", store_total_installs=2)
    await fact_session.commit()

    qb = QueryBuilder(_context(groups=ALL_GROUPS, scopes=[("all", None)]))
    params = MetricFilters(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    rows = (
        (await fact_session.execute(qb.breakdown(params, "pod", ["store_total_installs"])))
        .mappings()
        .all()
    )
    assert [(r["pod"], int(r["store_total_installs"])) for r in rows] == [
        ("POD_B", 42),
        ("POD_A", 10),
    ]


# ── table: keyset pagination + sort whitelist ────────────────────────────────
async def test_table_keyset_pagination(fact_session: Any) -> None:
    for key, installs in [("a", 50), ("b", 40), ("c", 30), ("d", 20)]:
        await _insert_fact(
            fact_session, canonical_key=key, app_name=key.upper(), store_total_installs=installs
        )
    await fact_session.commit()

    qb = QueryBuilder(_context(groups=ALL_GROUPS, scopes=[("all", None)]))
    params = MetricFilters(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))

    page1 = (
        (
            await fact_session.execute(
                qb.table(params, sort="store_total_installs", direction="desc", limit=2)
            )
        )
        .mappings()
        .all()
    )
    assert [r["canonical_key"] for r in page1] == ["a", "b"]

    last = page1[-1]
    page2 = (
        (
            await fact_session.execute(
                qb.table(
                    params,
                    sort="store_total_installs",
                    direction="desc",
                    limit=2,
                    cursor=(last["store_total_installs"], last["canonical_key"]),
                )
            )
        )
        .mappings()
        .all()
    )
    assert [r["canonical_key"] for r in page2] == ["c", "d"]


async def test_table_rejects_non_whitelisted_sort(fact_session: Any) -> None:
    qb = QueryBuilder(_context(groups=ALL_GROUPS, scopes=[("all", None)]))
    params = MetricFilters(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    with pytest.raises(ValueError, match="not allowed"):
        qb.table(params, sort="date; DROP TABLE")


# ── metric permissions enforced ──────────────────────────────────────────────
async def test_forbidden_metric_rejected() -> None:
    # viewer: only store_installs; revenue is not permitted.
    qb = QueryBuilder(_context(groups=["store_installs"], scopes=[("all", None)]))
    params = MetricFilters(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    with pytest.raises(ValueError, match="not permitted"):
        qb.timeseries(params, ["total_revenue_usd"], "day")


def test_invalid_date_range_rejected() -> None:
    with pytest.raises(ValueError, match="date_from"):
        MetricFilters(date_from=date(2026, 1, 31), date_to=date(2026, 1, 1))
