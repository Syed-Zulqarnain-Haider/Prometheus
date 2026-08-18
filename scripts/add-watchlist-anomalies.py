#!/usr/bin/env python3
"""Feature 4: per-app anomaly detection and a personal watchlist.

The existing alerts_service watches the WHOLE FLEET: total revenue fell, total spend
spiked, ROAS crossed a floor. That is the right check for "is the business okay" and
the wrong one for "is MY app okay" - one app can halve while the fleet total moves two
percent, and nobody hears about it until someone opens the dashboard.

This adds the per-app layer and the subscription to go with it:

  * ``/api/v1/metrics/anomalies`` - which entities moved unusually on the latest
    COMPLETE day, under the caller's own RBAC.
  * A watchlist: star an app, and the daily post-sync pass notifies YOU about anomalies
    on the apps you starred - resolved through YOUR context, so a viewer never receives
    a revenue figure they cannot see on screen.

Statistics, and why not a simple percentage:

  * A day-over-day percentage flags every app with a weekend, and misses a slow app that
    quietly halves. The baseline here is the MEDIAN of the trailing days with a MEDIAN
    ABSOLUTE DEVIATION scale - both robust, so one spike in the history does not inflate
    the yardstick and hide the next one. The score is the standard 0.6745·(x−median)/MAD.
  * A flat series has MAD = 0 and would divide by zero, so that case is decided on the
    relative move alone and reported with no score rather than a fabricated one.
  * A deviation must ALSO clear a minimum percentage of the baseline. Without it, an app
    earning a few dollars a day generates an "anomaly" every time it earns a few dollars
    more, and the feature trains people to ignore it.
  * The latest fact date is routinely PARTIAL (Apple lags 2-3 days). Scoring it would
    report the entire catalogue as collapsing, every single day - the same false alarm
    alerts_service and digest_service already guard against. The evaluated day is the
    latest COMPLETE one, defined the same way they define it.

RBAC: the endpoint runs through QueryBuilder, so the metric must be permitted and the
row scopes are injected. The watchlist is per-user and you can only star an app that is
already visible to you - the apps endpoint enforces that, and a star on an invisible app
would be an existence probe.

Anchored: every anchor must appear EXACTLY once or NOTHING is written - all files
validate before any is touched. Idempotent. Requires `alembic upgrade head`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MODEL = Path("backend/app/models/watchlist.py")
MIGRATION = Path("backend/alembic/versions/20260818_1200_b2c3d4e5f6a7_watchlist.py")
COMPLETENESS = Path("backend/app/services/day_completeness.py")
SERVICE = Path("backend/app/services/anomaly_service.py")
SCHEMA = Path("backend/app/schemas/watchlist.py")
ROUTER = Path("backend/app/api/v1/watchlist.py")
TEST = Path("backend/tests/test_anomalies.py")
PANEL = Path("frontend/components/overview/watchlist-panel.tsx")
TOGGLE = Path("frontend/components/app-detail/watch-toggle.tsx")

MODELS_INIT = Path("backend/app/models/__init__.py")
MAIN = Path("backend/app/main.py")
QB = Path("backend/app/services/query_builder.py")
METRICS_ROUTE = Path("backend/app/api/v1/metrics.py")
REGISTRY = Path("backend/app/core/settings_registry.py")
SCHEDULER = Path("backend/app/services/sync_scheduler.py")
TYPES = Path("frontend/lib/types.ts")
HOOKS = Path("frontend/lib/api-hooks.ts")
DETAIL = Path("frontend/components/app-detail/app-detail-client.tsx")
LAYOUT = Path("frontend/lib/overview-layout.ts")
CLIENT = Path("frontend/components/overview/overview-client.tsx")
TEST_META = Path("backend/tests/test_models_metadata.py")
TEST_MIGRATIONS = Path("backend/tests/test_migrations.py")

MODEL_SOURCE = '''"""Per-user app watchlist - "tell me when THIS app moves"."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WatchlistItem(Base):
    """One (user, app) subscription. The composite primary key makes starring twice a
    no-op rather than a duplicate row."""

    __tablename__ = "watchlist_items"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # dim_app.canonical_key. NOT a foreign key: the fact table's catalogue is sync-owned
    # and an app can disappear from a rebuild, which must not delete someone's list.
    canonical_key: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (Index("ix_watchlist_items_user", "user_id"),)
'''

MIGRATION_SOURCE = '''"""Per-user app watchlist.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_key", sa.Text(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_watchlist_items_user", "watchlist_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_watchlist_items_user", table_name="watchlist_items")
    op.drop_table("watchlist_items")
'''

COMPLETENESS_SOURCE = '''"""Which fact date is the latest COMPLETE one.

The newest rows in ``fact_daily_performance`` are routinely partial - Apple's data lags
two to three days, so today's row set is a fraction of a normal day. Reporting on it
produces "$0 / -100%" for the whole catalogue, which is how a digest once announced that
the business had collapsed overnight.

A date counts as complete when its row count reaches a share of the trailing median row
count. The median (not a fixed number) means the threshold follows the catalogue as apps
are added or removed.

NOTE: ``alerts_service`` and ``digest_service`` carry this same rule inline, written
before this module existed. They are deliberately left alone here - folding them in is a
behaviour-preserving refactor that deserves its own change and its own test run, not a
drive-by edit inside a feature.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_FACT = "fact_daily_performance"

# Identical to the constants alerts_service and digest_service use.
COMPLETE_DAY_RATIO = 0.8
RECENT_DAYS_FOR_MEDIAN = 7

# Fixed identifiers from a module constant, never user input - safe despite the f-string.
_LATEST_COMPLETE_SQL = text(  # noqa: S608
    f"SELECT date FROM {_FACT} GROUP BY date "
    f"HAVING COUNT(*) >= COALESCE((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY c) "
    f"FROM (SELECT COUNT(*) AS c FROM {_FACT} GROUP BY date "
    f"ORDER BY date DESC LIMIT {RECENT_DAYS_FOR_MEDIAN}) recent), 0) * {COMPLETE_DAY_RATIO} "
    f"ORDER BY date DESC LIMIT 1"
)


