"""Read, write and apply the admin-editable SMTP configuration.

The database row OVERRIDES the environment, field by field, and only where it actually
has a value. That ordering matters both ways round:

  * a deployment that has never opened the admin page keeps working exactly as before,
    on its environment variables;
  * an admin who fills the form in takes over without anyone touching the container;
  * clearing a field in the form falls back to the environment rather than to nothing,
    so a half-filled row cannot silently disable mail.

The password is encrypted at rest with Fernet, keyed from ``settings.smtp_secret_key``
(env / Secret Manager - never the database). Without that key the service refuses to
store a password at all rather than writing one in the clear: a credential sitting in
plaintext in a table that admins can read would be worse than the env var it replaced.
Everything else on the form stays editable in that state.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.smtp_config import SmtpConfig

log = logging.getLogger("app.services.smtp_config")

_ROW_ID = 1


class SmtpConfigError(ValueError):
    """A caller error worth showing an admin verbatim (never an internal detail)."""


def _cipher(settings: Settings) -> Fernet | None:
    key = (settings.smtp_secret_key or "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:  # noqa: BLE001 - a malformed key is a config error, not a crash
        log.error("smtp_secret_key is set but is not a valid Fernet key - ignoring it")
        return None


def encryption_available(settings: Settings) -> bool:
    return _cipher(settings) is not None


async def _row(db: AsyncSession) -> SmtpConfig | None:
    return (
        await db.execute(select(SmtpConfig).where(SmtpConfig.id == _ROW_ID))
    ).scalar_one_or_none()


async def get_config(db: AsyncSession, settings: Settings) -> dict[str, object]:
    """The current settings for display. Never includes the password."""
    row = await _row(db)
    effective = await effective_settings(db, settings)
    return {
        "host": row.host if row else settings.smtp_host,
        "port": row.port if row else settings.smtp_port,
        "username": row.username if row else settings.smtp_username,
        "from_address": row.from_address if row else settings.smtp_from,
        "use_tls": row.use_tls if row else settings.smtp_use_tls,
        "password_set": bool(
            (row.password_encrypted if row else None) or settings.smtp_password
        ),
        "updated_at": row.updated_at if row else None,
        "encryption_available": encryption_available(settings),
        "configured": bool(effective.smtp_host and effective.smtp_from),
    }


async def save_config(
    db: AsyncSession,
    settings: Settings,
    *,
    host: str | None,
    port: int,
    username: str | None,
    from_address: str | None,
    use_tls: bool,
    password: str | None,
    user_id: object,
) -> None:
    """Write the non-secret fields; apply the three-valued password rule.

    ``password`` None leaves the stored one alone, "" clears it, anything else replaces
    it. Raises ``SmtpConfigError`` if a password was supplied but cannot be encrypted -
    refusing is the only honest outcome, since accepting it would mean either storing it
    in the clear or silently dropping it.
    """
    row = await _row(db)
    if row is None:
        row = SmtpConfig(id=_ROW_ID)
        db.add(row)

    row.host = (host or "").strip() or None
    row.port = port
    row.username = (username or "").strip() or None
    row.from_address = (from_address or "").strip() or None
    row.use_tls = use_tls
    row.updated_by = user_id  # type: ignore[assignment]

    if password is not None:
        if password == "":
            row.password_encrypted = None
        else:
            cipher = _cipher(settings)
            if cipher is None:
                raise SmtpConfigError(
                    "This server has no SMTP_SECRET_KEY configured, so a password cannot "
                    "be stored securely. Set that environment variable (or leave the "
                    "password blank and keep using the one from the environment)."
                )
            row.password_encrypted = cipher.encrypt(password.encode()).decode()

    await db.flush()


def _decrypt(settings: Settings, ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    cipher = _cipher(settings)
    if cipher is None:
        log.warning("a stored SMTP password exists but no key is configured to read it")
        return None
    try:
        return cipher.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # The key was rotated or replaced. Say so once, loudly, and fall back to env -
        # silently sending unauthenticated would look like a mail server fault instead.
        log.error("stored SMTP password cannot be decrypted with the current key")
        return None


async def effective_settings(db: AsyncSession, settings: Settings) -> Settings:
    """``settings`` with any values the admin has set layered on top.

    Returns a COPY - the process-wide Settings object is never mutated, so one request
    can never change how another one sends mail.
    """
    row = await _row(db)
    if row is None:
        return settings
    override: dict[str, object] = {}
    if row.host:
        override["smtp_host"] = row.host
        override["smtp_port"] = row.port
        override["smtp_use_tls"] = row.use_tls
    if row.from_address:
        override["smtp_from"] = row.from_address
    if row.username:
        override["smtp_username"] = row.username
    password = _decrypt(settings, row.password_encrypted)
    if password:
        override["smtp_password"] = password
    if not override:
        return settings
    return settings.model_copy(update=override)
