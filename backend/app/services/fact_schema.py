"""Fact-table schema reconcile + the in-memory dynamic-registry refresh.

The admin "Match Database & BigQuery Schema" button (metrics side) reconciles the Postgres
``fact_daily_performance`` table to the live BigQuery view, adopting any new columns as
``unclassified`` (admin-only) dynamic columns. After a reconcile — and periodically on the
serving path — the in-memory effective registry is refreshed so RBAC response models and the
query builder pick the new columns up without a redeploy.

Multi-worker note: the refresh is TTL-guarded and runs on the metrics request path, so every
worker converges within ``_TTL`` seconds of a reconcile without a restart.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.fact_table import FACT_TABLE
from app.core.metric_registry import REGISTRY, Col, Group, set_dynamic_columns
from app.models.dynamic_columns import FACT as _KIND_FACT
from app.schemas.integration import SchemaSyncResult
from app.services import schema_reconcile, settings_service
from app.services.response_models import build_response_model

log = logging.getLogger("app.fact_schema")

# Static fact column -> Postgres DDL type (the registry pg_type IS the DDL type here).
_FACT_STATIC_TYPES: dict[str, str] = {c.name: c.pg_type for c in REGISTRY}

# How long a worker may reuse its in-memory dynamic registry before re-reading from the DB.
_TTL_SECONDS = 60.0
_last_refresh: float = 0.0


async def refresh_dynamic_registry(session: AsyncSession, *, force: bool = False) -> None:
    """Load active dynamic fact columns from the DB into the in-memory effective registry,
    attach them to ``FACT_TABLE``, and clear the per-role response-model cache. TTL-guarded
    unless ``force`` (a reconcile forces an immediate refresh)."""
    global _last_refresh
    now = time.monotonic()
    if not force and (now - _last_refresh) < _TTL_SECONDS:
        return
    rows = await schema_reconcile.load_active_dynamic(session, _KIND_FACT)
    cols = [
        Col(name=r.name, bq_type=r.bq_type, pg_type=r.pg_type, group=Group.UNCLASSIFIED)
        for r in rows
    ]
    set_dynamic_columns(cols)
    schema_reconcile.attach_columns(FACT_TABLE, [(c.name, c.pg_type) for c in cols])
    # Response models are @cache'd by group set — a changed column set makes them stale.
    build_response_model.cache_clear()
    _last_refresh = now


async def reconcile(
    session: AsyncSession, settings: Settings, admin_id: object = None
) -> SchemaSyncResult:
    """Match ``fact_daily_performance`` to the live BigQuery view (additive, non-destructive),
    then refresh the in-memory registry so admins see the new columns immediately."""
    bq_view = str(await settings_service.get_value(session, "bq_view"))
    project = str(await settings_service.get_value(session, "gcp_project"))
    result = await schema_reconcile.reconcile(
        session,
        settings,
        table_kind=_KIND_FACT,
        pg_table="fact_daily_performance",
        bq_table_id=bq_view,
        gcp_project=project,
        static_types=_FACT_STATIC_TYPES,
        table_obj=FACT_TABLE,
        added_by=admin_id,
    )
    if result.ok:
        await refresh_dynamic_registry(session, force=True)
    return result
