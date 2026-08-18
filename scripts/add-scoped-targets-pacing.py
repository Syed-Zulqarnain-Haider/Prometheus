#!/usr/bin/env python3
"""Features 6 and 7: targets per pod/app/publisher, and UA budget pacing.

The dashboard has exactly ONE goal in it: an org-wide monthly revenue target. That is a
number for the board, and it is useless to the person who actually owns a pod - they
cannot tell whether THEIR slice is ahead or behind, because nobody ever wrote down what
their slice was supposed to do. And the other half of the question, "are we overspending
this month", has no goal at all: UA cost is shown, never compared to a budget.

Both are the same missing object, so they are one table and one board:

  * A target is (kind, scope, month, amount). ``kind`` is 'revenue' or 'ua_budget';
    ``scope`` is org-wide or one pod / app / publisher / HOU.
  * The board shows, for every target the caller may see: actual to date, expected to
    date on a straight line, month-end projection, attainment and pace.

Design decisions worth keeping:

  * DIRECTION IS PER KIND, and it is not cosmetic. Running ahead of a revenue target is
    good; running ahead of a UA budget is overspending. A board that coloured both green
    would actively mislead, so the direction ships in the payload rather than being
    guessed in the UI.
  * Visibility follows the caller's scopes, exactly like chart annotations: a target
    naming a pod is a fact about that pod. It ALSO follows metric permissions - a revenue
    target is a revenue figure, which is the rule /meta/targets already applies, and a UA
    budget needs the ua_spend group.
  * Monthly only, deliberately. Annual org targets already exist in ``revenue_targets``
    and drive the yearly donut; duplicating them here would create two answers to "what
    is the goal". Pacing is a monthly question anyway.
  * The board is at most a handful of queries, not one per target: targets are grouped by
    (kind, scope_type) and each group is answered with a single breakdown over that
    dimension. Fifty pods do not mean fifty round trips.
  * Writing is admin-only (the ``admin_panel`` capability) and audit-logged. Reading is
    open to anyone the scope and metric rules allow.

Anchored: every anchor must appear EXACTLY once or NOTHING is written - all files
validate before any is touched. Idempotent. Requires `alembic upgrade head`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MODEL = Path("backend/app/models/scoped_targets.py")
MIGRATION = Path("backend/alembic/versions/20260818_1300_c3d4e5f6a7b8_scoped_targets.py")
SCHEMA = Path("backend/app/schemas/scoped_targets.py")
SERVICE = Path("backend/app/services/scoped_target_service.py")
ROUTER = Path("backend/app/api/v1/scoped_targets.py")
TEST = Path("backend/tests/test_scoped_targets.py")
ADMIN_PANEL = Path("frontend/components/admin/scoped-targets-panel.tsx")
BOARD = Path("frontend/components/overview/pacing-board.tsx")

MODELS_INIT = Path("backend/app/models/__init__.py")
MAIN = Path("backend/app/main.py")
TYPES = Path("frontend/lib/types.ts")
HOOKS = Path("frontend/lib/api-hooks.ts")
ADMIN_CLIENT = Path("frontend/components/admin/admin-client.tsx")
LAYOUT = Path("frontend/lib/overview-layout.ts")
CLIENT = Path("frontend/components/overview/overview-client.tsx")
TEST_META = Path("backend/tests/test_models_metadata.py")
TEST_MIGRATIONS = Path("backend/tests/test_migrations.py")

MODEL_SOURCE = '''"""Scoped monthly targets: revenue goals and UA budgets, per pod / app / publisher.

Deliberately separate from ``revenue_targets``, which holds the ORG-WIDE annual and
monthly revenue goal and drives the yearly progress donut. Two tables because they answer
two questions; folding the org target in here would leave two rows claiming to be "the"
goal for the same month.

Monthly only. Pacing is a monthly question, and an annual scoped target would need a
second unique index and a second set of "which one wins" rules for no benefit anyone
asked for.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 'revenue' is a goal to BEAT; 'ua_budget' is a ceiling to stay under. The distinction
# decides which direction is good, so it is data, not a UI convention.
TARGET_KINDS = ("revenue", "ua_budget")
TARGET_SCOPE_TYPES = ("all", "app", "pod", "publisher", "hou")


class ScopedTarget(Base):
    """One month's target for one scope."""

    __tablename__ = "scoped_targets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'all'"))
    scope_value: Mapped[str | None] = mapped_column(Text)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    target_usd: Mapped[float] = mapped_column(Double, nullable=False)
    set_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("kind IN ('revenue','ua_budget')", name="scoped_targets_kind_valid"),
        CheckConstraint(
            "scope_type IN ('all','app','pod','publisher','hou')",
            name="scoped_targets_scope_type_valid",
        ),
        CheckConstraint(
            "(scope_type = 'all' AND scope_value IS NULL) "
            "OR (scope_type <> 'all' AND scope_value IS NOT NULL)",
            name="scoped_targets_scope_value_valid",
        ),
        CheckConstraint("period_month BETWEEN 1 AND 12", name="scoped_targets_month_valid"),
        CheckConstraint("period_year BETWEEN 2000 AND 2100", name="scoped_targets_year_valid"),
        CheckConstraint("target_usd >= 0", name="scoped_targets_nonneg"),
        # TWO partial unique indexes, because Postgres treats NULLs as distinct: a single
        # index over scope_value would happily accept ten org-wide targets for one month.
        Index(
            "uq_scoped_targets_org",
            "kind",
            "period_year",
            "period_month",
            unique=True,
            postgresql_where=text("scope_type = 'all'"),
        ),
        Index(
            "uq_scoped_targets_scoped",
            "kind",
            "scope_type",
            "scope_value",
            "period_year",
            "period_month",
            unique=True,
            postgresql_where=text("scope_type <> 'all'"),
        ),
        Index("ix_scoped_targets_period", "period_year", "period_month"),
    )
