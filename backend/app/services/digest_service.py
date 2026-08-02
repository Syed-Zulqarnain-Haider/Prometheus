"""Daily performance digest — an email summary of the latest complete day, sent to admins +
executives. Reuses the SMTP email service and reads Postgres only (never BigQuery). Off by
default (``digest_enabled``); best-effort, so a mail outage or empty table is a clean no-op.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.services import admin_service, email_service, notification_service, settings_service

log = logging.getLogger("digest")

_FACT = "fact_daily_performance"

# Fixed identifiers (module constants), no user input — safe despite the f-strings.
_TOTALS_SQL = text(  # noqa: S608
    f"SELECT date, "
    f"COALESCE(SUM(total_revenue_usd), 0) AS rev, "
    f"COALESCE(SUM(total_ua_spend_usd), 0) AS spend, "
    f"COALESCE(SUM(total_ad_revenue_usd), 0) AS ad, "
    f"COALESCE(SUM(total_iap_net_usd), 0) AS iap, "
    f"COALESCE(SUM(store_total_installs), 0) AS installs "
    f"FROM {_FACT} GROUP BY date ORDER BY date DESC LIMIT 2"
)
_TOP_APPS_SQL = text(  # noqa: S608
    f"SELECT COALESCE(app_name, canonical_key, 'unknown') AS name, "
    f"COALESCE(SUM(total_revenue_usd), 0) AS rev "
    f"FROM {_FACT} WHERE date = :d GROUP BY name ORDER BY rev DESC LIMIT 5"
)


def _pct(now: float, prev: float) -> str:
    if prev == 0:
        return "—"
    change = (now - prev) / prev * 100.0
    return f"{'+' if change >= 0 else ''}{change:.0f}%"


async def build_digest(db: AsyncSession) -> str | None:
    """Build the plain-text digest for the latest complete day, or None if there's no data."""
    rows = (await db.execute(_TOTALS_SQL)).all()
    if not rows:
        return None
    d = rows[0]
    prev = rows[1] if len(rows) >= 2 else None
    rev, spend = float(d.rev), float(d.spend)
    profit = rev - spend
    roas = rev / spend if spend > 0 else 0.0

    def delta(attr: str) -> str:
        return _pct(float(getattr(d, attr)), float(getattr(prev, attr))) if prev else "—"

    lines = [
        f"Prometheus daily digest — {d.date}",
        "",
        f"  Revenue:    ${rev:,.0f}  ({delta('rev')} vs prior day)",
        f"  UA spend:   ${spend:,.0f}  ({delta('spend')})",
        f"  Profit:     ${profit:,.0f}",
        f"  ROAS:       {roas:.2f}x",
        f"  Ad revenue: ${float(d.ad):,.0f}  ({delta('ad')})",
        f"  IAP (net):  ${float(d.iap):,.0f}  ({delta('iap')})",
        f"  Installs:   {int(d.installs):,}  ({delta('installs')})",
    ]

    top = (await db.execute(_TOP_APPS_SQL, {"d": d.date})).all()
    if top:
        lines += ["", "Top apps by revenue:"]
        lines += [f"  • {t.name}: ${float(t.rev):,.0f}" for t in top]
    return "\n".join(lines)


async def build_and_send(db: AsyncSession, settings: Settings) -> str | None:
    """Build + email the daily digest to admins (and post an in-app copy to admins/execs).
    No-op returning None when disabled or there's no data."""
    if not bool(await settings_service.get_value(db, "digest_enabled")):
        return None
    body = await build_digest(db)
    if body is None:
        return None

    subject = body.splitlines()[0]  # "Prometheus daily digest — <date>"
    emails = await admin_service.active_admin_emails(db)
    if emails:
        await email_service.send_email(settings, emails, subject=subject, body=body)
    # A lightweight in-app pointer too (execs who don't read email still see it).
    for role in ("admin", "executive"):
        await notification_service.notify_role(
            role,
            type="daily_digest",
            title="Daily performance digest",
            body=subject,
            severity="info",
            link="/overview",
        )
    return body


# Convenience for the manual endpoint response.
async def evaluate(db: AsyncSession, settings: Settings) -> dict[str, Any]:
    body = await build_and_send(db, settings)
    return {"sent": body is not None, "preview": body}
