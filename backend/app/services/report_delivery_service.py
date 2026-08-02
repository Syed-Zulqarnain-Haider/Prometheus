"""Scheduled report delivery.

Emails a saved report to its owner on a cadence. RBAC-safe by construction:

  * a schedule ALWAYS runs under its OWNER's resolved RBAC context (their scope + permitted
    metrics) — the report is re-executed server-side through that context's QueryBuilder, and
  * it is delivered ONLY to the owner's own email.

So a schedule can never hand anyone data they couldn't already see. Each delivery rolls the
report's date window forward (preserving its span) so the numbers are fresh. Multi-instance
safe: a schedule is atomically CLAIMED for the day (conditional UPDATE of ``last_run_on``)
before it is sent, so exactly one instance delivers it.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import ReportSchedule, SavedReport, User
from app.schemas.auth import UserContext
from app.services import email_service, reports_service
from app.services.auth import resolve_user_context
from app.services.email_service import Attachment
from app.services.query_builder import QueryBuilder

log = logging.getLogger("app.reports.delivery")

_XLSX_MIME = ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
_CSV_MIME = ("text", "csv")


def local_now(now_utc: datetime, tz_name: str) -> datetime:
    try:
        return now_utc.astimezone(ZoneInfo(tz_name))
    except Exception:  # noqa: BLE001 — a bad stored tz falls back to UTC
        return now_utc.astimezone(UTC)


def is_due(schedule: ReportSchedule, now_utc: datetime) -> bool:
    """True when the schedule should fire in the current minute-tick and hasn't run today."""
    if not schedule.enabled:
        return False
    local = local_now(now_utc, schedule.timezone)
    if local.hour != schedule.hour:
        return False
    if schedule.last_run_on is not None and schedule.last_run_on >= local.date():
        return False
    if schedule.cadence == "weekly":
        return local.weekday() == schedule.day_of_week
    if schedule.cadence == "monthly":
        return local.day == schedule.day_of_month
    return True  # daily


def _rolled_filters(filters: dict[str, Any], local_today: date) -> dict[str, Any]:
    """Roll the stored window forward to end today, preserving its span — so a scheduled
    report always carries fresh numbers rather than the static dates it was saved with."""
    out = dict(filters)
    try:
        df = date.fromisoformat(str(filters["date_from"]))
        dt = date.fromisoformat(str(filters["date_to"]))
        span = max(0, (dt - df).days)
        out["date_to"] = local_today.isoformat()
        out["date_from"] = (local_today - timedelta(days=span)).isoformat()
    except (KeyError, ValueError):
        pass  # malformed stored filters — leave as-is; run_report validates them
    return out


def _safe_stem(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return stem or "report"


async def build_and_email(
    db: AsyncSession,
    settings: Settings,
    context: UserContext,
    report: SavedReport,
    *,
    fmt: str,
    local_today: date,
) -> bool:
    """Run ``report`` under ``context``'s RBAC and email it (as ``fmt``) to the context's own
    email. Returns True if the mail was accepted. Shared by the scheduler and 'send now'."""
    qb = QueryBuilder(context)
    filters = reports_service.metric_filters_from_dict(
        _rolled_filters(report.filters, local_today)
    )
    result = await reports_service.run_report(db, qb, filters, report.group_by, report.columns)

    if fmt == "csv":
        content = reports_service.build_csv(result)
        maintype, subtype = _CSV_MIME
    else:
        content = reports_service.build_xlsx(result)
        maintype, subtype = _XLSX_MIME
    filename = f"{_safe_stem(report.name)}_{local_today.isoformat()}.{fmt}"

    body = (
        f"Your scheduled report \"{report.name}\" is attached "
        f"({filters.date_from} to {filters.date_to}).\n\n"
        "It reflects only the data you have access to. You are receiving this because you "
        "scheduled it in Prometheus; remove the schedule there to stop these emails."
    )
    attachment = Attachment(
        filename=filename, content=content, maintype=maintype, subtype=subtype
    )
    return await email_service.send_email(
        settings,
        [context.email],
        f"Scheduled report: {report.name}",
        body,
        attachments=[attachment],
    )


async def _claim(
    sessionmaker: async_sessionmaker[Any], schedule_id: Any, local_today: date
) -> bool:
    """Atomically mark the schedule as run-today; returns True only for the winning instance."""
    async with sessionmaker() as db:
        result = await db.execute(
            update(ReportSchedule)
            .where(
                ReportSchedule.id == schedule_id,
                (ReportSchedule.last_run_on.is_(None)) | (ReportSchedule.last_run_on < local_today),
            )
            .values(last_run_on=local_today)
            .returning(ReportSchedule.id)
        )
        claimed = result.first() is not None
        await db.commit()
        return claimed


async def _deliver_claimed(
    sessionmaker: async_sessionmaker[Any], settings: Settings, schedule_id: Any, local_today: date
) -> None:
    async with sessionmaker() as db:
        schedule = await db.get(ReportSchedule, schedule_id)
        if schedule is None:
            return
        user = await db.get(User, schedule.user_id)
        if user is None or not user.is_active:
            return
        context = await resolve_user_context(db, user.firebase_uid)
        if context is None or not context.is_active:
            return
        if context.access_expires_at is not None and context.access_expires_at <= datetime.now(UTC):
            return  # expired access → stop delivering
        report = await db.scalar(
            select(SavedReport).where(
                SavedReport.id == schedule.report_id, SavedReport.user_id == schedule.user_id
            )
        )
        if report is None:
            return  # report deleted / no longer owned
        await build_and_email(
            db, settings, context, report, fmt=schedule.fmt, local_today=local_today
        )


async def evaluate_due(
    sessionmaker: async_sessionmaker[Any], settings: Settings, now_utc: datetime
) -> int:
    """Claim + deliver every due schedule. Each is isolated and best-effort; returns the count
    delivered. Called once per scheduler tick — the per-schedule hour/date guards keep it cheap."""
    async with sessionmaker() as db:
        schedules = list(
            await db.scalars(select(ReportSchedule).where(ReportSchedule.enabled.is_(True)))
        )
    delivered = 0
    for schedule in schedules:
        if not is_due(schedule, now_utc):
            continue
        today = local_now(now_utc, schedule.timezone).date()
        try:
            if not await _claim(sessionmaker, schedule.id, today):
                continue  # another instance took it
            await _deliver_claimed(sessionmaker, settings, schedule.id, today)
            delivered += 1
        except Exception:  # noqa: BLE001 — one bad schedule must never break the loop
            log.exception("scheduled report delivery failed (schedule=%s)", schedule.id)
    return delivered