'''

MIGRATION_SOURCE = '''"""Scoped monthly targets (revenue goals + UA budgets) per pod / app / publisher.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scoped_targets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("scope_type", sa.Text(), nullable=False, server_default=sa.text("'all'")),
        sa.Column("scope_value", sa.Text(), nullable=True),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("target_usd", sa.Double(), nullable=False),
        sa.Column("set_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["set_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint("kind IN ('revenue','ua_budget')", name="scoped_targets_kind_valid"),
        sa.CheckConstraint(
            "scope_type IN ('all','app','pod','publisher','hou')",
            name="scoped_targets_scope_type_valid",
        ),
        sa.CheckConstraint(
            "(scope_type = 'all' AND scope_value IS NULL) "
            "OR (scope_type <> 'all' AND scope_value IS NOT NULL)",
            name="scoped_targets_scope_value_valid",
        ),
        sa.CheckConstraint("period_month BETWEEN 1 AND 12", name="scoped_targets_month_valid"),
        sa.CheckConstraint("period_year BETWEEN 2000 AND 2100", name="scoped_targets_year_valid"),
        sa.CheckConstraint("target_usd >= 0", name="scoped_targets_nonneg"),
    )
    # Partial, because Postgres treats NULL scope_value as distinct - one plain unique
    # index would accept ten org-wide targets for the same month.
    op.create_index(
        "uq_scoped_targets_org",
        "scoped_targets",
        ["kind", "period_year", "period_month"],
        unique=True,
        postgresql_where=sa.text("scope_type = 'all'"),
    )
    op.create_index(
        "uq_scoped_targets_scoped",
        "scoped_targets",
        ["kind", "scope_type", "scope_value", "period_year", "period_month"],
        unique=True,
        postgresql_where=sa.text("scope_type <> 'all'"),
    )
    op.create_index(
        "ix_scoped_targets_period", "scoped_targets", ["period_year", "period_month"]
    )


def downgrade() -> None:
    op.drop_index("ix_scoped_targets_period", table_name="scoped_targets")
    op.drop_index("uq_scoped_targets_scoped", table_name="scoped_targets")
    op.drop_index("uq_scoped_targets_org", table_name="scoped_targets")
    op.drop_table("scoped_targets")
'''

SCHEMA_SOURCE = '''"""Scoped target + pacing board models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TargetKind = Literal["revenue", "ua_budget"]
TargetScopeType = Literal["all", "app", "pod", "publisher", "hou"]


class ScopedTargetIn(BaseModel):
    kind: TargetKind
    scope_type: TargetScopeType = "all"
    scope_value: str | None = Field(default=None, max_length=200)
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)
    target_usd: float = Field(ge=0)

    @model_validator(mode="after")
    def _scope_value_matches_type(self) -> ScopedTargetIn:
        value = (self.scope_value or "").strip() or None
        if self.scope_type == "all" and value is not None:
            raise ValueError("An org-wide target cannot carry a scope value.")
        if self.scope_type != "all" and value is None:
            raise ValueError("A scoped target must name what it applies to.")
        self.scope_value = value
        return self


class ScopedTargetOut(BaseModel):
    id: uuid.UUID
    kind: str
    scope_type: str
    scope_value: str | None
    period_year: int
    period_month: int
    target_usd: float
    updated_at: datetime


class PacingRow(BaseModel):
    """One target and how it is actually going."""

    id: uuid.UUID
    kind: str
    scope_type: str
    scope_value: str | None
    label: str
    target_usd: float
    actual_usd: float
    # Straight-line expectation for the days elapsed - the yardstick, not a forecast.
    expected_to_date_usd: float
    # Month-end estimate at the current run rate.
    projected_usd: float | None
    attainment_pct: float | None
    pace_pct: float | None
    # TRUE for a revenue goal, FALSE for a UA budget. Running ahead of a budget is
    # overspending, so this is data - a board that coloured both green would mislead.
    higher_is_better: bool


class PacingBoard(BaseModel):
    year: int
    month: int
    days_elapsed: int
    days_in_month: int
    rows: list[PacingRow]
'''

SERVICE_SOURCE = '''"""Scoped targets and the pacing board.

The board answers, for every target the caller may see: how much has actually landed, how
much SHOULD have landed by now on a straight line, where the month is heading at the
current rate, and whether that is good news.

Two rules do most of the work here:

  * Direction is per KIND. Beating a revenue target is good; beating a UA budget means
    overspending. ``higher_is_better`` ships in the payload so no consumer has to guess.
  * The board never runs one query per target. Targets are grouped by (kind, scope_type)
    and each group is answered with ONE breakdown over that dimension, so fifty pods cost
    one round trip, not fifty.
"""

from __future__ import annotations

import calendar
import uuid
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, and_, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScopedTarget
from app.schemas.auth import UserContext
from app.schemas.metrics import MetricFilters
from app.services import metrics_service
from app.services.query_builder import QueryBuilder

# The measure each kind is measured against. Both are from the REPORTED ladder, so the
# board agrees with the KPI cards rather than quietly using a different definition.
KIND_METRIC: dict[str, str] = {
    "revenue": "rpt_gross_revenue_usd",
    "ua_budget": "rpt_ua_cost_usd",
}
KIND_HIGHER_IS_BETTER: dict[str, bool] = {"revenue": True, "ua_budget": False}

