"""Admin-panel data access: users, role config, revenue targets, audit, health.

Pure DB operations — the routes layer on capability checks, audit writes, and
UserContext cache busting. Role/scope sets are REPLACED wholesale on update, which
mirrors how the admin UI presents them (checkbox grids, not deltas).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    DimApp,
    RevenueTarget,
    Role,
    RoleCapability,
    RoleMetricPermission,
    SyncRun,
    User,
    UserRole,
    UserScope,
)
from app.schemas.admin import (
    AuditEntry,
    DataHealth,
    RoleConfig,
    ScopeIn,
    SyncRunOut,
    TargetOut,
    UnmappedApp,
    UserSummary,
)
from app.schemas.auth import ScopeOut

# Data is considered stale if the last successful build is older than this.
STALE_AFTER = timedelta(days=2)


async def _user_summary(db: AsyncSession, user: User) -> UserSummary:
    roles = list(
        await db.scalars(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
            .order_by(Role.name)
        )
    )
    scope_rows = (
        await db.execute(
            select(UserScope.scope_type, UserScope.scope_value)
            .where(UserScope.user_id == user.id)
            .order_by(UserScope.scope_type, UserScope.scope_value)
        )
    ).all()
    return UserSummary(
        id=user.id,
        firebase_uid=user.firebase_uid,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        roles=roles,
        scopes=[ScopeOut(scope_type=st, scope_value=sv) for st, sv in scope_rows],
        created_at=user.created_at,
    )


async def list_users(db: AsyncSession) -> list[UserSummary]:
    users = list((await db.execute(select(User).order_by(User.email))).scalars().all())
    return [await _user_summary(db, u) for u in users]


async def _role_ids(db: AsyncSession, role_names: list[str]) -> dict[str, int]:
    rows = (await db.execute(select(Role.name, Role.id))).all()
    by_name: dict[str, int] = dict(rows)  # type: ignore[arg-type]
    unknown = [r for r in role_names if r not in by_name]
    if unknown:
        raise ValueError(f"unknown roles: {unknown}")
    return by_name


async def _set_roles(db: AsyncSession, user_id: uuid.UUID, role_names: list[str]) -> None:
    by_name = await _role_ids(db, role_names)
    await db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    for name in dict.fromkeys(role_names):
        await db.execute(insert(UserRole).values(user_id=user_id, role_id=by_name[name]))


async def _set_scopes(
    db: AsyncSession, user_id: uuid.UUID, scopes: list[ScopeIn], granted_by: uuid.UUID
) -> None:
    await db.execute(delete(UserScope).where(UserScope.user_id == user_id))
    seen: set[tuple[str, str | None]] = set()
    for scope in scopes:
        value = None if scope.scope_type == "all" else scope.scope_value
        if scope.scope_type != "all" and not value:
            raise ValueError(f"scope '{scope.scope_type}' requires a value")
        key = (scope.scope_type, value)
        if key in seen:
            continue
        seen.add(key)
        await db.execute(
            insert(UserScope).values(
                user_id=user_id,
                scope_type=scope.scope_type,
                scope_value=value,
                granted_by=granted_by,
            )
        )


async def create_user(
    db: AsyncSession,
    *,
    firebase_uid: str,
    email: str,
    display_name: str | None,
    roles: list[str],
    scopes: list[ScopeIn],
    created_by: uuid.UUID,
) -> UserSummary:
    user = User(
        firebase_uid=firebase_uid,
        email=email,
        display_name=display_name,
        is_active=True,
        created_by=created_by,
    )
    db.add(user)
    await db.flush()
    await _set_roles(db, user.id, roles)
    await _set_scopes(db, user.id, scopes, granted_by=created_by)
    await db.commit()
    await db.refresh(user)
    return await _user_summary(db, user)


async def update_user(
    db: AsyncSession,
    user: User,
    *,
    display_name: str | None,
    is_active: bool | None,
    roles: list[str] | None,
    scopes: list[ScopeIn] | None,
    actor_id: uuid.UUID,
    display_name_set: bool,
) -> UserSummary:
    if display_name_set:
        user.display_name = display_name
    if is_active is not None:
        user.is_active = is_active
    if roles is not None:
        await _set_roles(db, user.id, roles)
    if scopes is not None:
        await _set_scopes(db, user.id, scopes, granted_by=actor_id)
    await db.commit()
    await db.refresh(user)
    return await _user_summary(db, user)


# ── Role configuration ────────────────────────────────────────────────────────
async def list_roles(db: AsyncSession) -> list[RoleConfig]:
    roles = list((await db.execute(select(Role).order_by(Role.id))).scalars().all())
    configs: list[RoleConfig] = []
    for role in roles:
        groups = list(
            await db.scalars(
                select(RoleMetricPermission.metric_group)
                .where(RoleMetricPermission.role_id == role.id)
                .order_by(RoleMetricPermission.metric_group)
            )
        )
        caps = list(
            await db.scalars(
                select(RoleCapability.capability)
                .where(RoleCapability.role_id == role.id)
                .order_by(RoleCapability.capability)
            )
        )
        configs.append(
            RoleConfig(id=role.id, name=role.name, metric_groups=groups, capabilities=caps)
        )
    return configs


async def set_role_config(
    db: AsyncSession, role_id: int, metric_groups: list[str], capabilities: list[str]
) -> RoleConfig:
    role = await db.get(Role, role_id)
    if role is None:
        raise ValueError("role not found")
    await db.execute(delete(RoleMetricPermission).where(RoleMetricPermission.role_id == role_id))
    for group in dict.fromkeys(metric_groups):
        await db.execute(insert(RoleMetricPermission).values(role_id=role_id, metric_group=group))
    await db.execute(delete(RoleCapability).where(RoleCapability.role_id == role_id))
    for cap in dict.fromkeys(capabilities):
        await db.execute(insert(RoleCapability).values(role_id=role_id, capability=cap))
    await db.commit()
    (config,) = [c for c in await list_roles(db) if c.id == role_id]
    return config


async def firebase_uids_for_role(db: AsyncSession, role_id: int) -> list[str]:
    return list(
        await db.scalars(
            select(User.firebase_uid)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role_id == role_id)
        )
    )


# ── Revenue targets ───────────────────────────────────────────────────────────
def _target_out(target: RevenueTarget) -> TargetOut:
    return TargetOut(
        id=target.id,
        period_type=target.period_type,
        period_year=target.period_year,
        period_month=target.period_month,
        target_usd=target.target_usd,
        updated_at=target.updated_at,
    )


async def targets_for_year(db: AsyncSession, year: int) -> tuple[TargetOut | None, list[TargetOut]]:
    rows = list(
        (
            await db.execute(
                select(RevenueTarget)
                .where(RevenueTarget.period_year == year)
                .order_by(RevenueTarget.period_month.nulls_first())
            )
        )
        .scalars()
        .all()
    )
    annual = next((r for r in rows if r.period_type == "year"), None)
    monthly = [r for r in rows if r.period_type == "month"]
    return (
        _target_out(annual) if annual else None,
        [_target_out(m) for m in monthly],
    )


async def upsert_target(
    db: AsyncSession,
    *,
    period_type: str,
    period_year: int,
    period_month: int | None,
    target_usd: float,
    set_by: uuid.UUID,
) -> TargetOut:
    if period_type == "year":
        period_month = None
    elif period_month is None:
        raise ValueError("monthly target requires period_month")

    existing = await db.scalar(
        select(RevenueTarget).where(
            RevenueTarget.period_type == period_type,
            RevenueTarget.period_year == period_year,
            RevenueTarget.period_month.is_(period_month)
            if period_month is None
            else RevenueTarget.period_month == period_month,
        )
    )
    if existing is None:
        existing = RevenueTarget(
            period_type=period_type,
            period_year=period_year,
            period_month=period_month,
            target_usd=target_usd,
            set_by=set_by,
        )
        db.add(existing)
    else:
        existing.target_usd = target_usd
        existing.set_by = set_by
        existing.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(existing)
    return _target_out(existing)


async def delete_target(db: AsyncSession, target_id: uuid.UUID) -> bool:
    target = await db.get(RevenueTarget, target_id)
    if target is None:
        return False
    await db.delete(target)
    await db.commit()
    return True


# ── Audit viewer ──────────────────────────────────────────────────────────────
async def query_audit(
    db: AsyncSession,
    *,
    action: str | None,
    user_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> tuple[list[AuditEntry], int | None]:
    stmt = select(AuditLog, User.email).join(User, User.id == AuditLog.user_id, isouter=True)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    stmt = stmt.order_by(AuditLog.id.desc()).offset(offset).limit(limit + 1)

    rows = (await db.execute(stmt)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    entries = [
        AuditEntry(
            id=log.id,
            user_id=log.user_id,
            user_email=email,
            action=log.action,
            resource=log.resource,
            detail=log.detail,
            ip_address=str(log.ip_address) if log.ip_address is not None else None,
            user_agent=log.user_agent,
            created_at=log.created_at,
        )
        for log, email in rows
    ]
    return entries, (offset + limit if has_more else None)


async def distinct_audit_actions(db: AsyncSession) -> list[str]:
    return list(await db.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)))


# ── Data health ───────────────────────────────────────────────────────────────
def _sync_out(run: SyncRun) -> SyncRunOut:
    return SyncRunOut(
        id=run.id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status,
        rows_loaded=run.rows_loaded,
        rows_previous=run.rows_previous,
        bq_built_at=run.bq_built_at,
        error_detail=run.error_detail,
    )


async def data_health(db: AsyncSession) -> DataHealth:
    latest = (
        (await db.execute(select(SyncRun).order_by(SyncRun.id.desc()).limit(1))).scalars().first()
    )
    last_success = (
        (
            await db.execute(
                select(SyncRun)
                .where(SyncRun.status == "success")
                .order_by(SyncRun.id.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    recent = list(
        (await db.execute(select(SyncRun).order_by(SyncRun.id.desc()).limit(10))).scalars().all()
    )

    warnings: list[str] = []
    is_stale = False
    built_at = last_success.bq_built_at if last_success else None
    if built_at is not None:
        age = datetime.now(UTC) - built_at
        if age > STALE_AFTER:
            is_stale = True
            warnings.append(
                f"Data is {age.days} day(s) old — last successful build {built_at.date()}."
            )
    else:
        warnings.append("No successful sync has ever completed.")
    if latest is not None and latest.status not in ("success", "running"):
        warnings.append(f"Most recent sync ended with status '{latest.status}'.")
        if latest.error_detail:
            warnings.append(latest.error_detail)

    unmapped_rows = list(
        (
            await db.execute(
                select(DimApp).where(DimApp.is_mapped.is_(False)).order_by(DimApp.canonical_key)
            )
        )
        .scalars()
        .all()
    )
    unmapped_count = await db.scalar(
        select(func.count()).select_from(DimApp).where(DimApp.is_mapped.is_(False))
    )
    unmapped_apps = [
        UnmappedApp(
            canonical_key=app.canonical_key,
            app_name=app.app_name,
            publisher=app.publisher,
            platform_keys=app.android_package or (str(app.apple_id) if app.apple_id else None),
        )
        for app in unmapped_rows[:100]
    ]

    return DataHealth(
        bq_built_at=built_at,
        last_status=latest.status if latest else None,
        last_run_finished_at=latest.finished_at if latest else None,
        rows_loaded=last_success.rows_loaded if last_success else None,
        is_stale=is_stale,
        warnings=warnings,
        recent_runs=[_sync_out(r) for r in recent],
        unmapped_count=int(unmapped_count or 0),
        unmapped_apps=unmapped_apps,
    )
