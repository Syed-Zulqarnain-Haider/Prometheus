"""SQLAlchemy ORM models — a faithful mirror of ``sql/postgres/001_init.sql``.

The sync-managed ``fact_daily_performance`` table (002, generated from the
metric registry) is intentionally NOT modeled here; it is owned by the sync job.

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogenerate and ``create_all`` see the full schema.
"""

from __future__ import annotations

from app.models.access import AccessRequest
from app.models.base import Base
from app.models.dim import DimApp
from app.models.identity import Role, User, UserRole
from app.models.layouts import DashboardLayout
from app.models.operations import AuditLog, SyncRun
from app.models.rbac import RoleCapability, RoleMetricPermission, UserScope
from app.models.reports import ReportShare, SavedReport, SavedView
from app.models.settings import AppSetting
from app.models.targets import RevenueTarget

__all__ = [
    "Base",
    "AccessRequest",
    "DimApp",
    "User",
    "Role",
    "UserRole",
    "RoleMetricPermission",
    "RoleCapability",
    "UserScope",
    "DashboardLayout",
    "AppSetting",
    "SavedView",
    "SavedReport",
    "ReportShare",
    "RevenueTarget",
    "AuditLog",
    "SyncRun",
]
