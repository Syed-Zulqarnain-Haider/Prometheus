#!/usr/bin/env python3
"""Wire up admin-editable SMTP settings: migration, config key, routes, and send path.

The pieces that stand alone (model, schemas, service) are checked out as files. This
joins them to the running app:

  backend/alembic/versions/…_smtp_config.py   the table (head detected at run time)
  backend/app/models/__init__.py              register SmtpConfig on Base.metadata
  backend/app/core/config.py                  SMTP_SECRET_KEY, the encryption key
  backend/app/api/v1/admin.py                 GET/PUT /admin/smtp + POST /admin/smtp/test
  backend/app/services/email_service.py       every send reads the DB config first

WHY THE PASSWORD IS NOT IN app_settings: that registry documents itself as having no
mechanism to store a credential, and constrains every value to a short format-validated
scalar precisely so one cannot be pasted in. Rather than punch a hole in that rule for
one field, SMTP gets its own table where the password is encrypted at rest and is never
serialised back out - ``SmtpConfigOut`` has no password field at all, so no code path can
leak it by accident. The API reports only whether one is set.

WHY email_service OPENS ITS OWN SESSION: send_email is called from four services, none of
which should have to learn about SMTP storage to keep working. Resolution happens inside
the send, on a short-lived session, so every existing caller picks up the admin's settings
with no signature change. Sends are rare (digests, alerts, scheduled reports), so the
extra round-trip costs nothing.

Behaviour with no admin config saved is IDENTICAL to today: the row does not exist, the
environment is used unchanged.

Anchored: every anchor must appear EXACTLY once or nothing is written; all files are
validated before any is touched. Idempotent. Run `alembic upgrade head` and restart.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

VERSIONS = Path("backend/alembic/versions")
MODELS_INIT = Path("backend/app/models/__init__.py")
CONFIG = Path("backend/app/core/config.py")
ADMIN = Path("backend/app/api/v1/admin.py")
EMAIL = Path("backend/app/services/email_service.py")

MODEL = Path("backend/app/models/smtp_config.py")
SCHEMA = Path("backend/app/schemas/smtp.py")
SERVICE = Path("backend/app/services/smtp_config_service.py")

# Globally new id - a reused id silently no-ops the glob check and the table never lands.
MIGRATION_ID = "c7d3e91a4b28"

# ── models/__init__.py ────────────────────────────────────────────────────────
MODELS_IMPORT_ANCHOR = "from app.models.settings import AppSetting\n"
MODELS_IMPORT_ADD = "from app.models.smtp_config import SmtpConfig\n"
MODELS_ALL_ANCHOR = '    "AppSetting",\n'
MODELS_ALL_ADD = '    "SmtpConfig",\n'

# ── core/config.py ────────────────────────────────────────────────────────────
CONFIG_ANCHOR = "    smtp_use_tls: bool = True\n"
CONFIG_ADD = '''    # Fernet key used to encrypt the admin-entered SMTP password at rest. Lives in the
    # environment / Secret Manager, NEVER in the database beside the ciphertext it
    # protects. Unset means the admin form still edits every non-secret field but refuses
    # to store a password, and the password below (from the environment) keeps being used.
    # Generate with: python -c "from cryptography.fernet import Fernet;
    # print(Fernet.generate_key().decode())"
    smtp_secret_key: str | None = None
'''

# ── api/v1/admin.py ───────────────────────────────────────────────────────────
# email_service is not currently imported there (sends go through other services), so it
# rides in with smtp_config_service. The services import block is alphabetised; each
# addition sits after the anchor it alphabetically follows.
ADMIN_IMPORT_ANCHOR = "    settings_service,\n"
ADMIN_IMPORT_ADD = "    smtp_config_service,\n"
ADMIN_EMAIL_IMPORT_ANCHOR = "    digest_service,\n"
ADMIN_EMAIL_IMPORT_ADD = "    email_service,\n"

ADMIN_ROUTE_ANCHOR = "# ── System: on-demand sync trigger (admin-only, audited, tightly rate-limited) ──\n"
ADMIN_ROUTE_ADD = '''# ── System: SMTP settings (admin-only, audited; the password is write-only) ─────
@router.get("/smtp", response_model=SmtpConfigOut)
async def get_smtp_config(db: DbSession) -> SmtpConfigOut:
    """Current mail settings. Contains no secret - only whether a password is stored."""
    return SmtpConfigOut(**await smtp_config_service.get_config(db, get_settings()))


@router.put("/smtp", response_model=SmtpConfigOut)
async def update_smtp_config(
    body: SmtpConfigUpdate,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> SmtpConfigOut:
    settings = get_settings()
    try:
        await smtp_config_service.save_config(
            db,
            settings,
            host=body.host,
            port=body.port,
            username=body.username,
            from_address=str(body.from_address) if body.from_address else None,
            use_tls=body.use_tls,
            password=body.password,
            user_id=context.user_id,
        )
    except smtp_config_service.SmtpConfigError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # The audit detail records WHETHER the password changed, never any part of it.
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_update_smtp",
        resource="smtp_config",
        detail={
            "host": body.host,
            "port": body.port,
            "username": body.username,
            "from_address": str(body.from_address) if body.from_address else None,
            "use_tls": body.use_tls,
            "password_changed": body.password is not None,
        },
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return SmtpConfigOut(**await smtp_config_service.get_config(db, settings))


@router.post("/smtp/test", response_model=SmtpTestResult)
async def test_smtp_config(
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> SmtpTestResult:
    """Send a test message to the CALLER'S OWN address.

    Not to an address supplied in the request: an admin-triggered send to an arbitrary
    recipient is an open relay with extra steps. Proving the settings work only requires
    reaching the person doing the proving.
    """
    settings = await smtp_config_service.effective_settings(db, get_settings())
    if not context.email:
        return SmtpTestResult(ok=False, detail="Your account has no email address to send to.")
    sent = await email_service.send_email(
        settings,
        [context.email],
        subject="Prometheus SMTP test",
        body=(
            "This is a test message from the Prometheus admin panel.\\n\\n"
            "If you are reading it, the mail settings work."
        ),
        resolve=False,
    )
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_test_smtp",
        resource="smtp_config",
        detail={"ok": sent},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return SmtpTestResult(
        ok=sent,
        detail=(
            f"Test message sent to {context.email}."
            if sent
            else "Could not send. Check the host, port, credentials and the server logs."
        ),
    )


'''

# ── services/email_service.py ─────────────────────────────────────────────────
EMAIL_SIG_ANCHOR = '''async def send_email(
    settings: Settings,
    recipients: list[str],
    subject: str,
    body: str,
    attachments: list[Attachment] | None = None,
) -> bool:
'''
EMAIL_SIG_NEW = '''async def _with_admin_config(settings: Settings) -> Settings:
    """Layer the admin-entered SMTP settings over the environment, if any are saved.

    Opens its own short-lived session so that every existing caller keeps working
    unchanged - none of them should have to know where mail settings are stored. Any
    failure here falls back to ``settings`` untouched: a database hiccup must degrade
    mail to "as configured in the environment", never to "silently not sent".
    """
    try:
        from app.core.database import AsyncSessionLocal
        from app.services import smtp_config_service

        async with AsyncSessionLocal() as session:
            return await smtp_config_service.effective_settings(session, settings)
    except Exception:  # noqa: BLE001 - configuration lookup must never break a send
        log.exception("could not read the stored SMTP config; using the environment")
        return settings


async def send_email(
    settings: Settings,
    recipients: list[str],
    subject: str,
    body: str,
    attachments: list[Attachment] | None = None,
    resolve: bool = True,
) -> bool:
'''

EMAIL_BODY_ANCHOR = """    clean = [r.strip() for r in recipients if r and r.strip()]
    if not clean:
        return False
    if not is_configured(settings):
