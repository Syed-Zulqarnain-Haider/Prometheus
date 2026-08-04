"""Shared schema-reconciliation engine for the admin "Match Database & BigQuery Schema"
buttons (App Master and the metrics fact table).

What it does, additively and safely:
  * Reads the live BigQuery table/view columns (read-only, via INFORMATION_SCHEMA).
  * Ensures every STATIC registry column physically exists in the Postgres serving table
    (``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``) — heals registry↔DB drift.
  * Adds any BigQuery column NOT covered by the static registry as a *dynamic* column:
    ``ALTER TABLE ... ADD COLUMN`` + a ``dynamic_columns`` record, and attaches it to the
    in-memory SQLAlchemy ``Table`` so it serves immediately.
  * Flags (never drops) columns that have vanished from BigQuery — the Postgres column and
    its history are kept; the ``dynamic_columns`` row is marked ``active=false``.

Security: identifiers are validated against a strict lowercase pattern and column TYPES map
from a fixed allow-list; unsupported BigQuery types (STRUCT/ARRAY/JSON/GEOGRAPHY/…) are
skipped and reported, never coerced. Fact-table dynamic columns are served to admins only
(the ``unclassified`` metric group). DDL uses validated identifiers only — never user input.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import anyio
from sqlalchemy import Column, Table, select, text
from sqlalchemy import types as satypes
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.dynamic_columns import DynamicColumn
from app.schemas.integration import SchemaSyncColumn, SchemaSyncResult
from app.services import integration_service

log = logging.getLogger("app.schema_reconcile")

# Strict identifier guard: lowercase start, then lowercase/digit/underscore, ≤63 chars
# (Postgres identifier limit). Anything else is reported as unsupported, never used in DDL.
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

# BigQuery INFORMATION_SCHEMA data_type -> Postgres DDL type. Only these are auto-adopted;
# a BigQuery column of any other type is skipped and reported (unsupported_types).
_PG_FROM_BQ: dict[str, str] = {
    "STRING": "TEXT",
    "BYTES": "TEXT",
    "INT64": "BIGINT",
    "INTEGER": "BIGINT",
    "FLOAT64": "DOUBLE PRECISION",
    "FLOAT": "DOUBLE PRECISION",
    "NUMERIC": "NUMERIC(38,9)",
    "BIGNUMERIC": "NUMERIC(38,9)",
    "BOOL": "BOOLEAN",
    "BOOLEAN": "BOOLEAN",
    "TIMESTAMP": "TIMESTAMPTZ",
    "DATETIME": "TIMESTAMPTZ",
    "DATE": "DATE",
}

_NUMERIC_RE = re.compile(r"NUMERIC\((\d+),\s*(\d+)\)", re.IGNORECASE)


def map_bq_type(bq_type: str) -> str | None:
    """Postgres DDL type for a BigQuery data_type, or None if unsupported (skip + report).

    Parameterized/complex forms like ``NUMERIC(10, 2)`` or ``ARRAY<INT64>`` collapse to
    their head token before lookup, so ``NUMERIC(...)`` maps and ``ARRAY<...>`` does not.
    """
    head = re.split(r"[(<]", bq_type.strip(), maxsplit=1)[0].strip().upper()
    return _PG_FROM_BQ.get(head)


def sa_type_for(pg_ddl: str) -> satypes.TypeEngine[Any]:
    """SQLAlchemy type for a Postgres DDL type string (mirrors fact_table/app_master maps)."""
    pg = pg_ddl.strip().upper()
    if pg == "DATE":
        return satypes.Date()
    if pg == "TEXT":
        return satypes.Text()
    if pg == "BIGINT":
        return satypes.BigInteger()
    if pg == "BOOLEAN":
        return satypes.Boolean()
    if pg == "DOUBLE PRECISION":
        return satypes.Float()
    if pg == "TIMESTAMPTZ":
        return satypes.DateTime(timezone=True)
    match = _NUMERIC_RE.fullmatch(pg)
    if match:
        return satypes.Numeric(int(match.group(1)), int(match.group(2)))
    # Unknown/legacy type from a dynamic_columns row — serve it as text rather than crash.
    return satypes.Text()


def attach_columns(table: Table, cols: list[tuple[str, str]]) -> None:
    """Attach ``(name, pg_ddl)`` columns to an in-memory Table if not already present, so a
    freshly-reconciled column is queryable/serializable without a process restart."""
    existing = set(table.c.keys())
    for name, pg_ddl in cols:
        if name not in existing:
            table.append_column(Column(name, sa_type_for(pg_ddl)))


async def _physical_columns(session: AsyncSession, pg_table: str) -> set[str]:
    """The column names that physically exist in the Postgres serving table right now."""
    rows = await session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": pg_table},
    )
    return {r[0] for r in rows}


async def load_active_dynamic(session: AsyncSession, table_kind: str) -> list[DynamicColumn]:
    """All active dynamic columns tracked for a serving table (fact | app_master)."""
    stmt = (
        select(DynamicColumn)
        .where(DynamicColumn.table_kind == table_kind, DynamicColumn.active.is_(True))
        .order_by(DynamicColumn.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def reconcile(
    session: AsyncSession,
    settings: Settings,
    *,
    table_kind: str,
    pg_table: str,
    bq_table_id: str,
    gcp_project: str,
    static_types: dict[str, str],
    table_obj: Table,
    added_by: Any = None,
    bq_aliases: dict[str, str] | None = None,
) -> SchemaSyncResult:
    """Reconcile ``pg_table`` to the live BigQuery schema. Additive + non-destructive.

    ``static_types`` maps every static registry column name to its Postgres DDL type.
    ``table_obj`` is the in-memory Table the newly-added columns are attached to so they
    serve immediately. Never drops a column; vanished columns are flagged, not removed.
    """
    if not integration_service._bq_key_present(settings):
        return SchemaSyncResult(
            configured=False,
            message="No BigQuery reader key mounted — set BQ_CREDENTIALS_PATH and mount the key.",
        )

    actual, error = await anyio.to_thread.run_sync(
        integration_service._run_schema_diff, settings.bq_credentials_path, gcp_project, bq_table_id
    )
    if actual is None:
        return SchemaSyncResult(configured=True, ok=False, message=error or "Schema read failed.")

    static_names = set(static_types)
    # Case-fold BigQuery names to our lowercase identifier convention for comparison.
    bq_by_lower: dict[str, str] = {name.lower(): dtype for name, dtype in actual.items()}
    bq_lower = set(bq_by_lower)

    # Map a (lowercased) BigQuery column to the static registry column it satisfies — via an
    # explicit bq_name alias (e.g. "net revenue share" → "net_revenue_share"), else itself when
    # it already IS a static name. This lets a BigQuery column whose real name differs from our
    # sanitized column (spaces / caps) be recognised as the KNOWN static column, not treated as a
    # new/"unsafe-name" one — which was flagging net_revenue_share as missing + skipping the BQ
    # column every reconcile.
    aliases = {k.lower(): v for k, v in (bq_aliases or {}).items()}

    def _static_for(lname: str) -> str | None:
        if lname in aliases:
            return aliases[lname]
        return lname if lname in static_names else None

    present_static = {s for lname in bq_lower if (s := _static_for(lname)) is not None}

    tracked = {c.name: c for c in await load_active_dynamic_all(session, table_kind)}
    physical = await _physical_columns(session, pg_table)

    added: list[SchemaSyncColumn] = []
    reactivated: list[str] = []
    deactivated: list[str] = []
    healed_static: list[str] = []
    missing_in_bq: list[str] = []
    unsupported: list[SchemaSyncColumn] = []
    to_attach: list[tuple[str, str]] = []

    # 1) Heal registry↔DB drift: ensure every static registry column physically exists.
    for name in static_names:
        if name not in physical:
            pg_ddl = static_types[name]
            await session.execute(
                text(f'ALTER TABLE {pg_table} ADD COLUMN IF NOT EXISTS "{name}" {pg_ddl}')
            )
            healed_static.append(name)

    # 2) Static columns the BigQuery source no longer exposes — flag only (keep the column).
    #    Present if a BQ column maps to it directly OR via a bq_name alias.
    missing_in_bq = sorted(n for n in static_names if n not in present_static)

    # 3) BigQuery columns not covered by the static registry (directly or by alias) -> dynamic.
    for lname in sorted(bq_lower):
        if _static_for(lname) is not None:
            continue  # a known static column (possibly under a spaced/cased BigQuery name)
        bq_type = bq_by_lower[lname]
        existing = tracked.get(lname)
        if not _IDENT_RE.match(lname):
            unsupported.append(SchemaSyncColumn(name=lname, type=bq_type, reason="unsafe name"))
            continue
        mapped = map_bq_type(bq_type)
        if mapped is None:
            unsupported.append(
                SchemaSyncColumn(name=lname, type=bq_type, reason="unsupported type")
            )
            continue

        if lname not in physical:
            await session.execute(
                text(f'ALTER TABLE {pg_table} ADD COLUMN IF NOT EXISTS "{lname}" {mapped}')
            )
        if existing is None:
            session.add(
                DynamicColumn(
                    table_kind=table_kind,
                    name=lname,
                    pg_type=mapped,
                    bq_type=bq_type,
                    active=True,
                    added_by=added_by,
                )
            )
            added.append(SchemaSyncColumn(name=lname, type=mapped))
        elif not existing.active:
            existing.active = True
            existing.bq_type = bq_type
            reactivated.append(lname)
        to_attach.append((lname, mapped))

    # 4) Previously-adopted dynamic columns now gone from BigQuery -> flag (keep data).
    #    ALSO deactivate any dynamic column that has since been PROMOTED into the static
    #    registry (e.g. apple_account): leaving it active makes the sync's column list carry
    #    the name twice ("DuplicateColumn … specified more than once" → failed sync daily).
    #    The static column serves the data from here on; nothing is dropped.
    for name, col in tracked.items():
        # Only rows that are CURRENTLY active can be "newly deactivated" — an already-inactive
        # row must not be re-reported on every reconcile (it spammed the admin notification and
        # made the "Already in sync" state unreachable once any column had ever vanished).
        if col.active and (name in static_names or name not in bq_lower):
            col.active = False
            deactivated.append(name)

    await session.commit()
    attach_columns(table_obj, to_attach)

    return SchemaSyncResult(
        configured=True,
        ok=True,
        added=added,
        reactivated=reactivated,
        deactivated=deactivated,
        healed_static=healed_static,
        missing_in_bigquery=missing_in_bq,
        unsupported_types=unsupported,
    )


async def load_active_dynamic_all(session: AsyncSession, table_kind: str) -> list[DynamicColumn]:
    """All dynamic rows for a table_kind (active AND inactive) — the reconcile needs the
    inactive ones to detect reactivation."""
    stmt = (
        select(DynamicColumn)
        .where(DynamicColumn.table_kind == table_kind)
        .order_by(DynamicColumn.id)
    )
    return list((await session.execute(stmt)).scalars().all())
