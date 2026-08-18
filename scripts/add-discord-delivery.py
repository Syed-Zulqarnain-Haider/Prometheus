#!/usr/bin/env python3
"""Feature 9: Discord delivery for the daily digest and the alerts.

Email is where alerts go to die. The teams here live in Discord, so the digest and the
proactive alerts post there as embeds - the same content the email carries, formatted for
a channel instead of an inbox.

Security, because a webhook URL IS a credential:

  * Anyone holding the URL can post into that channel as the app, so it is treated exactly
    like the SMTP password: encrypted at rest with Fernet, keyed from the environment
    (never the database), never returned by any endpoint, and never written to a log. The
    API reports only whether one is stored.
  * Without the encryption key the service REFUSES to store the URL rather than writing it
    in the clear - the same rule smtp_config_service already applies. An environment
    variable (``DISCORD_WEBHOOK_URL``) keeps working in that state, so a deployment is
    never forced to choose between the feature and plaintext.
  * The URL is validated against Discord's own host before it is stored. A webhook field
    that will POST anywhere is a server-side request forgery primitive handed to whoever
    holds the admin panel; restricting the host to discord.com closes it.
  * Delivery is best-effort and isolated: a Discord outage must never affect the sync, the
    digest email, or the request path.

Wiring: the scheduler already HAS both payloads - evaluate_and_notify returns the fired
alerts and build_and_send returns the digest text - so delivery hooks in there without
touching either service's internals. The admin trigger endpoints post too, so "Send digest
now" actually tests the whole path.

Anchored: every anchor must appear EXACTLY once or NOTHING is written - all files
validate before any is touched. Idempotent. Requires `alembic upgrade head`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MODEL = Path("backend/app/models/discord_config.py")
MIGRATION = Path("backend/alembic/versions/20260818_1400_d40a7f35e1c6_discord_config.py")
SCHEMA = Path("backend/app/schemas/discord.py")
SERVICE = Path("backend/app/services/discord_service.py")
TEST = Path("backend/tests/test_discord.py")
PANEL = Path("frontend/components/admin/discord-panel.tsx")

MODELS_INIT = Path("backend/app/models/__init__.py")
CONFIG = Path("backend/app/core/config.py")
REGISTRY = Path("backend/app/core/settings_registry.py")
SCHEDULER = Path("backend/app/services/sync_scheduler.py")
ADMIN = Path("backend/app/api/v1/admin.py")
TYPES = Path("frontend/lib/types.ts")
HOOKS = Path("frontend/lib/api-hooks.ts")
SYSTEM_PANEL = Path("frontend/components/admin/system-panel.tsx")
TEST_META = Path("backend/tests/test_models_metadata.py")
TEST_MIGRATIONS = Path("backend/tests/test_migrations.py")

MODEL_SOURCE = '''"""Admin-editable Discord webhook (single row; the URL is encrypted at rest).

A webhook URL is a credential: anyone holding it can post into that channel as this
application. It is stored exactly like the SMTP password - Fernet ciphertext, keyed from
the environment, never returned by an endpoint, never logged.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DiscordConfig(Base):
    """The Discord destination. A singleton - a table that can hold two invites the
    question of which one is live."""

    __tablename__ = "discord_config"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    # Fernet ciphertext. Never plaintext, and never returned by the API.
    webhook_url_encrypted: Mapped[str | None] = mapped_column(Text)
    # Cosmetic only - what the embeds are posted as.
    username: Mapped[str | None] = mapped_column(Text)
    send_digest: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    send_alerts: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (CheckConstraint("id = 1", name="ck_discord_config_singleton"),)
'''

MIGRATION_SOURCE = '''"""Admin-editable Discord webhook (single row; URL encrypted at rest).

Revision ID: d40a7f35e1c6
Revises: c39f6e24d0b5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d40a7f35e1c6"
down_revision: str | None = "c39f6e24d0b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discord_config",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        # Fernet ciphertext. Never plaintext, and never returned by the API.
        sa.Column("webhook_url_encrypted", sa.Text(), nullable=True),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("send_digest", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("send_alerts", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint("id = 1", name="ck_discord_config_singleton"),
    )


def downgrade() -> None:
    op.drop_table("discord_config")
'''

SCHEMA_SOURCE = '''"""Discord configuration models. The webhook URL is WRITE-ONLY."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DiscordConfigOut(BaseModel):
    """What an admin is shown. Deliberately carries no part of the URL."""

    webhook_set: bool
    username: str | None
    send_digest: bool
    send_alerts: bool
    updated_at: datetime | None
    # False when no Fernet key is configured: the URL cannot be stored, and the form says
    # so rather than accepting input it will silently drop.
    encryption_available: bool
    # True when a URL is available from EITHER the row or the environment.
    configured: bool


