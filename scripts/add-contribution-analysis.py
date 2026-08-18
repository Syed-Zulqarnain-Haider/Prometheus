#!/usr/bin/env python3
"""/metrics/contribution - which entities moved the number, and by how much.

The Revenue card says -34.3%. The only question anyone asks next is WHICH APPS, and
today that means opening Apps Explorer and diffing two periods by hand. This endpoint
answers it directly: per entity (app / pod / publisher / platform / hou), the current
value, the previous value, the delta, and the share of the total move - sorted so the
biggest movers come first.

Design notes that matter:

* ONE query, not two. It follows the exact pattern ``QueryBuilder.summary`` already
  uses for compare: CASE sums over the current and previous windows in a single
  GROUP BY. Two round trips would also have needed a client-side join and would drift
  from summary's definition of "previous period" - which is the number the KPI card
  shows, so they must agree.
* The previous window comes from ``self.previous_period(params)``, the same helper
  summary uses. If contribution and the KPI card disagreed about the comparison
  window, the breakdown would not add up to the headline - the one thing this feature
  exists to make true.
* Ordering is by ABSOLUTE delta in SQL, so ``limit`` keeps the biggest movers in either
  direction rather than the largest positives.
* RBAC is inherited whole: the metric must be in ``permitted_measures`` (enforced by
  ``_validate_metrics``) and the row scopes come from ``_base_filters``. A caller
  cannot ask this endpoint anything they could not ask /breakdown.
* ``total_delta`` is the sum over the ENTITIES RETURNED, and is reported separately
  from the true overall move so the UI can say "these 10 explain 82% of it" honestly
  instead of implying the list is complete.

Patches: query_builder.py (the query), metrics_service.py (the shaping),
schemas/metrics.py (response models), api/v1/metrics.py (the route).

Anchored: every anchor must appear EXACTLY once or NOTHING is written - all four files
validate before any is touched. Idempotent. Backend restart; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

QB = Path("backend/app/services/query_builder.py")
SVC = Path("backend/app/services/metrics_service.py")
SCHEMA = Path("backend/app/schemas/metrics.py")
ROUTE = Path("backend/app/api/v1/metrics.py")

# ── query_builder.py ──────────────────────────────────────────────────────────
QB_ANCHOR = "    # ── table (keyset paginated, sort whitelist) ─────────────────────────────\n"
QB_ADD = '''    # ── contribution (who moved the number) ──────────────────────────────────
    def contribution(
        self,
        params: MetricFilters,
        group_by: GroupBy,
        metric: str,
        *,
        limit: int,
    ) -> Select[Any]:
        """Per-entity current vs previous totals for ONE metric, biggest movers first.

        Deliberately mirrors ``summary``: CASE sums over both windows in a single
        GROUP BY, using the SAME ``previous_period`` helper. If this disagreed with
        summary about which days count as "previous", the per-app deltas would not
        reconcile with the headline figure the KPI card shows - which is the entire
        point of the feature.
        """
        self._validate_metrics([metric])
        group_col = FACT_TABLE.c[_GROUP_BY_COLUMN[group_by]]
        column = FACT_TABLE.c[metric]

        current = and_(FACT_TABLE.c.date >= params.date_from, FACT_TABLE.c.date <= params.date_to)
        prev_from, prev_to = self.previous_period(params)
        previous = and_(FACT_TABLE.c.date >= prev_from, FACT_TABLE.c.date <= prev_to)

        current_sum = func.coalesce(func.sum(case((current, column), else_=0)), 0)
        previous_sum = func.coalesce(func.sum(case((previous, column), else_=0)), 0)

        columns: list[Any] = [group_col.label(group_by)]
        if group_by == "app":
            columns.append(func.max(FACT_TABLE.c.app_name).label("app_name"))
        columns.extend(
            [current_sum.label("current"), previous_sum.label("previous")]
        )

        where = [
            *self._base_filters(params),
            FACT_TABLE.c.date >= prev_from,
            FACT_TABLE.c.date <= params.date_to,
        ]
        return (
            select(*columns)
            .where(and_(*where))
            .group_by(group_col)
            # ABSOLUTE delta: `limit` must keep the biggest movers in EITHER direction,
            # not the largest gains.
            .order_by(func.abs(current_sum - previous_sum).desc())
            .limit(limit)
        )

'''

# ── metrics_service.py ────────────────────────────────────────────────────────
SVC_ANCHOR = "async def run_breakdown(\n"
SVC_ADD = '''async def run_contribution(
    session: AsyncSession,
    qb: QueryBuilder,
    params: MetricFilters,
    group_by: GroupBy,
    metric: str,
    limit: int,
) -> dict[str, Any]:
    """Shape the contribution query into gainers, losers and an honest coverage figure."""
    rows = (
        (await session.execute(qb.contribution(params, group_by, metric, limit=limit)))
        .mappings()
        .all()
    )

    entries: list[dict[str, Any]] = []
    for row in rows:
        current = float(row["current"] or 0.0)
        previous = float(row["previous"] or 0.0)
        delta = current - previous
        entries.append(
            {
                "key": _to_jsonable(row[group_by]),
                "label": _to_jsonable(row.get("app_name") or row[group_by]),
                "current": current,
                "previous": previous,
                "delta": delta,
                # None, not 0, when there is nothing to grow from: "+100%" off a zero
                # base is a division artefact, not a fact about the business.
                "change_pct": (delta / abs(previous)) if previous else None,
            }
        )

    # The move explained by the rows we are RETURNING - reported separately from the
    # overall move so the UI can say "these N explain X% of it" instead of implying the
    # list is the whole story.
    covered_delta = sum(entry["delta"] for entry in entries)

    return {
        "metric": metric,
        "group_by": group_by,
        "gainers": [e for e in entries if e["delta"] > 0][:limit],
        "losers": [e for e in entries if e["delta"] < 0][:limit],
        "covered_delta": covered_delta,
    }


'''

# ── schemas/metrics.py ────────────────────────────────────────────────────────
SCHEMA_ANCHOR = "class MetricFilters(BaseModel):\n"
SCHEMA_ADD = '''class ContributionRow(BaseModel):
    """One entity's movement between the two windows."""

    key: str | None
    label: str | None
    current: float
    previous: float
    delta: float
    # None when the previous window was zero - a percentage off nothing is meaningless.
    change_pct: float | None


