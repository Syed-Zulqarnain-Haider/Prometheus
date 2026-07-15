"""App Master service — list/filter the Postgres serving copy, edit with BigQuery
write-back, and refresh the copy from BigQuery.

Read scope is admin-only (enforced at the router). Edits touch ONLY the owner-approved
editable columns; the write goes to BigQuery FIRST, and Postgres is updated only if that
succeeds — so the serving copy never diverges from the source of truth on a failed write.
"""

from __future__ import annotations

import asyncio
from typing import Any

import anyio
from sqlalchemy import String, delete, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.app_master_columns import ALL_COLUMNS, EDITABLE_SET, PRIMARY_KEY, REGISTRY
from app.core.config import Settings
from app.models.app_master import APP_MASTER_TABLE
from app.schemas.app_master import AppMasterColumnMeta, AppMasterListResponse
from app.schemas.integration import BigQueryColumn, SchemaColumnDiff, SchemaDiff
from app.services import app_master_bq, integration_service, settings_service

# The admin-editable setting holding the fully-qualified BigQuery table id.
_TABLE_SETTING_KEY = "app_master_bq_table"


async def _bq_table_id(db: AsyncSession) -> str:
    """The App Master BigQuery table id from the admin setting (or the registry default)."""
    return str(await settings_service.get_value(db, _TABLE_SETTING_KEY))


_TABLE = APP_MASTER_TABLE
# Typed Any: the table is built dynamically, so keep column expressions untyped for mypy.
_PK_COL: Any = _TABLE.c[PRIMARY_KEY]
# Columns a free-text search scans.
_SEARCH_COLUMNS = ("app_name", "canonical_key", "publisher", "ios_bundle_id", "android_package")

_COLUMN_META = [
    AppMasterColumnMeta(name=c.name, type=c.pg_type, editable=c.editable) for c in REGISTRY
]


class AppMasterRowNotFound(Exception):
    """No editable row with the given primary key exists in the serving copy."""


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {name: row._mapping[name] for name in ALL_COLUMNS}


def _apply_filters(
    stmt: Any,
    *,
    search: str | None,
    platform: str | None,
    hou: str | None,
    pod: int | None,
    needs_review: bool | None,
) -> Any:
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(*[_TABLE.c[col].cast(String).ilike(like) for col in _SEARCH_COLUMNS]))
    if platform:
        stmt = stmt.where(_TABLE.c.platform == platform)
    if hou:
        stmt = stmt.where(_TABLE.c.hou == hou)
    if pod is not None:
        stmt = stmt.where(_TABLE.c.pod == pod)
    if needs_review is not None:
        stmt = stmt.where(_TABLE.c.needs_review.is_(needs_review))
    return stmt


