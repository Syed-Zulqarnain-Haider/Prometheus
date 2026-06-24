"""Resolve a user's full RBAC context from the database."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Role,
    RoleCapability,
    RoleMetricPermission,
    User,
    UserRole,
    UserScope,
)
from app.schemas.auth import ScopeOut, UserContext

USER_CONTEXT_TTL_SECONDS = 300  # 5 minutes


def user_context_cache_key(firebase_uid: str) -> str:
    return f"userctx:{firebase_uid}"


async def resolve_user_context(db: AsyncSession, firebase_uid: str) -> UserContext | None:
    """Load the user and their roles, metric groups, capabilities, and scopes.

    Returns ``None`` if no user exists for the given Firebase UID.
    """
    user = await db.scalar(select(User).where(User.firebase_uid == firebase_uid))
    if user is None:
        return None

    roles = list(
        await db.scalars(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
            .order_by(Role.name)
        )
    )
    metric_groups = list(
        await db.scalars(
            select(RoleMetricPermission.metric_group)
            .join(UserRole, UserRole.role_id == RoleMetricPermission.role_id)
            .where(UserRole.user_id == user.id)
        )
    )
    capabilities = list(
        await db.scalars(
            select(RoleCapability.capability)
            .join(UserRole, UserRole.role_id == RoleCapability.role_id)
            .where(UserRole.user_id == user.id)
        )
    )
    scope_rows = (
        await db.execute(
            select(UserScope.scope_type, UserScope.scope_value)
            .where(UserScope.user_id == user.id)
            .order_by(UserScope.scope_type, UserScope.scope_value)
        )
    ).all()

    return UserContext(
        user_id=user.id,
        firebase_uid=user.firebase_uid,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        access_expires_at=user.access_expires_at,
        roles=roles,
        metric_groups=sorted(set(metric_groups)),
        capabilities=sorted(set(capabilities)),
        scopes=[ScopeOut(scope_type=st, scope_value=sv) for st, sv in scope_rows],
    )
