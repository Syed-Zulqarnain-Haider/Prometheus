#!/usr/bin/env python3
"""Three backend fixes from the security audit.

1. app/api/v1/meta.py - /meta/targets no longer discloses revenue targets to roles
   without a revenue measure. pacing_service already enforces exactly this ("so a
   store-installs-only role never learns the org's revenue goal"), but the raw targets
   endpoint - which powers the same donut - handed the full figures to ANY authenticated
   user. A viewer (store_installs only) could read the org's revenue goal one endpoint
   over from where it was correctly hidden. The response keeps its shape (year, annual
   null, monthly empty), so the donut renders its "target not set" state rather than the
   frontend having to learn a 403.

2. app/services/reports_service.py - CSV/XLSX cells are neutralised against formula
   injection. Dimension labels (app_name from the stores, publisher/pod_owner/hou from
   App Master edits) land in cells verbatim; a value starting with = + - @ (or TAB/CR)
   is executed as a formula by Excel/Sheets when the export opens. Exports re-run under
   the caller's RBAC by design - the file itself should be equally safe to open. Values
   get the standard leading-apostrophe guard, which Excel treats as "text follows" and
   never displays in the formula bar's result.

3. app/core/http.py - client_ip takes the LAST X-Forwarded-For hop, not the first.
   The first entry is written by the CLIENT and is free text; the last is appended by
   our own nginx and is the only hop we can trust. With the old order any authenticated
   caller could forge the IP recorded in the append-only audit trail and shown in
   "recent devices" with one header. (Rate limiting keys on user_id, so throttling was
   never affected - this is about the audit trail telling the truth.)

Anchored: every anchor must appear EXACTLY once in its file or NOTHING is written -
all files validate before any is touched. Idempotent. Backend restart; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

META = Path("backend/app/api/v1/meta.py")
REPORTS = Path("backend/app/services/reports_service.py")
HTTP = Path("backend/app/core/http.py")

# ── 1. meta.py ────────────────────────────────────────────────────────────────
# Anchored on the CODE only, never the docstring: the deployed tree has had its em
# dashes replaced with plain hyphens, and a prose difference must not be able to abort
# a security fix.
META_ANCHOR = """    annual, monthly = await admin_service.targets_for_year(db, year)
    return TargetsResponse(year=year, annual=annual, monthly=monthly)
"""
META_NEW = """    # Only disclosed to callers permitted a revenue measure - the same rule
    # pacing_service applies, so a store-installs-only role never learns the org's
    # revenue goal here either. The shape is kept (annual null, monthly empty) so the
    # donut renders its "target not set" state instead of surfacing an error.
    if "total_revenue_usd" not in QueryBuilder(context).permitted_measures:
        return TargetsResponse(year=year, annual=None, monthly=[])
    annual, monthly = await admin_service.targets_for_year(db, year)
    return TargetsResponse(year=year, annual=annual, monthly=monthly)
"""

# ── 2. reports_service.py ─────────────────────────────────────────────────────
REPORTS_HELPER_ANCHOR = "def build_csv(result: dict[str, Any]) -> bytes:\n"
REPORTS_HELPER_ADD = '''def _formula_safe(value: Any) -> Any:
    """Neutralise spreadsheet formula injection in text cells.

    A cell beginning with = + - @ (or TAB/CR) is executed as a formula when the export
    opens in Excel or Sheets. Dimension labels here include admin-edited fields and
    store-sourced app names, so they are not trusted. The leading apostrophe is the
    spreadsheet convention for "literal text" and is not displayed. Numbers pass
    through untouched - only strings can carry a formula.
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\\t", "\\r"):
        return f"'{value}"
    return value


'''

REPORTS_CSV_ANCHOR = """    for row in result["rows"]:
        writer.writerow(row)
"""
REPORTS_CSV_NEW = """    for row in result["rows"]:
        writer.writerow({k: _formula_safe(v) for k, v in row.items()})
"""

REPORTS_XLSX_ANCHOR = """    for row in result["rows"]:
        sheet.append([row.get(f) for f in fields])
"""
REPORTS_XLSX_NEW = """    for row in result["rows"]:
        sheet.append([_formula_safe(row.get(f)) for f in fields])
"""

# ── 3. http.py ────────────────────────────────────────────────────────────────
HTTP_ANCHOR = '''def client_ip(request: Request) -> str | None:
    """Best-effort client IP, honoring a single X-Forwarded-For hop from the edge."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
'''
HTTP_NEW = '''def client_ip(request: Request) -> str | None:
    """Best-effort client IP: the LAST X-Forwarded-For hop, i.e. the one our own edge
    proxy appended. The first hop is written by the client and is free text - trusting
    it let any caller forge the IP recorded in the audit trail with one header."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else None
'''


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def require_once(path: Path, text: str, anchor: str) -> None:
    if text.count(anchor) != 1:
        first = anchor.splitlines()[0].strip()
        die(f"{path}: expected exactly one {first!r}, found {text.count(anchor)}")


def main() -> None:
    for path in (META, REPORTS, HTTP):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    meta = META.read_text()
    reports = REPORTS.read_text()
    http = HTTP.read_text()

    todo: dict[Path, str] = {}

    if "permitted_measures" in meta:
        print(f"{META}: already gated")
    else:
        require_once(META, meta, META_ANCHOR)
        if "QueryBuilder" not in meta:
            die(f"{META}: QueryBuilder is not imported - the file has changed shape")
        todo[META] = meta

    if "_formula_safe" in reports:
        print(f"{REPORTS}: already neutralised")
    else:
        for anchor in (REPORTS_HELPER_ANCHOR, REPORTS_CSV_ANCHOR, REPORTS_XLSX_ANCHOR):
            require_once(REPORTS, reports, anchor)
        todo[REPORTS] = reports

    if 'split(",")[-1]' in http:
        print(f"{HTTP}: already takes the trusted hop")
    else:
        require_once(HTTP, http, HTTP_ANCHOR)
        todo[HTTP] = http

    if not todo:
        print("already hardened - nothing to do")
        return

    if META in todo:
        text = todo[META].replace(META_ANCHOR, META_NEW, 1)
        # Best-effort: the docstring above still claims the endpoint is visible to any
        # authenticated user, which the gate has just made false. Wording differs
        # between trees, so a miss here is not worth aborting a security fix over.
        stale = "    Visible to any authenticated user; only admins can set them (``/admin/targets``).\n"
        fixed = (
            "    Only callers permitted a revenue measure see the figures; everyone else\n"
            "    gets the same shape with nothing in it. Only admins can SET them\n"
            "    (``/admin/targets``).\n"
        )
        if text.count(stale) == 1:
            text = text.replace(stale, fixed, 1)
        META.write_text(text)
        print(f"patched {META}: targets gated on revenue permission")

    if REPORTS in todo:
        text = todo[REPORTS]
        text = text.replace(REPORTS_HELPER_ANCHOR, REPORTS_HELPER_ADD + REPORTS_HELPER_ANCHOR, 1)
        text = text.replace(REPORTS_CSV_ANCHOR, REPORTS_CSV_NEW, 1)
        text = text.replace(REPORTS_XLSX_ANCHOR, REPORTS_XLSX_NEW, 1)
        REPORTS.write_text(text)
        print(f"patched {REPORTS}: exports formula-safe")

    if HTTP in todo:
        HTTP.write_text(todo[HTTP].replace(HTTP_ANCHOR, HTTP_NEW, 1))
        print(f"patched {HTTP}: audit IP takes the proxy-appended hop")


if __name__ == "__main__":
    main()