class DiscordConfigUpdate(BaseModel):
    # None means "leave the stored URL alone"; an empty string means "remove it".
    webhook_url: str | None = Field(default=None, max_length=500)
    username: str | None = Field(default=None, max_length=80)
    send_digest: bool = True
    send_alerts: bool = True


class DiscordTestResult(BaseModel):
    sent: bool
    detail: str
'''

SERVICE_SOURCE = '''"""Post the digest and the alerts to Discord as embeds.

Why a separate service rather than a branch inside the email path: the two have different
failure modes and different audiences. Mail can be unconfigured while Discord works, and a
Discord outage must not stop the digest email. Everything here is best-effort and swallows
its own failures - the daily pass, the sync and the request path all continue regardless.

The webhook URL is a CREDENTIAL. Anyone holding it can post into that channel as this
application, so it gets the same treatment as the SMTP password: Fernet at rest, keyed
from the environment, never returned by an endpoint, never logged - not even truncated,
because the interesting part of a Discord webhook URL is the id and token at the end.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.discord_config import DiscordConfig

log = logging.getLogger("discord")

_ROW_ID = 1

# A webhook field that will POST anywhere is a server-side request forgery primitive
# handed to whoever holds the admin panel. Discord's own hosts, or nothing.
ALLOWED_HOSTS = frozenset(
    {"discord.com", "discordapp.com", "canary.discord.com", "ptb.discord.com"}
)

# Embed colours. Decimal, which is what the Discord API takes.
COLOR_INFO = 0x5865F2  # blurple
COLOR_WARNING = 0xF0B232
COLOR_CRITICAL = 0xED4245

# Discord truncates hard and silently; do it here so the message stays readable.
_MAX_DESCRIPTION = 3800
_MAX_FIELDS = 10

# Short: a hung webhook must never hold the daily pass open.
_TIMEOUT_SECONDS = 6.0


class DiscordConfigError(ValueError):
    """A caller error worth showing an admin verbatim (never an internal detail)."""


def _cipher(settings: Settings) -> Fernet | None:
    """The app's at-rest cipher. Keyed from ``smtp_secret_key`` - one key for the whole
    application, named after the feature that needed it first rather than a second
    environment variable for every future secret."""
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


def validate_webhook_url(url: str) -> str:
    """Accept only an HTTPS Discord webhook. Raises DiscordConfigError otherwise."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise DiscordConfigError("The webhook URL must start with https://")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise DiscordConfigError("That is not a Discord webhook URL.")
    if "/api/webhooks/" not in parsed.path:
        raise DiscordConfigError("That is not a Discord webhook URL.")
    return url.strip()


async def _row(db: AsyncSession) -> DiscordConfig | None:
    return (
        await db.execute(select(DiscordConfig).where(DiscordConfig.id == _ROW_ID))
    ).scalar_one_or_none()


