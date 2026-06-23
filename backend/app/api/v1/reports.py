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
from sqlalchemy import and_, select

from app.api.deps import CurrentUser, DbSession, require_capability
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.models import ReportShare, SavedReport, User
from app.schemas.auth import UserContext
from app.schemas.reports import (
    ReportRunResult,
    SavedReportCreate,
    SavedReportOut,
    ShareCreate,
    ShareOut,
)
from app.services import reports_service
from app.services.audit import AuditDep
from app.services.query_builder import QueryBuilder

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(enforce_rate_limit)])

ADMIN_CAPABILITY = "admin_panel"

# Capability-gated caller contexts (Annotated to avoid B008 default-call lint).
AdminUser = Annotated[UserContext, Depends(require_capability(ADMIN_CAPABILITY))]
ShareUser = Annotated[UserContext, Depends(require_capability("share_report"))]


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
    report = await db.scalar(
        select(SavedReport).where(
            and_(SavedReport.id == report_id, SavedReport.user_id == context.user_id)
        )
    )
    if report is None:
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
        detail={"name": report.name, "group_by": report.group_by},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _report_out(report, is_owner=True)


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
