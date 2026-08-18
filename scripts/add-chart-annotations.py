#!/usr/bin/env python3
"""Feature 3: chart annotations - the institutional memory a dashboard normally loses.

Revenue steps down on the 14th and stays down. Six weeks later nobody remembers that
the 14th is the day UA was paused on the two biggest apps, so the same question gets
re-investigated from scratch. An annotation is one dated sentence pinned to the charts:
"UA paused on Alpha + Beta - budget freeze". It costs ten seconds to write and saves the
investigation every time.

Design decisions worth keeping:

* Annotations are SCOPED exactly like rows are (all / app / pod / publisher / hou), and
  visibility is enforced server-side with the caller's own scopes. An annotation naming
  an app is only readable by people who can already see that app - otherwise "UA paused
  on Alpha" tells a scoped user that an app called Alpha exists, which is precisely what
  row scoping exists to prevent. Platform is deliberately NOT a scope type here: nobody
  is scoped by platform, so it would be an org-wide note wearing a scope's clothes.
* Creating an annotation is checked against the SAME rule. You cannot pin a note to an
  app you cannot see - that would be a write-side existence probe around the read gate.
* Editing and deleting are the author's or an admin's. Notes are shared context; one
  person's correction should not be able to quietly rewrite another's record. Every
  create/update/delete is audit-logged with the scope and the date.
* Out-of-scope annotations return 404, never 403 - the house rule, and for the same
  reason: 403 confirms the row exists.
* The note is capped at 280 characters. A chart marker is a label, not a document; the
  cap is also the input-validation rule the rest of the API follows.

Backend: model + migration + schemas + router + main wiring + tests.
Frontend: types, hooks, an ECharts markLine helper, markers on the two DAILY charts
(Overview "Revenue vs Spend" and every App Detail trend - monthly buckets cannot place
a dated marker honestly), and a management panel registered as an Overview widget.

Anchored: every anchor must appear EXACTLY once or NOTHING is written - all files
validate before any is touched. Idempotent. Requires `alembic upgrade head`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── new files ─────────────────────────────────────────────────────────────────
MODEL = Path("backend/app/models/annotations.py")
MIGRATION = Path("backend/alembic/versions/20260818_1100_a17f4c02be93_chart_annotations.py")
SCHEMA = Path("backend/app/schemas/annotations.py")
ROUTER = Path("backend/app/api/v1/annotations.py")
TEST = Path("backend/tests/test_annotations.py")
HELPER = Path("frontend/lib/annotations.ts")
PANEL = Path("frontend/components/overview/annotations-panel.tsx")

# ── patched files ─────────────────────────────────────────────────────────────
MODELS_INIT = Path("backend/app/models/__init__.py")
MAIN = Path("backend/app/main.py")
TYPES = Path("frontend/lib/types.ts")
HOOKS = Path("frontend/lib/api-hooks.ts")
RVS = Path("frontend/components/overview/revenue-vs-spend.tsx")
TREND = Path("frontend/components/app-detail/app-trend.tsx")
LAYOUT = Path("frontend/lib/overview-layout.ts")
CLIENT = Path("frontend/components/overview/overview-client.tsx")
ECHARTS = Path("frontend/lib/echarts.ts")
TEST_META = Path("backend/tests/test_models_metadata.py")
TEST_MIGRATIONS = Path("backend/tests/test_migrations.py")

MODEL_SOURCE = '''"""Chart annotations - dated notes pinned to the time-series charts.

Scoped exactly like fact rows are (all / app / pod / publisher / hou) so an annotation
naming an app is only readable by callers who can already see that app. ``scope_value``
is NULL only for ``scope_type='all'``.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# The scope types an annotation may carry. Deliberately the SAME set the row scopes use
# (minus 'platform', which nobody is scoped by) so visibility can be enforced by
# comparing like with like.
ANNOTATION_SCOPE_TYPES = ("all", "app", "pod", "publisher", "hou")


class ChartAnnotation(Base):
    """One dated note, visible to everyone whose scopes cover its scope."""

    __tablename__ = "chart_annotations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    annotation_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'all'")
    )
    scope_value: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('all','app','pod','publisher','hou')",
            name="chart_annotations_scope_type_valid",
        ),
        # 'all' carries no value; every other scope MUST carry one, or it would be an
        # org-wide note that merely looks scoped.
        CheckConstraint(
            "(scope_type = 'all' AND scope_value IS NULL) "
            "OR (scope_type <> 'all' AND scope_value IS NOT NULL)",
            name="chart_annotations_scope_value_valid",
        ),
        CheckConstraint(
            "char_length(note) BETWEEN 1 AND 280", name="chart_annotations_note_length"
        ),
        # Every read is "the notes between these two dates", so the date leads.
        Index("ix_chart_annotations_date", "annotation_date"),
        Index("ix_chart_annotations_scope", "scope_type", "scope_value"),
    )