class ContributionResponse(BaseModel):
    metric: str
    group_by: str
    gainers: list[ContributionRow]
    losers: list[ContributionRow]
    # Sum of the returned rows' deltas. Compare against the headline move to know how
    # much of it these entities actually explain.
    covered_delta: float


'''

# ── api/v1/metrics.py ─────────────────────────────────────────────────────────
ROUTE_ANCHOR = '@router.get("/breakdown")\n'
ROUTE_ADD = '''@router.get("/contribution")
async def contribution(
    filters: Filters,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    group_by: GroupBy,
    metric: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    """Which entities moved ``metric`` between this window and the previous one.

    Answers the question the KPI cards raise and cannot answer: revenue is down 34% -
    which apps? Same RBAC as /breakdown; the metric must be permitted and row scopes
    are injected by the query builder.
    """
    qb = QueryBuilder(context)
    key = aggregate_cache_key(
        "metrics.contribution",
        scope_token(context.scopes),
        perms_token(context.metric_groups),
        _params(filters, group_by=group_by, metric=metric, limit=limit),
    )

    async def produce() -> dict[str, Any]:
        try:
            return await metrics_service.run_contribution(db, qb, filters, group_by, metric, limit)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    result: dict[str, Any] = await cached_json(redis, key, produce)
    return result


'''


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    targets = {QB: QB_ANCHOR, SVC: SVC_ANCHOR, SCHEMA: SCHEMA_ANCHOR, ROUTE: ROUTE_ANCHOR}
    for path in targets:
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    # Per-file markers. A single lowercase "contribution" check was WRONG: the schema
    # file only ever contains the capitalised class names, so the guard never matched
    # and a rerun appended the classes a second time.
    markers = {
        QB: "def contribution(",
        SVC: "async def run_contribution(",
        SCHEMA: "class ContributionRow",
        ROUTE: '@router.get("/contribution")',
    }
    texts = {path: path.read_text() for path in targets}
    if all(markers[path] in texts[path] for path in targets):
        print("already added - nothing to do")
        return

    # Validate EVERY file before writing ANY: a route without its query is a 500.
    for path, anchor in targets.items():
        if markers[path] in texts[path]:
            continue
        if texts[path].count(anchor) != 1:
            die(f"{path}: expected exactly one {anchor.strip()!r}, found {texts[path].count(anchor)}")
    # The query needs these already imported; the file uses them for summary.
    for name in ("case", "func", "and_", "select"):
        if name not in texts[QB]:
            die(f"{QB}: {name} is not imported - the file has changed shape")

    additions = {QB: QB_ADD, SVC: SVC_ADD, SCHEMA: SCHEMA_ADD, ROUTE: ROUTE_ADD}
    for path, anchor in targets.items():
        if markers[path] in texts[path]:
            print(f"{path}: already has it")
            continue
        path.write_text(texts[path].replace(anchor, additions[path] + anchor, 1))
        print(f"patched {path}")

    print("\nGET /api/v1/metrics/contribution?group_by=app&metric=rpt_gross_revenue_usd")
    print("Restart the backend: docker compose -f docker-compose.prod.yml up -d --build backend")


if __name__ == "__main__":
    main()