async def latest_complete_date(db: AsyncSession) -> date | None:
    """The newest date whose rows have actually all landed, or None on an empty table.

    Deliberately NOT scoped to the caller: completeness is a property of the sync, not of
    who is asking. A scoped user asking "has today finished loading?" must get the same
    answer as everyone else.
    """
    result: date | None = (await db.execute(_LATEST_COMPLETE_SQL)).scalar()
    return result
'''

SERVICE_SOURCE = '''"""Per-app (or per-pod, per-publisher, ...) anomaly detection.

Answers "is MY app okay", which the fleet-wide alerts_service structurally cannot: one
app can halve while the fleet total moves two percent.

The method, and why it is not a percentage change:

  * The baseline is the MEDIAN of the trailing days and the scale is the MEDIAN ABSOLUTE
    DEVIATION. Both are robust: one spike in the history does not inflate the yardstick
    and hide the next one, which is exactly what a mean and a standard deviation do.
  * The score is the standard robust z, 0.6745·(x − median) / MAD. 0.6745 is the value
    that makes MAD comparable to a standard deviation for normal data, so a threshold of
    3.5 means what people expect it to mean.
  * A perfectly flat series has MAD = 0 and no score exists. That case is decided on the
    relative move alone and reported with ``score = None`` rather than a fabricated
    number - a made-up infinity would sort to the top of every list forever.
  * A deviation must ALSO clear a minimum percentage of the baseline, or an app earning
    four dollars a day is "anomalous" every time it earns six, and people learn to
    ignore the feature.
  * The day scored is the latest COMPLETE one (see day_completeness). Scoring the newest
    partial day reports the whole catalogue as collapsing, every day.
"""

from __future__ import annotations

import logging
import statistics
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import User, WatchlistItem
from app.schemas.metrics import GroupBy, MetricFilters
from app.services import auth as auth_service
from app.services import day_completeness, notification_service, settings_service
from app.services.query_builder import QueryBuilder

log = logging.getLogger("anomaly")

# 0.6745 is the 75th percentile of the standard normal: it rescales MAD so that, for
# normally distributed data, the result is comparable to a z-score.
_MAD_TO_SIGMA = 0.6745

# Below this many baseline days the median and MAD are noise. Two weeks of history is
# the minimum at which "unusual" means anything.
_MIN_BASELINE_DAYS = 10

# How much history to read when scoring. Long enough for a stable median, short enough
# that a change three months ago is not still shaping today's baseline.
_BASELINE_WINDOW_DAYS = 28

# Metrics offered for watchlist alerts, best first. The first one the user is permitted
# is used - so a viewer gets installs, not a revenue figure they cannot see on screen.
_WATCH_METRIC_PREFERENCE = (
    "rpt_gross_revenue_usd",
    "total_revenue_usd",
    "store_total_installs",
)


@dataclass
class Anomaly:
    key: str | None
    label: str | None
    value: float
    baseline: float
    delta: float
    change_pct: float | None
    # None when the series is perfectly flat: no scale exists, so no score does either.
    score: float | None
    direction: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "baseline": self.baseline,
            "delta": self.delta,
            "change_pct": self.change_pct,
            "score": self.score,
            "direction": self.direction,
        }


def _score(latest: float, baseline: list[float], z_threshold: float, min_change: float) -> (
    tuple[float | None, bool]
):
    """Robust z for ``latest`` against ``baseline``, and whether it is an anomaly.

    Returns ``(score, is_anomaly)``. ``score`` is None when the baseline has no spread.
    """
    median = statistics.median(baseline)
    deviation = latest - median

    # The relative gate, applied in BOTH branches: an absolute move that is a rounding
    # error against the baseline is not news, however statistically improbable.
    # When the baseline is zero there is nothing to be relative to, so any activity at
    # all is the signal.
    material = (
        latest != 0 if median == 0 else abs(deviation) / abs(median) >= min_change
    )

    mad = statistics.median([abs(v - median) for v in baseline])
    if mad == 0:
        # A flat series. There is no scale, so there is no score - say so rather than
        # inventing one that would sort to the top of every list forever.
        return None, material and deviation != 0

    score = _MAD_TO_SIGMA * deviation / mad
    return score, material and abs(score) >= z_threshold


async def detect(
    db: AsyncSession,
    qb: QueryBuilder,
    params: MetricFilters,
    group_by: GroupBy,
    metric: str,
    *,
    limit: int,
    z_threshold: float,
    min_change_pct: float,
) -> dict[str, Any]:
    """Score every entity in the window and return the anomalous ones, worst first."""
    on_date = await day_completeness.latest_complete_date(db)
    if on_date is None:
        return {
            "metric": metric,
            "group_by": group_by,
            "as_of": None,
            "rows": [],
            "reason": "no data",
        }

    # Read a fixed baseline window ending at the complete day, INDEPENDENT of the
    # caller's filter dates. "Unusual" has to be measured against the same amount of
    # history whichever range happens to be selected on screen, or the same app is an
    # anomaly on one page and not on another.
    window = params.model_copy(
        update={
            "date_from": on_date - timedelta(days=_BASELINE_WINDOW_DAYS),
            "date_to": on_date,
            "compare": False,
        }
    )
    rows = (
        (await db.execute(qb.daily_by_entity(window, group_by, metric)))
        .mappings()
        .all()
    )

    series: dict[str, list[tuple[date, float]]] = {}
    labels: dict[str, str | None] = {}
    for row in rows:
        key = row[group_by]
        if key is None:
            continue  # unattributed rows cannot be an entity's anomaly
        series.setdefault(key, []).append((row["date"], float(row["value"] or 0.0)))
        if group_by == "app":
            labels.setdefault(key, row.get("app_name"))

    found: list[Anomaly] = []
    for key, points in series.items():
        points.sort(key=lambda p: p[0])
        latest_day, latest_value = points[-1]
        if latest_day != on_date:
            # The entity has no row on the scored day. That is itself worth knowing, but
            # it is a coverage question, not a statistical one - Data Health owns it.
            continue
        baseline = [value for day, value in points[:-1]]
        if len(baseline) < _MIN_BASELINE_DAYS:
            continue

        score, is_anomaly = _score(latest_value, baseline, z_threshold, min_change_pct)
        if not is_anomaly:
            continue
        median = statistics.median(baseline)
        found.append(
            Anomaly(
                key=key,
                label=labels.get(key) or key,
                value=latest_value,
                baseline=median,
                delta=latest_value - median,
                change_pct=((latest_value - median) / abs(median)) if median else None,
                score=score,
                direction="up" if latest_value >= median else "down",
            )
        )

    # Worst first. A flat-series hit has no score, so it sorts on relative move instead -
    # ranked below anything with a real score, which is the honest ordering.
    found.sort(
        key=lambda a: (a.score is not None, abs(a.score or 0.0), abs(a.change_pct or 0.0)),
        reverse=True,
    )
    return {
        "metric": metric,
        "group_by": group_by,
        "as_of": on_date,
        "rows": [a.as_dict() for a in found[:limit]],
        "reason": None,
    }