'''

MIGRATION_SOURCE = '''"""Chart annotations - dated notes pinned to the time-series charts.

Revision ID: a17f4c02be93
Revises: c7d3e91a4b28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a17f4c02be93"
down_revision: str | None = "c7d3e91a4b28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chart_annotations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("annotation_date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("scope_type", sa.Text(), nullable=False, server_default=sa.text("'all'")),
        sa.Column("scope_value", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "scope_type IN ('all','app','pod','publisher','hou')",
            name="chart_annotations_scope_type_valid",
        ),
        sa.CheckConstraint(
            "(scope_type = 'all' AND scope_value IS NULL) "
            "OR (scope_type <> 'all' AND scope_value IS NOT NULL)",
            name="chart_annotations_scope_value_valid",
        ),
        sa.CheckConstraint(
            "char_length(note) BETWEEN 1 AND 280", name="chart_annotations_note_length"
        ),
    )
    op.create_index("ix_chart_annotations_date", "chart_annotations", ["annotation_date"])
    op.create_index(
        "ix_chart_annotations_scope", "chart_annotations", ["scope_type", "scope_value"]
    )


def downgrade() -> None:
    op.drop_index("ix_chart_annotations_scope", table_name="chart_annotations")
    op.drop_index("ix_chart_annotations_date", table_name="chart_annotations")
    op.drop_table("chart_annotations")
'''

SCHEMA_SOURCE = '''"""Request/response models for chart annotations."""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ScopeType = Literal["all", "app", "pod", "publisher", "hou"]


class AnnotationIn(BaseModel):
    """A note to pin. ``scope_value`` is required for every scope except ``all``."""

    annotation_date: date_type
    # 280 characters: a chart marker is a label, not a document. Matches the DB check.
    note: str = Field(min_length=1, max_length=280)
    scope_type: ScopeType = "all"
    scope_value: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _scope_value_matches_type(self) -> AnnotationIn:
        value = (self.scope_value or "").strip() or None
        if self.scope_type == "all" and value is not None:
            raise ValueError("An org-wide annotation cannot carry a scope value.")
        if self.scope_type != "all" and value is None:
            raise ValueError("A scoped annotation must name what it applies to.")
        self.scope_value = value
        self.note = self.note.strip()
        return self


class AnnotationOut(BaseModel):
    id: uuid.UUID
    annotation_date: date_type
    note: str
    scope_type: str
    scope_value: str | None
    created_by: uuid.UUID | None
    created_by_name: str | None
    # Whether THIS caller may edit or delete it (author or admin). The frontend hides
    # the controls from this; the server enforces it regardless.
    can_edit: bool
    created_at: datetime
    updated_at: datetime
'''

ROUTER_SOURCE = '''"""Chart annotations: dated notes pinned to the time-series charts.

Visibility is the whole design. An annotation carries a scope of the same shape a user
scope has, and a caller sees a note only when their own scopes cover it. Otherwise
"UA paused on Alpha" would tell a scoped user that an app called Alpha exists - exactly
what row scoping exists to prevent - so the read gate, the write gate and the 404 all
follow the same rule.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import ColumnElement, and_, false, or_, select, true

from app.api.deps import CurrentUser, DbSession
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.models import ChartAnnotation, User
from app.schemas.annotations import AnnotationIn, AnnotationOut
from app.schemas.auth import UserContext
from app.services.audit import AuditDep

router = APIRouter(
    prefix="/annotations", tags=["annotations"], dependencies=[Depends(enforce_rate_limit)]
)

# How many notes one request may return. A chart with 500 markers is unreadable, and an
# uncapped list is a free way to pull the whole table.
_MAX_LIMIT = 200


def _visible_to(context: UserContext) -> ColumnElement[bool]:
    """The WHERE clause for "annotations this caller may see".

    Org-wide notes are always visible. A scoped note is visible only when the caller
    holds a scope of the SAME type covering the SAME value - the union of their
    ``user_scopes`` rows, which is how row access is defined everywhere else.
    """
    scope_types = {s.scope_type for s in context.scopes}
    if "all" in scope_types:
        return true()
    # No scopes at all -> no rows, the same fail-closed rule scopes.build_scope_filter
    # applies. Such a user can see no data, so they have no business reading notes
    # about it either.
    if not context.scopes:
        return false()

    conditions: list[ColumnElement[bool]] = [ChartAnnotation.scope_type == "all"]
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
                    ChartAnnotation.scope_type == scope_type,
                    ChartAnnotation.scope_value.in_(values),
                )
            )
    return or_(*conditions)


def _may_write(context: UserContext, scope_type: str, scope_value: str | None) -> bool:
    """Can this caller pin a note to this scope?

    The same rule as reading: you cannot annotate what you cannot see. Writing is where
    an existence probe would otherwise slip through the read gate - "does app Alpha
    exist?" answered by whether the POST succeeds.
    """
    scope_types = {s.scope_type for s in context.scopes}
    if "all" in scope_types:
        return True
    if scope_type == "all":
        # An org-wide note is visible to everyone, so only an unrestricted caller may
        # write one. A pod-scoped user broadcasting to the whole company is not a
        # permission they were given.
        return False
    return any(
        s.scope_type == scope_type and s.scope_value == scope_value for s in context.scopes
    )


