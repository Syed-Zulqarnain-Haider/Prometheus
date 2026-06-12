"""Query builder for the metrics API.

Builds parameterized SQLAlchemy SELECTs over ``fact_daily_performance`` for the
summary / timeseries / breakdown / table endpoints. Two invariants:

  1. The caller's row-scope filter is applied FIRST in every query; client filter
     params are AND-ed on top, so they can only NARROW the result, never widen it.
  2. Only ADDITIVE measures are summed. Derived ratios (cpi, *_ecpm, *_ctr, roas,
     ad_roas, organic_install_share) are computed per-row in the BigQuery view and
     are never re-aggregated here (CLAUDE.md contract #4).

Everything is parameterized — no SQL is built from user input via string formatting.
Whitelisted identifiers (group_by, bucket, sort) select pre-defined columns; they
are never interpolated into SQL.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select

from app.core.fact_table import FACT_TABLE
from app.core.metric_registry import REGISTRY, Col, Group
from app.schemas.auth import UserContext
from app.schemas.metrics import Bucket, GroupBy, MetricFilters, SortDirection
from app.services.response_models import groups_from_names
from app.services.scopes import build_scope_filter

_METRIC_GROUPS: frozenset[Group] = frozenset(
    {
        Group.STORE_INSTALLS,
        Group.UA_SPEND,
        Group.AD_REVENUE,
        Group.IAP_REVENUE,
        Group.ATTRIBUTION,
        Group.PROFITABILITY,
    }
)

# Derived ratios: computed per-row in the BQ view; summing them is meaningless.
DERIVED_METRICS: frozenset[str] = frozenset(
    {
        "organic_install_share",
        "cpi",
        "fb_cpi",
        "gads_cpi",
        "mint_adv_cpi",
        "fb_ctr",
        "gads_ctr",
        "mint_adv_ctr",
        "admob_ecpm",
        "applovin_ecpm",
        "roas",
        "ad_roas",
    }
)

_NUMERIC_PREFIXES = ("BIGINT", "DOUBLE PRECISION", "NUMERIC")


def _is_additive(col: Col) -> bool:
    return (
        col.group in _METRIC_GROUPS
        and col.name not in DERIVED_METRICS
        and col.pg_type.upper().startswith(_NUMERIC_PREFIXES)
    )


# name -> Col for every additive measure in the registry.
ADDITIVE_MEASURES: dict[str, Col] = {c.name: c for c in REGISTRY if _is_additive(c)}

# group_by token -> fact column to group on.
_GROUP_BY_COLUMN: dict[str, str] = {
    "app": "canonical_key",
    "pod": "pod",
    "publisher": "publisher",
    "platform": "platform",
    "hou": "hou",
}


class QueryBuilder:
    """Builds scoped, parameterized SELECTs for one caller."""

    def __init__(self, context: UserContext) -> None:
        self._scope_filter = build_scope_filter(context.scopes)
        groups = groups_from_names(frozenset(context.metric_groups))
        self.permitted_measures: set[str] = {
            name for name, col in ADDITIVE_MEASURES.items() if col.group in groups
        }

    # ── shared helpers ───────────────────────────────────────────────────────
    def _base_filters(self, params: MetricFilters) -> list[Any]:
        """Scope filter FIRST, then client narrowing filters (no date bounds)."""
        conditions: list[Any] = [self._scope_filter]
        if params.platform is not None:
            conditions.append(FACT_TABLE.c.platform == params.platform)
        if params.pods:
            conditions.append(FACT_TABLE.c.pod.in_(params.pods))
        if params.publishers:
            conditions.append(FACT_TABLE.c.publisher.in_(params.publishers))
        if params.apps:
            conditions.append(FACT_TABLE.c.canonical_key.in_(params.apps))
        return conditions

    def _windowed_filters(self, params: MetricFilters, date_from: Any, date_to: Any) -> list[Any]:
        return [
            *self._base_filters(params),
            FACT_TABLE.c.date >= date_from,
            FACT_TABLE.c.date <= date_to,
        ]

    def _validate_metrics(self, metrics: list[str]) -> None:
        if not metrics:
            raise ValueError("at least one metric is required")
        forbidden = [m for m in metrics if m not in self.permitted_measures]
        if forbidden:
            raise ValueError(f"metrics not permitted or not additive: {forbidden}")

    def _sum(self, name: str) -> Any:
        return func.coalesce(func.sum(FACT_TABLE.c[name]), 0)

    @staticmethod
    def previous_period(params: MetricFilters) -> tuple[Any, Any]:
        """The immediately-preceding window of equal length."""
        length = (params.date_to - params.date_from).days + 1
        prev_to = params.date_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=length - 1)
        return prev_from, prev_to

    # ── summary ──────────────────────────────────────────────────────────────
    def summary(self, params: MetricFilters) -> Select[Any]:
        """One row of permitted-measure totals; previous-period columns if compare."""
        measures = sorted(self.permitted_measures)
        if not measures:
            raise ValueError("no permitted metrics for this user")

        current = and_(FACT_TABLE.c.date >= params.date_from, FACT_TABLE.c.date <= params.date_to)
        columns: list[Any] = [
            func.coalesce(func.sum(case((current, FACT_TABLE.c[name]), else_=0)), 0).label(name)
            for name in measures
        ]

        if params.compare:
            prev_from, prev_to = self.previous_period(params)
            previous = and_(FACT_TABLE.c.date >= prev_from, FACT_TABLE.c.date <= prev_to)
            columns.extend(
                func.coalesce(func.sum(case((previous, FACT_TABLE.c[name]), else_=0)), 0).label(
                    f"{name}__previous"
                )
                for name in measures
            )
            where = [
                *self._base_filters(params),
                FACT_TABLE.c.date >= prev_from,
                FACT_TABLE.c.date <= params.date_to,
            ]
        else:
            where = self._windowed_filters(params, params.date_from, params.date_to)

        return select(*columns).where(and_(*where))

    # ── timeseries ───────────────────────────────────────────────────────────
    def timeseries(self, params: MetricFilters, metrics: list[str], bucket: Bucket) -> Select[Any]:
        self._validate_metrics(metrics)
        bucket_expr = func.date_trunc(bucket, FACT_TABLE.c.date).label("bucket")
        columns: list[Any] = [
            bucket_expr,
            *[self._sum(m).label(m) for m in metrics],
        ]
        where = self._windowed_filters(params, params.date_from, params.date_to)
        return select(*columns).where(and_(*where)).group_by(bucket_expr).order_by(bucket_expr)

    # ── breakdown ────────────────────────────────────────────────────────────
    def breakdown(
        self,
        params: MetricFilters,
        group_by: GroupBy,
        metrics: list[str],
        *,
        limit: int | None = None,
    ) -> Select[Any]:
        self._validate_metrics(metrics)
        group_col = FACT_TABLE.c[_GROUP_BY_COLUMN[group_by]]
        columns: list[Any] = [group_col.label(group_by)]
        if group_by == "app":
            columns.append(func.max(FACT_TABLE.c.app_name).label("app_name"))
        columns.extend(self._sum(m).label(m) for m in metrics)

        where = self._windowed_filters(params, params.date_from, params.date_to)
        stmt = (
            select(*columns)
            .where(and_(*where))
            .group_by(group_col)
            .order_by(self._sum(metrics[0]).desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return stmt

    # ── table (keyset paginated, sort whitelist) ─────────────────────────────
    def table(
        self,
        params: MetricFilters,
        *,
        sort: str,
        direction: SortDirection = "desc",
        limit: int = 50,
        cursor: tuple[Any, str] | None = None,
    ) -> Select[Any]:
        """One aggregated row per app, keyset-paginated, sorted by a whitelisted column."""
        measures = sorted(self.permitted_measures)
        sort_whitelist = set(measures) | {"canonical_key", "app_name"}
        if sort not in sort_whitelist:
            raise ValueError(f"sort column '{sort}' is not allowed")

        where = self._windowed_filters(params, params.date_from, params.date_to)
        inner = (
            select(
                FACT_TABLE.c.canonical_key.label("canonical_key"),
                func.max(FACT_TABLE.c.app_name).label("app_name"),
                func.max(FACT_TABLE.c.publisher).label("publisher"),
                func.max(FACT_TABLE.c.pod).label("pod"),
                func.max(FACT_TABLE.c.hou).label("hou"),
                *[self._sum(m).label(m) for m in measures],
            )
            .where(and_(*where))
            .group_by(FACT_TABLE.c.canonical_key)
            .subquery("agg")
        )

        sort_col = inner.c[sort]
        key_col = inner.c.canonical_key
        stmt = select(inner)

        if cursor is not None:
            last_sort, last_key = cursor
            if direction == "desc":
                stmt = stmt.where(
                    or_(
                        sort_col < last_sort,
                        and_(sort_col == last_sort, key_col > last_key),
                    )
                )
            else:
                stmt = stmt.where(
                    or_(
                        sort_col > last_sort,
                        and_(sort_col == last_sort, key_col > last_key),
                    )
                )

        order = (
            [sort_col.desc(), key_col.asc()]
            if direction == "desc"
            else [sort_col.asc(), key_col.asc()]
        )
        return stmt.order_by(*order).limit(limit)
