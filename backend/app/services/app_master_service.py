"""App Master service — list/filter the Postgres serving copy, edit with BigQuery
write-back, and refresh the copy from BigQuery.

Read scope is admin-only (enforced at the router). Edits touch ONLY the owner-approved
editable columns; the write goes to BigQuery FIRST, and Postgres is updated only if that
succeeds — so the serving copy never diverges from the source of truth on a failed write.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import anyio
from sqlalchemy import String, delete, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.app_master_columns import ALL_COLUMNS, EDITABLE_SET, PRIMARY_KEY, REGISTRY
from app.core.config import Settings
from app.models import AppMasterConfig, AppMasterEdit, User
from app.models.app_master import APP_MASTER_TABLE
from app.models.dynamic_columns import APP_MASTER as _KIND_APP_MASTER
from app.schemas.app_master import (
    AppMasterColumnMeta,
    AppMasterEditOut,
    AppMasterFilterValues,
    AppMasterListResponse,
)
from app.schemas.integration import (
    BigQueryColumn,
    SchemaColumnDiff,
    SchemaDiff,
    SchemaSyncResult,
)
from app.services import app_master_bq, integration_service, schema_reconcile, settings_service

# Static app-master column -> Postgres DDL type (for schema reconcile ALTER statements).
_PG_DDL_FROM_APP_MASTER: dict[str, str] = {
    "text": "TEXT",
    "bigint": "BIGINT",
    "boolean": "BOOLEAN",
    "double": "DOUBLE PRECISION",
    "timestamptz": "TIMESTAMPTZ",
}
_APP_MASTER_STATIC_TYPES: dict[str, str] = {
    c.name: _PG_DDL_FROM_APP_MASTER[c.pg_type] for c in REGISTRY
}

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


class NoEditToUndo(Exception):
    """There is no prior edit on this row to undo."""


def _row_to_dict(row: Any, names: list[str]) -> dict[str, Any]:
    # .get(): a just-added dynamic column may not be selected on every worker until it
    # attaches — serve NULL rather than KeyError until the next request heals it.
    return {name: row._mapping.get(name) for name in names}


async def _effective_columns(
    session: AsyncSession,
) -> tuple[list[str], list[AppMasterColumnMeta]]:
    """Static registry columns plus any active BigQuery-discovered dynamic columns
    (always read-only). Dynamic columns are attached to the in-memory Table so
    ``select(_TABLE)`` returns them. The single source of truth for what the grid shows."""
    dynamic = await schema_reconcile.load_active_dynamic(session, _KIND_APP_MASTER)
    schema_reconcile.attach_columns(_TABLE, [(c.name, c.pg_type) for c in dynamic])
    names = [*ALL_COLUMNS, *[c.name for c in dynamic if c.name not in set(ALL_COLUMNS)]]
    meta = [*_COLUMN_META, *[AppMasterColumnMeta(name=c.name, type=c.pg_type, editable=False)
                             for c in dynamic if c.name not in set(ALL_COLUMNS)]]
    return names, meta


def _apply_filters(
    stmt: Any,
    *,
    search: str | None,
    platform: list[str],
    hou: list[str],
    publisher: list[str],
    pod: int | None,
    needs_review: bool | None,
    package: str | None,
    app_id: str | None,
) -> Any:
    """Apply the App Master filters. ``platform``/``hou``/``publisher`` are multi-select
    (IN lists); ``package``/``app_id`` are substring matches across the relevant columns."""
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(*[_TABLE.c[col].cast(String).ilike(like) for col in _SEARCH_COLUMNS]))
    if platform:
        stmt = stmt.where(_TABLE.c.platform.in_(platform))
    if hou:
        stmt = stmt.where(_TABLE.c.hou.in_(hou))
    if publisher:
        stmt = stmt.where(_TABLE.c.publisher.in_(publisher))
    if pod is not None:
        stmt = stmt.where(_TABLE.c.pod == pod)
    if needs_review is not None:
        stmt = stmt.where(_TABLE.c.needs_review.is_(needs_review))
    if package:
        like = f"%{package}%"
        stmt = stmt.where(
            or_(_TABLE.c.android_package.ilike(like), _TABLE.c.ios_bundle_id.ilike(like))
        )
    if app_id:
        like = f"%{app_id}%"
        stmt = stmt.where(
            or_(_TABLE.c.canonical_key.ilike(like), _TABLE.c.apple_id.cast(String).ilike(like))
        )
    return stmt


def _ordered_columns(
    order: list[str], meta: list[AppMasterColumnMeta]
) -> list[AppMasterColumnMeta]:
    """Column metadata reordered by ``order`` (unknown names dropped, missing ones appended)."""
    by_name = {c.name: c for c in meta}
    ordered = [by_name[n] for n in order if n in by_name]
    ordered += [c for c in meta if c.name not in set(order)]
    return ordered


async def list_rows(
    session: AsyncSession,
    *,
    search: str | None = None,
    platform: list[str] | None = None,
    hou: list[str] | None = None,
    publisher: list[str] | None = None,
    pod: int | None = None,
    needs_review: bool | None = None,
    package: str | None = None,
    app_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AppMasterListResponse:
    """One page of rows matching the (separate) App Master filters, plus the total. Columns
    come back already ordered by the admin-set global column order."""
    flt: dict[str, Any] = {
        "search": search,
        "platform": platform or [],
        "hou": hou or [],
        "publisher": publisher or [],
        "pod": pod,
        "needs_review": needs_review,
        "package": package,
        "app_id": app_id,
    }
    names, meta = await _effective_columns(session)
    total_stmt = _apply_filters(select(func.count()).select_from(_TABLE), **flt)
    total = int((await session.execute(total_stmt)).scalar_one())
    page = (
        _apply_filters(select(_TABLE), **flt)
        .order_by(_TABLE.c.app_name.asc().nullslast(), _PK_COL.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(page)).all()
    order = await get_column_order(session)
    return AppMasterListResponse(
        rows=[_row_to_dict(r, names) for r in rows],
        total=total,
        columns=_ordered_columns(order, meta),
        column_order=order,
        primary_key=PRIMARY_KEY,
    )


async def filter_values(session: AsyncSession) -> AppMasterFilterValues:
    """Distinct values for the filter dropdowns (platforms / HOU / publishers / pods)."""

    async def _distinct(col: Any) -> list[Any]:
        stmt = select(col).distinct().where(col.isnot(None)).order_by(col)
        return list((await session.execute(stmt)).scalars().all())

    return AppMasterFilterValues(
        platforms=[str(v) for v in await _distinct(_TABLE.c.platform)],
        hou=[str(v) for v in await _distinct(_TABLE.c.hou)],
        publishers=[str(v) for v in await _distinct(_TABLE.c.publisher)],
        pods=[int(v) for v in await _distinct(_TABLE.c.pod)],
    )


# ── Global column order (admin-set, shared by all users) ─────────────────────────
async def _all_effective_names(session: AsyncSession) -> list[str]:
    """Static + active dynamic column names (dynamic appended after static)."""
    dynamic = await schema_reconcile.load_active_dynamic(session, _KIND_APP_MASTER)
    return [*ALL_COLUMNS, *[c.name for c in dynamic if c.name not in set(ALL_COLUMNS)]]


async def get_column_order(session: AsyncSession) -> list[str]:
    """The admin-set global column order, sanitized: only known columns, with any columns
    missing from the saved order appended (so a newly-added registry OR dynamic column
    still appears)."""
    all_names = await _all_effective_names(session)
    cfg = await session.get(AppMasterConfig, 1)
    saved = list(cfg.column_order) if cfg and cfg.column_order else []
    known = set(all_names)
    order = [c for c in saved if c in known]
    order += [c for c in all_names if c not in set(order)]
    return order


async def set_column_order(
    session: AsyncSession, order: list[str], admin_id: uuid.UUID | None
) -> list[str]:
    """Persist the global column order (admin-only). Unknown names are dropped; any omitted
    columns are appended so the order always covers every column."""
    all_names = await _all_effective_names(session)
    known = set(all_names)
    clean = [c for c in order if c in known]
    clean += [c for c in all_names if c not in set(clean)]
    cfg = await session.get(AppMasterConfig, 1)
    if cfg is None:
        cfg = AppMasterConfig(id=1)
        session.add(cfg)
    cfg.column_order = clean
    cfg.updated_at = datetime.now(UTC)
    cfg.updated_by = admin_id
    await session.commit()
    return clean


async def get_row(session: AsyncSession, key: str) -> dict[str, Any] | None:
    names, _ = await _effective_columns(session)
    row = (await session.execute(select(_TABLE).where(key == _PK_COL))).first()
    return _row_to_dict(row, names) if row else None


async def _write_change(
    session: AsyncSession, settings: Settings, key: str, changes: dict[str, Any]
) -> None:
    """BigQuery write-back FIRST (source of truth), then the Postgres serving copy. The
    caller records history + commits."""
    table_id = await _bq_table_id(session)
    # If BigQuery rejects the write, Postgres is untouched and the error propagates.
    await asyncio.to_thread(app_master_bq.push_update, settings, table_id, key, changes)
    await session.execute(update(_TABLE).where(key == _PK_COL).values(**changes))


async def update_row(
    session: AsyncSession,
    settings: Settings,
    key: str,
    changes: dict[str, Any],
    editor_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Apply ``changes`` (already narrowed to editable columns), recording the before/after in
    the change history so the edit can be undone. BigQuery first, then Postgres + history in
    one transaction. Raises ``AppMasterRowNotFound`` for an unknown key; propagates
    ``app_master_bq.BigQuery*`` errors on write-back problems."""
    changes = {k: v for k, v in changes.items() if k in EDITABLE_SET}
    existing = await get_row(session, key)
    if existing is None:
        raise AppMasterRowNotFound(key)
    if not changes:
        return existing

    before = {k: existing.get(k) for k in changes}
    await _write_change(session, settings, key, changes)
    session.add(
        AppMasterEdit(
            canonical_key=key, editor_user_id=editor_id, action="edit", before=before, after=changes
        )
    )
    await session.commit()
    updated = await get_row(session, key)
    assert updated is not None  # noqa: S101 — just updated it in the same txn
    return updated