def _out(row: ChartAnnotation, author: str | None, *, can_edit: bool) -> AnnotationOut:
    return AnnotationOut(
        id=row.id,
        annotation_date=row.annotation_date,
        note=row.note,
        scope_type=row.scope_type,
        scope_value=row.scope_value,
        created_by=row.created_by,
        created_by_name=author,
        can_edit=can_edit,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _can_edit(context: UserContext, row: ChartAnnotation) -> bool:
    """Author or admin. Notes are shared context; one person's correction must not be
    able to quietly rewrite another person's record of what happened."""
    return row.created_by == context.user_id or "admin" in context.roles


async def _load_visible(
    db: DbSession, context: UserContext, annotation_id: uuid.UUID
) -> ChartAnnotation:
    row = await db.scalar(
        select(ChartAnnotation).where(
            ChartAnnotation.id == annotation_id, _visible_to(context)
        )
    )
    if row is None:
        # 404, never 403: a 403 confirms the annotation exists.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annotation not found")
    return row


@router.get("", response_model=list[AnnotationOut])
async def list_annotations(
    context: CurrentUser,
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _MAX_LIMIT,
) -> list[AnnotationOut]:
    """Notes in a date window that this caller may see, newest date first."""
    where: list[ColumnElement[bool]] = [_visible_to(context)]
    if date_from is not None:
        where.append(ChartAnnotation.annotation_date >= date_from)
    if date_to is not None:
        where.append(ChartAnnotation.annotation_date <= date_to)

    rows = (
        await db.execute(
            select(ChartAnnotation, User.display_name, User.email)
            .outerjoin(User, User.id == ChartAnnotation.created_by)
            .where(*where)
            .order_by(ChartAnnotation.annotation_date.desc(), ChartAnnotation.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        _out(row, display_name or email, can_edit=_can_edit(context, row))
        for row, display_name, email in rows
    ]


@router.post("", response_model=AnnotationOut, status_code=status.HTTP_201_CREATED)
async def create_annotation(
    body: AnnotationIn,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> AnnotationOut:
    if not _may_write(context, body.scope_type, body.scope_value):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You can only annotate what your access already covers.",
        )
    row = ChartAnnotation(
        annotation_date=body.annotation_date,
        note=body.note,
        scope_type=body.scope_type,
        scope_value=body.scope_value,
        created_by=context.user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await audit.write(
        user_id=context.user_id,
        action="annotation_create",
        resource=str(row.id),
        detail={
            "date": str(row.annotation_date),
            "scope_type": row.scope_type,
            "scope_value": row.scope_value,
        },
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _out(row, context.display_name or context.email, can_edit=True)


@router.put("/{annotation_id}", response_model=AnnotationOut)
async def update_annotation(
    annotation_id: uuid.UUID,
    body: AnnotationIn,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> AnnotationOut:
    row = await _load_visible(db, context, annotation_id)
    if not _can_edit(context, row):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the author or an admin can edit this.")
    if not _may_write(context, body.scope_type, body.scope_value):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You can only annotate what your access already covers.",
        )
    row.annotation_date = body.annotation_date
    row.note = body.note
    row.scope_type = body.scope_type
    row.scope_value = body.scope_value
    row.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    await audit.write(
        user_id=context.user_id,
        action="annotation_update",
        resource=str(annotation_id),
        detail={
            "date": str(row.annotation_date),
            "scope_type": row.scope_type,
            "scope_value": row.scope_value,
        },
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _out(row, context.display_name or context.email, can_edit=True)


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    annotation_id: uuid.UUID,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> Response:
    row = await _load_visible(db, context, annotation_id)
    if not _can_edit(context, row):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the author or an admin can delete this."
        )
    await db.delete(row)
    await db.commit()
    await audit.write(
        user_id=context.user_id,
        action="annotation_delete",
        resource=str(annotation_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

'''

TEST_SOURCE = '''"""Chart annotations: scope-based visibility, authorship, and the audit trail.

The interesting tests are the negative ones. A pod-scoped user must not see a note about
an app outside their pod (the note names the app - that IS the leak), must not be able
to write an org-wide note, and must get a 404 rather than a 403 when they reach for one.
"""

from typing import Any

from app.models import AuditLog
from sqlalchemy import select

from tests.conftest import MetricsEnv

URL = "/api/v1/annotations"


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


def _note(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "annotation_date": "2026-06-01",
        "note": "UA paused - budget freeze",
        "scope_type": "all",
        "scope_value": None,
    }
    body.update(overrides)
    return body


async def test_requires_auth(metrics_env: MetricsEnv) -> None:
    assert (await metrics_env.client.get(URL)).status_code == 401
    assert (await metrics_env.client.post(URL, json=_note())).status_code == 401


async def test_create_list_round_trip(metrics_env: MetricsEnv) -> None:
    created = await metrics_env.client.post(URL, json=_note(), headers=_auth("admin"))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["note"] == "UA paused - budget freeze"
    assert body["can_edit"] is True

    listed = await metrics_env.client.get(URL, headers=_auth("admin"))
    assert listed.status_code == 200
    assert [a["id"] for a in listed.json()] == [body["id"]]


async def test_date_window_filters(metrics_env: MetricsEnv) -> None:
    for day in ("2026-06-01", "2026-07-15"):
        await metrics_env.client.post(
            URL, json=_note(annotation_date=day), headers=_auth("admin")
        )

    inside = await metrics_env.client.get(
        URL, params={"from": "2026-06-01", "to": "2026-06-30"}, headers=_auth("admin")
    )
    assert [a["annotation_date"] for a in inside.json()] == ["2026-06-01"]


async def test_scope_value_required_for_scoped_note(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post(
        URL, json=_note(scope_type="pod", scope_value=None), headers=_auth("admin")
    )
    assert resp.status_code == 422


async def test_note_length_is_capped(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post(
        URL, json=_note(note="x" * 281), headers=_auth("admin")
    )
    assert resp.status_code == 422


async def test_scoped_user_cannot_see_other_scopes(metrics_env: MetricsEnv) -> None:
    """The note names the app - so the note itself is the leak the scope must stop."""
    await metrics_env.client.post(
        URL,
        json=_note(scope_type="pod", scope_value="POD_B", note="Creative refresh on POD_B"),
        headers=_auth("admin"),
    )
    mine = await metrics_env.client.post(
        URL,
        json=_note(scope_type="pod", scope_value="POD_A", note="Creative refresh on POD_A"),
        headers=_auth("admin"),
    )
    org = await metrics_env.client.post(
        URL, json=_note(note="Company all-hands"), headers=_auth("admin")
    )

    listed = await metrics_env.client.get(URL, headers=_auth("pod_owner_scoped"))
    assert listed.status_code == 200
    visible = {a["id"] for a in listed.json()}
    assert mine.json()["id"] in visible  # their own pod
    assert org.json()["id"] in visible  # org-wide notes are for everyone
    assert len(visible) == 2  # and NOTHING from POD_B


async def test_out_of_scope_annotation_is_404_not_403(metrics_env: MetricsEnv) -> None:
    other = await metrics_env.client.post(
        URL, json=_note(scope_type="pod", scope_value="POD_B"), headers=_auth("admin")
    )
    resp = await metrics_env.client.delete(
        f"{URL}/{other.json()['id']}", headers=_auth("pod_owner_scoped")
    )
    assert resp.status_code == 404  # 403 would confirm it exists


async def test_scoped_user_cannot_write_org_wide(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post(URL, json=_note(), headers=_auth("pod_owner_scoped"))
    assert resp.status_code == 403


async def test_scoped_user_cannot_write_outside_their_scope(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post(
        URL, json=_note(scope_type="pod", scope_value="POD_B"), headers=_auth("pod_owner_scoped")
    )
    assert resp.status_code == 403


async def test_scoped_user_can_write_inside_their_scope(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post(
        URL, json=_note(scope_type="pod", scope_value="POD_A"), headers=_auth("pod_owner_scoped")
    )
    assert resp.status_code == 201


async def test_non_author_non_admin_cannot_edit(metrics_env: MetricsEnv) -> None:
    created = await metrics_env.client.post(URL, json=_note(), headers=_auth("admin"))
    resp = await metrics_env.client.put(
        f"{URL}/{created.json()['id']}", json=_note(note="rewritten"), headers=_auth("finance")
    )
    assert resp.status_code == 403
    assert created.json()["note"] != "rewritten"


async def test_admin_can_edit_another_authors_note(metrics_env: MetricsEnv) -> None:
    created = await metrics_env.client.post(URL, json=_note(), headers=_auth("finance"))
    resp = await metrics_env.client.put(
        f"{URL}/{created.json()['id']}", json=_note(note="corrected"), headers=_auth("admin")
    )
    assert resp.status_code == 200
    assert resp.json()["note"] == "corrected"


async def test_author_can_delete_and_it_is_audited(metrics_env: MetricsEnv) -> None:
    created = await metrics_env.client.post(URL, json=_note(), headers=_auth("finance"))
    resp = await metrics_env.client.delete(
        f"{URL}/{created.json()['id']}", headers=_auth("finance")
    )
    assert resp.status_code == 204
    assert (await metrics_env.client.get(URL, headers=_auth("finance"))).json() == []

    async with metrics_env.sessionmaker() as session:
        actions = set(
            (await session.execute(select(AuditLog.action))).scalars().all()
        )
    assert {"annotation_create", "annotation_delete"} <= actions
'''

HELPER_SOURCE = '''import type { MarkLineComponentOption } from "echarts";

import type { Annotation } from "@/lib/types";

/** ECharts markLine for dated notes on a CATEGORY x-axis of ISO dates.
 *
 *  Only DAILY charts get markers. A monthly bucket cannot place "the 14th" anywhere
 *  honest, and a marker in the wrong place is worse than no marker - so callers pass the
 *  same ``labels`` array they gave the axis and anything not on it is dropped rather
 *  than nudged to a neighbour.
 *
 *  Attach the result to ONE series (markLine is a series-level option, but ECharts draws
 *  it across the whole grid, so a second copy is just overdraw). */
export function annotationMarkLine(
  annotations: Annotation[],
  labels: string[],
  color: string,
): MarkLineComponentOption {
  const onAxis = new Set(labels);
  return {
    symbol: ["none", "circle"],
    symbolSize: 6,
    animation: false,
    lineStyle: { color, width: 1, type: "dashed", opacity: 0.85 },
    label: {
      show: true,
      formatter: "{b}",
      position: "insideEndTop",
      color,
      fontSize: 10,
      distance: 2,
    },
    emphasis: { label: { fontWeight: "bold" } },
    data: annotations
      .filter((a) => onAxis.has(a.annotation_date))
      .map((a) => ({
        xAxis: a.annotation_date,
        // ECharts shows `name` in the marker label; the panel carries the full text,
        // so the marker only needs enough to recognise it.
        name: a.note.length > 24 ? `${a.note.slice(0, 23)}\u2026` : a.note,
      })),
  };
}
'''

PANEL_SOURCE = r'''"use client";

import { Plus, Trash2, X } from "lucide-react";
import { useState } from "react";

import { ChartCard } from "@/components/charts/chart-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAnnotations,
  useCreateAnnotation,
  useDeleteAnnotation,
  useMe,
} from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";

/* Timeline notes - the institutional memory the charts otherwise lose.
 *
 * Revenue steps down on the 14th and stays down; six weeks later nobody remembers the
 * 14th is the day UA was paused. One dated sentence here puts a marker on every daily
 * chart in the window and answers the question permanently.
 *
 * Scope is the important control, and it is enforced server-side: an org-wide note is
 * only writable by an unrestricted user, and a scoped note is only writable - and only
 * readable - by people whose access already covers it. The picker below offers what the
 * caller actually has, so the UI does not invite a 403. */

const SCOPE_TYPES = [
  { id: "all", label: "Everyone" },
  { id: "app", label: "App" },
  { id: "pod", label: "Pod" },
  { id: "publisher", label: "Publisher" },
  { id: "hou", label: "HOU" },
] as const;

const FIELD_CLASS =
  "h-8 w-full rounded-[var(--radius-inner)] border border-input bg-background px-2 text-xs outline-none focus:ring-1 focus:ring-ring";

export function AnnotationsPanel({ filters }: { filters: Filters }) {
  const { data: me } = useMe();
  const list = useAnnotations(filters.dateFrom, filters.dateTo);
  const create = useCreateAnnotation();
  const remove = useDeleteAnnotation();

  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(filters.dateTo);
  const [note, setNote] = useState("");
  const [scopeType, setScopeType] = useState<string>("all");
  const [scopeValue, setScopeValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  // An unrestricted caller may write org-wide notes; a scoped one may only write inside
  // a scope they hold. Mirrors exactly what the server enforces.
  const scopes = me?.scopes ?? [];
  const unrestricted = scopes.some((s) => s.scope_type === "all");
  const writableTypes = unrestricted
    ? SCOPE_TYPES
    : SCOPE_TYPES.filter(
        (t) => t.id !== "all" && scopes.some((s) => s.scope_type === t.id),
      );
  // DERIVED, not trusted from state. scopeType starts as "all", which a scoped user
  // cannot write - so the select would show "Pod" while the state still said "all", the
  // value field (gated on !== "all") would stay hidden, and every save would 403. It
  // could never recover either, because the state is only corrected after a successful
  // save. Deriving it is correct on the first render and self-heals if scopes change.
  const scopeTypeIsWritable = writableTypes.some((t) => t.id === scopeType);
  const effectiveScopeType = scopeTypeIsWritable ? scopeType : (writableTypes[0]?.id ?? "all");

  const suggestions = scopes
    .filter((s) => s.scope_type === effectiveScopeType && s.scope_value)
    .map((s) => s.scope_value as string);

  function reset() {
    setNote("");
    setScopeValue("");
    setScopeType(writableTypes[0]?.id ?? "all");
    setError(null);
    setOpen(false);
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    create.mutate(
      {
        annotation_date: date,
        note: note.trim(),
        scope_type: effectiveScopeType,
        scope_value: effectiveScopeType === "all" ? null : scopeValue.trim() || null,
      },
      {
        onSuccess: reset,
        onError: (err) => setError((err as Error).message),
      },
    );
  }

  const canWrite = writableTypes.length > 0;
  const action = canWrite ? (
    <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)}>
      {open ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
      <span className="ml-1 text-xs">{open ? "Cancel" : "Add note"}</span>
    </Button>
  ) : undefined;

  return (
    <ChartCard title="Timeline notes" action={action}>
      <div className="space-y-3">
        {open && (
          <form onSubmit={submit} className="space-y-2 rounded-[var(--radius-inner)] border p-2">
            <div className="grid grid-cols-2 gap-2">
              <input
                type="date"
                aria-label="Date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
                className={FIELD_CLASS}
              />
              <select
                aria-label="Applies to"
                value={effectiveScopeType}
                onChange={(e) => {
                  setScopeType(e.target.value);
                  setScopeValue("");
                }}
                className={FIELD_CLASS}
              >
                {writableTypes.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            {effectiveScopeType !== "all" && (
              <>
                <input
                  aria-label="Scope value"
                  list="annotation-scope-values"
                  value={scopeValue}
                  onChange={(e) => setScopeValue(e.target.value)}
                  placeholder="Which one?"
                  required
                  maxLength={200}
                  className={FIELD_CLASS}
                />
                <datalist id="annotation-scope-values">
                  {suggestions.map((s) => (
                    <option key={s} value={s} />
                  ))}
                </datalist>
              </>
            )}
            <textarea
              aria-label="Note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What happened on this day?"
              required
              maxLength={280}
              rows={2}
              className="w-full rounded-[var(--radius-inner)] border border-input bg-background px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-ring"
            />
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-[var(--color-text-muted)]">
                {280 - note.length} characters left
              </span>
              <Button type="submit" size="sm" disabled={create.isPending || note.trim() === ""}>
                {create.isPending ? "Saving…" : "Pin to charts"}
              </Button>
            </div>
            {error && <p className="text-xs text-[var(--color-negative)]">{error}</p>}
          </form>
        )}

        {list.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : list.isError ? (
          <p className="text-sm text-[var(--color-negative)]">
            Could not load notes: {(list.error as Error).message}
          </p>
        ) : (list.data ?? []).length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            No notes in this window. Pin one and it appears on every daily chart here.
          </p>
        ) : (
          <ul className="divide-y">
            {(list.data ?? []).map((a) => (
              <li key={a.id} className="flex items-start gap-2 py-2">
                <span className="w-20 shrink-0 text-xs tabular-nums text-[var(--color-text-muted)]">
                  {a.annotation_date}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm">{a.note}</span>
                  <span className="block text-[10px] text-[var(--color-text-muted)]">
                    {a.scope_type === "all" ? "Everyone" : `${a.scope_type}: ${a.scope_value}`}
                    {a.created_by_name ? ` · ${a.created_by_name}` : ""}
                  </span>
                </span>
                {a.can_edit && (
                  <button
                    type="button"
                    aria-label={`Delete note from ${a.annotation_date}`}
                    onClick={() => remove.mutate(a.id)}
                    className="shrink-0 rounded p-1 text-[var(--color-text-muted)] hover:text-[var(--color-negative)]"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </ChartCard>
  );
}
'''


# echarts.ts is TREE-SHAKEN: markLine draws nothing at all unless MarkLineComponent is
# registered. Silent no-op, not an error - exactly the kind of thing that ships broken.
# echarts.ts is TREE-SHAKEN: markLine draws NOTHING at all unless MarkLineComponent is
# registered - a silent no-op, not an error, which is exactly the kind of thing that ships
# broken. The registration appears in two places (the import statement and the use() call)
# and each is checked SEPARATELY. An earlier version used one "MarkLineComponent" marker
# for the whole file; that string was already present in the deployed copy for another
# reason, so every edit was skipped and the build failed on the one that mattered.
_ECHARTS_IMPORT_RE = re.compile(r'import \{([^}]*)\} from "echarts/components";', re.S)
_ECHARTS_USE_RE = re.compile(r"echarts\.use\(\[(.*?)\]\);", re.S)


def plan_echarts(path: Path, text: str) -> list[tuple[str, str, bool | None]]:
    """Register MarkLineComponent, checking the import and the use() list independently."""
    edits: list[tuple[str, str, bool | None]] = []

    imports = _ECHARTS_IMPORT_RE.search(text)
    if imports is None:
        die(f"{path}: no `import {{...}} from \"echarts/components\"` - file has changed shape")
    if "MarkLineComponent" not in imports.group(1):
        anchor = "  LegendComponent,\n  TitleComponent,\n"
        if text.count(anchor) != 1:
            die(f"{path}: cannot place MarkLineComponent in the import block")
        edits.append((anchor, "  LegendComponent,\n  MarkLineComponent,\n  TitleComponent,\n", None))
    else:
        print(f"{path}: MarkLineComponent already imported")

    used = _ECHARTS_USE_RE.search(text)
    if used is None:
        die(f"{path}: no `echarts.use([...])` call - file has changed shape")
    if "MarkLineComponent" not in used.group(1):
        anchor = "  LegendComponent,\n  DataZoomComponent,\n"
        if text.count(anchor) != 1:
            die(f"{path}: cannot place MarkLineComponent in the use() list")
        edits.append((anchor, "  LegendComponent,\n  MarkLineComponent,\n  DataZoomComponent,\n", None))
    else:
        print(f"{path}: MarkLineComponent already registered")

    return edits



# Two existing tests know the schema by heart and MUST be told about the new table,
# or they fail the moment this ships - which is the point of them.
#   * test_models_metadata asserts SET EQUALITY over every ORM table.
#   * test_migrations pins the head revision, so the chain is actually walked to the end.
TEST_META_EDITS = [('    "smtp_config",\n', '    "chart_annotations",\n', False)]

# ── anchored edits ────────────────────────────────────────────────────────────
MODELS_INIT_EDITS = [
    (
        "from app.models.app_master import APP_MASTER_TABLE\n",
        "from app.models.annotations import ANNOTATION_SCOPE_TYPES, ChartAnnotation\n",
        True,
    ),
    ('    "APP_MASTER_TABLE",\n', '    "ANNOTATION_SCOPE_TYPES",\n    "ChartAnnotation",\n', True),
]

MAIN_EDITS = [
    (
        "from app.api.v1 import app_master as app_master_routes\n",
        "from app.api.v1 import annotations as annotations_routes\n",
        True,
    ),
    (
        "app.include_router(account_routes.router, prefix=settings.api_v1_prefix)\n",
        "app.include_router(annotations_routes.router, prefix=settings.api_v1_prefix)\n",
        False,
    ),
]

TYPES_ANCHOR = "export interface TableResponse {\n"
TYPES_ADD = """/** A dated note pinned to the time-series charts. ``scope_value`` is null only for
 *  ``scope_type: "all"``; ``can_edit`` is what the SERVER says this caller may do. */
export interface Annotation {
  id: string;
  annotation_date: string;
  note: string;
  scope_type: string;
  scope_value: string | null;
  created_by: string | null;
  created_by_name: string | null;
  can_edit: boolean;
  created_at: string;
  updated_at: string;
}

export interface AnnotationInput {
  annotation_date: string;
  note: string;
  scope_type: string;
  scope_value: string | null;
}

"""

HOOKS_IMPORT_ANCHOR = "import type {\n  AdminUser,\n"
HOOKS_IMPORT_ADD = "  Annotation,\n  AnnotationInput,\n"

HOOKS_ANCHOR = "// ── Identity (RBAC context + share directory) ────────────────────────────────\n"
HOOKS_ADD = '''// ── Chart annotations (dated notes pinned to the daily charts) ───────────────
/** Notes in a date window that the SERVER decides this caller may see. */
export function useAnnotations(from: string, to: string) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["annotations", from, to],
    queryFn: () =>
      apiFetch<Annotation[]>(`/api/v1/annotations${buildQuery({ from, to })}`),
    enabled: Boolean(user),
    staleTime: AGG_STALE,
  });
}

export function useCreateAnnotation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AnnotationInput) =>
      apiFetch<Annotation>("/api/v1/annotations", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["annotations"] }),
  });
}

export function useDeleteAnnotation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/v1/annotations/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["annotations"] }),
  });
}

'''

LAYOUT_ID_ANCHOR = '  "what-moved",\n'
LAYOUT_ID_ADD = '  "annotations",\n'
LAYOUT_GRID_ANCHOR = '  { i: "what-moved", x: 0, y: 52, w: 12, h: 24, minW: 4, minH: 14 },\n'
LAYOUT_GRID_ADD = '  { i: "annotations", x: 0, y: 76, w: 12, h: 18, minW: 4, minH: 10 },\n'

CLIENT_IMPORT_ANCHOR = 'import { DemoSection } from "@/components/overview/demo-section";\n'
CLIENT_IMPORT_ADD = 'import { AnnotationsPanel } from "@/components/overview/annotations-panel";\n'
CLIENT_ITEM_ANCHOR = '    "what-moved": <WhatMoved filters={filters} />,\n'
CLIENT_ITEM_ADD = '    annotations: <AnnotationsPanel filters={filters} />,\n'

# Revenue vs Spend: markers on the daily chart.
# One import line, not two: eslint's import/no-duplicates rejects a second statement
# from the same module, and it would be noise regardless.
RVS_IMPORT_ANCHOR = 'import { usePreviousTimeseries, useTimeseries } from "@/lib/api-hooks";\n'
RVS_IMPORT_NEW = (
    'import { annotationMarkLine } from "@/lib/annotations";\n'
    'import { useAnnotations, usePreviousTimeseries, useTimeseries } from "@/lib/api-hooks";\n'
)
RVS_DATA_ANCHOR = "  const ts = useTimeseries(filters, METRICS, \"day\");\n"
RVS_DATA_ADD = (
    "  // Dated notes for this window, drawn as dashed markers on the chart. Only the\n"
    "  // dates that are actually ON the axis are drawn - see annotationMarkLine.\n"
    "  const notes = useAnnotations(filters.dateFrom, filters.dateTo);\n"
)
RVS_SERIES_ANCHOR = """    {
      name: "Revenue",
      type: "line",
      data: revenue,
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2, color: token("--chart-spark") },
      itemStyle: { color: token("--chart-spark") },
      z: 3,
    },
"""
RVS_SERIES_NEW = """    {
      name: "Revenue",
      type: "line",
      data: revenue,
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2, color: token("--chart-spark") },
      itemStyle: { color: token("--chart-spark") },
      z: 3,
      markLine: annotationMarkLine(notes.data ?? [], labels, token("--color-text-muted")),
    },
"""

TREND_IMPORT_ANCHOR = 'import { useTimeseries } from "@/lib/api-hooks";\n'
TREND_IMPORT_NEW = (
    'import { annotationMarkLine } from "@/lib/annotations";\n'
    'import { useAnnotations, useTimeseries } from "@/lib/api-hooks";\n'
)
TREND_DATA_ANCHOR = "  const labels = bucketLabels(ts.data);\n"
TREND_DATA_ADD = (
    "  // Dated notes for this window. Every App Detail trend is daily, so a marker\n"
    "  // always lands on a real bucket.\n"
    "  const notes = useAnnotations(filters.dateFrom, filters.dateTo);\n"
)
TREND_SERIES_ANCHOR = """    series: metrics.map((m, i) => ({
      name: m.label,
      type: "line",
      data: metricValues(ts.data, m.key),
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2, color: token(COLORS[i % COLORS.length]) },
      itemStyle: { color: token(COLORS[i % COLORS.length]) },
    })),
"""
TREND_SERIES_NEW = """    series: metrics.map((m, i) => ({
      name: m.label,
      type: "line",
      data: metricValues(ts.data, m.key),
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2, color: token(COLORS[i % COLORS.length]) },
      itemStyle: { color: token(COLORS[i % COLORS.length]) },
      // markLine is a series option; only the first series carries it so the markers
      // are drawn once, not once per metric.
      markLine:
        i === 0
          ? annotationMarkLine(notes.data ?? [], labels, token("--color-text-muted"))
          : undefined,
    })),
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def plan_edits(
    path: Path, text: str, marker: str, edits: list[tuple[str, str, bool]]
) -> list[tuple[str, str, bool]] | None:
    """Validate every anchor; return the edits, or None when already applied."""
    if marker in text:
        print(f"{path}: already patched")
        return None
    for anchor, _, _ in edits:
        if text.count(anchor) != 1:
            first = anchor.splitlines()[0].strip()
            die(f"{path}: expected exactly one {first!r}, found {text.count(anchor)}")
    return edits



# The four ids this batch first used - a1b2c3d4e5f6, b2c3d4e5f6a7, c3d4e5f6a7b8,
# d4e5f6a7b8c9 - were ALREADY TAKEN by migrations from June and July. I picked the
# "obvious next" ids in the same rolling-hex family and collided head-on, which alembic
# reported as "present more than once" and then as a cycle. These are the ids that
# replaced them, and the stale file has to go or the duplicate survives.
REVISION_ID = "a17f4c02be93"
BATCH_CHAIN = (
    "a17f4c02be93",  # chart_annotations
    "b28e5d13cfa4",  # watchlist
    "c39f6e24d0b5",  # scoped_targets
    "d40a7f35e1c6",  # discord_config
)
SUPERSEDED_REVISIONS = ("a1b2c3d4e5f6", "b2c3d4e5f6a7", "c3d4e5f6a7b8", "d4e5f6a7b8c9")
STALE_MIGRATION = Path("backend/alembic/versions/20260818_1100_a1b2c3d4e5f6_chart_annotations.py")


def drop_stale_migration() -> None:
    """Remove the colliding migration an earlier version of this script wrote."""
    if STALE_MIGRATION.exists():
        STALE_MIGRATION.unlink()
        print(f"removed {STALE_MIGRATION} (its revision id collided with an existing one)")


def assert_revision_free(migration: Path, revision: str) -> None:
    """Refuse to write a migration whose id is already used by a DIFFERENT file.

    A duplicate id does not fail at write time - it fails much later, at `alembic upgrade`,
    as an unreadable cycle error. Catching it here names the file instead.
    """
    versions = migration.parent
    if not versions.is_dir():
        return
    pattern = re.compile(r"^revision(?::\s*str)?\s*=\s*[\"']" + re.escape(revision) + r"[\"']", re.M)
    for other in sorted(versions.glob("*.py")):
        if other.name == migration.name:
            continue
        if pattern.search(other.read_text()):
            die(
                f"revision id {revision!r} is already used by {other.name} - "
                f"pick a different one rather than creating a cycle"
            )


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
    if current in SUPERSEDED_REVISIONS:
        # The pin still names one of the colliding ids this batch first used.
        # Correct it rather than leaving the test asserting a revision that no
        # longer exists.
        return [(f'_HEAD = "{current}"', f'_HEAD = "{new}"', None)]
    if current in BATCH_CHAIN and BATCH_CHAIN.index(current) >= BATCH_CHAIN.index(new):
        # Already at or beyond this patch's revision, because a LATER patch in the same
        # batch moved it. That is the normal steady state once the batch has shipped, and
        # warning about it every run just teaches people to ignore warnings.
        print(f"{path}: head pin already at {current} - correct, nothing to do")
        return None
    if current != old:
        # Not one of this batch's revisions and not the expected predecessor, so the pin
        # is somewhere this patch does not understand - probably BEHIND, which means the
        # chain has not been run in order. Do not rewrite it, and do not pretend it is
        # fine: a pin behind the database fails test_migrations.
        print(
            f"{path}: head pin is {current}, expected {old} - not touching it. "
            f"If the chain has not been run in order, this test will fail against a "
            f"database at {new}."
        )
        return None
    return [(f'_HEAD = "{old}"', f'_HEAD = "{new}"', None)]


def main() -> None:
    patched = [
        MODELS_INIT, MAIN, TYPES, HOOKS, RVS, TREND, LAYOUT, CLIENT, ECHARTS,
        TEST_META, TEST_MIGRATIONS,
    ]
    for path in patched:
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    # The Overview widgets this patch sits next to must already exist: the annotations
    # panel is placed relative to "What moved", so add-contribution-ui.py comes first.
    if '"what-moved"' not in LAYOUT.read_text():
        die(f"{LAYOUT}: run scripts/add-contribution-ui.py first - this builds on it")

    texts = {path: path.read_text() for path in patched}

    plan: dict[Path, list[tuple[str, str, bool]]] = {}
    for path, marker, edits in (
        (MODELS_INIT, "ChartAnnotation", MODELS_INIT_EDITS),
        (TEST_META, "chart_annotations", TEST_META_EDITS),
        (MAIN, "annotations_routes", MAIN_EDITS),
        (TYPES, "interface Annotation", [(TYPES_ANCHOR, TYPES_ADD, True)]),
        (
            HOOKS,
            "useAnnotations",
            [
                (HOOKS_IMPORT_ANCHOR, HOOKS_IMPORT_ADD, False),
                (HOOKS_ANCHOR, HOOKS_ADD, True),
            ],
        ),
        (
            RVS,
            "annotationMarkLine",
            [
                (RVS_IMPORT_ANCHOR, RVS_IMPORT_NEW, None),
                (RVS_DATA_ANCHOR, RVS_DATA_ADD, False),
                (RVS_SERIES_ANCHOR, RVS_SERIES_NEW, None),
            ],
        ),
        (
            TREND,
            "annotationMarkLine",
            [
                (TREND_IMPORT_ANCHOR, TREND_IMPORT_NEW, None),
                (TREND_DATA_ANCHOR, TREND_DATA_ADD, False),
                (TREND_SERIES_ANCHOR, TREND_SERIES_NEW, None),
            ],
        ),
        (
            LAYOUT,
            '  "annotations",\n',
            [(LAYOUT_ID_ANCHOR, LAYOUT_ID_ADD, False), (LAYOUT_GRID_ANCHOR, LAYOUT_GRID_ADD, False)],
        ),
        (
            CLIENT,
            "AnnotationsPanel",
            [
                (CLIENT_IMPORT_ANCHOR, CLIENT_IMPORT_ADD, True),
                (CLIENT_ITEM_ANCHOR, CLIENT_ITEM_ADD, False),
            ],
        ),
    ):
        edits_or_none = plan_edits(path, texts[path], marker, edits)
        if edits_or_none is not None:
            plan[path] = edits_or_none

    drop_stale_migration()
    assert_revision_free(MIGRATION, REVISION_ID)

    echarts_edits = plan_echarts(ECHARTS, texts[ECHARTS])
    if echarts_edits:
        plan[ECHARTS] = echarts_edits

    head_edits = plan_head_pin(TEST_MIGRATIONS, texts[TEST_MIGRATIONS], "c7d3e91a4b28", "a17f4c02be93")
    if head_edits is not None:
        plan[TEST_MIGRATIONS] = head_edits

    new_files = {
        MODEL: MODEL_SOURCE,
        MIGRATION: MIGRATION_SOURCE,
        SCHEMA: SCHEMA_SOURCE,
        ROUTER: ROUTER_SOURCE,
        TEST: TEST_SOURCE,
        HELPER: HELPER_SOURCE,
        PANEL: PANEL_SOURCE,
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
            if before is None:  # a REPLACEMENT, not an insertion
                text = text.replace(anchor, addition, 1)
            else:
                text = text.replace(anchor, (addition + anchor) if before else (anchor + addition), 1)
        path.write_text(text)
        print(f"patched {path}")

    print("\nMIGRATION REQUIRED: alembic upgrade head (creates chart_annotations).")
    print("Timeline notes appear as an Overview widget; markers show on the daily charts")
    print("(Revenue vs Spend, and every App Detail trend).")


if __name__ == "__main__":
    main()