# scope_type -> the breakdown dimension that answers it.
SCOPE_TO_GROUP_BY: dict[str, str] = {
    "app": "app",
    "pod": "pod",
    "publisher": "publisher",
    "hou": "hou",
}

# A board is a board, not an export. Past this it is a spreadsheet and should be one.
MAX_ROWS = 200


def visible_to(context: UserContext) -> ColumnElement[bool]:
    """WHERE clause for "targets this caller may see".

    Same rule as chart annotations: an org-wide target is for everyone, a scoped one is
    visible only to callers holding a scope of the same type and value. A target naming a
    pod is a fact about that pod.
    """
    scope_types = {s.scope_type for s in context.scopes}
    if "all" in scope_types:
        return true()
    if not context.scopes:
        return false()  # no scopes -> no rows, the same fail-closed rule as everywhere

    conditions: list[ColumnElement[bool]] = [ScopedTarget.scope_type == "all"]
    for scope_type in ("app", "pod", "publisher", "hou"):
        values = sorted(
            {
                s.scope_value
                for s in context.scopes
                if s.scope_type == scope_type and s.scope_value is not None
            }
        )
        if values:
            conditions.append(
                and_(
                    ScopedTarget.scope_type == scope_type,
                    ScopedTarget.scope_value.in_(values),
                )
            )
    return or_(*conditions)


def permitted_kinds(qb: QueryBuilder) -> set[str]:
    """Which kinds this caller may be told about at all.

    A revenue target is a revenue figure - the same rule /meta/targets applies, so a
    store-installs-only role never learns the goal. A UA budget needs the spend measure.
    """
    return {kind for kind, metric in KIND_METRIC.items() if metric in qb.permitted_measures}


async def list_targets(
    db: AsyncSession, context: UserContext, qb: QueryBuilder, year: int, month: int
) -> list[ScopedTarget]:
    kinds = permitted_kinds(qb)
    if not kinds:
        return []
    rows = (
        await db.scalars(
            select(ScopedTarget)
            .where(
                ScopedTarget.period_year == year,
                ScopedTarget.period_month == month,
                ScopedTarget.kind.in_(sorted(kinds)),
                visible_to(context),
            )
            .order_by(ScopedTarget.kind, ScopedTarget.scope_type, ScopedTarget.scope_value)
            .limit(MAX_ROWS)
        )
    ).all()
    return list(rows)


def _elapsed(year: int, month: int, today: date) -> tuple[int, int]:
    """(days elapsed in the month, days in the month) as of ``today``."""
    days_in_month = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, days_in_month)
    if today < start:
        return 0, days_in_month
    if today >= end:
        return days_in_month, days_in_month
    return (today - start).days + 1, days_in_month


async def pacing_board(
    db: AsyncSession,
    context: UserContext,
    qb: QueryBuilder,
    year: int,
    month: int,
    today: date,
) -> dict[str, Any]:
    """Every visible target for the month, with actual / expected / projected."""
    days_elapsed, days_in_month = _elapsed(year, month, today)
    targets = await list_targets(db, context, qb, year, month)
    if not targets or days_elapsed == 0:
        return {
            "year": year,
            "month": month,
            "days_elapsed": days_elapsed,
            "days_in_month": days_in_month,
            # A month that has not started has no actuals. Returning the targets with
            # zeros would read as "everything is at 0% with days to go", which is alarming
            # and false; an empty board is the honest shape.
            "rows": [],
        }

    month_start = date(year, month, 1)
    window_end = min(today, date(year, month, days_in_month))
    base = MetricFilters(date_from=month_start, date_to=window_end)

    # ONE query per (kind, scope_type) group, not one per target.
    actuals: dict[tuple[str, str, str | None], float] = {}
    groups: dict[tuple[str, str], list[str | None]] = {}
    for target in targets:
        groups.setdefault((target.kind, target.scope_type), []).append(target.scope_value)

    for (kind, scope_type), _values in groups.items():
        metric = KIND_METRIC[kind]
        if scope_type == "all":
            summary = await metrics_service.run_summary(db, qb, base)
            actuals[(kind, "all", None)] = float(summary["current"].get(metric) or 0.0)
            continue
        group_by = SCOPE_TO_GROUP_BY[scope_type]
        rows = (
            (await db.execute(qb.breakdown(base, group_by, [metric])))  # type: ignore[arg-type]
            .mappings()
            .all()
        )
        for row in rows:
            actuals[(kind, scope_type, row[group_by])] = float(row[metric] or 0.0)

    fraction = days_elapsed / days_in_month if days_in_month else 0.0
    out: list[dict[str, Any]] = []
    for target in targets:
        actual = actuals.get((target.kind, target.scope_type, target.scope_value), 0.0)
        goal = float(target.target_usd)
        expected = goal * fraction
        out.append(
            {
                "id": target.id,
                "kind": target.kind,
                "scope_type": target.scope_type,
                "scope_value": target.scope_value,
                "label": target.scope_value or "Everyone",
                "target_usd": goal,
                "actual_usd": actual,
                "expected_to_date_usd": expected,
                "projected_usd": (actual / fraction) if fraction > 0 else None,
                # Guarded on zero rather than reported as 0% or infinity: a target of
                # zero has no attainment, and saying so beats printing a division.
                "attainment_pct": (actual / goal) if goal else None,
                "pace_pct": (actual / expected) if expected else None,
                "higher_is_better": KIND_HIGHER_IS_BETTER[target.kind],
            }
        )
    return {
        "year": year,
        "month": month,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "rows": out,
    }