async def notify_watchlists(db: AsyncSession, settings: Settings) -> int:
    """Daily pass: tell each user about anomalies on the apps THEY starred.

    Each user is evaluated through their OWN resolved context, so the metric chosen and
    the rows read are exactly what that user could have queried themselves. Best-effort
    per user: one broken account never stops the rest.
    """
    if not bool(await settings_service.get_value(db, "watchlist_alerts_enabled")):
        return 0

    z_threshold = float(await settings_service.get_value(db, "anomaly_z_threshold")) / 10.0
    min_change = float(await settings_service.get_value(db, "anomaly_min_change_pct")) / 100.0

    on_date = await day_completeness.latest_complete_date(db)
    if on_date is None:
        return 0

    watchers = (
        await db.execute(
            select(User.id, User.firebase_uid, WatchlistItem.canonical_key)
            .join(WatchlistItem, WatchlistItem.user_id == User.id)
            .where(User.is_active.is_(True))
            .order_by(User.id)
        )
    ).all()

    by_user: dict[uuid.UUID, tuple[str, list[str]]] = {}
    for user_id, firebase_uid, canonical_key in watchers:
        by_user.setdefault(user_id, (firebase_uid, []))[1].append(canonical_key)

    sent = 0
    for user_id, (firebase_uid, keys) in by_user.items():
        try:
            context = await auth_service.resolve_user_context(db, firebase_uid)
            if context is None:
                continue
            qb = QueryBuilder(context)
            metric = next((m for m in _WATCH_METRIC_PREFERENCE if m in qb.permitted_measures), None)
            if metric is None:
                continue  # nothing this user is allowed to be told about
            params = MetricFilters(
                date_from=on_date - timedelta(days=_BASELINE_WINDOW_DAYS),
                date_to=on_date,
                apps=keys,
            )
            result = await detect(
                db,
                qb,
                params,
                "app",
                metric,
                limit=len(keys),
                z_threshold=z_threshold,
                min_change_pct=min_change,
            )
            for row in result["rows"]:
                arrow = "rose" if row["direction"] == "up" else "fell"
                pct = f" ({row['change_pct'] * 100:+.0f}%)" if row["change_pct"] is not None else ""
                await notification_service.notify_user(
                    user_id,
                    type="watchlist_anomaly",
                    title=f"{row['label']}: unusual {metric.replace('_', ' ')}",
                    body=f"On {on_date}, {row['label']} {arrow} to {row['value']:,.0f} "
                    f"against a {row['baseline']:,.0f} baseline{pct}.",
                    severity="warning",
                    link=f"/apps/{row['key']}",
                )
                sent += 1
        except Exception:  # noqa: BLE001 - one bad account must not stop the pass
            log.exception("watchlist alert failed for user %s", user_id)
    return sent
'''

SCHEMA_SOURCE = '''"""Watchlist and anomaly response models."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class WatchlistItemOut(BaseModel):
    canonical_key: str
    app_name: str | None
    created_at: datetime


class AnomalyRow(BaseModel):
    key: str | None
    label: str | None
    value: float
    baseline: float
    delta: float
    change_pct: float | None
    # None when the baseline series is perfectly flat - no scale, so no score.
    score: float | None
    direction: str


class AnomalyResponse(BaseModel):
    metric: str
    group_by: str
    # The latest COMPLETE fact date - never the newest partial one.
    as_of: date | None
    rows: list[AnomalyRow]
    reason: str | None = None
'''

ROUTER_SOURCE = '''"""The personal watchlist: star an app, hear about it when it moves.

You can only star an app you can already see. The check is the same scope filter the
apps endpoints use - a star on an invisible app would answer "does this app exist?",
which is what row scoping exists to refuse.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import CurrentUser, DbSession
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.models import DimApp, WatchlistItem
from app.schemas.watchlist import WatchlistItemOut
from app.services.audit import AuditDep
from app.services.scopes import build_scope_filter

router = APIRouter(
    prefix="/watchlist", tags=["watchlist"], dependencies=[Depends(enforce_rate_limit)]
)

# A watchlist is a shortlist. Past a certain size the daily notification is spam, and an
# unbounded list would also make the daily pass unbounded.
_MAX_ITEMS = 50


def _dim_scope_columns() -> dict[str, Any]:
    """dim_app columns for the scope filter - the apps endpoints scope the same way."""
    return {
        "hou": DimApp.hou,
        "pod": DimApp.pod,
        "publisher": DimApp.publisher,
        "app": DimApp.canonical_key,
    }


@router.get("", response_model=list[WatchlistItemOut])
async def list_watchlist(context: CurrentUser, db: DbSession) -> list[WatchlistItemOut]:
    """This user's starred apps, newest first.

    Filtered through the CURRENT scope: access can be narrowed after a star was added,
    and a stale row must not keep showing an app the user may no longer see.
    """
    rows = (
        await db.execute(
            select(WatchlistItem.canonical_key, DimApp.app_name, WatchlistItem.created_at)
            .join(DimApp, DimApp.canonical_key == WatchlistItem.canonical_key)
            .where(
                WatchlistItem.user_id == context.user_id,
                build_scope_filter(context.scopes, columns=_dim_scope_columns()),
            )
            .order_by(WatchlistItem.created_at.desc())
        )
    ).all()
    return [
        WatchlistItemOut(canonical_key=key, app_name=name, created_at=created)
        for key, name, created in rows
    ]