def _decrypt(settings: Settings, ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    cipher = _cipher(settings)
    if cipher is None:
        return None
    try:
        return cipher.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # The key was rotated without re-entering the URL. Say so once; do NOT log the
        # ciphertext.
        log.error("stored Discord webhook cannot be decrypted with the current key")
        return None


async def webhook_url(db: AsyncSession, settings: Settings) -> str | None:
    """The effective webhook: the stored row first, the environment as a fallback.

    That ordering means an admin who fills the form in takes over without a redeploy,
    while a deployment that has never opened the page keeps working on its env var.
    """
    row = await _row(db)
    stored = _decrypt(settings, row.webhook_url_encrypted if row else None)
    return stored or (getattr(settings, "discord_webhook_url", None) or None)


async def get_config(db: AsyncSession, settings: Settings) -> dict[str, Any]:
    """What an admin is shown. Carries no part of the URL."""
    row = await _row(db)
    return {
        "webhook_set": bool(await webhook_url(db, settings)),
        "username": row.username if row else None,
        "send_digest": row.send_digest if row else True,
        "send_alerts": row.send_alerts if row else True,
        "updated_at": row.updated_at if row else None,
        "encryption_available": encryption_available(settings),
        "configured": bool(await webhook_url(db, settings)),
    }


async def save_config(
    db: AsyncSession,
    settings: Settings,
    *,
    webhook_url_value: str | None,
    username: str | None,
    send_digest: bool,
    send_alerts: bool,
    user_id: Any,
) -> None:
    """Store the destination. ``webhook_url_value`` of None leaves the stored URL alone;
    an empty string removes it."""
    row = await _row(db)
    if row is None:
        row = DiscordConfig(id=_ROW_ID)
        db.add(row)

    row.username = (username or "").strip() or None
    row.send_digest = send_digest
    row.send_alerts = send_alerts

    if webhook_url_value is not None:
        if webhook_url_value.strip() == "":
            row.webhook_url_encrypted = None
        else:
            cipher = _cipher(settings)
            if cipher is None:
                # Refuse rather than store a credential in the clear. A plaintext webhook
                # in a table admins can read would be worse than the env var it replaces.
                raise DiscordConfigError(
                    "Set SMTP_SECRET_KEY (the app's at-rest encryption key) before saving "
                    "a webhook URL. Until then, DISCORD_WEBHOOK_URL in the environment "
                    "still works."
                )
            validated = validate_webhook_url(webhook_url_value)
            row.webhook_url_encrypted = cipher.encrypt(validated.encode()).decode()

    row.updated_at = datetime.now(UTC)
    row.updated_by = user_id
    await db.commit()


def build_embed(
    title: str, description: str, *, color: int, fields: list[tuple[str, str]] | None = None
) -> dict[str, Any]:
    """One Discord embed, truncated to what Discord will actually render."""
    embed: dict[str, Any] = {
        "title": title[:256],
        "description": description[:_MAX_DESCRIPTION],
        "color": color,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if fields:
        embed["fields"] = [
            {"name": name[:256], "value": value[:1024], "inline": True}
            for name, value in fields[:_MAX_FIELDS]
        ]
    return embed


async def post(
    db: AsyncSession, settings: Settings, embeds: list[dict[str, Any]]
) -> tuple[bool, str]:
    """POST embeds to the configured webhook. Returns (sent, human-readable detail).

    Never raises: a Discord outage must not affect the sync, the digest email, or a
    request. The detail is sanitised to a status code or an exception TYPE - a provider
    error body can echo the URL back, and that URL is a credential.
    """
    url = await webhook_url(db, settings)
    if not url:
        return False, "No Discord webhook configured."
    row = await _row(db)
    payload: dict[str, Any] = {"embeds": embeds}
    if row and row.username:
        payload["username"] = row.username

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
    except Exception as exc:  # noqa: BLE001 - best-effort by design
        log.warning("Discord post failed: %s", type(exc).__name__)
        return False, f"Could not reach Discord ({type(exc).__name__})."

    if response.status_code >= 400:
        log.warning("Discord rejected the post: HTTP %s", response.status_code)
        return False, f"Discord rejected the message (HTTP {response.status_code})."
    return True, "Sent."


async def deliver_alerts(
    db: AsyncSession, settings: Settings, alerts: list[dict[str, Any]]
) -> bool:
    """Post fired alerts. One embed per alert, coloured by severity."""
    if not alerts:
        return False
    row = await _row(db)
    if row is not None and not row.send_alerts:
        return False
    embeds = [
        build_embed(
            str(alert.get("title", "Alert")),
            str(alert.get("body", "")),
            color=COLOR_CRITICAL if alert.get("severity") == "critical" else COLOR_WARNING,
        )
        # Discord accepts at most 10 embeds per message, and 10 alerts at once is already
        # a bad morning - the rest are in the email and the app.
        for alert in alerts[:_MAX_FIELDS]
    ]
    sent, _ = await post(db, settings, embeds)
    return sent


async def deliver_digest(db: AsyncSession, settings: Settings, digest: str | None) -> bool:
    """Post the daily digest as a single embed - the same text the email carries."""
    if not digest:
        return False
    row = await _row(db)
    if row is not None and not row.send_digest:
        return False
    sent, _ = await post(
        db,
        settings,
        [build_embed("Daily performance digest", digest, color=COLOR_INFO)],
    )
    return sent
'''

TEST_SOURCE = '''"""Discord delivery: the URL is a credential, and it is treated like one.

The tests that matter are the negative ones. An arbitrary URL must be refused (a webhook
field that POSTs anywhere is an SSRF primitive handed to whoever holds the admin panel),
the stored URL must never come back out of any endpoint, and saving without an encryption
key must fail rather than write a credential in the clear.
"""

import pytest
from app.core.config import Settings
from app.services import discord_service

from tests.conftest import MetricsEnv

URL = "/api/v1/admin/discord"
GOOD = "https://discord.com/api/webhooks/123456789/abcdefTOKEN"


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


def test_a_real_discord_webhook_is_accepted() -> None:
    assert discord_service.validate_webhook_url(GOOD) == GOOD


@pytest.mark.parametrize(
    "url",
    [
        "http://discord.com/api/webhooks/1/t",  # not https
        "https://evil.example/api/webhooks/1/t",  # not Discord
        "https://discord.com/channels/1/2",  # Discord, but not a webhook
        "https://discord.com.evil.example/api/webhooks/1/t",  # lookalike host
    ],
)
def test_anything_else_is_refused(url: str) -> None:
    """A webhook field that will POST anywhere is an SSRF primitive."""
    with pytest.raises(discord_service.DiscordConfigError):
        discord_service.validate_webhook_url(url)


def test_embed_is_truncated_to_what_discord_renders() -> None:
    embed = discord_service.build_embed(
        "t" * 400, "d" * 5000, color=discord_service.COLOR_INFO
    )
    assert len(embed["title"]) == 256
    assert len(embed["description"]) <= 3800


def test_no_encryption_key_means_no_cipher() -> None:
    assert discord_service.encryption_available(Settings(smtp_secret_key=None)) is False
    assert discord_service.encryption_available(Settings(smtp_secret_key="not-a-key")) is False


async def test_requires_admin(metrics_env: MetricsEnv) -> None:
    assert (await metrics_env.client.get(URL, headers=_auth("finance"))).status_code == 403


async def test_config_never_returns_the_url(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get(URL, headers=_auth("admin"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Only WHETHER one is set - no field anywhere may carry the credential.
    assert set(body) == {
        "webhook_set",
        "username",
        "send_digest",
        "send_alerts",
        "updated_at",
        "encryption_available",
        "configured",
    }
    assert "webhook" not in str(body.get("username") or "")


async def test_saving_a_url_without_a_key_is_refused_not_stored(
    metrics_env: MetricsEnv,
) -> None:
    """The suite runs with no SMTP_SECRET_KEY, so this is the real deployment state
    today: refuse, rather than write a credential in plaintext."""
    resp = await metrics_env.client.put(
        URL,
        json={"webhook_url": GOOD, "send_digest": True, "send_alerts": True},
        headers=_auth("admin"),
    )
    assert resp.status_code == 400
    assert (await metrics_env.client.get(URL, headers=_auth("admin"))).json()[
        "webhook_set"
    ] is False


async def test_toggles_save_without_a_key(metrics_env: MetricsEnv) -> None:
    """Everything that is NOT a credential stays editable in that state."""
    resp = await metrics_env.client.put(
        URL,
        json={"username": "Prometheus", "send_digest": False, "send_alerts": True},
        headers=_auth("admin"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["send_digest"] is False
    assert body["username"] == "Prometheus"


async def test_post_with_nothing_configured_is_a_clean_no_op(
    metrics_env: MetricsEnv,
) -> None:
    async with metrics_env.sessionmaker() as session:
        sent, detail = await discord_service.post(session, Settings(), [])
    assert sent is False
    assert "No Discord webhook" in detail
'''

PANEL_SOURCE = r'''"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useDiscordConfig,
  useSaveDiscordConfig,
  useTestDiscord,
} from "@/lib/api-hooks";

/* Discord delivery for the digest and the alerts.
 *
 * The webhook URL is WRITE-ONLY. It is never returned by the API and never rendered here
 * - the form only reports whether one is stored, because anyone holding that URL can post
 * into the channel as this application. */

export function DiscordPanel() {
  const config = useDiscordConfig();
  const save = useSaveDiscordConfig();
  const test = useTestDiscord();

  const [webhook, setWebhook] = useState("");
  const [username, setUsername] = useState("");
  const [sendDigest, setSendDigest] = useState(true);
  const [sendAlerts, setSendAlerts] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!config.data) return;
    setUsername(config.data.username ?? "");
    setSendDigest(config.data.send_digest);
    setSendAlerts(config.data.send_alerts);
  }, [config.data]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    save.mutate(
      {
        // Undefined leaves the stored URL alone; the field is blank on every load
        // because the server never sends it back.
        webhook_url: webhook.trim() === "" ? undefined : webhook.trim(),
        username: username.trim() || null,
        send_digest: sendDigest,
        send_alerts: sendAlerts,
      },
      {
        onSuccess: () => setWebhook(""),
        onError: (err) => setError((err as Error).message),
      },
    );
  }

  const encryptionMissing = config.data ? !config.data.encryption_available : false;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Discord</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <p className="text-xs text-[var(--color-text-muted)]">
            {config.data?.webhook_set
              ? "A webhook is stored. Leave the field blank to keep it; type a new one to replace it."
              : "No webhook stored yet. Create one in your Discord channel under Integrations → Webhooks."}
          </p>

          {encryptionMissing && (
            <p className="rounded-[var(--radius-inner)] border border-[var(--color-amber)] p-2 text-xs">
              SMTP_SECRET_KEY is not set, so a webhook URL cannot be stored — it would have
              to be written in plaintext. The toggles below still save, and
              DISCORD_WEBHOOK_URL in the environment still works.
            </p>
          )}

          <div>
            <Label htmlFor="discord-webhook">Webhook URL</Label>
            <Input
              id="discord-webhook"
              type="password"
              autoComplete="off"
              value={webhook}
              onChange={(e) => setWebhook(e.target.value)}
              placeholder="https://discord.com/api/webhooks/…"
              disabled={encryptionMissing}
              maxLength={500}
            />
          </div>

          <div>
            <Label htmlFor="discord-username">Post as (optional)</Label>
            <Input
              id="discord-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Prometheus"
              maxLength={80}
            />
          </div>

          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={sendDigest}
                onChange={(e) => setSendDigest(e.target.checked)}
              />
              Send the daily digest
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={sendAlerts}
                onChange={(e) => setSendAlerts(e.target.checked)}
              />
              Send alerts
            </label>
          </div>

          <div className="flex items-center gap-2">
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={test.isPending || !config.data?.configured}
              onClick={() => test.mutate()}
            >
              {test.isPending ? "Sending…" : "Send test message"}
            </Button>
          </div>

          {error && <p className="text-xs text-[var(--color-negative)]">{error}</p>}
          {test.data && (
            <p
              className="text-xs"
              style={{
                color: test.data.sent ? "var(--color-positive)" : "var(--color-negative)",
              }}
            >
              {test.data.detail}
            </p>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
'''

# ── anchored edits ────────────────────────────────────────────────────────────
MODELS_INIT_EDITS = [
    (
        "from app.models.dynamic_columns import DynamicColumn\n",
        "from app.models.discord_config import DiscordConfig\n",
        True,
    ),
    ('    "DynamicColumn",\n', '    "DiscordConfig",\n', True),
]

CONFIG_EDITS = [
    (
        "    smtp_secret_key: str | None = None\n",
        "    smtp_secret_key: str | None = None\n"
        "    # Optional Discord destination. The admin panel's stored (encrypted) webhook\n"
        "    # takes precedence; this keeps a deployment working before anyone opens the\n"
        "    # page, and while no at-rest encryption key is configured.\n"
        "    discord_webhook_url: str | None = None\n",
        None,
    )
]

SCHEDULER_IMPORT_ANCHOR = "    digest_service,\n"
SCHEDULER_IMPORT_ADD = "    discord_service,\n"

# CODE ONLY. An earlier version of these two anchors carried the `# noqa: BLE001 —`
# comment lines with them and aborted on a tree whose style pass had replaced the em
# dashes with hyphens. A comment is prose; prose drifts. Anchor on the statement.
SCHEDULER_ALERTS_ANCHOR = (
    "                fired = await alerts_service.evaluate_and_notify(db, settings)\n"
)
SCHEDULER_ALERTS_NEW = (
    "                fired = await alerts_service.evaluate_and_notify(db, settings)\n"
    "                # Discord gets the same alerts the email carries. Best-effort and\n"
    "                # separately isolated: a Discord outage must not cost anyone the\n"
    "                # email, so it sits inside the same try and swallows its own errors.\n"
    "                await discord_service.deliver_alerts(db, settings, fired)\n"
)

SCHEDULER_DIGEST_ANCHOR = "                await digest_service.build_and_send(db, settings)\n"
SCHEDULER_DIGEST_NEW = (
    "                digest_text = await digest_service.build_and_send(db, settings)\n"
    "                await discord_service.deliver_digest(db, settings, digest_text)\n"
)

# app.schemas.discord sorts between .admin and .integration - ruff's isort rule is a
# gate here, not a preference.
ADMIN_SCHEMA_IMPORT_ANCHOR = "from app.schemas.integration import (\n"
ADMIN_SCHEMA_IMPORT_NEW = (
    "from app.schemas.discord import DiscordConfigOut, DiscordConfigUpdate, DiscordTestResult\n"
    "from app.schemas.integration import (\n"
)
ADMIN_SERVICE_IMPORT_ANCHOR = "    digest_service,\n"
ADMIN_SERVICE_IMPORT_ADD = "    discord_service,\n"

# The routes are APPENDED, not anchored. The only landmark near the SMTP section is a
# banner comment made of box-drawing characters - the single most drift-prone string in
# the file. A router decorator works wherever it sits, so position buys nothing.
ADMIN_ROUTE_ADD = '''# ── System: Discord delivery (admin-only, audited; the webhook is write-only) ───
@router.get("/discord", response_model=DiscordConfigOut)
async def get_discord_config(db: DbSession) -> DiscordConfigOut:
    """Current Discord settings. Carries no part of the webhook URL - only whether one
    is stored. That URL is a credential: anyone holding it can post as this app."""
    return DiscordConfigOut(**await discord_service.get_config(db, get_settings()))


@router.put("/discord", response_model=DiscordConfigOut)
async def update_discord_config(
    body: DiscordConfigUpdate,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> DiscordConfigOut:
    settings = get_settings()
    try:
        await discord_service.save_config(
            db,
            settings,
            webhook_url_value=body.webhook_url,
            username=body.username,
            send_digest=body.send_digest,
            send_alerts=body.send_alerts,
            user_id=context.user_id,
        )
    except discord_service.DiscordConfigError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # The audit detail records WHETHER the webhook changed, never any part of it.
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_update_discord",
        resource="discord_config",
        detail={
            "username": body.username,
            "send_digest": body.send_digest,
            "send_alerts": body.send_alerts,
            "webhook_changed": body.webhook_url is not None,
        },
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return DiscordConfigOut(**await discord_service.get_config(db, settings))


@router.post(
    "/discord/test",
    response_model=DiscordTestResult,
    dependencies=[Depends(enforce_diagnostics_rate_limit)],
)
async def test_discord_config(
    request: Request, context: CurrentUser, db: DbSession, audit: AuditDep
) -> DiscordTestResult:
    """Post a test embed to the configured channel. Rate-limited like the other
    diagnostics, because it is an outbound request an admin can trigger at will."""
    sent, detail = await discord_service.post(
        db,
        get_settings(),
        [
            discord_service.build_embed(
                "Prometheus test message",
                f"Sent by {context.email}. If you can read this, delivery works.",
                color=discord_service.COLOR_INFO,
            )
        ],
    )
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_test_discord",
        detail={"sent": sent},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return DiscordTestResult(sent=sent, detail=detail)


'''

ADMIN_ALERTS_ANCHOR = """    fired = await alerts_service.evaluate_and_notify(db, get_settings())
"""
ADMIN_ALERTS_NEW = """    settings = get_settings()
    fired = await alerts_service.evaluate_and_notify(db, settings)
    # So that "evaluate now" tests the WHOLE path, Discord included - a delivery that
    # only ever runs at 06:15 is a delivery nobody can verify.
    await discord_service.deliver_alerts(db, settings, fired)
"""

ADMIN_DIGEST_ANCHOR = """    result = await digest_service.evaluate(db, get_settings())
"""
ADMIN_DIGEST_NEW = """    settings = get_settings()
    result = await digest_service.evaluate(db, settings)
    # digest_service.evaluate returns {"sent", "preview"}; the preview IS the body.
    await discord_service.deliver_digest(db, settings, result["preview"])
"""

TYPES_ANCHOR = "export interface TableResponse {\n"
TYPES_ADD = """/** Discord delivery settings. The webhook URL is WRITE-ONLY and never appears here -
 *  anyone holding it can post into the channel as this application. */
export interface DiscordConfig {
  webhook_set: boolean;
  username: string | null;
  send_digest: boolean;
  send_alerts: boolean;
  updated_at: string | null;
  encryption_available: boolean;
  configured: boolean;
}

export interface DiscordConfigInput {
  /** Omit to keep the stored URL; empty string removes it. */
  webhook_url?: string;
  username: string | null;
  send_digest: boolean;
  send_alerts: boolean;
}

export interface DiscordTestResult {
  sent: boolean;
  detail: string;
}

"""

HOOKS_IMPORT_ANCHOR = "  BenchmarkResponse,\n"
HOOKS_IMPORT_ADD = "  DiscordConfig,\n  DiscordConfigInput,\n  DiscordTestResult,\n"

HOOKS_ANCHOR = "// ── Identity (RBAC context + share directory) ────────────────────────────────\n"
HOOKS_ADD = '''// ── Discord delivery (admin) ─────────────────────────────────────────────────
export function useDiscordConfig() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["discord-config"],
    queryFn: () => apiFetch<DiscordConfig>("/api/v1/admin/discord"),
    enabled: Boolean(user),
  });
}

export function useSaveDiscordConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DiscordConfigInput) =>
      apiFetch<DiscordConfig>("/api/v1/admin/discord", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["discord-config"] }),
  });
}