async def undo_last_edit(
    session: AsyncSession, settings: Settings, key: str, editor_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Revert the most recent (not-yet-undone) edit on ``key`` — restore its ``before`` values
    to BigQuery + Postgres, mark that edit undone, and record the undo itself in the history."""
    last = (
        await session.execute(
            select(AppMasterEdit)
            .where(
                AppMasterEdit.canonical_key == key,
                AppMasterEdit.action == "edit",
                AppMasterEdit.undone.is_(False),
            )
            .order_by(AppMasterEdit.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is None:
        raise NoEditToUndo(key)

    restore = {k: v for k, v in (last.before or {}).items() if k in EDITABLE_SET}
    if restore:
        await _write_change(session, settings, key, restore)
    last.undone = True
    session.add(
        AppMasterEdit(
            canonical_key=key,
            editor_user_id=editor_id,
            action="undo",
            before=last.after,
            after=restore,
        )
    )
    await session.commit()
    updated = await get_row(session, key)
    assert updated is not None  # noqa: S101
    return updated


async def list_history(session: AsyncSession, key: str, limit: int = 20) -> list[AppMasterEditOut]:
    """The change history for one app (newest first) — for the audit/undo panel."""
    rows = (
        await session.execute(
            select(AppMasterEdit, User.email)
            .outerjoin(User, AppMasterEdit.editor_user_id == User.id)
            .where(AppMasterEdit.canonical_key == key)
            .order_by(AppMasterEdit.id.desc())
            .limit(limit)
        )
    ).all()
    return [
        AppMasterEditOut(
            id=e.id,
            canonical_key=e.canonical_key,
            edited_at=e.edited_at,
            editor_email=email,
            action=e.action,
            before=e.before,
            after=e.after,
            undone=e.undone,
        )
        for e, email in rows
    ]


async def refresh_from_bigquery(session: AsyncSession, settings: Settings) -> dict[str, int]:
    """Full refresh of the serving copy from BigQuery. Rows without a canonical_key can't be
    keyed, so they are skipped (counted). Blocking BQ read runs in a worker thread."""
    names, _ = await _effective_columns(session)
    dynamic_names = [n for n in names if n not in set(ALL_COLUMNS)]
    table_id = await _bq_table_id(session)
    rows = await asyncio.to_thread(app_master_bq.fetch_rows, settings, table_id, dynamic_names)
    by_key: dict[str, dict[str, Any]] = {}
    skipped = 0
    for row in rows:
        key = row.get(PRIMARY_KEY)
        if not key:
            skipped += 1
            continue
        by_key[str(key)] = {name: row.get(name) for name in names}

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


async def reconcile_schema(
    session: AsyncSession, settings: Settings, admin_id: uuid.UUID | None = None
) -> SchemaSyncResult:
    """Match the Postgres App Master serving table to the live BigQuery schema: add any
    new BigQuery columns (read-only), heal missing static columns, flag vanished ones.
    Non-destructive. App Master is admin-only, so new columns carry no RBAC decision."""
    table_id = await _bq_table_id(session)
    project = str(await settings_service.get_value(session, "gcp_project"))
    return await schema_reconcile.reconcile(
        session,
        settings,
        table_kind=_KIND_APP_MASTER,
        pg_table="app_master",
        bq_table_id=table_id,
        gcp_project=project,
        static_types=_APP_MASTER_STATIC_TYPES,
        table_obj=_TABLE,
        added_by=admin_id,
    )


def _key_present(key_path: str) -> bool:
    import os

    return bool(key_path) and os.path.exists(key_path)
