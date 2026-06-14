"""Saved views: per-user named filter/date/compare states."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import enforce_rate_limit
from app.models import SavedView
from app.schemas.reports import SavedViewCreate, SavedViewOut

router = APIRouter(prefix="/views", tags=["views"], dependencies=[Depends(enforce_rate_limit)])


def _out(view: SavedView) -> SavedViewOut:
    return SavedViewOut(
        id=view.id,
        name=view.name,
        page=view.page,
        filters=view.filters,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


@router.get("", response_model=list[SavedViewOut])
async def list_views(context: CurrentUser, db: DbSession) -> list[SavedViewOut]:
    rows = (
        (
            await db.execute(
                select(SavedView)
                .where(SavedView.user_id == context.user_id)
                .order_by(SavedView.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_out(v) for v in rows]


@router.post("", response_model=SavedViewOut, status_code=status.HTTP_201_CREATED)
async def create_view(body: SavedViewCreate, context: CurrentUser, db: DbSession) -> SavedViewOut:
    view = SavedView(user_id=context.user_id, name=body.name, page=body.page, filters=body.filters)
    db.add(view)
    await db.commit()
    await db.refresh(view)
    return _out(view)


@router.put("/{view_id}", response_model=SavedViewOut)
async def update_view(
    view_id: uuid.UUID, body: SavedViewCreate, context: CurrentUser, db: DbSession
) -> SavedViewOut:
    view = await db.scalar(
        select(SavedView).where(SavedView.id == view_id, SavedView.user_id == context.user_id)
    )
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "View not found")
    view.name = body.name
    view.page = body.page
    view.filters = body.filters
    view.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(view)
    return _out(view)


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(view_id: uuid.UUID, context: CurrentUser, db: DbSession) -> Response:
    view = await db.scalar(
        select(SavedView).where(SavedView.id == view_id, SavedView.user_id == context.user_id)
    )
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "View not found")
    await db.delete(view)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
