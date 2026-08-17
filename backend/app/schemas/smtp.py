"""Request/response models for the admin SMTP settings.

The one rule that shapes all of this: the password goes IN and never comes back out.
``SmtpConfigOut`` has no password field at all - not a masked one, not a redacted one -
so there is no code path that can serialise it by accident. The UI learns only whether
one is stored, from ``password_set``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SmtpConfigOut(BaseModel):
    """SMTP settings as shown to an admin. Contains NO secret."""

    host: str | None
    port: int
    username: str | None
    from_address: str | None
    use_tls: bool
    # Whether a password is stored - never the password itself.
    password_set: bool
    updated_at: datetime | None
    # True when the server can encrypt a password at all; False means the deployment has
    # no key configured, so the form must say so rather than silently discarding input.
    encryption_available: bool
    # True when host + from-address are both present, i.e. mail can actually be sent.
    configured: bool


class SmtpConfigUpdate(BaseModel):
    """A full replacement of the non-secret fields, plus optional password handling.

    ``password`` is three-valued on purpose:
      * omitted (None) - leave whatever is stored alone. This is what an ordinary save
        does, so editing the host does not require retyping the password.
      * "" (empty)     - clear the stored password (switch to an unauthenticated relay).
      * any other text - replace it.
    """

    host: str | None = Field(default=None, max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    from_address: EmailStr | None = None
    use_tls: bool = True
    password: str | None = Field(default=None, max_length=512)


class SmtpTestResult(BaseModel):
    """Outcome of a test send. ``detail`` is a human message, never a stack trace."""

    ok: bool
    detail: str
