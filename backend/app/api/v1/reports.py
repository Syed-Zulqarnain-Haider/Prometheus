"""Saved reports + admin-approval sharing.

A report is a named, RBAC-scoped breakdown spec (filters + permitted metric
columns + group-by). It is owned by its author; other users can only see it if
the author shared it AND an admin approved the share. Crucially, running a shared
report always re-derives the rows through the *recipient's* own QueryBuilder, so a
share can never leak data the recipient couldn't otherwise query.

Sharing lifecycle (CLAUDE.md RBAC):
  * non-admin share  -> status='pending'  (any admin approves/rejects)
  * admin self-share -> status='approved' (skips the queue)
  * approve / reject  -> admin_panel capability only
  * revoke            -> the sharer or any admin
Every share / approve / reject / revoke is written to the audit log.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import and_, func, select

from app.api.deps import CurrentUser, DbSession, require_capability
from app.core.config import get_settings
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.models import ReportSchedule, ReportShare, SavedReport, User
from app.schemas.auth import UserContext
from app.schemas.report_schedule import ReportScheduleCreate, ReportScheduleOut
from app.schemas.reports import (
    EditDecision,
    ReportRunResult,
    SavedReportCreate,
    SavedReportOut,
    ShareCreate,
    ShareOut,
)
from app.services import notification_service, report_delivery_service, reports_service
from app.services.audit import AuditDep
from app.services.query_builder import QueryBuilder

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(enforce_rate_limit)])

ADMIN_CAPABILITY = "admin_panel"

# Capability-gated caller contexts (Annotated to avoid B008 default-call lint).
AdminUser = Annotated[UserContext, Depends(require_capability(ADMIN_CAPABILITY))]
ShareUser = Annotated[UserContext, Depends(require_capability("share_report"))]
# Scheduling a report emails a CSV/XLSX export, so it is an EXPORT — gated on the same
# capability (a viewer, who has no export, must not be able to receive files by email).
ExportUser = Annotated[UserContext, Depends(require_capability("export"))]


def _is_admin(context: UserContext) -> bool:
    return ADMIN_CAPABILITY in context.capabilities


def _report_out(report: SavedReport, *, is_owner: bool) -> SavedReportOut:
    columns = report.columns if isinstance(report.columns, list) else list(report.columns)
    return SavedReportOut(
        id=report.id,
        name=report.name,
        description=report.description,
        filters=report.filters,
        columns=columns,
        group_by=report.group_by,
        sort=report.sort,
        owner_id=report.user_id,
        is_owner=is_owner,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def _share_out(share: ReportShare, report_name: str | None = None) -> ShareOut:
    return ShareOut(
        id=share.id,
        report_id=share.report_id,
        report_name=report_name,
        shared_by=share.shared_by,
        shared_with=share.shared_with,
        status=share.status,
        edit_status=share.edit_status,
        created_at=share.created_at,
    )


async def _load_visible_report(
    db: DbSession, report_id: uuid.UUID, context: UserContext
) -> tuple[SavedReport, bool]:
    """Return (report, is_owner). Visible to the owner or an approved recipient.

    Anything else is reported as 404 (indistinguishable from nonexistent), never
    403 — an out-of-scope resource must not reveal its own existence.
    """
    report = await db.scalar(select(SavedReport).where(SavedReport.id == report_id))
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    if report.user_id == context.user_id:
        return report, True
    approved = await db.scalar(
        select(ReportShare.id).where(
            and_(
                ReportShare.report_id == report_id,
                ReportShare.shared_with == context.user_id,
                ReportShare.status == "approved",
            )
        )
    )
    if approved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return report, False


# ── Saved reports CRUD ───────────────────────────────────────────────────────
@router.get("", response_model=list[SavedReportOut])
async def list_reports(context: CurrentUser, db: DbSession) -> list[SavedReportOut]:
    rows = (
        (
            await db.execute(
                select(SavedReport)
                .where(SavedReport.user_id == context.user_id)
                .order_by(SavedReport.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_report_out(r, is_owner=True) for r in rows]


@router.post("", response_model=SavedReportOut, status_code=status.HTTP_201_CREATED)
async def create_report(
    body: SavedReportCreate,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> SavedReportOut:
    qb = QueryBuilder(context)
    try:
        reports_service.validate_columns(body.columns, qb.permitted_measures)
        reports_service.metric_filters_from_dict(body.filters)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    report = SavedReport(
        user_id=context.user_id,
        name=body.name,
        description=body.description,
        filters=body.filters,
        columns=body.columns,
        group_by=body.group_by,
        sort=body.sort,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    await audit.write(
        user_id=context.user_id,
        action="saved_report_create",
        resource=str(report.id),
        detail={"name": report.name, "group_by": report.group_by},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _report_out(report, is_owner=True)


@router.get("/shared-with-me", response_model=list[SavedReportOut])
async def shared_with_me(context: CurrentUser, db: DbSession) -> list[SavedReportOut]:
    """Reports an admin approved for me to see (run through my own RBAC)."""
    rows = (
        (
            await db.execute(
                select(SavedReport)
                .join(ReportShare, ReportShare.report_id == SavedReport.id)
                .where(
                    and_(
                        ReportShare.shared_with == context.user_id,
                        ReportShare.status == "approved",
                    )
                )
                .order_by(SavedReport.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_report_out(r, is_owner=False) for r in rows]


@router.get("/shares/pending", response_model=list[ShareOut])
async def pending_shares(
    db: DbSession,
    _: AdminUser,
) -> list[ShareOut]:
    """Admin queue: every share awaiting approval."""
    rows = (
        await db.execute(
            select(ReportShare, SavedReport.name)
            .join(SavedReport, SavedReport.id == ReportShare.report_id)
            .where(ReportShare.status == "pending")
            .order_by(ReportShare.created_at.asc())
        )
    ).all()
    return [_share_out(share, name) for share, name in rows]


@router.get("/{report_id}", response_model=SavedReportOut)
async def get_report(report_id: uuid.UUID, context: CurrentUser, db: DbSession) -> SavedReportOut:
    report, is_owner = await _load_visible_report(db, report_id, context)
    return _report_out(report, is_owner=is_owner)


@router.put("/{report_id}", response_model=SavedReportOut)
async def update_report(
    report_id: uuid.UUID,
    body: SavedReportCreate,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> SavedReportOut:
    report = await db.scalar(select(SavedReport).where(SavedReport.id == report_id))
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    is_owner = report.user_id == context.user_id
    if not is_owner:
        # A non-owner may edit ONLY with a granted edit request on an approved share.
        granted = await db.scalar(
            select(ReportShare.id).where(
                and_(
                    ReportShare.report_id == report_id,
                    ReportShare.shared_with == context.user_id,
                    ReportShare.status == "approved",
                    ReportShare.edit_status == "granted",
                )
            )
        )
        if granted is None:
            # No grant → indistinguishable 404 (never reveal the report's existence/edit-lock).
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")

    qb = QueryBuilder(context)
    try:
        reports_service.validate_columns(body.columns, qb.permitted_measures)
        reports_service.metric_filters_from_dict(body.filters)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    report.name = body.name
    report.description = body.description
    report.filters = body.filters
    report.columns = body.columns
    report.group_by = body.group_by
    report.sort = body.sort
    report.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(report)
    await audit.write(
        user_id=context.user_id,
        action="saved_report_update",
        resource=str(report_id),
        detail={"name": report.name, "group_by": report.group_by, "by_owner": is_owner},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _report_out(report, is_owner=is_owner)


@router.post("/{report_id}/request-edit", response_model=ShareOut)
async def request_edit(
    report_id: uuid.UUID, request: Request, context: CurrentUser, db: DbSession, audit: AuditDep
) -> ShareOut:
    """A recipient of a shared report requests edit access. Routes the request to the report
    OWNER and all admins (deep-linked). No-op-safe if already granted."""
    share = await db.scalar(
        select(ReportShare).where(
            and_(
                ReportShare.report_id == report_id,
                ReportShare.shared_with == context.user_id,
                ReportShare.status == "approved",
            )
        )
    )
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    report = await db.scalar(select(SavedReport).where(SavedReport.id == report_id))
    if share.edit_status != "granted":
        share.edit_status = "requested"
        await db.commit()
    await audit.write(
        user_id=context.user_id,
        action="report_edit_requested",
        resource=str(report_id),
        detail={"share_id": str(share.id)},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    name = report.name if report else "a report"
    kwargs = {
        "type": "report_edit_request",
        "title": "Edit access requested",
        "body": f"{context.email} wants to edit “{name}”.",
        "severity": "warning",
        "link": "/reports?tab=shares",
        "actor_id": context.user_id,
        "resource": str(report_id),
    }
    if report is not None:
        await notification_service.notify_user(report.user_id, **kwargs)
    await notification_service.notify_admins(**kwargs)
    return _share_out(share, name if report else None)


@router.post("/shares/{share_id}/edit-decision", response_model=ShareOut)
async def decide_edit(
    share_id: uuid.UUID,
    body: EditDecision,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> ShareOut:
    """Grant or deny a recipient's edit request. Allowed for the report OWNER or any admin."""
    share = await db.scalar(select(ReportShare).where(ReportShare.id == share_id))
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share not found")
    report = await db.scalar(select(SavedReport).where(SavedReport.id == share.report_id))
    is_admin = ADMIN_CAPABILITY in context.capabilities
    if not (is_admin or (report is not None and report.user_id == context.user_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share not found")

    share.edit_status = "granted" if body.grant else "none"
    await db.commit()
    await db.refresh(share)
    await audit.write(
        user_id=context.user_id,
        action="report_edit_" + ("granted" if body.grant else "denied"),
        resource=str(share.report_id),
        detail={"share_id": str(share.id), "shared_with": str(share.shared_with)},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await notification_service.notify_user(
        share.shared_with,
        type="report_edit_decision",
        title="Edit access " + ("granted" if body.grant else "denied"),
        severity="info" if body.grant else "warning",
        link="/reports",
        actor_id=context.user_id,
        resource=str(share.report_id),
    )
    return _share_out(share, report.name if report else None)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: uuid.UUID, request: Request, context: CurrentUser, db: DbSession, audit: AuditDep
) -> Response:
    report = await db.scalar(
        select(SavedReport).where(
            and_(SavedReport.id == report_id, SavedReport.user_id == context.user_id)
        )
    )
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    await db.delete(report)
    await db.commit()
    await audit.write(
        user_id=context.user_id,
        action="saved_report_delete",
        resource=str(report_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{report_id}/run", response_model=ReportRunResult)
async def run_report(report_id: uuid.UUID, context: CurrentUser, db: DbSession) -> ReportRunResult:
    """Execute the report under the CALLER's RBAC (never the author's)."""
    report, _ = await _load_visible_report(db, report_id, context)
    qb = QueryBuilder(context)
    try:
        filters = reports_service.metric_filters_from_dict(report.filters)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    columns = report.columns if isinstance(report.columns, list) else list(report.columns)
    result = await reports_service.run_report(db, qb, filters, report.group_by, columns)
    return ReportRunResult(**result)


# ── Scheduled delivery (owner-only; always runs as + delivers to the owner) ──
MAX_SCHEDULES_PER_REPORT = 5


def _schedule_out(schedule: ReportSchedule) -> ReportScheduleOut:
    return ReportScheduleOut(
        id=schedule.id,
        report_id=schedule.report_id,
        cadence=schedule.cadence,
        hour=schedule.hour,
        day_of_week=schedule.day_of_week,
        day_of_month=schedule.day_of_month,
        fmt=schedule.fmt,
        timezone=schedule.timezone,
        enabled=schedule.enabled,
        last_run_on=schedule.last_run_on,
        created_at=schedule.created_at,
    )


async def _owned_report(
    db: DbSession, report_id: uuid.UUID, context: UserContext, *, lock: bool = False
) -> SavedReport:
    """A report the CALLER owns — scheduling is owner-only (a schedule runs as its owner).
    404 (not 403) for anything else, so it never reveals another user's report exists.
    ``lock=True`` takes a row lock so concurrent schedule creates serialize (accurate cap)."""
    stmt = select(SavedReport).where(
        and_(SavedReport.id == report_id, SavedReport.user_id == context.user_id)
    )
    if lock:
        stmt = stmt.with_for_update()
    report = await db.scalar(stmt)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return report


@router.get("/{report_id}/schedules", response_model=list[ReportScheduleOut])
async def list_schedules(
    report_id: uuid.UUID, context: CurrentUser, db: DbSession
) -> list[ReportScheduleOut]:
    await _owned_report(db, report_id, context)
    rows = await db.scalars(
        select(ReportSchedule)
        .where(
            and_(
                ReportSchedule.report_id == report_id,
                ReportSchedule.user_id == context.user_id,
            )
        )
        .order_by(ReportSchedule.created_at)
    )
    return [_schedule_out(s) for s in rows]


@router.post(
    "/{report_id}/schedules",
    response_model=ReportScheduleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_schedule(
    report_id: uuid.UUID,
    body: ReportScheduleCreate,
    request: Request,
    context: ExportUser,
    db: DbSession,
    audit: AuditDep,
) -> ReportScheduleOut:
    # Lock the report row so two concurrent creates can't both pass the cap check (which would
    # let a report exceed MAX_SCHEDULES and amplify emails).
    await _owned_report(db, report_id, context, lock=True)
    existing = await db.scalar(
        select(func.count())
        .select_from(ReportSchedule)
        .where(
            and_(
                ReportSchedule.report_id == report_id,
                ReportSchedule.user_id == context.user_id,
            )
        )
    )
    if (existing or 0) >= MAX_SCHEDULES_PER_REPORT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"A report can have at most {MAX_SCHEDULES_PER_REPORT} schedules.",
        )
    schedule = ReportSchedule(
        report_id=report_id,
        user_id=context.user_id,
        cadence=body.cadence,
        hour=body.hour,
        day_of_week=body.day_of_week,
        day_of_month=body.day_of_month,
        fmt=body.fmt,
        timezone=body.timezone,
        enabled=body.enabled,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    await audit.write(
        user_id=context.user_id,
        action="report_schedule_create",
        resource=str(report_id),
        detail={"cadence": body.cadence, "fmt": body.fmt},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _schedule_out(schedule)


async def _owned_schedule(
    db: DbSession, schedule_id: uuid.UUID, context: UserContext
) -> ReportSchedule:
    schedule = await db.scalar(
        select(ReportSchedule).where(
            and_(
                ReportSchedule.id == schedule_id,
                ReportSchedule.user_id == context.user_id,
            )
        )
    )
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    return schedule


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: uuid.UUID, request: Request, context: CurrentUser, db: DbSession, audit: AuditDep
) -> Response:
    schedule = await _owned_schedule(db, schedule_id, context)
    await db.delete(schedule)
    await db.commit()
    await audit.write(
        user_id=context.user_id,
        action="report_schedule_delete",
        resource=str(schedule_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/schedules/{schedule_id}/run-now")
async def run_schedule_now(
    schedule_id: uuid.UUID, request: Request, context: ExportUser, db: DbSession, audit: AuditDep
) -> dict[str, bool]:
    """Send this schedule's report to the owner now (a test send). Runs under the caller's own
    RBAC and emails only the caller — so it can never deliver another user's data."""
    schedule = await _owned_schedule(db, schedule_id, context)
    report = await _owned_report(db, schedule.report_id, context)
    today = report_delivery_service.local_now(datetime.now(UTC), schedule.timezone).date()
    try:
        sent = await report_delivery_service.build_and_email(
            db, get_settings(), context, report, fmt=schedule.fmt, local_today=today
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    # A delivery IS an export — log it as one (re-runs through the caller's RBAC server-side).
    await audit.log_export(
        user_id=context.user_id,
        resource=str(report.id),
        detail={"via": "report_schedule_run_now", "schedule_id": str(schedule_id), "sent": sent},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return {"sent": sent}


# ── Sharing ──────────────────────────────────────────────────────────────────
@router.post(
    "/{report_id}/share",
    response_model=ShareOut,
    status_code=status.HTTP_201_CREATED,
)
async def share_report(
    report_id: uuid.UUID,
    body: ShareCreate,
    request: Request,
    db: DbSession,
    audit: AuditDep,
    context: ShareUser,
) -> ShareOut:
    report = await db.scalar(
        select(SavedReport).where(
            and_(SavedReport.id == report_id, SavedReport.user_id == context.user_id)
        )
    )
    if report is None:
        # Only the owner can share; for non-owners the report is simply "not found".
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    if body.shared_with == context.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot share a report with yourself")

    recipient = await db.scalar(
        select(User).where(and_(User.id == body.shared_with, User.is_active.is_(True)))
    )
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipient not found")

    auto_approve = _is_admin(context)
    new_status = "approved" if auto_approve else "pending"
    approved_by = context.user_id if auto_approve else None
    approved_at = datetime.now(UTC) if auto_approve else None

    # One share row per (report, recipient): re-sharing resets a prior decision.
    share = await db.scalar(
        select(ReportShare).where(
            and_(
                ReportShare.report_id == report_id,
                ReportShare.shared_with == body.shared_with,
            )
        )
    )
    if share is None:
        share = ReportShare(
            report_id=report_id,
            shared_by=context.user_id,
            shared_with=body.shared_with,
            status=new_status,
            approved_by=approved_by,
            approved_at=approved_at,
        )
        db.add(share)
    else:
        share.shared_by = context.user_id
        share.status = new_status
        share.approved_by = approved_by
        share.approved_at = approved_at
    await db.commit()
    await db.refresh(share)

    await audit.write(
        user_id=context.user_id,
        action="report_share",
        resource=str(report_id),
        detail={
            "share_id": str(share.id),
            "shared_with": str(body.shared_with),
            "status": new_status,
            "auto_approved": auto_approve,
        },
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    if new_status == "pending":
        # A non-admin share needs approval — route it up the hierarchy: every admin AND
        # every pod owner is notified, with a deep-link to the approvals view.
        _kwargs = {
            "type": "share_request",
            "title": "Report share awaiting approval",
            "body": f"{context.email} shared “{report.name}” — needs approval.",
            "severity": "warning",
            "link": "/reports?tab=shares",
            "actor_id": context.user_id,
            "resource": str(report_id),
        }
        await notification_service.notify_admins(**_kwargs)
        await notification_service.notify_role("pod_owner", **_kwargs)
    return _share_out(share, report.name)


async def _decide_share(
    share_id: uuid.UUID,
    new_status: str,
    context: UserContext,
    db: DbSession,
    audit: AuditDep,
    request: Request,
) -> ShareOut:
    share = await db.scalar(select(ReportShare).where(ReportShare.id == share_id))
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share not found")
    if share.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Share is already {share.status}")
    share.status = new_status
    share.approved_by = context.user_id
    share.approved_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(share)

    await audit.log_admin_action(
        user_id=context.user_id,
        action=f"report_share_{new_status}",
        resource=str(share.report_id),
        detail={"share_id": str(share.id), "shared_with": str(share.shared_with)},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    # Tell the person who requested the share how it was decided.
    await notification_service.notify_user(
        share.shared_by,
        type="share_decision",
        title=f"Your report share was {new_status}",
        severity="info" if new_status == "approved" else "warning",
        link="/reports",
        actor_id=context.user_id,
        resource=str(share.report_id),
    )
    return _share_out(share)


@router.post("/shares/{share_id}/approve", response_model=ShareOut)
async def approve_share(
    share_id: uuid.UUID,
    request: Request,
    db: DbSession,
    audit: AuditDep,
    context: AdminUser,
) -> ShareOut:
    return await _decide_share(share_id, "approved", context, db, audit, request)


@router.post("/shares/{share_id}/reject", response_model=ShareOut)
async def reject_share(
    share_id: uuid.UUID,
    request: Request,
    db: DbSession,
    audit: AuditDep,
    context: AdminUser,
) -> ShareOut:
    return await _decide_share(share_id, "rejected", context, db, audit, request)


@router.post("/shares/{share_id}/revoke", response_model=ShareOut)
async def revoke_share(
    share_id: uuid.UUID,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> ShareOut:
    """The sharer or any admin may revoke a share, cutting off recipient access."""
    share = await db.scalar(select(ReportShare).where(ReportShare.id == share_id))
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share not found")
    if share.shared_by != context.user_id and not _is_admin(context):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share not found")

    share.status = "revoked"
    share.approved_by = context.user_id
    share.approved_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(share)

    await audit.write(
        user_id=context.user_id,
        action="report_share_revoked",
        resource=str(share.report_id),
        detail={"share_id": str(share.id), "shared_with": str(share.shared_with)},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _share_out(share)
