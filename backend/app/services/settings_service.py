"""Read/write operational app settings (non-secret), backed by ``app_settings``.

Reads fall back to the registry default when a key is unset or holds an invalid
value. Writes go through the registry, which constrains values to int/bool — so a
credential string can never be stored.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings_registry import SETTINGS_REGISTRY, SettingSpec, coerce_value
from app.models import AppSetting
from app.schemas.system import ClientSettings, SettingOut


def _coerce_or_default(spec: SettingSpec, raw: object | None) -> int | bool | str:
    if raw is None:
        return spec.default
    try:
        return coerce_value(spec, raw)
    except ValueError:
        return spec.default  # tolerate a legacy/invalid stored value


async def get_value(db: AsyncSession, key: str) -> int | bool | str:
    """Effective value for a registered setting (stored value or default)."""
    spec = SETTINGS_REGISTRY[key]
    row = await db.get(AppSetting, key)
    return _coerce_or_default(spec, row.value if row else None)


async def list_settings(db: AsyncSession) -> list[SettingOut]:
    rows = {r.key: r for r in (await db.scalars(select(AppSetting))).all()}
    out: list[SettingOut] = []
    for key, spec in SETTINGS_REGISTRY.items():
        row = rows.get(key)
        out.append(
            SettingOut(
                key=key,
                type=spec.type,
                value=_coerce_or_default(spec, row.value if row else None),
                default=spec.default,
                label=spec.label,
                description=spec.description,
                group=spec.group,
                minimum=spec.minimum,
                maximum=spec.maximum,
                updated_at=row.updated_at if row else None,
            )
        )
    return out


async def set_value(
    db: AsyncSession, key: str, raw_value: object, actor_id: uuid.UUID
) -> SettingOut:
    """Validate and upsert a setting. Raises ValueError for unknown keys or bad values."""
    spec = SETTINGS_REGISTRY.get(key)
    if spec is None:
        raise ValueError(f"Unknown setting '{key}'")
    value = coerce_value(spec, raw_value)
    now = datetime.now(UTC)
    await db.execute(
        pg_insert(AppSetting)
        .values(key=key, value=value, updated_at=now, updated_by=actor_id)
        .on_conflict_do_update(
            index_elements=[AppSetting.key],
            set_={"value": value, "updated_at": now, "updated_by": actor_id},
        )
    )
    await db.commit()
    return SettingOut(
        key=key,
        type=spec.type,
        value=value,
        default=spec.default,
        label=spec.label,
        description=spec.description,
        group=spec.group,
        minimum=spec.minimum,
        maximum=spec.maximum,
        updated_at=now,
    )


async def client_settings(db: AsyncSession) -> ClientSettings:
    return ClientSettings(
        data_freshness_threshold_hours=int(await get_value(db, "data_freshness_threshold_hours")),
        show_demo_widgets=bool(await get_value(db, "show_demo_widgets")),
    )