"""
EMAIL_BODY_NEW = """    clean = [r.strip() for r in recipients if r and r.strip()]
    if not clean:
        return False
    # The admin panel's settings win over the environment. ``resolve=False`` is for the
    # caller that has already resolved them (the test-send route), so a test never
    # re-reads and silently tests something other than what it was handed.
    if resolve:
        settings = await _with_admin_config(settings)
    if not is_configured(settings):
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def detect_head() -> str:
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        rev = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        if rev:
            revisions.add(rev.group(1))
        for down in re.findall(r"^down_revision[^=]*=\s*(.+)$", text, re.M):
            parents.update(re.findall(r"[\"']([0-9a-f]{8,})[\"']", down))
    heads = revisions - parents
    if len(heads) != 1:
        die(f"expected exactly one migration head, found {len(heads)}: {sorted(heads)}")
    return heads.pop()


def require_once(path: Path, text: str, anchor: str) -> None:
    if text.count(anchor) != 1:
        first = anchor.splitlines()[0].strip() if anchor.strip() else anchor
        die(f"{path}: expected exactly one {first!r}, found {text.count(anchor)}")


def main() -> None:
    for path in (VERSIONS, MODELS_INIT, CONFIG, ADMIN, EMAIL):
        if not path.exists():
            die(f"{path} not found - run from the repository root")
    for path in (MODEL, SCHEMA, SERVICE):
        if not path.exists():
            die(f"{path} not found - check the new backend files out before running this")

    models = MODELS_INIT.read_text()
    config = CONFIG.read_text()
    admin = ADMIN.read_text()
    email = EMAIL.read_text()

    todo: dict[Path, str] = {}

    if "SmtpConfig" in models:
        print(f"{MODELS_INIT}: already registered")
    else:
        require_once(MODELS_INIT, models, MODELS_IMPORT_ANCHOR)
        require_once(MODELS_INIT, models, MODELS_ALL_ANCHOR)
        todo[MODELS_INIT] = models

    if "smtp_secret_key" in config:
        print(f"{CONFIG}: already has the key")
    else:
        require_once(CONFIG, config, CONFIG_ANCHOR)
        todo[CONFIG] = config

    if "admin_update_smtp" in admin:
        print(f"{ADMIN}: routes already present")
    else:
        require_once(ADMIN, admin, ADMIN_IMPORT_ANCHOR)
        require_once(ADMIN, admin, ADMIN_EMAIL_IMPORT_ANCHOR)
        require_once(ADMIN, admin, ADMIN_ROUTE_ANCHOR)
        for needed in ("SmtpConfigOut", "SmtpConfigUpdate", "SmtpTestResult"):
            if needed in admin:
                die(f"{ADMIN}: {needed} is already imported - merge by hand")
        todo[ADMIN] = admin

    if "_with_admin_config" in email:
        print(f"{EMAIL}: already resolves the stored config")
    else:
        require_once(EMAIL, email, EMAIL_SIG_ANCHOR)
        require_once(EMAIL, email, EMAIL_BODY_ANCHOR)
        todo[EMAIL] = email

    migration_needed = not list(VERSIONS.glob(f"*{MIGRATION_ID}*"))

    if not todo and not migration_needed:
        print("already wired - nothing to do")
        return

    # ── write ──
    if MODELS_INIT in todo:
        text = todo[MODELS_INIT]
        text = text.replace(MODELS_IMPORT_ANCHOR, MODELS_IMPORT_ANCHOR + MODELS_IMPORT_ADD, 1)
        text = text.replace(MODELS_ALL_ANCHOR, MODELS_ALL_ANCHOR + MODELS_ALL_ADD, 1)
        MODELS_INIT.write_text(text)
        print(f"patched {MODELS_INIT}")

    if CONFIG in todo:
        CONFIG.write_text(todo[CONFIG].replace(CONFIG_ANCHOR, CONFIG_ANCHOR + CONFIG_ADD, 1))
        print(f"patched {CONFIG}: SMTP_SECRET_KEY")

    if ADMIN in todo:
        text = todo[ADMIN]
        text = text.replace(ADMIN_IMPORT_ANCHOR, ADMIN_IMPORT_ANCHOR + ADMIN_IMPORT_ADD, 1)
        text = text.replace(
            ADMIN_EMAIL_IMPORT_ANCHOR, ADMIN_EMAIL_IMPORT_ANCHOR + ADMIN_EMAIL_IMPORT_ADD, 1
        )
        text = text.replace(ADMIN_ROUTE_ANCHOR, ADMIN_ROUTE_ADD + ADMIN_ROUTE_ANCHOR, 1)
        # The schema import slots before app.schemas.system, keeping the block sorted.
        text = text.replace(
            "from app.schemas.system import",
            "from app.schemas.smtp import SmtpConfigOut, SmtpConfigUpdate, SmtpTestResult\n"
            "from app.schemas.system import",
            1,
        )
        ADMIN.write_text(text)
        print(f"patched {ADMIN}: /admin/smtp routes")

    if EMAIL in todo:
        text = todo[EMAIL]
        text = text.replace(EMAIL_SIG_ANCHOR, EMAIL_SIG_NEW, 1)
        text = text.replace(EMAIL_BODY_ANCHOR, EMAIL_BODY_NEW, 1)
        EMAIL.write_text(text)
        print(f"patched {EMAIL}: sends read the stored config")

    if migration_needed:
        head = detect_head()
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M")
        path = VERSIONS / f"{stamp}_{MIGRATION_ID}_smtp_config.py"
        path.write_text(
            f'''"""Admin-editable SMTP configuration (single row; password encrypted at rest).

Revision ID: {MIGRATION_ID}
Revises: {head}
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "{MIGRATION_ID}"
down_revision: str | None = "{head}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "smtp_config",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("host", sa.Text(), nullable=True),
        sa.Column("port", sa.Integer(), nullable=False, server_default=sa.text("587")),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("from_address", sa.Text(), nullable=True),
        sa.Column("use_tls", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        # Fernet ciphertext. Never plaintext, and never returned by the API.
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        # "The SMTP settings" is a singleton; a table that can hold two invites the
        # question of which one is live.
        sa.CheckConstraint("id = 1", name="ck_smtp_config_singleton"),
    )


def downgrade() -> None:
    op.drop_table("smtp_config")
'''
        )
        print(f"created {path.name} (revises {head})")

    print("\nNext: alembic upgrade head, then restart the backend.")
    print("Until an admin saves the form, mail behaves exactly as it does today.")


if __name__ == "__main__":
    main()