async def list_rows(
    session: AsyncSession,
    *,
    search: str | None = None,
    platform: str | None = None,
    hou: str | None = None,
    pod: int | None = None,
    needs_review: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AppMasterListResponse:
    """One page of rows matching the (separate) App Master filters, plus the total."""
    base = _apply_filters(
        select(_TABLE),
        search=search,
        platform=platform,
        hou=hou,
        pod=pod,
        needs_review=needs_review,
    )
    total_stmt = _apply_filters(
        select(func.count()).select_from(_TABLE),
        search=search,
        platform=platform,
        hou=hou,
        pod=pod,
        needs_review=needs_review,
    )
    total = int((await session.execute(total_stmt)).scalar_one())
    page = (
        base.order_by(_TABLE.c.app_name.asc().nullslast(), _PK_COL.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(page)).all()
    return AppMasterListResponse(
        rows=[_row_to_dict(r) for r in rows],
        total=total,
        columns=_COLUMN_META,
        primary_key=PRIMARY_KEY,
    )


async def get_row(session: AsyncSession, key: str) -> dict[str, Any] | None:
    row = (await session.execute(select(_TABLE).where(key == _PK_COL))).first()
    return _row_to_dict(row) if row else None


async def update_row(
    session: AsyncSession,
    settings: Settings,
    key: str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    """Apply ``changes`` (already narrowed to editable columns) to the row.

    Order: BigQuery write-back FIRST (source of truth), then the Postgres serving copy.
    Raises ``AppMasterRowNotFound`` for an unknown key; propagates
    ``app_master_bq.BigQuery*`` errors on write-back problems (the caller maps them to HTTP).
    """
    # Only known editable columns survive (defence in depth over the schema's extra=forbid).
    changes = {k: v for k, v in changes.items() if k in EDITABLE_SET}
    if not changes:
        current = await get_row(session, key)
        if current is None:
            raise AppMasterRowNotFound(key)
        return current

    existing = await get_row(session, key)
    if existing is None:
        raise AppMasterRowNotFound(key)

    table_id = await _bq_table_id(session)
    # 1) BigQuery first — if this fails, Postgres is untouched and the caller sees an error.
    await asyncio.to_thread(app_master_bq.push_update, settings, table_id, key, changes)

    # 2) Serving copy — only reached when the source of truth already accepted the change.
    await session.execute(update(_TABLE).where(key == _PK_COL).values(**changes))
    await session.commit()
    updated = await get_row(session, key)
    assert updated is not None  # noqa: S101 — just updated it in the same txn
    return updated


async def refresh_from_bigquery(session: AsyncSession, settings: Settings) -> dict[str, int]:
    """Full refresh of the serving copy from BigQuery. Rows without a canonical_key can't be
    keyed, so they are skipped (counted). Blocking BQ read runs in a worker thread."""
    table_id = await _bq_table_id(session)
    rows = await asyncio.to_thread(app_master_bq.fetch_rows, settings, table_id)
    by_key: dict[str, dict[str, Any]] = {}
    skipped = 0
    for row in rows:
        key = row.get(PRIMARY_KEY)
        if not key:
            skipped += 1
            continue
        by_key[str(key)] = {name: row.get(name) for name in ALL_COLUMNS}

    await session.execute(delete(_TABLE))
    if by_key:
        await session.execute(insert(_TABLE), list(by_key.values()))
    await session.commit()
    return {"synced": len(by_key), "skipped": skipped}


# BigQuery INFORMATION_SCHEMA data_type expected for each registry column (GoogleSQL types
# match our bq_type values exactly: STRING / INT64 / FLOAT64 / BOOL / TIMESTAMP).
_EXPECTED_BQ_SCHEMA: dict[str, str] = {c.bq_name: c.bq_type for c in REGISTRY}


async def schema_diff(session: AsyncSession, settings: Settings) -> SchemaDiff:
    """Read-only comparison of the configured BigQuery table's columns against the App Master
    registry — so an admin can confirm a (possibly newly-pointed) table's schema matches
    before refreshing/editing. Never alters anything; reports only."""
    if not settings.bq_credentials_path or not _key_present(settings.bq_credentials_path):
        return SchemaDiff(
            configured=False,
            message="No BigQuery reader key mounted — set BQ_CREDENTIALS_PATH and mount the key.",
        )
    table_id = await _bq_table_id(session)
    project = str(await settings_service.get_value(session, "gcp_project"))
    # Reuse the generic INFORMATION_SCHEMA column reader (read-only, sanitized errors).
    actual, error = await anyio.to_thread.run_sync(
        integration_service._run_schema_diff, settings.bq_credentials_path, project, table_id
    )
    if actual is None:
        return SchemaDiff(configured=True, message=error or "Schema check failed.")

    expected = _EXPECTED_BQ_SCHEMA
    missing = [c for c in expected if c not in actual]
    mismatches = [
        SchemaColumnDiff(column=c, expected=expected[c], actual=actual[c])
        for c in expected
        if c in actual and actual[c] != expected[c]
    ]
    unregistered = [
        BigQueryColumn(column=c, data_type=t) for c, t in actual.items() if c not in expected
    ]
    return SchemaDiff(
        configured=True,
        in_sync=not missing and not mismatches,
        missing_in_view=missing,
        type_mismatches=mismatches,
        unregistered_in_view=unregistered,
    )


def _key_present(key_path: str) -> bool:
    import os

    return bool(key_path) and os.path.exists(key_path)
