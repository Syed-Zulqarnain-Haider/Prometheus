"""Export route: CSV / XLSX of a report or ad-hoc breakdown.

Exports are capability-gated (``export``), rate-limited (10/min), and ALWAYS
re-run server-side through the caller's own QueryBuilder — the request body never
carries pre-computed rows, so a client cannot exfiltrate data outside its scope.
Every export is written to the audit log. Google Sheets export is recognized but
not enabled (it requires per-user OAuth that is not configured in v1).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse

from app.api.deps import DbSession, require_capability
from app.api.v1.reports import _load_visible_report
from app.core.http import client_ip
from app.core.rate_limit import enforce_export_rate_limit, enforce_rate_limit
from app.schemas.auth import UserContext
from app.schemas.metrics import MetricFilters
from app.schemas.reports import ExportRequest
from app.services import reports_service
from app.services.audit import AuditDep
from app.services.query_builder import QueryBuilder

router = APIRouter(
    prefix="/export",
    tags=["export"],
    dependencies=[Depends(enforce_rate_limit), Depends(enforce_export_rate_limit)],
)

_CSV_MEDIA = "text/csv"
_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Export capability-gated caller context (Annotated to avoid B008 default-call lint).
ExportUser = Annotated[UserContext, Depends(require_capability("export"))]


async def _resolve_spec(
    body: ExportRequest, context: UserContext, db: DbSession
) -> tuple[MetricFilters, str, list[str], str]:
    """Return (filters, group_by, columns, source) for either a saved report or
    an ad-hoc breakdown, validated and bounded to what the caller may see."""
    if body.report_id is not None:
        report, _ = await _load_visible_report(db, body.report_id, context)
        filters_dict = report.filters
        group_by = report.group_by
        columns = report.columns if isinstance(report.columns, list) else list(report.columns)
        source = f"report:{report.id}"
    else:
        if body.filters is None or body.group_by is None or not body.columns:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Provide a report_id, or filters + group_by + columns",
            )
        filters_dict = body.filters
        group_by = body.group_by
        columns = body.columns
        source = "adhoc"

    try:
        filters = reports_service.metric_filters_from_dict(filters_dict)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return filters, group_by, columns, source


@router.post("")
async def export(
    body: ExportRequest,
    request: Request,
    db: DbSession,
    audit: AuditDep,
    context: ExportUser,
) -> Response:
    if body.format == "gsheet":
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "Google Sheets export requires per-user OAuth configuration (not enabled in v1).",
        )

    filters, group_by, columns, source = await _resolve_spec(body, context, db)
    qb = QueryBuilder(context)
    result = await reports_service.run_report(db, qb, filters, group_by, columns)

    detail: dict[str, Any] = {
        "format": body.format,
        "source": source,
        "group_by": result["group_by"],
        "columns": result["columns"],
        "row_count": len(result["rows"]),
    }
    await audit.log_export(
        user_id=context.user_id,
        resource=source,
        detail=detail,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    if body.format == "csv":
        payload = reports_service.build_csv(result)
        return StreamingResponse(
            iter([payload]),
            media_type=_CSV_MEDIA,
            headers={"Content-Disposition": 'attachment; filename="report.csv"'},
        )

    payload = reports_service.build_xlsx(result)
    return Response(
        content=payload,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="report.xlsx"'},
    )