@router.put("/{canonical_key}", response_model=WatchlistItemOut)
async def add_to_watchlist(
    canonical_key: str,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> WatchlistItemOut:
    """Star an app. Idempotent - starring twice is not an error, it is the same star."""
    app = await db.scalar(
        select(DimApp).where(
            DimApp.canonical_key == canonical_key,
            build_scope_filter(context.scopes, columns=_dim_scope_columns()),
        )
    )
    if app is None:
        # 404, not 403: the same answer a nonexistent app gives.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "App not found")

    count = len(
        (
            await db.scalars(
                select(WatchlistItem.canonical_key).where(
                    WatchlistItem.user_id == context.user_id
                )
            )
        ).all()
    )
    existing = await db.get(WatchlistItem, (context.user_id, canonical_key))
    if existing is None and count >= _MAX_ITEMS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"A watchlist holds at most {_MAX_ITEMS} apps. Remove one first.",
        )

    await db.execute(
        pg_insert(WatchlistItem)
        .values(user_id=context.user_id, canonical_key=canonical_key)
        .on_conflict_do_nothing(index_elements=["user_id", "canonical_key"])
    )
    await db.commit()
    row = await db.get(WatchlistItem, (context.user_id, canonical_key))
    await audit.write(
        user_id=context.user_id,
        action="watchlist_add",
        resource=canonical_key,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return WatchlistItemOut(
        canonical_key=canonical_key,
        app_name=app.app_name,
        # The row was just inserted in this transaction, so it is always there; the
        # fallback exists so a surprise cannot turn a successful star into a 500.
        created_at=row.created_at if row else datetime.now(UTC),
    )


@router.delete("/{canonical_key}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    canonical_key: str,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> Response:
    """Unstar. Removing something that is not there is a success, not a 404 - the caller
    asked for it to be gone and it is gone."""
    row = await db.get(WatchlistItem, (context.user_id, canonical_key))
    if row is not None:
        await db.delete(row)
        await db.commit()
        await audit.write(
            user_id=context.user_id,
            action="watchlist_remove",
            resource=canonical_key,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
'''

TEST_SOURCE = '''"""Watchlist scoping and the anomaly scorer.

The scorer is tested as pure arithmetic (no database): a flat series with one spike must
fire, a noisy series with the same spike must NOT, and a tiny absolute move against a
tiny baseline must not fire however improbable it looks. Those three are the whole
difference between an alert people act on and one they filter to a folder.
"""

from typing import Any

from app.services.anomaly_service import _score

from tests.conftest import MetricsEnv

URL = "/api/v1/watchlist"

Z = 3.5
MIN_CHANGE = 0.20


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


def test_spike_on_a_steady_series_is_an_anomaly() -> None:
    baseline = [100.0, 102.0, 98.0, 101.0, 99.0, 100.0, 103.0, 97.0, 100.0, 101.0]
    score, fired = _score(400.0, baseline, Z, MIN_CHANGE)
    assert fired is True
    assert score is not None and score > Z


def test_same_spike_on_a_volatile_series_is_not() -> None:
    """Identical absolute move, but this series does that every other day."""
    baseline = [100.0, 400.0, 50.0, 380.0, 60.0, 410.0, 40.0, 390.0, 70.0, 420.0]
    _, fired = _score(400.0, baseline, Z, MIN_CHANGE)
    assert fired is False


def test_a_rounding_error_never_fires_however_improbable() -> None:
    """A perfectly flat 100.00 series, then 100.01. Statistically infinite, actually
    nothing - this is the gate that stops the feature training people to ignore it."""
    baseline = [100.0] * 12
    _, fired = _score(100.01, baseline, Z, MIN_CHANGE)
    assert fired is False


def test_flat_series_reports_no_score_rather_than_infinity() -> None:
    baseline = [100.0] * 12
    score, fired = _score(500.0, baseline, Z, MIN_CHANGE)
    assert score is None  # no spread, so no score exists
    assert fired is True  # but a 5x move is still an anomaly


def test_collapse_is_detected_not_only_growth() -> None:
    baseline = [100.0, 102.0, 98.0, 101.0, 99.0, 100.0, 103.0, 97.0, 100.0, 101.0]
    score, fired = _score(5.0, baseline, Z, MIN_CHANGE)
    assert fired is True
    assert score is not None and score < 0


async def test_watchlist_requires_auth(metrics_env: MetricsEnv) -> None:
    assert (await metrics_env.client.get(URL)).status_code == 401


async def test_star_and_list_round_trip(metrics_env: MetricsEnv) -> None:
    added = await metrics_env.client.put(f"{URL}/appA", headers=_auth("admin"))
    assert added.status_code == 200, added.text
    assert added.json()["canonical_key"] == "appA"

    listed = await metrics_env.client.get(URL, headers=_auth("admin"))
    assert [i["canonical_key"] for i in listed.json()] == ["appA"]


async def test_starring_twice_is_idempotent(metrics_env: MetricsEnv) -> None:
    await metrics_env.client.put(f"{URL}/appA", headers=_auth("admin"))
    await metrics_env.client.put(f"{URL}/appA", headers=_auth("admin"))
    listed = await metrics_env.client.get(URL, headers=_auth("admin"))
    assert len(listed.json()) == 1


async def test_cannot_star_an_app_outside_scope(metrics_env: MetricsEnv) -> None:
    """appB is in POD_B; the scoped user only holds POD_A. 404, not 403 - a 403 would
    confirm the app exists."""
    resp = await metrics_env.client.put(f"{URL}/appB", headers=_auth("pod_owner_scoped"))
    assert resp.status_code == 404


async def test_can_star_an_app_inside_scope(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.put(f"{URL}/appA", headers=_auth("pod_owner_scoped"))
    assert resp.status_code == 200


async def test_watchlists_are_private_per_user(metrics_env: MetricsEnv) -> None:
    await metrics_env.client.put(f"{URL}/appA", headers=_auth("admin"))
    others = await metrics_env.client.get(URL, headers=_auth("finance"))
    assert others.json() == []


async def test_unstar_is_idempotent(metrics_env: MetricsEnv) -> None:
    async def unstar() -> int:
        resp = await metrics_env.client.delete(f"{URL}/appA", headers=_auth("admin"))
        return resp.status_code

    assert await unstar() == 204  # never starred - still a success
    await metrics_env.client.put(f"{URL}/appA", headers=_auth("admin"))
    assert await unstar() == 204
    assert (await metrics_env.client.get(URL, headers=_auth("admin"))).json() == []


async def test_anomalies_endpoint_refuses_a_forbidden_metric(metrics_env: MetricsEnv) -> None:
    """viewer holds store_installs only - revenue must be a 400, not a silent empty."""
    params: dict[str, Any] = {
        "from": "2026-06-01",
        "to": "2026-06-30",
        "group_by": "app",
        "metric": "total_revenue_usd",
    }
    resp = await metrics_env.client.get(
        "/api/v1/metrics/anomalies", params=params, headers=_auth("viewer")
    )
    assert resp.status_code == 400


async def test_anomalies_endpoint_returns_a_shape_on_thin_history(metrics_env: MetricsEnv) -> None:
    """The seed has two days - far below the baseline minimum. The endpoint must answer
    cleanly with an empty list, never divide by an empty baseline."""
    params: dict[str, Any] = {
        "from": "2026-06-01",
        "to": "2026-06-30",
        "group_by": "app",
        "metric": "total_revenue_usd",
    }
    resp = await metrics_env.client.get(
        "/api/v1/metrics/anomalies", params=params, headers=_auth("admin")
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["metric"] == "total_revenue_usd"
    assert body["rows"] == []
'''

PANEL_SOURCE = r'''"use client";

import { AlertTriangle, ArrowDownRight, ArrowUpRight, Star } from "lucide-react";
import Link from "next/link";

import { ChartCard } from "@/components/charts/chart-card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnomalies, useWatchlist } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";
import { formatPercent } from "@/lib/format";

/* Watchlist + anomalies.
 *
 * The fleet-wide alerts answer "is the business okay". This answers "is MY app okay",
 * which they structurally cannot: one app can halve while the fleet total moves two
 * percent and nobody hears about it.
 *
 * Anomalies are scored server-side against a robust baseline (median + MAD over the
 * trailing four weeks) on the latest COMPLETE day - never the newest partial one, which
 * would report the whole catalogue as collapsing every morning. */

const METRIC = "rpt_gross_revenue_usd";

export function WatchlistPanel({ filters }: { filters: Filters }) {
  const watchlist = useWatchlist();
  const anomalies = useAnomalies(filters, "app", METRIC, 8);

  const watched = watchlist.data ?? [];
  const rows = anomalies.data?.rows ?? [];
  const asOf = anomalies.data?.as_of;

  return (
    <ChartCard title="Watchlist & anomalies">
      <div className="space-y-4">
        <section>
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            Unusual today{asOf ? ` · ${asOf}` : ""}
          </p>
          {anomalies.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : anomalies.isError ? (
            <p className="text-sm text-[var(--color-negative)]">
              Could not score anomalies: {(anomalies.error as Error).message}
            </p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              Nothing unusual against the last four weeks.
            </p>
          ) : (
            <ul className="divide-y">
              {rows.map((row) => {
                const up = row.direction === "up";
                const color = up ? "var(--color-positive)" : "var(--color-negative)";
                return (
                  <li key={row.key ?? row.label} className="flex items-center gap-2 py-1.5">
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" style={{ color }} />
                    <Link
                      href={`/apps/${row.key}`}
                      className="min-w-0 flex-1 truncate text-sm hover:underline"
                    >
                      {row.label}
                    </Link>
                    {up ? (
                      <ArrowUpRight className="h-3.5 w-3.5 shrink-0" style={{ color }} />
                    ) : (
                      <ArrowDownRight className="h-3.5 w-3.5 shrink-0" style={{ color }} />
                    )}
                    <span className="shrink-0 text-sm font-semibold tabular-nums" style={{ color }}>
                      {row.change_pct != null ? formatPercent(row.change_pct) : "—"}
                    </span>
                    {/* A flat baseline has no spread, so it has no score. Saying so beats
                        printing an invented number. */}
                    <span className="hidden w-16 shrink-0 text-right text-xs tabular-nums text-[var(--color-text-muted)] sm:block">
                      {row.score != null ? `${row.score.toFixed(1)}σ` : "flat"}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section>
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            Watching
          </p>
          {watchlist.isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : watched.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              No apps starred. Open an app and star it to be told when it moves unusually.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {watched.map((item) => (
                <li key={item.canonical_key}>
                  <Link
                    href={`/apps/${item.canonical_key}`}
                    className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs hover:bg-[var(--color-bg-elevated)]"
                  >
                    <Star className="h-3 w-3 fill-current text-[var(--color-amber)]" />
                    {item.app_name ?? item.canonical_key}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </ChartCard>
  );
}
'''

TOGGLE_SOURCE = r'''"use client";

import { Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAddToWatchlist, useRemoveFromWatchlist, useWatchlist } from "@/lib/api-hooks";

/** Star an app to be told when it moves unusually.
 *
 *  Optimism is deliberately avoided here: the star reflects the SERVER's list, because a
 *  star that appears and then silently fails is worse than one that takes a moment. */
export function WatchToggle({ canonicalKey }: { canonicalKey: string }) {
  const watchlist = useWatchlist();
  const add = useAddToWatchlist();
  const remove = useRemoveFromWatchlist();

  const watching = (watchlist.data ?? []).some((i) => i.canonical_key === canonicalKey);
  const busy = add.isPending || remove.isPending || watchlist.isLoading;

  return (
    <Button
      size="sm"
      variant={watching ? "default" : "outline"}
      disabled={busy}
      aria-pressed={watching}
      onClick={() => (watching ? remove.mutate(canonicalKey) : add.mutate(canonicalKey))}
      title={
        watching
          ? "You are notified when this app moves unusually"
          : "Get notified when this app moves unusually"
      }
    >
      <Star className={`h-4 w-4 ${watching ? "fill-current" : ""}`} />
      <span className="ml-1">{watching ? "Watching" : "Watch"}</span>
    </Button>
  );
}
'''

# ── anchored edits ────────────────────────────────────────────────────────────
MODELS_INIT_EDITS = [
    (
        "from app.models.targets import RevenueTarget\n",
        "from app.models.watchlist import WatchlistItem\n",
        False,
    ),
    ('    "JobRun",\n', '    "WatchlistItem",\n', False),
]

MAIN_EDITS = [
    (
        "from app.api.v1 import views as views_routes\n",
        "from app.api.v1 import watchlist as watchlist_routes\n",
        False,
    ),
    (
        "app.include_router(annotations_routes.router, prefix=settings.api_v1_prefix)\n",
        "app.include_router(watchlist_routes.router, prefix=settings.api_v1_prefix)\n",
        False,
    ),
]

QB_ANCHOR = "    # ── table (keyset paginated, sort whitelist) ─────────────────────────────\n"
QB_ADD = '''    # ── daily series per entity (the anomaly scorer's input) ─────────────────
    def daily_by_entity(
        self, params: MetricFilters, group_by: GroupBy, metric: str
    ) -> Select[Any]:
        """One row per (entity, day) for ONE metric - the shape a per-app scorer needs.

        ``timeseries`` collapses every entity into one line and ``breakdown`` collapses
        every day into one number; scoring an app against its own history needs both
        axes at once. Same scope filter, same metric validation, same client narrowing
        as every other query here.
        """
        self._validate_metrics([metric])
        group_col = FACT_TABLE.c[_GROUP_BY_COLUMN[group_by]]
        columns: list[Any] = [group_col.label(group_by), FACT_TABLE.c.date.label("date")]
        if group_by == "app":
            columns.append(func.max(FACT_TABLE.c.app_name).label("app_name"))
        columns.append(self._sum(metric).label("value"))

        where = self._windowed_filters(params, params.date_from, params.date_to)
        return (
            select(*columns)
            .where(and_(*where))
            .group_by(group_col, FACT_TABLE.c.date)
            .order_by(group_col, FACT_TABLE.c.date)
        )

'''

METRICS_IMPORT_ANCHOR = (
    "from app.schemas.metrics import Bucket, GroupBy, MetricFilters, Platform, SortDirection\n"
    "from app.services import fact_schema, forecast_service, metrics_service, pacing_service\n"
)
METRICS_IMPORT_NEW = (
    "from app.schemas.metrics import Bucket, GroupBy, MetricFilters, Platform, SortDirection\n"
    "from app.schemas.watchlist import AnomalyResponse\n"
    "from app.services import (\n"
    "    anomaly_service,\n"
    "    fact_schema,\n"
    "    forecast_service,\n"
    "    metrics_service,\n"
    "    pacing_service,\n"
    "    settings_service,\n"
    ")\n"
)

METRICS_ROUTE_ANCHOR = '@router.get("/contribution")\n'
METRICS_ROUTE_ADD = '''@router.get("/anomalies", response_model=AnomalyResponse)
async def anomalies(
    filters: Filters,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    group_by: GroupBy = "app",
    metric: Annotated[str, Query(min_length=1)] = "rpt_gross_revenue_usd",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> AnomalyResponse:
    """Which entities moved unusually on the latest COMPLETE day.

    Scored against a robust baseline (median + MAD over the trailing four weeks), not a
    day-over-day percentage - a percentage flags every app with a weekend and misses the
    slow app that quietly halves. Same RBAC as /breakdown: the metric must be permitted
    and row scopes are injected.

    The baseline window is FIXED and independent of the selected dates, so the same app
    is not an anomaly on one page and not on another purely because of the date picker.
    That is also why this is not keyed on the filter dates alone in the cache.
    """
    qb = QueryBuilder(context)
    z_threshold = float(await settings_service.get_value(db, "anomaly_z_threshold")) / 10.0
    min_change = float(await settings_service.get_value(db, "anomaly_min_change_pct")) / 100.0
    key = aggregate_cache_key(
        "metrics.anomalies",
        scope_token(context.scopes),
        perms_token(context.metric_groups),
        _params(
            filters,
            group_by=group_by,
            metric=metric,
            limit=limit,
            z=z_threshold,
            c=min_change,
        ),
    )

    async def produce() -> dict[str, Any]:
        try:
            result = await anomaly_service.detect(
                db,
                qb,
                filters,
                group_by,
                metric,
                limit=limit,
                z_threshold=z_threshold,
                min_change_pct=min_change,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        # as_of is a date; the cache round-trips JSON, so serialise it here rather than
        # letting a datetime.date reach json.dumps.
        return {**result, "as_of": result["as_of"].isoformat() if result["as_of"] else None}

    result: dict[str, Any] = await cached_json(redis, key, produce)
    return AnomalyResponse(**result)


'''

REGISTRY_ANCHOR = '    "digest_enabled": SettingSpec(\n'
REGISTRY_ADD = '''    "watchlist_alerts_enabled": SettingSpec(
        key="watchlist_alerts_enabled",
        type="bool",
        default=False,
        label="Watchlist anomaly alerts",
        description="Once a day after the sync, notify each user about unusual movement on "
        "the apps THEY starred. Evaluated through each user's own permissions, so nobody "
        "is told a figure they cannot see on screen.",
    ),
    "anomaly_z_threshold": SettingSpec(
        key="anomaly_z_threshold",
        type="int",
        default=35,
        label="Anomaly threshold (×10)",
        description="How far from an app's own normal counts as unusual, in robust standard "
        "deviations × 10 (35 = 3.5σ). Lower finds more and cries wolf more.",
        minimum=10,
        maximum=100,
    ),
    "anomaly_min_change_pct": SettingSpec(
        key="anomaly_min_change_pct",
        type="int",
        default=20,
        label="Anomaly minimum change (%)",
        description="A move must also be at least this percent of the app's baseline. Without "
        "it, an app earning four dollars a day is 'anomalous' every time it earns six.",
        minimum=1,
        maximum=100,
    ),
'''

SCHEDULER_IMPORT_ANCHOR = "    alerts_service,\n"
SCHEDULER_IMPORT_ADD = "    anomaly_service,\n"
SCHEDULER_GATE_ANCHOR = """        alerts_on = bool(await settings_service.get_value(db, "alerts_enabled"))
        digest_on = bool(await settings_service.get_value(db, "digest_enabled"))
        if not alerts_on and not digest_on:
            return
"""
SCHEDULER_GATE_NEW = """        alerts_on = bool(await settings_service.get_value(db, "alerts_enabled"))
        digest_on = bool(await settings_service.get_value(db, "digest_enabled"))
        watchlist_on = bool(await settings_service.get_value(db, "watchlist_alerts_enabled"))
        if not alerts_on and not digest_on and not watchlist_on:
            return
"""
SCHEDULER_RUN_ANCHOR = """        # The digest is gated by its OWN setting and runs independently of alerts.
        if digest_on:
"""
SCHEDULER_RUN_NEW = """        # Per-user watchlist anomalies. Gated by its own setting and isolated like the
        # rest: a broken account must not stop the digest or the loop.
        if watchlist_on:
            try:
                await anomaly_service.notify_watchlists(db, settings)
            except Exception:  # noqa: BLE001 - must never block the digest or the loop
                log.exception("watchlist anomaly pass failed")
        # The digest is gated by its OWN setting and runs independently of alerts.
        if digest_on:
"""

TYPES_ANCHOR = "export interface TableResponse {\n"
TYPES_ADD = """/** One starred app. */
export interface WatchlistItem {
  canonical_key: string;
  app_name: string | null;
  created_at: string;
}

/** One entity that moved unusually against its OWN recent history.
 *  ``score`` is null when the baseline is perfectly flat - no spread, so no score. */
export interface AnomalyRow {
  key: string | null;
  label: string | null;
  value: number;
  baseline: number;
  delta: number;
  change_pct: number | null;
  score: number | null;
  direction: string;
}

export interface AnomalyResponse {
  metric: string;
  group_by: string;
  /** The latest COMPLETE fact date - never the newest partial one. */
  as_of: string | null;
  rows: AnomalyRow[];
  reason: string | null;
}

"""

HOOKS_IMPORT_ANCHOR = "  AdminUser,\n  Annotation,\n"
HOOKS_IMPORT_ADD = "  AnomalyResponse,\n"
HOOKS_IMPORT2_ANCHOR = "  UserContext,\n} from \"@/lib/types\";\n"
HOOKS_IMPORT2_NEW = "  UserContext,\n  WatchlistItem,\n} from \"@/lib/types\";\n"

HOOKS_ANCHOR = "// ── Identity (RBAC context + share directory) ────────────────────────────────\n"
HOOKS_ADD = '''// ── Watchlist + anomalies (per-app, not fleet-wide) ──────────────────────────
export function useWatchlist() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["watchlist"],
    queryFn: () => apiFetch<WatchlistItem[]>("/api/v1/watchlist"),
    enabled: Boolean(user),
  });
}

export function useAddToWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (canonicalKey: string) =>
      apiFetch<WatchlistItem>(`/api/v1/watchlist/${encodeURIComponent(canonicalKey)}`, {
        method: "PUT",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

export function useRemoveFromWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (canonicalKey: string) =>
      apiFetch<void>(`/api/v1/watchlist/${encodeURIComponent(canonicalKey)}`, {
        method: "DELETE",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

/** Entities that moved unusually on the latest COMPLETE day, scored server-side against
 *  their own recent history. */
export function useAnomalies(filters: Filters, groupBy: string, metric: string, limit = 10) {
  const { user } = useAuth();
  const params = { ...filtersToApiQuery(filters), group_by: groupBy, metric, limit };
  return useQuery({
    queryKey: ["anomalies", params],
    queryFn: () =>
      apiFetch<AnomalyResponse>(`/api/v1/metrics/anomalies${buildQuery(params)}`),
    enabled: Boolean(user) && metric.length > 0,
    staleTime: AGG_STALE,
  });
}

'''

DETAIL_IMPORT_ANCHOR = 'import { MetadataCard } from "@/components/app-detail/metadata-card";\n'
DETAIL_IMPORT_ADD = 'import { WatchToggle } from "@/components/app-detail/watch-toggle";\n'
DETAIL_BUTTON_ANCHOR = """        <div className="flex items-center gap-1">
          {PLATFORMS.map((p) => (
"""
DETAIL_BUTTON_NEW = """        <div className="flex items-center gap-1">
          <WatchToggle canonicalKey={canonicalKey} />
          {PLATFORMS.map((p) => (
"""

LAYOUT_ID_ANCHOR = '  "annotations",\n'
LAYOUT_ID_ADD = '  "watchlist",\n'
LAYOUT_GRID_ANCHOR = '  { i: "annotations", x: 0, y: 76, w: 12, h: 18, minW: 4, minH: 10 },\n'
LAYOUT_GRID_ADD = '  { i: "watchlist", x: 0, y: 76, w: 12, h: 18, minW: 4, minH: 10 },\n'

CLIENT_IMPORT_ANCHOR = 'import { WhatMoved } from "@/components/overview/what-moved";\n'
CLIENT_IMPORT_ADD = 'import { WatchlistPanel } from "@/components/overview/watchlist-panel";\n'
CLIENT_ITEM_ANCHOR = '    annotations: <AnnotationsPanel filters={filters} />,\n'
CLIENT_ITEM_ADD = '    watchlist: <WatchlistPanel filters={filters} />,\n'

TEST_META_EDITS = [('    "chart_annotations",\n', '    "watchlist_items",\n', False)]


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def plan_edits(
    path: Path, text: str, marker: str, edits: list[tuple[str, str, bool | None]]
) -> list[tuple[str, str, bool | None]] | None:
    if marker in text:
        print(f"{path}: already patched")
        return None
    for anchor, _, _ in edits:
        if text.count(anchor) != 1:
            first = anchor.splitlines()[0].strip()
            die(f"{path}: expected exactly one {first!r}, found {text.count(anchor)}")
    return edits


def plan_head_pin(path: Path, text: str, old: str, new: str) -> list[tuple[str, str, None]] | None:
    """Move test_migrations.py's pinned head revision - tolerantly.

    Every migration-bearing patch moves this ONE line, so re-running an earlier script
    after a later one would otherwise find its anchor gone and abort. The chain is
    forward-only: a head further along is correct, not broken. So the pin is only
    rewritten when it is still sitting on exactly the revision this patch supersedes.
    """
    match = re.search(r'_HEAD = "([0-9a-f]+)"', text)
    if match is None:
        die(f"{path}: no _HEAD pin found - the file has changed shape")
    current = match.group(1)
    if current == new:
        print(f"{path}: already pinned to {new}")
        return None
    if current != old:
        # NOT necessarily "further along" - it may be BEHIND, which means an earlier
        # migration patch in the chain has not run here. Either way this patch must not
        # rewrite a pin it does not recognise, but a pin left behind the database WILL
        # fail test_migrations, so say which case it is rather than implying it is fine.
        print(
            f"{path}: head pin is {current}, expected {old} - not touching it. "
            f"If the chain has not been run in order, this test will fail against a "
            f"database at {new}."
        )
        return None
    return [(f'_HEAD = "{old}"', f'_HEAD = "{new}"', None)]


def main() -> None:
    patched = [
        MODELS_INIT, MAIN, QB, METRICS_ROUTE, REGISTRY, SCHEDULER,
        TYPES, HOOKS, DETAIL, LAYOUT, CLIENT, TEST_META, TEST_MIGRATIONS,
    ]
    for path in patched:
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    # This sits next to the widgets the previous two feature patches added.
    if '"annotations"' not in LAYOUT.read_text():
        die(f"{LAYOUT}: run scripts/add-chart-annotations.py first - this builds on it")

    texts = {path: path.read_text() for path in patched}

    plan: dict[Path, list[tuple[str, str, bool | None]]] = {}
    for path, marker, edits in (
        (MODELS_INIT, "WatchlistItem", MODELS_INIT_EDITS),
        (MAIN, "watchlist_routes", MAIN_EDITS),
        (QB, "def daily_by_entity", [(QB_ANCHOR, QB_ADD, True)]),
        (
            METRICS_ROUTE,
            '"/anomalies"',
            [
                (METRICS_IMPORT_ANCHOR, METRICS_IMPORT_NEW, None),
                (METRICS_ROUTE_ANCHOR, METRICS_ROUTE_ADD, True),
            ],
        ),
        (REGISTRY, "watchlist_alerts_enabled", [(REGISTRY_ANCHOR, REGISTRY_ADD, True)]),
        (
            SCHEDULER,
            "anomaly_service",
            [
                (SCHEDULER_IMPORT_ANCHOR, SCHEDULER_IMPORT_ADD, False),
                (SCHEDULER_GATE_ANCHOR, SCHEDULER_GATE_NEW, None),
                (SCHEDULER_RUN_ANCHOR, SCHEDULER_RUN_NEW, None),
            ],
        ),
        (TYPES, "interface WatchlistItem", [(TYPES_ANCHOR, TYPES_ADD, True)]),
        (
            HOOKS,
            "useWatchlist",
            [
                (HOOKS_IMPORT_ANCHOR, HOOKS_IMPORT_ADD, False),
                (HOOKS_IMPORT2_ANCHOR, HOOKS_IMPORT2_NEW, None),
                (HOOKS_ANCHOR, HOOKS_ADD, True),
            ],
        ),
        (
            DETAIL,
            "WatchToggle",
            [
                (DETAIL_IMPORT_ANCHOR, DETAIL_IMPORT_ADD, False),
                (DETAIL_BUTTON_ANCHOR, DETAIL_BUTTON_NEW, None),
            ],
        ),
        (
            LAYOUT,
            '  "watchlist",\n',
            [(LAYOUT_ID_ANCHOR, LAYOUT_ID_ADD, False), (LAYOUT_GRID_ANCHOR, LAYOUT_GRID_ADD, False)],
        ),
        (
            CLIENT,
            "WatchlistPanel",
            [
                (CLIENT_IMPORT_ANCHOR, CLIENT_IMPORT_ADD, False),
                (CLIENT_ITEM_ANCHOR, CLIENT_ITEM_ADD, False),
            ],
        ),
        (TEST_META, "watchlist_items", TEST_META_EDITS),
    ):
        edits_or_none = plan_edits(path, texts[path], marker, edits)
        if edits_or_none is not None:
            plan[path] = edits_or_none

    head_edits = plan_head_pin(TEST_MIGRATIONS, texts[TEST_MIGRATIONS], "a1b2c3d4e5f6", "b2c3d4e5f6a7")
    if head_edits is not None:
        plan[TEST_MIGRATIONS] = head_edits

    # The route additions need names the file may not import yet. Check before writing
    # anything - a route referencing an unimported service is a 500 on the first call.
    if METRICS_ROUTE in plan:
        route_text = texts[METRICS_ROUTE]
        for name in ("aggregate_cache_key", "cached_json", "perms_token", "scope_token", "_params"):
            if name not in route_text:
                die(f"{METRICS_ROUTE}: {name} is missing - the file has changed shape")

    new_files = {
        MODEL: MODEL_SOURCE,
        MIGRATION: MIGRATION_SOURCE,
        COMPLETENESS: COMPLETENESS_SOURCE,
        SERVICE: SERVICE_SOURCE,
        SCHEMA: SCHEMA_SOURCE,
        ROUTER: ROUTER_SOURCE,
        TEST: TEST_SOURCE,
        PANEL: PANEL_SOURCE,
        TOGGLE: TOGGLE_SOURCE,
    }
    stale = {p: s for p, s in new_files.items() if not p.exists() or p.read_text() != s}

    if not plan and not stale:
        print("already installed - nothing to do")
        return

    for path, source in stale.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        print(f"wrote {path}")

    for path, edits in plan.items():
        text = texts[path]
        for anchor, addition, before in edits:
            if before is None:
                text = text.replace(anchor, addition, 1)
            else:
                text = text.replace(anchor, (addition + anchor) if before else (anchor + addition), 1)
        path.write_text(text)
        print(f"patched {path}")

    print("\nMIGRATION REQUIRED: alembic upgrade head (creates watchlist_items).")
    print("Watchlist alerts are OFF by default - turn on 'Watchlist anomaly alerts' in")
    print("Admin > System once you want the daily per-user notifications.")


if __name__ == "__main__":
    main()
