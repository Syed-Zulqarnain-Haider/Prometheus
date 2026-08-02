"""Proactive anomaly alerts, evaluated against the freshly-synced Postgres fact table.

Checks the latest complete day against the prior day (and the freshness of the data) and, when
a threshold is crossed, notifies admins + executives in-app and emails the admins. All thresholds
are operational settings (System tab); the whole feature is OFF by default (``alerts_enabled``).

This reads Postgres only (never BigQuery) and is system-wide (admin/exec audience), so it does
not apply per-user RBAC. Best-effort: a failure here never affects the sync or the request path.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.services import admin_service, email_service, notification_service, settings_service

log = logging.getLogger("alerts")

_FACT = "fact_daily_performance"
# Whole-fleet totals for the two most recent days. Fixed identifiers (a module constant), no
# user input — safe despite the f-string.
_LATEST_TWO_DAYS_SQL = text(  # noqa: S608
    f"SELECT date, COALESCE(SUM(total_revenue_usd), 0) AS rev, "
    f"COALESCE(SUM(total_ua_spend_usd), 0) AS spend "
    f"FROM {_FACT} GROUP BY date ORDER BY date DESC LIMIT 2"
)


async def _threshold(db: AsyncSession, key: str) -> int:
    return int(await settings_service.get_value(db, key))


async def evaluate_and_notify(db: AsyncSession, settings: Settings) -> list[dict[str, Any]]:
    """Evaluate the alert rules once. Returns the fired alerts (empty if disabled or all clear).
    Sends in-app notifications (admins + executives) and one summary email to admins."""
    if not bool(await settings_service.get_value(db, "alerts_enabled")):
        return []

    freshness_hours = await _threshold(db, "data_freshness_threshold_hours")
    drop_pct = await _threshold(db, "alert_revenue_drop_pct")
    spike_pct = await _threshold(db, "alert_spend_spike_pct")
    roas_floor = await _threshold(db, "alert_roas_floor_pct") / 100.0

    rows = (await db.execute(_LATEST_TWO_DAYS_SQL)).all()

    alerts: list[dict[str, Any]] = []

    if not rows:
        return alerts

    latest = rows[0]
    latest_date = latest.date

    # 1) Stale data — the newest fact date is older than the freshness threshold.
    age_hours = (datetime.now(UTC).date() - latest_date).days * 24
    if age_hours > freshness_hours:
        alerts.append({
            "key": "stale_data",
            "severity": "critical",
            "title": "Data is stale",
            "body": f"Latest data is {latest_date} (~{age_hours}h old, "
                    f"threshold {freshness_hours}h). The sync may be failing.",
        })

    if len(rows) >= 2:
        prior = rows[1]
        rev_now, rev_prev = float(latest.rev), float(prior.rev)
        spend_now, spend_prev = float(latest.spend), float(prior.spend)

        # 2) Revenue drop vs prior day.
        if rev_prev > 0:
            change = (rev_now - rev_prev) / rev_prev * 100.0
            if change <= -drop_pct:
                alerts.append({
                    "key": "revenue_drop",
                    "severity": "warning",
                    "title": "Revenue dropped",
                    "body": f"Revenue on {latest_date} fell {abs(change):.0f}% vs {prior.date} "
                            f"(${rev_now:,.0f} vs ${rev_prev:,.0f}, threshold {drop_pct}%).",
                })

        # 3) Spend spike vs prior day.
        if spend_prev > 0:
            change = (spend_now - spend_prev) / spend_prev * 100.0
            if change >= spike_pct:
                alerts.append({
                    "key": "spend_spike",
                    "severity": "warning",
                    "title": "UA spend spiked",
                    "body": f"Spend on {latest_date} rose {change:.0f}% vs {prior.date} "
                            f"(${spend_now:,.0f} vs ${spend_prev:,.0f}, threshold {spike_pct}%).",
                })

    # 4) ROAS below floor (latest day). Disabled when floor is 0.
    if roas_floor > 0 and float(latest.spend) > 0:
        roas = float(latest.rev) / float(latest.spend)
        if roas < roas_floor:
            alerts.append({
                "key": "low_roas",
                "severity": "warning",
                "title": "ROAS below floor",
                "body": f"ROAS on {latest_date} was {roas:.2f}× (floor {roas_floor:.2f}×).",
            })

    if alerts:
        await _dispatch(db, settings, alerts)
    return alerts


async def _dispatch(db: AsyncSession, settings: Settings, alerts: list[dict[str, Any]]) -> None:
    # In-app: notify admins AND executives (they own the numbers). Deep-link to the Overview.
    for a in alerts:
        for role in ("admin", "executive"):
            await notification_service.notify_role(
                role,
                type=f"alert_{a['key']}",
                title=a["title"],
                body=a["body"],
                severity=a["severity"],
                link="/overview",
            )
    # Email: one digest to admins (best-effort; unconfigured SMTP is a no-op).
    emails = await admin_service.active_admin_emails(db)
    if emails:
        body = "Prometheus detected the following:\n\n" + "\n".join(
            f"  • [{a['severity'].upper()}] {a['title']} — {a['body']}" for a in alerts
        )
        await email_service.send_email(
            settings,
            emails,
            subject=f"[Prometheus] {len(alerts)} alert(s): "
            + ", ".join(a["title"] for a in alerts),
            body=body,
        )