export function useTestDiscord() {
  return useMutation({
    mutationFn: () =>
      apiFetch<DiscordTestResult>("/api/v1/admin/discord/test", { method: "POST" }),
  });
}

'''

SYSTEM_IMPORT_ANCHOR = 'import { SmtpPanel } from "@/components/admin/smtp-panel";\n'
SYSTEM_IMPORT_ADD = 'import { DiscordPanel } from "@/components/admin/discord-panel";\n'
SYSTEM_RENDER_ANCHOR = "        <SmtpPanel />\n"
SYSTEM_RENDER_ADD = "        <DiscordPanel />\n"

TEST_META_EDITS = [('    "scoped_targets",\n', '    "discord_config",\n', False)]
TEST_MIGRATIONS_EDITS = [('_HEAD = "c39f6e24d0b5"', '_HEAD = "d40a7f35e1c6"', None)]


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def plan_edits(
    path: Path, text: str, marker: str, edits: list[tuple[str, str, bool | None]]
) -> list[tuple[str, str, bool | None]] | None:
    if marker in text:
        print(f"{path}: already patched")
        return None
    for anchor, _, _ in edits:
        if text.count(anchor) != 1:
            first = anchor.splitlines()[0].strip()
            die(f"{path}: expected exactly one {first!r}, found {text.count(anchor)}")
    return edits



# The four ids this batch first used - a1b2c3d4e5f6, b2c3d4e5f6a7, c3d4e5f6a7b8,
# d4e5f6a7b8c9 - were ALREADY TAKEN by migrations from June and July. I picked the
# "obvious next" ids in the same rolling-hex family and collided head-on, which alembic
# reported as "present more than once" and then as a cycle. These are the ids that
# replaced them, and the stale file has to go or the duplicate survives.
REVISION_ID = "d40a7f35e1c6"
SUPERSEDED_REVISIONS = ("a1b2c3d4e5f6", "b2c3d4e5f6a7", "c3d4e5f6a7b8", "d4e5f6a7b8c9")
STALE_MIGRATION = Path("backend/alembic/versions/20260818_1400_d4e5f6a7b8c9_discord_config.py")


def drop_stale_migration() -> None:
    """Remove the colliding migration an earlier version of this script wrote."""
    if STALE_MIGRATION.exists():
        STALE_MIGRATION.unlink()
        print(f"removed {STALE_MIGRATION} (its revision id collided with an existing one)")


def assert_revision_free(migration: Path, revision: str) -> None:
    """Refuse to write a migration whose id is already used by a DIFFERENT file.

    A duplicate id does not fail at write time - it fails much later, at `alembic upgrade`,
    as an unreadable cycle error. Catching it here names the file instead.
    """
    versions = migration.parent
    if not versions.is_dir():
        return
    pattern = re.compile(r"^revision(?::\s*str)?\s*=\s*[\"']" + re.escape(revision) + r"[\"']", re.M)
    for other in sorted(versions.glob("*.py")):
        if other.name == migration.name:
            continue
        if pattern.search(other.read_text()):
            die(
                f"revision id {revision!r} is already used by {other.name} - "
                f"pick a different one rather than creating a cycle"
            )


def plan_head_pin(path: Path, text: str, old: str, new: str) -> list[tuple[str, str, None]] | None:
    """Move test_migrations.py's pinned head revision - tolerantly.

    Every migration-bearing patch moves this ONE line, so re-running an earlier script
    after a later one would otherwise find its anchor gone and abort. The chain is
    forward-only: a head further along is correct, not broken. So the pin is only
    rewritten when it is still sitting on exactly the revision this patch supersedes.
    """
    match = re.search(r'_HEAD = "([0-9a-f]+)"', text)
    if match is None:
        die(f"{path}: no _HEAD pin found - the file has changed shape")
    current = match.group(1)
    if current == new:
        print(f"{path}: already pinned to {new}")
        return None
    if current in SUPERSEDED_REVISIONS:
        # The pin still names one of the colliding ids this batch first used.
        # Correct it rather than leaving the test asserting a revision that no
        # longer exists.
        return [(f'_HEAD = "{current}"', f'_HEAD = "{new}"', None)]
    if current != old:
        # NOT necessarily "further along" - it may be BEHIND, which means an earlier
        # migration patch in the chain has not run here. Either way this patch must not
        # rewrite a pin it does not recognise, but a pin left behind the database WILL
        # fail test_migrations, so say which case it is rather than implying it is fine.
        print(
            f"{path}: head pin is {current}, expected {old} - not touching it. "
            f"If the chain has not been run in order, this test will fail against a "
            f"database at {new}."
        )
        return None
    return [(f'_HEAD = "{old}"', f'_HEAD = "{new}"', None)]


def main() -> None:
    patched = [
        MODELS_INIT, CONFIG, SCHEDULER, ADMIN, TYPES, HOOKS, SYSTEM_PANEL,
        TEST_META, TEST_MIGRATIONS,
    ]
    for path in patched:
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    if "scoped_targets" not in TEST_META.read_text():
        die("run scripts/add-scoped-targets-pacing.py first - the migration chains onto it")

    texts = {path: path.read_text() for path in patched}

    plan: dict[Path, list[tuple[str, str, bool | None]]] = {}
    for path, marker, edits in (
        (MODELS_INIT, "DiscordConfig", MODELS_INIT_EDITS),
        (CONFIG, "discord_webhook_url", CONFIG_EDITS),
        (
            SCHEDULER,
            "discord_service",
            [
                (SCHEDULER_IMPORT_ANCHOR, SCHEDULER_IMPORT_ADD, False),
                (SCHEDULER_ALERTS_ANCHOR, SCHEDULER_ALERTS_NEW, None),
                (SCHEDULER_DIGEST_ANCHOR, SCHEDULER_DIGEST_NEW, None),
            ],
        ),
        (
            ADMIN,
            "discord_service",
            [
                (ADMIN_SCHEMA_IMPORT_ANCHOR, ADMIN_SCHEMA_IMPORT_NEW, None),
                (ADMIN_SERVICE_IMPORT_ANCHOR, ADMIN_SERVICE_IMPORT_ADD, False),
                        (ADMIN_ALERTS_ANCHOR, ADMIN_ALERTS_NEW, None),
                (ADMIN_DIGEST_ANCHOR, ADMIN_DIGEST_NEW, None),
            ],
        ),
        (TYPES, "interface DiscordConfig", [(TYPES_ANCHOR, TYPES_ADD, True)]),
        (
            HOOKS,
            "useDiscordConfig",
            [(HOOKS_IMPORT_ANCHOR, HOOKS_IMPORT_ADD, False), (HOOKS_ANCHOR, HOOKS_ADD, True)],
        ),
        (
            SYSTEM_PANEL,
            "DiscordPanel",
            [
                (SYSTEM_IMPORT_ANCHOR, SYSTEM_IMPORT_ADD, True),
                (SYSTEM_RENDER_ANCHOR, SYSTEM_RENDER_ADD, False),
            ],
        ),
        (TEST_META, "discord_config", TEST_META_EDITS),
    ):
        edits_or_none = plan_edits(path, texts[path], marker, edits)
        if edits_or_none is not None:
            plan[path] = edits_or_none

    drop_stale_migration()
    assert_revision_free(MIGRATION, REVISION_ID)

    head_edits = plan_head_pin(TEST_MIGRATIONS, texts[TEST_MIGRATIONS], "c39f6e24d0b5", "d40a7f35e1c6")
    if head_edits is not None:
        plan[TEST_MIGRATIONS] = head_edits

    # Appended rather than planned as an edit, but still decided BEFORE anything is
    # written, so a half-applied admin router is impossible.
    admin_append = ADMIN_ROUTE_ADD if '@router.get("/discord"' not in texts[ADMIN] else None
    if admin_append is not None:
        for name in ("router = APIRouter", "get_settings", "AuditDep"):
            if name not in texts[ADMIN]:
                die(f"{ADMIN}: {name} is missing - the file has changed shape")

    new_files = {
        MODEL: MODEL_SOURCE,
        MIGRATION: MIGRATION_SOURCE,
        SCHEMA: SCHEMA_SOURCE,
        SERVICE: SERVICE_SOURCE,
        TEST: TEST_SOURCE,
        PANEL: PANEL_SOURCE,
    }
    stale = {p: s for p, s in new_files.items() if not p.exists() or p.read_text() != s}

    if not plan and not stale and admin_append is None:
        print("already installed - nothing to do")
        return

    for path, source in stale.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        print(f"wrote {path}")

    for path, edits in plan.items():
        text = texts[path]
        for anchor, addition, before in edits:
            if before is None:
                text = text.replace(anchor, addition, 1)
            else:
                text = text.replace(anchor, (addition + anchor) if before else (anchor + addition), 1)
        if path is ADMIN and admin_append is not None:
            text = text.rstrip("\n") + "\n\n\n" + admin_append.strip("\n") + "\n"
        path.write_text(text)
        print(f"patched {path}")

    # ADMIN may have had no planned edits (already imported) but still need the routes.
    if admin_append is not None and ADMIN not in plan:
        ADMIN.write_text(texts[ADMIN].rstrip("\n") + "\n\n\n" + admin_append.strip("\n") + "\n")
        print(f"patched {ADMIN}: Discord routes appended")

    print("\nMIGRATION REQUIRED: alembic upgrade head (creates discord_config).")
    print("Admin > System > Discord holds the webhook. Storing it needs SMTP_SECRET_KEY")
    print("(the app's at-rest encryption key); until that is set, DISCORD_WEBHOOK_URL in")
    print("the environment works and the panel says so instead of accepting plaintext.")


if __name__ == "__main__":
    main()