async def upsert(
    db: AsyncSession,
    *,
    kind: str,
    scope_type: str,
    scope_value: str | None,
    period_year: int,
    period_month: int,
    target_usd: float,
    set_by: uuid.UUID,
) -> ScopedTarget:
    """Set one target. Setting the same scope and month again REPLACES it - a second row
    for the same slice would leave two answers to "what is the goal"."""
    existing = await db.scalar(
        select(ScopedTarget).where(
            ScopedTarget.kind == kind,
            ScopedTarget.scope_type == scope_type,
            ScopedTarget.scope_value.is_(None)
            if scope_value is None
            else ScopedTarget.scope_value == scope_value,
            ScopedTarget.period_year == period_year,
            ScopedTarget.period_month == period_month,
        )
    )
    if existing is not None:
        existing.target_usd = target_usd
        existing.set_by = set_by
        await db.commit()
        await db.refresh(existing)
        return existing

    row = ScopedTarget(
        kind=kind,
        scope_type=scope_type,
        scope_value=scope_value,
        period_year=period_year,
        period_month=period_month,
        target_usd=target_usd,
        set_by=set_by,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
'''

ROUTER_SOURCE = '''"""Scoped targets: monthly revenue goals and UA budgets per pod / app / publisher.

Reading is open to anyone the scope and metric rules allow. Writing is admin-only and
audit-logged - a target is what everyone else is measured against, so who set it matters.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.api.deps import CurrentUser, DbSession, require_capability
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.models import ScopedTarget
from app.schemas.scoped_targets import PacingBoard, ScopedTargetIn, ScopedTargetOut
from app.services import scoped_target_service
from app.services.audit import AuditDep
from app.services.query_builder import QueryBuilder

router = APIRouter(
    prefix="/scoped-targets", tags=["targets"], dependencies=[Depends(enforce_rate_limit)]
)

RequireAdmin = Depends(require_capability("admin_panel"))


def _out(row: ScopedTarget) -> ScopedTargetOut:
    return ScopedTargetOut(
        id=row.id,
        kind=row.kind,
        scope_type=row.scope_type,
        scope_value=row.scope_value,
        period_year=row.period_year,
        period_month=row.period_month,
        target_usd=row.target_usd,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[ScopedTargetOut])
async def list_scoped_targets(
    context: CurrentUser,
    db: DbSession,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> list[ScopedTargetOut]:
    """Targets for one month that this caller may see."""
    qb = QueryBuilder(context)
    rows = await scoped_target_service.list_targets(db, context, qb, year, month)
    return [_out(row) for row in rows]


@router.get("/pacing", response_model=PacingBoard)
async def pacing(
    context: CurrentUser,
    db: DbSession,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> PacingBoard:
    """Every visible target with actual, expected-to-date, projection and pace.

    ``higher_is_better`` is per row: beating a revenue target is good news, beating a UA
    budget is overspending, and a board that coloured both green would mislead.
    """
    qb = QueryBuilder(context)
    board = await scoped_target_service.pacing_board(
        db, context, qb, year, month, datetime.now(UTC).date()
    )
    return PacingBoard(**board)


@router.put("", response_model=ScopedTargetOut, dependencies=[RequireAdmin])
async def put_scoped_target(
    body: ScopedTargetIn,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> ScopedTargetOut:
    """Set (or replace) one target. Admin only - this is what everyone else is measured
    against."""
    try:
        row = await scoped_target_service.upsert(
            db,
            kind=body.kind,
            scope_type=body.scope_type,
            scope_value=body.scope_value,
            period_year=body.period_year,
            period_month=body.period_month,
            target_usd=body.target_usd,
            set_by=context.user_id,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_set_scoped_target",
        resource=f"{body.kind}:{body.scope_type}:{body.scope_value or ''}",
        detail={
            "period": f"{body.period_year}-{body.period_month:02d}",
            "target_usd": body.target_usd,
        },
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _out(row)


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[RequireAdmin])
async def delete_scoped_target(
    target_id: uuid.UUID,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> Response:
    row = await db.get(ScopedTarget, target_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
    detail: dict[str, Any] = {
        "kind": row.kind,
        "scope": f"{row.scope_type}:{row.scope_value or ''}",
        "period": f"{row.period_year}-{row.period_month:02d}",
    }
    await db.delete(row)
    await db.commit()
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_delete_scoped_target",
        resource=str(target_id),
        detail=detail,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

'''

TEST_SOURCE = '''"""Scoped targets: who may see one, who may set one, and the pacing arithmetic.

The direction rule is the one worth guarding hardest. Beating a revenue target is good
news; beating a UA budget is overspending, and a board that reported both the same way
would be actively misleading.
"""

from datetime import date
from typing import Any

from app.services.scoped_target_service import (
    KIND_HIGHER_IS_BETTER,
    KIND_METRIC,
    SCOPE_TO_GROUP_BY,
    _elapsed,
)

from tests.conftest import MetricsEnv

URL = "/api/v1/scoped-targets"


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


def _target(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "kind": "revenue",
        "scope_type": "all",
        "scope_value": None,
        "period_year": 2026,
        "period_month": 6,
        "target_usd": 1000.0,
    }
    body.update(overrides)
    return body


def test_direction_differs_by_kind() -> None:
    """The whole point: ahead of a revenue goal is good, ahead of a budget is not."""
    assert KIND_HIGHER_IS_BETTER["revenue"] is True
    assert KIND_HIGHER_IS_BETTER["ua_budget"] is False


def test_elapsed_days_clamp_to_the_month() -> None:
    assert _elapsed(2026, 6, date(2026, 5, 20)) == (0, 30)  # month not started
    assert _elapsed(2026, 6, date(2026, 6, 10)) == (10, 30)
    assert _elapsed(2026, 6, date(2026, 7, 5)) == (30, 30)  # month finished
    assert _elapsed(2026, 2, date(2026, 2, 28)) == (28, 28)  # not a leap year


def test_every_scope_type_maps_to_a_breakdown_dimension() -> None:
    """A scope with no dimension would silently score every target against zero."""
    assert set(SCOPE_TO_GROUP_BY) == {"app", "pod", "publisher", "hou"}


def test_both_kinds_measure_the_reported_ladder() -> None:
    """Not total_revenue_usd / total_ua_spend_usd - the board has to agree with the KPI
    cards rather than quietly using a second definition of revenue."""
    assert KIND_METRIC == {
        "revenue": "rpt_gross_revenue_usd",
        "ua_budget": "rpt_ua_cost_usd",
    }


async def test_requires_auth(metrics_env: MetricsEnv) -> None:
    assert (await metrics_env.client.put(URL, json=_target())).status_code == 401


async def test_only_admins_can_set_a_target(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.put(URL, json=_target(), headers=_auth("finance"))
    assert resp.status_code == 403


async def test_set_then_read_round_trip(metrics_env: MetricsEnv) -> None:
    created = await metrics_env.client.put(URL, json=_target(), headers=_auth("admin"))
    assert created.status_code == 200, created.text

    listed = await metrics_env.client.get(
        URL, params={"year": 2026, "month": 6}, headers=_auth("admin")
    )
    assert [t["id"] for t in listed.json()] == [created.json()["id"]]


async def test_setting_the_same_scope_replaces_rather_than_duplicates(
    metrics_env: MetricsEnv,
) -> None:
    first = await metrics_env.client.put(URL, json=_target(), headers=_auth("admin"))
    second = await metrics_env.client.put(
        URL, json=_target(target_usd=2000.0), headers=_auth("admin")
    )
    assert second.json()["id"] == first.json()["id"]  # same row, not a second goal
    assert second.json()["target_usd"] == 2000.0


async def test_scoped_target_needs_a_value(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.put(
        URL, json=_target(scope_type="pod", scope_value=None), headers=_auth("admin")
    )
    assert resp.status_code == 422


async def test_scoped_user_sees_only_their_own_scope(metrics_env: MetricsEnv) -> None:
    mine = await metrics_env.client.put(
        URL, json=_target(scope_type="pod", scope_value="POD_A"), headers=_auth("admin")
    )
    await metrics_env.client.put(
        URL, json=_target(scope_type="pod", scope_value="POD_B"), headers=_auth("admin")
    )
    org = await metrics_env.client.put(URL, json=_target(), headers=_auth("admin"))

    listed = await metrics_env.client.get(
        URL, params={"year": 2026, "month": 6}, headers=_auth("pod_owner_scoped")
    )
    visible = {t["id"] for t in listed.json()}
    assert visible == {mine.json()["id"], org.json()["id"]}  # nothing from POD_B


async def test_viewer_is_not_told_the_revenue_goal(metrics_env: MetricsEnv) -> None:
    """A target is a revenue figure - the same rule /meta/targets applies."""
    await metrics_env.client.put(URL, json=_target(), headers=_auth("admin"))
    listed = await metrics_env.client.get(
        URL, params={"year": 2026, "month": 6}, headers=_auth("viewer")
    )
    assert listed.status_code == 200
    assert listed.json() == []


async def test_pacing_board_shape(metrics_env: MetricsEnv) -> None:
    await metrics_env.client.put(URL, json=_target(), headers=_auth("admin"))
    resp = await metrics_env.client.get(
        f"{URL}/pacing", params={"year": 2026, "month": 6}, headers=_auth("admin")
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["days_in_month"] == 30
    for row in body["rows"]:
        assert row["higher_is_better"] is True
        # Expected-to-date is the straight line, never above the goal itself.
        assert row["expected_to_date_usd"] <= row["target_usd"] + 1e-9


async def test_delete_is_admin_only_and_removes_the_row(metrics_env: MetricsEnv) -> None:
    created = await metrics_env.client.put(URL, json=_target(), headers=_auth("admin"))
    target_id = created.json()["id"]
    assert (
        await metrics_env.client.delete(f"{URL}/{target_id}", headers=_auth("finance"))
    ).status_code == 403
    assert (
        await metrics_env.client.delete(f"{URL}/{target_id}", headers=_auth("admin"))
    ).status_code == 204
    listed = await metrics_env.client.get(
        URL, params={"year": 2026, "month": 6}, headers=_auth("admin")
    )
    assert listed.json() == []
'''

ADMIN_PANEL_SOURCE = r'''"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useDeleteScopedTarget,
  useScopedTargets,
  useSetScopedTarget,
} from "@/lib/api-hooks";
import { formatUSD } from "@/lib/format";

/* Per-pod / per-app goals and UA budgets.
 *
 * The org-wide annual and monthly revenue goal lives in the panel above - it drives the
 * yearly progress donut and is deliberately a separate object. These are the goals the
 * people who actually own a slice are measured against, plus the budget half of the
 * question, which had no goal at all before: UA cost was shown and never compared to
 * anything. */

const KINDS = [
  { id: "revenue", label: "Revenue goal" },
  { id: "ua_budget", label: "UA budget" },
] as const;

const SCOPE_TYPES = [
  { id: "all", label: "Everyone" },
  { id: "pod", label: "Pod" },
  { id: "app", label: "App" },
  { id: "publisher", label: "Publisher" },
  { id: "hou", label: "HOU" },
] as const;

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const NOW = new Date();
const YEAR_OPTIONS = [NOW.getFullYear() - 1, NOW.getFullYear(), NOW.getFullYear() + 1];

const SELECT_CLASS =
  "h-9 w-full rounded-[var(--radius-inner)] border border-input bg-background px-2 text-sm outline-none focus:ring-1 focus:ring-ring";

export function ScopedTargetsPanel() {
  const [year, setYear] = useState(NOW.getFullYear());
  const [month, setMonth] = useState(NOW.getMonth() + 1);
  const list = useScopedTargets(year, month);
  const save = useSetScopedTarget();
  const remove = useDeleteScopedTarget();

  const [kind, setKind] = useState<string>("revenue");
  const [scopeType, setScopeType] = useState<string>("pod");
  const [scopeValue, setScopeValue] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const parsed = Number(amount.replace(/,/g, ""));
    if (!Number.isFinite(parsed) || parsed < 0) {
      setError("Enter a number of dollars, zero or more.");
      return;
    }
    save.mutate(
      {
        kind,
        scope_type: scopeType,
        scope_value: scopeType === "all" ? null : scopeValue.trim() || null,
        period_year: year,
        period_month: month,
        target_usd: parsed,
      },
      {
        onSuccess: () => {
          setScopeValue("");
          setAmount("");
        },
        onError: (err) => setError((err as Error).message),
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pod, app &amp; publisher targets</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="scoped-year">Year</Label>
            <select
              id="scoped-year"
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className={SELECT_CLASS}
            >
              {YEAR_OPTIONS.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="scoped-month">Month</Label>
            <select
              id="scoped-month"
              value={month}
              onChange={(e) => setMonth(Number(e.target.value))}
              className={SELECT_CLASS}
            >
              {MONTHS.map((name, index) => (
                <option key={name} value={index + 1}>
                  {name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <form onSubmit={submit} className="grid gap-3 rounded-[var(--radius-inner)] border p-3 sm:grid-cols-4">
          <div>
            <Label htmlFor="scoped-kind">Kind</Label>
            <select
              id="scoped-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className={SELECT_CLASS}
            >
              {KINDS.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="scoped-scope">Applies to</Label>
            <select
              id="scoped-scope"
              value={scopeType}
              onChange={(e) => {
                setScopeType(e.target.value);
                setScopeValue("");
              }}
              className={SELECT_CLASS}
            >
              {SCOPE_TYPES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="scoped-value">Which one</Label>
            <Input
              id="scoped-value"
              value={scopeValue}
              onChange={(e) => setScopeValue(e.target.value)}
              placeholder={scopeType === "all" ? "—" : "e.g. POD_A"}
              disabled={scopeType === "all"}
              maxLength={200}
            />
          </div>
          <div>
            <Label htmlFor="scoped-amount">Amount (USD)</Label>
            <Input
              id="scoped-amount"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="250000"
              inputMode="decimal"
            />
          </div>
          <div className="sm:col-span-4 flex items-center justify-between">
            <span className="text-xs text-[var(--color-text-muted)]">
              Setting the same scope and month again replaces it — one goal per slice.
            </span>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Set target"}
            </Button>
          </div>
          {error && <p className="sm:col-span-4 text-xs text-[var(--color-negative)]">{error}</p>}
        </form>

        {list.isLoading ? (
          <p className="text-sm text-[var(--color-text-muted)]">Loading…</p>
        ) : (list.data ?? []).length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            Nothing set for {MONTHS[month - 1]} {year}.
          </p>
        ) : (
          <ul className="divide-y">
            {(list.data ?? []).map((target) => (
              <li key={target.id} className="flex items-center gap-2 py-2">
                <span className="w-28 shrink-0 text-xs text-[var(--color-text-muted)]">
                  {target.kind === "revenue" ? "Revenue goal" : "UA budget"}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm">
                  {target.scope_type === "all"
                    ? "Everyone"
                    : `${target.scope_type}: ${target.scope_value}`}
                </span>
                <span className="shrink-0 text-sm font-semibold tabular-nums">
                  {formatUSD(target.target_usd)}
                </span>
                <button
                  type="button"
                  aria-label={`Delete ${target.kind} target`}
                  onClick={() => remove.mutate(target.id)}
                  className="shrink-0 rounded p-1 text-[var(--color-text-muted)] hover:text-[var(--color-negative)]"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
'''

BOARD_SOURCE = r'''"use client";

import { ChartCard } from "@/components/charts/chart-card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePacingBoard } from "@/lib/api-hooks";
import { formatPercent, formatUSD } from "@/lib/format";
import type { PacingRow } from "@/lib/types";

/* Targets and budgets, and whether they are actually going to be hit.
 *
 * The direction is NOT cosmetic and is not decided here: running ahead of a revenue goal
 * is good news, running ahead of a UA budget is overspending. The server sends
 * higher_is_better per row, and this only renders it. */

const NOW = new Date();

function verdict(row: PacingRow): { text: string; color: string } {
  if (row.pace_pct == null) {
    return { text: "no pace yet", color: "var(--color-text-muted)" };
  }
  const ahead = row.pace_pct >= 1;
  const good = ahead === row.higher_is_better;
  const word = row.higher_is_better
    ? ahead
      ? "ahead of pace"
      : "behind pace"
    : ahead
      ? "over budget pace"
      : "under budget";
  return { text: word, color: good ? "var(--color-positive)" : "var(--color-negative)" };
}

function Row({ row }: { row: PacingRow }) {
  const { text, color } = verdict(row);
  // Bar is the straight-line expectation vs what actually landed, capped so a runaway
  // month does not push the layout sideways.
  const share = row.target_usd > 0 ? Math.min(1, row.actual_usd / row.target_usd) : 0;
  const expectedShare = row.target_usd > 0 ? Math.min(1, row.expected_to_date_usd / row.target_usd) : 0;

  return (
    <li className="space-y-1 py-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 flex-1 truncate text-sm">
          {row.label}
          <span className="ml-1.5 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
            {row.kind === "revenue" ? "revenue" : "UA budget"}
          </span>
        </span>
        <span className="shrink-0 text-sm font-semibold tabular-nums">
          {formatUSD(row.actual_usd, { compact: true })}
          <span className="text-[var(--color-text-muted)]">
            {" / "}
            {formatUSD(row.target_usd, { compact: true })}
          </span>
        </span>
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-[var(--color-bg-elevated)]">
        <span
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${share * 100}%`, backgroundColor: color }}
        />
        {/* Where a straight line says we should be today. */}
        <span
          className="absolute inset-y-0 w-px bg-[var(--color-text-muted)]"
          style={{ left: `${expectedShare * 100}%` }}
          aria-hidden
        />
      </div>
      <div className="flex items-center justify-between text-[10px]">
        <span style={{ color }}>{text}</span>
        <span className="tabular-nums text-[var(--color-text-muted)]">
          {row.projected_usd != null
            ? `projected ${formatUSD(row.projected_usd, { compact: true })}`
            : "—"}
          {row.attainment_pct != null ? ` · ${formatPercent(row.attainment_pct, 0)}` : ""}
        </span>
      </div>
    </li>
  );
}

export function PacingBoard() {
  const query = usePacingBoard(NOW.getFullYear(), NOW.getMonth() + 1);
  const rows = query.data?.rows ?? [];

  return (
    <ChartCard title="Targets & budgets">
      {query.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : query.isError ? (
        <p className="text-sm text-[var(--color-negative)]">
          Could not load pacing: {(query.error as Error).message}
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">
          No targets set for this month that you can see. An admin sets them in Admin →
          Targets &amp; budgets.
        </p>
      ) : (
        <>
          <p className="text-[10px] text-[var(--color-text-muted)]">
            Day {query.data?.days_elapsed} of {query.data?.days_in_month} · the tick marks
            where a straight line says today should be.
          </p>
          <ul className="divide-y">
            {rows.map((row) => (
              <Row key={row.id} row={row} />
            ))}
          </ul>
        </>
      )}
    </ChartCard>
  );
}
'''

# ── anchored edits ────────────────────────────────────────────────────────────
MODELS_INIT_EDITS = [
    (
        "from app.models.settings import AppSetting\n",
        "from app.models.scoped_targets import ScopedTarget\n",
        True,
    ),
    ('    "RevenueTarget",\n', '    "ScopedTarget",\n', False),
]

MAIN_EDITS = [
    (
        "from app.api.v1 import reports as reports_routes\n",
        "from app.api.v1 import scoped_targets as scoped_targets_routes\n",
        False,
    ),
    (
        "app.include_router(watchlist_routes.router, prefix=settings.api_v1_prefix)\n",
        "app.include_router(scoped_targets_routes.router, prefix=settings.api_v1_prefix)\n",
        False,
    ),
]

TYPES_ANCHOR = "export interface TableResponse {\n"
TYPES_ADD = """/** A monthly goal for one slice. ``kind`` is "revenue" (a goal to beat) or
 *  "ua_budget" (a ceiling to stay under). */
export interface ScopedTarget {
  id: string;
  kind: string;
  scope_type: string;
  scope_value: string | null;
  period_year: number;
  period_month: number;
  target_usd: number;
  updated_at: string;
}

export interface ScopedTargetInput {
  kind: string;
  scope_type: string;
  scope_value: string | null;
  period_year: number;
  period_month: number;
  target_usd: number;
}

export interface PacingRow {
  id: string;
  kind: string;
  scope_type: string;
  scope_value: string | null;
  label: string;
  target_usd: number;
  actual_usd: number;
  expected_to_date_usd: number;
  projected_usd: number | null;
  attainment_pct: number | null;
  pace_pct: number | null;
  /** TRUE for a revenue goal, FALSE for a UA budget - running ahead of a budget is
   *  overspending, so the direction is data, not a UI convention. */
  higher_is_better: boolean;
}

export interface PacingBoardResponse {
  year: number;
  month: number;
  days_elapsed: number;
  days_in_month: number;
  rows: PacingRow[];
}

"""

HOOKS_IMPORT_ANCHOR = "  BenchmarkResponse,\n"
HOOKS_IMPORT_ADD = "  PacingBoardResponse,\n"
HOOKS_IMPORT2_ANCHOR = '  UserContext,\n  WatchlistItem,\n} from "@/lib/types";\n'
HOOKS_IMPORT2_NEW = (
    '  ScopedTarget,\n  ScopedTargetInput,\n  UserContext,\n  WatchlistItem,\n'
    '} from "@/lib/types";\n'
)

HOOKS_ANCHOR = "// ── Identity (RBAC context + share directory) ────────────────────────────────\n"
HOOKS_ADD = '''// ── Scoped targets + pacing (per pod/app goals and UA budgets) ───────────────
export function useScopedTargets(year: number, month: number) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["scoped-targets", year, month],
    queryFn: () =>
      apiFetch<ScopedTarget[]>(`/api/v1/scoped-targets${buildQuery({ year, month })}`),
    enabled: Boolean(user),
  });
}

export function useSetScopedTarget() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ScopedTargetInput) =>
      apiFetch<ScopedTarget>("/api/v1/scoped-targets", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scoped-targets"] });
      queryClient.invalidateQueries({ queryKey: ["pacing-board"] });
    },
  });
}

export function useDeleteScopedTarget() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/v1/scoped-targets/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scoped-targets"] });
      queryClient.invalidateQueries({ queryKey: ["pacing-board"] });
    },
  });
}

/** Every visible target with actual, expected-to-date, projection and pace. */
export function usePacingBoard(year: number, month: number) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["pacing-board", year, month],
    queryFn: () =>
      apiFetch<PacingBoardResponse>(
        `/api/v1/scoped-targets/pacing${buildQuery({ year, month })}`,
      ),
    enabled: Boolean(user),
    staleTime: AGG_STALE,
  });
}

'''

ADMIN_IMPORT_ANCHOR = 'import { TargetsPanel } from "@/components/admin/targets-panel";\n'
ADMIN_IMPORT_ADD = 'import { ScopedTargetsPanel } from "@/components/admin/scoped-targets-panel";\n'
ADMIN_TAB_ANCHOR = '  { value: "targets", label: "Revenue targets" },\n'
ADMIN_TAB_NEW = '  { value: "targets", label: "Targets & budgets" },\n'
ADMIN_RENDER_ANCHOR = "      {tab === \"targets\" && <TargetsPanel />}\n"
ADMIN_RENDER_NEW = """      {tab === "targets" && (
        <div className="space-y-4">
          <TargetsPanel />
          <ScopedTargetsPanel />
        </div>
      )}
"""

LAYOUT_ID_ANCHOR = '  "benchmarks",\n'
LAYOUT_ID_ADD = '  "pacing",\n'
LAYOUT_GRID_ANCHOR = '  { i: "benchmarks", x: 0, y: 94, w: 12, h: 18, minW: 4, minH: 10 },\n'
LAYOUT_GRID_ADD = '  { i: "pacing", x: 0, y: 112, w: 12, h: 18, minW: 4, minH: 10 },\n'

CLIENT_IMPORT_ANCHOR = 'import { BenchmarksPanel } from "@/components/overview/benchmarks-panel";\n'
CLIENT_IMPORT_ADD = 'import { PacingBoard } from "@/components/overview/pacing-board";\n'
CLIENT_ITEM_ANCHOR = '    benchmarks: <BenchmarksPanel filters={filters} />,\n'
CLIENT_ITEM_ADD = '    pacing: <PacingBoard />,\n'

TEST_META_EDITS = [('    "watchlist_items",\n', '    "scoped_targets",\n', False)]
TEST_MIGRATIONS_EDITS = [('_HEAD = "b2c3d4e5f6a7"', '_HEAD = "c3d4e5f6a7b8"', None)]


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
        MODELS_INIT, MAIN, TYPES, HOOKS, ADMIN_CLIENT, LAYOUT, CLIENT,
        TEST_META, TEST_MIGRATIONS,
    ]
    for path in patched:
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    if '"benchmarks"' not in LAYOUT.read_text():
        die(f"{LAYOUT}: run scripts/add-portfolio-benchmarks.py first - this builds on it")

    texts = {path: path.read_text() for path in patched}

    plan: dict[Path, list[tuple[str, str, bool | None]]] = {}
    for path, marker, edits in (
        (MODELS_INIT, "ScopedTarget", MODELS_INIT_EDITS),
        (MAIN, "scoped_targets_routes", MAIN_EDITS),
        (TYPES, "interface ScopedTarget", [(TYPES_ANCHOR, TYPES_ADD, True)]),
        (
            HOOKS,
            "useScopedTargets",
            [
                (HOOKS_IMPORT_ANCHOR, HOOKS_IMPORT_ADD, False),
                (HOOKS_IMPORT2_ANCHOR, HOOKS_IMPORT2_NEW, None),
                (HOOKS_ANCHOR, HOOKS_ADD, True),
            ],
        ),
        (
            ADMIN_CLIENT,
            "ScopedTargetsPanel",
            [
                (ADMIN_IMPORT_ANCHOR, ADMIN_IMPORT_ADD, True),
                (ADMIN_TAB_ANCHOR, ADMIN_TAB_NEW, None),
                (ADMIN_RENDER_ANCHOR, ADMIN_RENDER_NEW, None),
            ],
        ),
        (
            LAYOUT,
            '"pacing"',
            [(LAYOUT_ID_ANCHOR, LAYOUT_ID_ADD, False), (LAYOUT_GRID_ANCHOR, LAYOUT_GRID_ADD, False)],
        ),
        (
            CLIENT,
            "PacingBoard",
            [
                (CLIENT_IMPORT_ANCHOR, CLIENT_IMPORT_ADD, True),
                (CLIENT_ITEM_ANCHOR, CLIENT_ITEM_ADD, False),
            ],
        ),
        (TEST_META, "scoped_targets", TEST_META_EDITS),
    ):
        edits_or_none = plan_edits(path, texts[path], marker, edits)
        if edits_or_none is not None:
            plan[path] = edits_or_none

    head_edits = plan_head_pin(TEST_MIGRATIONS, texts[TEST_MIGRATIONS], "b2c3d4e5f6a7", "c3d4e5f6a7b8")
    if head_edits is not None:
        plan[TEST_MIGRATIONS] = head_edits

    new_files = {
        MODEL: MODEL_SOURCE,
        MIGRATION: MIGRATION_SOURCE,
        SCHEMA: SCHEMA_SOURCE,
        SERVICE: SERVICE_SOURCE,
        ROUTER: ROUTER_SOURCE,
        TEST: TEST_SOURCE,
        ADMIN_PANEL: ADMIN_PANEL_SOURCE,
        BOARD: BOARD_SOURCE,
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

    print("\nMIGRATION REQUIRED: alembic upgrade head (creates scoped_targets).")
    print("Admin > Targets & budgets sets them; the Overview widget shows the pacing.")
    print("Nothing shows until at least one target is set - that is deliberate.")


if __name__ == "__main__":
    main()
