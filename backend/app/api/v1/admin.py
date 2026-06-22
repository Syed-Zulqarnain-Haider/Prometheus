"""Admin panel routes — all gated on the ``admin_panel`` capability.

User & role administration, revenue targets, the audit viewer, and the data-health
view. Every mutating action is audit-logged, and any change that affects a user's
resolved RBAC busts their cached UserContext so it takes effect immediately rather
than waiting out the 5-minute cache.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, RedisClient, require_capability
from app.core.config import get_settings
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit, enforce_sync_rate_limit
from app.models import User
from app.schemas.admin import (
    AuditPage,
    DataHealth,
    RoleConfig,
    RoleUpdate,
    TargetOut,
    TargetsResponse,
    TargetUpsert,
    UserCreate,
    UserSummary,
    UserUpdate,
)
from app.schemas.system import SettingOut, SettingUpdate, SyncTriggerResult, SystemHealth
from app.services import admin_service, settings_service, system_service
from app.services.audit import AuditDep
from app.services.auth import user_context_cache_key

# Router-level dependency enforces admin_panel; routes use CurrentUser for identity.
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(enforce_rate_limit), Depends(require_capability("admin_panel"))],
)


async def _bust_cache(redis: Redis, firebase_uid: str) -> None:
    """Drop a cached UserContext so RBAC changes apply on the next request."""
    await redis.delete(user_context_cache_key(firebase_uid))


# ── Users ─────────────────────────────────────────────────────────────────────
@router.get("/users", response_model=list[UserSummary])
async def list_users(db: DbSession) -> list[UserSummary]:
    return await admin_service.list_users(db)


@router.post("/users", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> UserSummary:
    try:
        summary = await admin_service.create_user(
            db,
            firebase_uid=body.firebase_uid,
            email=body.email,
            display_name=body.display_name,
            roles=body.roles,
            scopes=body.scopes,
            created_by=context.user_id,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A user with that email or Firebase UID already exists"
        ) from exc

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_create_user",
        resource=str(summary.id),
        detail={"email": body.email, "roles": summary.roles},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return summary


@router.patch("/users/{user_id}", response_model=UserSummary)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> UserSummary:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    try:
        summary = await admin_service.update_user(
            db,
            user,
            display_name=body.display_name,
            is_active=body.is_active,
            roles=body.roles,
            scopes=body.scopes,
            actor_id=context.user_id,
            display_name_set="display_name" in body.model_fields_set,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # Any of these can change resolved RBAC — bust the cache for instant effect.
    if body.is_active is not None or body.roles is not None or body.scopes is not None:
        await _bust_cache(redis, user.firebase_uid)

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_update_user",
        resource=str(user_id),
        detail=body.model_dump(exclude_unset=True, mode="json"),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return summary


# ── Roles ─────────────────────────────────────────────────────────────────────
@router.get("/roles", response_model=list[RoleConfig])
async def list_roles(db: DbSession) -> list[RoleConfig]:
    return await admin_service.list_roles(db)


@router.put("/roles/{role_id}", response_model=RoleConfig)
async def update_role(
    role_id: int,
    body: RoleUpdate,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> RoleConfig:
    try:
        config = await admin_service.set_role_config(
            db, role_id, list(body.metric_groups), list(body.capabilities)
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    # Every user holding this role has a stale cached context now.
    for firebase_uid in await admin_service.firebase_uids_for_role(db, role_id):
        await _bust_cache(redis, firebase_uid)

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_update_role",
        resource=config.name,
        detail={"metric_groups": config.metric_groups, "capabilities": config.capabilities},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return config


# ── Revenue targets ───────────────────────────────────────────────────────────
@router.get("/targets", response_model=TargetsResponse)
async def get_targets(db: DbSession, year: int = Query(ge=2000, le=2100)) -> TargetsResponse:
    annual, monthly = await admin_service.targets_for_year(db, year)
    return TargetsResponse(year=year, annual=annual, monthly=monthly)


@router.put("/targets", response_model=TargetOut)
async def put_target(
    body: TargetUpsert,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> TargetOut:
    try:
        target = await admin_service.upsert_target(
            db,
            period_type=body.period_type,
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
        action="admin_set_target",
        resource=f"{body.period_type}:{body.period_year}:{body.period_month or ''}",
        detail={"target_usd": body.target_usd},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return target


@router.delete("/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_target(
    target_id: uuid.UUID,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> Response:
    deleted = await admin_service.delete_target(db, target_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_delete_target",
        resource=str(target_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Audit viewer ──────────────────────────────────────────────────────────────
@router.get("/audit", response_model=AuditPage)
async def get_audit(
    db: DbSession,
    action: str | None = None,
    user_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPage:
    entries, next_offset = await admin_service.query_audit(
        db,
        action=action,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return AuditPage(entries=entries, next_offset=next_offset)


@router.get("/audit/actions", response_model=list[str])
async def get_audit_actions(db: DbSession) -> list[str]:
    return await admin_service.distinct_audit_actions(db)


# ── Data health ───────────────────────────────────────────────────────────────
@router.get("/data-health", response_model=DataHealth)
async def get_data_health(db: DbSession) -> DataHealth:
    return await admin_service.data_health(db)


# ── System: connection health ───────────────────────────────────────────────────
@router.get("/system/health", response_model=SystemHealth)
async def get_system_health(db: DbSession, redis: RedisClient) -> SystemHealth:
    """Live Postgres/Redis/BigQuery status — up/down + latency only, NO credentials."""
    return await system_service.check_connections(db, redis, get_settings())


# ── System: operational settings ────────────────────────────────────────────────
@router.get("/settings", response_model=list[SettingOut])
async def get_settings_list(db: DbSession) -> list[SettingOut]:
    return await settings_service.list_settings(db)


@router.put("/settings/{key}", response_model=SettingOut)
async def update_setting(
    key: str,
    body: SettingUpdate,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> SettingOut:
    try:
        setting = await settings_service.set_value(db, key, body.value, context.user_id)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_update_setting",
        resource=key,
        detail={"value": body.value},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return setting


# ── System: on-demand sync trigger (admin-only, audited, tightly rate-limited) ──
@router.post(
    "/system/sync",
    response_model=SyncTriggerResult,
    dependencies=[Depends(enforce_sync_rate_limit)],
)
async def run_sync_now(
    request: Request,
    context: CurrentUser,
    audit: AuditDep,
) -> SyncTriggerResult:
    """Trigger the data sync on demand. Returns an honest 'not configured' result when
    no real data source is wired (never a faked success)."""
    result = await system_service.run_sync_now(get_settings())
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_run_sync",
        detail={"triggered": result.triggered, "configured": result.configured},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return result
