"""Admin panel routes — all gated on the ``admin_panel`` capability.

User & role administration, revenue targets, the audit viewer, and the data-health
view. Every mutating action is audit-logged, and any change that affects a user's
resolved RBAC busts their cached UserContext so it takes effect immediately rather
than waiting out the 5-minute cache.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, RedisClient, require_capability
from app.core.cache import AGG_PREFIX
from app.core.config import get_settings
from app.core.http import client_ip
from app.core.rate_limit import (
    enforce_diagnostics_rate_limit,
    enforce_rate_limit,
    enforce_sync_rate_limit,
)
from app.models import User
from app.schemas.access import AccessRequestApprove, AccessRequestOut
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
from app.schemas.integration import (
    BigQueryTestResult,
    ClearDataRequest,
    ClearDataResult,
    IntegrationStatus,
    SchemaDiff,
    SchemaSyncResult,
)
from app.schemas.system import SettingOut, SettingUpdate, SyncTriggerResult, SystemHealth
from app.services import (
    access_service,
    account_service,
    admin_service,
    alerts_service,
    digest_service,
    fact_schema,
    integration_service,
    notification_service,
    settings_service,
    sync_service,
    system_service,
)
from app.services.audit import AuditDep
from app.services.auth import user_context_cache_key

logger = logging.getLogger("app.api.admin")

async def enforce_admin_2fa(request: Request, context: CurrentUser, db: DbSession) -> None:
    """When ``require_admin_2fa`` is on, admin actions require a 2FA sign-in.

    BREAK-GLASS: the Settings routes are exempt, so an admin can always turn the requirement
    back off even from a non-2FA session — this makes the toggle impossible to lock yourself
    out of. ``request.state.two_factor`` is set by get_user_context from the verified token.
    """
    if "/settings" in request.url.path:  # break-glass: always allow settings read/write
        return
    if not bool(await settings_service.get_value(db, "require_admin_2fa")):
        return
    if not getattr(request.state, "two_factor", False):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Admin actions require two-factor authentication. Sign in again with 2FA.",
        )


# Router-level dependency enforces admin_panel; routes use CurrentUser for identity.
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[
        Depends(enforce_rate_limit),
        Depends(require_capability("admin_panel")),
        Depends(enforce_admin_2fa),
    ],
)


async def _bust_cache(redis: Redis, firebase_uid: str) -> None:
    """Drop a cached UserContext so RBAC changes apply on the next request."""
    await redis.delete(user_context_cache_key(firebase_uid))


def _resolve_expiry(expires_at: datetime | None, duration_days: int | None) -> datetime | None:
    """Absolute, TZ-AWARE timestamp from either an explicit instant or a duration in days
    (the latter takes precedence). A naive instant is interpreted as UTC so downstream
    comparisons (e.g. the last-admin guard) never mix naive/aware. None = permanent."""
    if duration_days is not None:
        return datetime.now(UTC) + timedelta(days=duration_days)
    if expires_at is not None and expires_at.tzinfo is None:
        return expires_at.replace(tzinfo=UTC)
    return expires_at


def _reject_both_expiry(expires_at: datetime | None, duration_days: int | None) -> None:
    if expires_at is not None and duration_days is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Provide either access_expires_at or access_duration_days, not both",
        )


# ── Users ─────────────────────────────────────────────────────────────────────
@router.get("/users", response_model=list[UserSummary])
async def list_users(db: DbSession) -> list[UserSummary]:
    return await admin_service.list_users(db)


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_user_sessions(
    user_id: uuid.UUID,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> dict[str, str]:
    """Force-sign-out a user from every device (offboarding / suspected compromise). Stamps
    their revoke instant and busts their cached context so it takes effect immediately."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    revoked_at = await account_service.revoke_sessions(db, user_id)
    await _bust_cache(redis, user.firebase_uid)
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_revoke_sessions",
        resource=str(user_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return {"revoked_at": revoked_at.isoformat()}


@router.post("/users", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> UserSummary:
    _reject_both_expiry(body.access_expires_at, body.access_duration_days)
    expiry = _resolve_expiry(body.access_expires_at, body.access_duration_days)
    try:
        summary = await admin_service.create_user(
            db,
            firebase_uid=body.firebase_uid,
            email=body.email,
            display_name=body.display_name,
            roles=body.roles,
            scopes=body.scopes,
            created_by=context.user_id,
            access_expires_at=expiry,
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
        detail={
            "email": body.email,
            "roles": summary.roles,
            "expires_at": expiry.isoformat() if expiry else None,
        },
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

    _reject_both_expiry(body.access_expires_at, body.access_duration_days)
    access_set = bool({"access_expires_at", "access_duration_days"} & body.model_fields_set)
    new_expiry = (
        _resolve_expiry(body.access_expires_at, body.access_duration_days)
        if access_set
        else user.access_expires_at
    )

    # Last-active-admin lockout guard: refuse any change (demote / deactivate / already-past
    # expiry) that would leave the system with zero active admins. A FUTURE expiry is allowed.
    current_roles = await admin_service.role_names(db, user.id)
    new_is_active = user.is_active if body.is_active is None else body.is_active
    new_roles = current_roles if body.roles is None else body.roles
    was_admin = admin_service.is_active_admin(
        is_active=user.is_active, roles=current_roles, access_expires_at=user.access_expires_at
    )
    will_admin = admin_service.is_active_admin(
        is_active=new_is_active, roles=new_roles, access_expires_at=new_expiry
    )
    would_orphan_admins = (
        was_admin
        and not will_admin
        and not await admin_service.other_active_admins_exist(db, user.id)
    )
    if would_orphan_admins:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Cannot remove access from the last active admin"
        )

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
            access_expires_at=new_expiry,
            access_set=access_set,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # Anything affecting resolved access/RBAC — bust the cache for instant effect.
    if (
        body.is_active is not None
        or body.roles is not None
        or body.scopes is not None
        or access_set
    ):
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


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> Response:
    """Hard-delete a user (roles/scopes/layouts/saved views+reports cascade; audit + other
    actor links are nulled). GUARDS: an admin cannot delete their OWN account, nor the LAST
    active admin — both return 400 (lockout prevention)."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user_id == context.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account")

    current_roles = await admin_service.role_names(db, user.id)
    if admin_service.is_active_admin(
        is_active=user.is_active, roles=current_roles, access_expires_at=user.access_expires_at
    ) and not await admin_service.other_active_admins_exist(db, user.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete the last active admin")

    # Capture before the row is gone; the deleted user's own audit rows have user_id nulled.
    firebase_uid, email = user.firebase_uid, user.email
    await admin_service.delete_user(db, user_id)
    await _bust_cache(redis, firebase_uid)
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_delete_user",
        resource=str(user_id),
        detail={"email": email},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Access requests (Google sign-in -> admin approves/rejects) ──────────────────
@router.get("/access-requests", response_model=list[AccessRequestOut])
async def list_access_requests(db: DbSession) -> list[AccessRequestOut]:
    """Pending access requests awaiting approval (oldest first)."""
    return await access_service.list_pending(db)


@router.post("/access-requests/{request_id}/approve", response_model=UserSummary)
async def approve_access_request(
    request_id: uuid.UUID,
    body: AccessRequestApprove,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> UserSummary:
    """Provision the requester with the chosen role/scope (+ optional expiry) and mark the
    request approved. Never auto-grants admin — the admin selects the roles explicitly."""
    _reject_both_expiry(body.access_expires_at, body.access_duration_days)
    expiry = _resolve_expiry(body.access_expires_at, body.access_duration_days)
    try:
        summary, firebase_uid = await access_service.approve(
            db,
            request_id,
            roles=body.roles,
            scopes=body.scopes,
            access_expires_at=expiry,
            actor_id=context.user_id,
        )
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except access_service.RequestAlreadyDecided as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await _bust_cache(redis, firebase_uid)
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_approve_access",
        resource=str(request_id),
        detail={
            "email": summary.email,
            "roles": summary.roles,
            "expires_at": expiry.isoformat() if expiry else None,
        },
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return summary


@router.post("/access-requests/{request_id}/reject", response_model=AccessRequestOut)
async def reject_access_request(
    request_id: uuid.UUID,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> AccessRequestOut:
    """Reject a request: zero access, no role. The identity may re-request by signing in."""
    try:
        req = await access_service.reject(db, request_id, context.user_id)
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except access_service.RequestAlreadyDecided as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_reject_access",
        resource=str(request_id),
        detail={"email": req.email, "firebase_uid": req.firebase_uid},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return req


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
    db: DbSession,
    audit: AuditDep,
    mode: Annotated[str, Query(pattern="^(incremental|full|range)$")] = "incremental",
    start: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    end: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
) -> SyncTriggerResult:
    """Trigger the data sync on demand (advisory-lock guarded; delegates to the configured
    trigger URL or runs the vendored sync locally). ``incremental`` (default) re-pulls and
    overwrites the rolling window; ``full`` backfills ALL history; ``range`` overwrites the
    explicit ``start``..``end`` window (both YYYY-MM-DD). Honest 'not configured' when no
    execution path is wired — never a faked success."""
    if mode == "range" and not start:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "A start date is required for a range sync"
        )
    settings = get_settings()
    gcp_project = str(await settings_service.get_value(db, "gcp_project"))
    bq_view = str(await settings_service.get_value(db, "bq_view"))
    window_days = int(await settings_service.get_value(db, "sync_window_days"))
    # The lock/run uses its own short-lived session (the request session is closing); the
    # app-state sessionmaker resolves to the test factory under dependency overrides.
    result = await sync_service.run_sync(
        request.app.state.sessionmaker,
        settings,
        gcp_project=gcp_project,
        bq_view=bq_view,
        mode=mode,
        window_days=window_days,
        start_date=start,
        end_date=end,
    )
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_run_sync",
        detail={
            "triggered": result.triggered,
            "configured": result.configured,
            "mode": mode,
            "start": start,
            "end": end,
        },
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return result


# ── System: evaluate proactive alerts on demand (admin-only, audited) ───────────
@router.post("/alerts/evaluate", dependencies=[Depends(enforce_diagnostics_rate_limit)])
async def evaluate_alerts(
    request: Request, context: CurrentUser, db: DbSession, audit: AuditDep
) -> dict[str, Any]:
    """Run the anomaly-alert checks now (revenue drop, spend spike, low ROAS, stale data) and
    notify admins/execs on anything fired. No-op returning [] when alerts are disabled."""
    fired = await alerts_service.evaluate_and_notify(db, get_settings())
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_evaluate_alerts",
        detail={"fired": [a["key"] for a in fired]},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return {"count": len(fired), "fired": fired}


@router.post("/digest/send", dependencies=[Depends(enforce_diagnostics_rate_limit)])
async def send_digest(
    request: Request, context: CurrentUser, db: DbSession, audit: AuditDep
) -> dict[str, Any]:
    """Build + send the daily performance digest now (admin). No-op when the digest is disabled
    or there's no data; returns a preview of what was sent."""
    result = await digest_service.evaluate(db, get_settings())
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_send_digest",
        detail={"sent": result["sent"]},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return result


# ── Integration: status (BigQuery key presence + Postgres/Redis + sync history) ─
@router.get("/integration/status", response_model=IntegrationStatus)
async def get_integration_status(db: DbSession, redis: RedisClient) -> IntegrationStatus:
    """Integration tab status: is the BigQuery reader key mounted, are Postgres/Redis
    healthy, and the recent sync history. Status/history only — NO credential, key
    path, or connection string is ever returned."""
    return await integration_service.integration_status(db, redis, get_settings())


# ── Integration: read-only BigQuery 'Test Connection' (audited, rate-limited) ───
@router.post(
    "/integration/test-bigquery",
    response_model=BigQueryTestResult,
    dependencies=[Depends(enforce_diagnostics_rate_limit)],
)
async def test_bigquery_connection(
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> BigQueryTestResult:
    """Lightweight, READ-ONLY BigQuery reachability check. Loads the reader key from its
    configured path (separate from Firebase creds) and dry-runs a query. Returns a
    sanitized ok/fail message — never a credential or raw provider error."""
    settings = get_settings()
    project = str(await settings_service.get_value(db, "gcp_project"))
    result = await integration_service.test_bigquery(settings, project)
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_test_bigquery",
        detail={"ok": result.ok},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return result


# ── Integration: read-only schema diff (BQ view vs registry — informational) ────
@router.get(
    "/integration/schema-diff",
    response_model=SchemaDiff,
    dependencies=[Depends(enforce_diagnostics_rate_limit)],
)
async def get_schema_diff(db: DbSession) -> SchemaDiff:
    """Compare the live BigQuery view's columns against the metric registry. READ-ONLY
    and INFORMATIONAL — it never alters any schema; adopting a column stays a deliberate
    registry change."""
    settings = get_settings()
    gcp_project = str(await settings_service.get_value(db, "gcp_project"))
    bq_view = str(await settings_service.get_value(db, "bq_view"))
    return await integration_service.schema_diff(settings, gcp_project, bq_view)


# ── Integration: Match Database & BigQuery Schema (additive, non-destructive) ────
@router.post(
    "/integration/schema-sync",
    response_model=SchemaSyncResult,
    dependencies=[Depends(enforce_diagnostics_rate_limit)],
)
async def integration_schema_sync(
    request: Request,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> SchemaSyncResult:
    """Match the Postgres fact table to the live BigQuery view: add any new columns
    (served to ADMINS ONLY as 'unclassified' until you give them a curated metric group),
    heal missing static columns, and flag columns that vanished from BigQuery. Never drops
    data. The next daily sync (or a manual sync) populates the new columns' values."""
    result = await fact_schema.reconcile(db, get_settings(), context.user_id)
    if result.added or result.deactivated or result.healed_static:
        # New/changed columns can alter what admins can request — bust the aggregate cache
        # so payloads reflect the new schema instead of serving pre-sync cached rows.
        try:
            async for key in redis.scan_iter(f"{AGG_PREFIX}*", count=500):
                await redis.delete(key)
        except Exception:  # noqa: BLE001 — cache staleness is TTL-bounded; never fail the sync
            logger.exception("aggregate cache bust after schema-sync failed (non-fatal)")
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_integration_schema_sync",
        resource="fact_daily_performance",
        detail=result.model_dump(mode="json"),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    if result.added or result.deactivated:
        await notification_service.notify_admins(
            type="schema_sync",
            title="Metrics schema updated from BigQuery",
            body=(
                f"Added {len(result.added)} column(s) (admin-only), "
                f"flagged {len(result.deactivated)} removed"
            ),
            severity="warning" if result.deactivated else "info",
            link="/admin?tab=integration",
            actor_id=context.user_id,
            resource="fact_daily_performance",
        )
    return result


# ── Integration: Clear Data (DESTRUCTIVE — typed confirmation, audited) ──────────
@router.post(
    "/integration/clear-data",
    response_model=ClearDataResult,
    dependencies=[Depends(enforce_sync_rate_limit)],
)
async def clear_data(
    body: ClearDataRequest,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> ClearDataResult:
    """Wipe ONLY analytics/fact data (fact_daily_performance, dim_app, sync_runs). NEVER
    users, roles, layouts, settings, targets, saved views/reports, or the audit log.
    Requires the exact typed confirmation phrase; fully audited (who/when/rows)."""
    if body.confirmation != integration_service.CLEAR_DATA_PHRASE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Confirmation phrase must be exactly '{integration_service.CLEAR_DATA_PHRASE}'.",
        )
    result = await integration_service.clear_analytics_data(db, redis)
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_clear_data",
        detail={"rows_deleted": result.rows_deleted, "total": result.total},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return result
