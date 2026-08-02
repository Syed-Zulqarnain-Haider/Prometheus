"""Minimal SMTP email sender for admin alerts (e.g. a new app discovered on refresh).

Design goals:
  * NO new dependency — stdlib ``smtplib`` run in a worker thread (never blocks the event loop).
  * Graceful degradation — if SMTP isn't configured (no host / no from-address), ``send_email``
    logs and returns ``False`` instead of raising, so callers' in-app notifications still work.
  * No secrets in logs — only recipient count and success/failure type are logged, never the
    password or message body.

Configuration lives on ``Settings`` (env-only): ``smtp_host``, ``smtp_port``, ``smtp_username``,
``smtp_password`` (secret), ``smtp_from``, ``smtp_use_tls``.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import Settings

log = logging.getLogger("email")


def is_configured(settings: Settings) -> bool:
    """Email can be sent only when a host and a from-address are set."""
    return bool(settings.smtp_host and settings.smtp_from)


def _send_blocking(settings: Settings, recipients: list[str], subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or ""
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    # timeout so a wedged relay can never hang the worker thread indefinitely.
    with smtplib.SMTP(settings.smtp_host or "", settings.smtp_port, timeout=20) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)


async def send_email(
    settings: Settings, recipients: list[str], subject: str, body: str
) -> bool:
    """Best-effort send to ``recipients``. Returns True on success, False if not configured or
    the send failed — NEVER raises, so a mail outage can't break the request that triggered it."""
    clean = [r.strip() for r in recipients if r and r.strip()]
    if not clean:
        return False
    if not is_configured(settings):
        log.info("email not configured (smtp_host/smtp_from unset) — skipping send of %r", subject)
        return False
    try:
        await asyncio.to_thread(_send_blocking, settings, clean, subject, body)
        log.info("sent email %r to %d recipient(s)", subject, len(clean))
        return True
    except Exception:  # noqa: BLE001 — mail failures must never propagate into the request path
        log.exception("email send failed for %r (%d recipient(s))", subject, len(clean))
        return False
