"""SQLAlchemy ORM models — a faithful mirror of ``sql/postgres/001_init.sql``.

The sync-managed ``fact_daily_performance`` table (002, generated from the
metric registry) is intentionally NOT modeled here; it is owned by the sync job.

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogenerate and ``create_all`` see the full schema.
"""

from __future__ import annotations

from app.models.base import Base
from app.models.dim import DimApp
from app.models.identity import Role, User, UserRole
from app.models.operations import AuditLog, SyncRun
from app.models.rbac import RoleCapability, RoleMetricPermission, UserScope
from app.models.reports import ReportShare, SavedReport, SavedView

__all__ = [
    "Base",
    "DimApp",
    "User",
    "Role",
    "UserRole",
    "RoleMetricPermission",
    "RoleCapability",
    "UserScope",
    "SavedView",
    "SavedReport",
    "ReportShare",
    "AuditLog",
    "SyncRun",
]
