"""Apps routes: scoped app list (filter population) and single-app metadata.

Out-of-scope or nonexistent apps return 404 (indistinguishable), never 403.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.cache import aggregate_cache_key, cached_json, scope_token
from app.core.rate_limit import enforce_rate_limit
from app.models import DimApp
from app.services.scopes import build_scope_filter

router = APIRouter(tags=["apps"], dependencies=[Depends(enforce_rate_limit)])

# scope_type -> dim_app column (mirrors the fact-table scope columns).
_DIM_SCOPE_COLUMNS: dict[str, Any] = {
    "hou": DimApp.hou,
    "pod": DimApp.pod,
    "publisher": DimApp.publisher,
    "app": DimApp.canonical_key,
}


def _app_payload(app: DimApp) -> dict[str, Any]:
    return {
        "canonical_key": app.canonical_key,
        "app_name": app.app_name,
        "publisher": app.publisher,
        "pod": app.pod,
        "pod_owner": app.pod_owner,
        "hou": app.hou,
        "app_category": app.app_category,
        "ownership_type": app.ownership_type,
        "is_mapped": app.is_mapped,
        "apple_id": app.apple_id,
        "android_package": app.android_package,
        "ios_bundle_id": app.ios_bundle_id,
    }


@router.get("/apps")
async def list_apps(context: CurrentUser, db: DbSession, redis: RedisClient) -> dict[str, Any]:
    scope = build_scope_filter(context.scopes, columns=_DIM_SCOPE_COLUMNS)
    key = aggregate_cache_key("apps.list", scope_token(context.scopes), {})

    async def produce() -> dict[str, Any]:
        stmt = (
            select(
                DimApp.canonical_key,
                DimApp.app_name,
                DimApp.publisher,
                DimApp.pod,
                DimApp.pod_owner,
                DimApp.hou,
                DimApp.is_mapped,
            )
            .where(scope)
            .order_by(DimApp.app_name)
        )
        rows = (await db.execute(stmt)).mappings().all()
        return {"apps": [dict(r) for r in rows]}

    result: dict[str, Any] = await cached_json(redis, key, produce)
    return result


@router.get("/apps/{canonical_key}")
async def get_app(canonical_key: str, context: CurrentUser, db: DbSession) -> dict[str, Any]:
    scope = build_scope_filter(context.scopes, columns=_DIM_SCOPE_COLUMNS)
    stmt = select(DimApp).where(DimApp.canonical_key == canonical_key).where(scope)
    app = (await db.execute(stmt)).scalars().first()
    if app is None:
        # Out of scope OR nonexistent — same response, by design.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
    return _app_payload(app)
