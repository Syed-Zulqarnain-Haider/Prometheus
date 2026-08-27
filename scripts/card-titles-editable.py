#!/usr/bin/env python3
"""Let an admin rename any card, table or page heading, in place.

WHAT A HEADING IS IDENTIFIED BY
-------------------------------
Not by where it appears. A key is derived from the heading's own built-in text
("Revenue vs Spend" -> ``revenue-vs-spend``), so the same heading on two pages is one
name, moving a card between pages does not lose its name, and no call site has to be
edited to opt in. The trade-off is deliberate and worth saying out loud: two DIFFERENT
cards that happen to share a heading share a name. That is nearly always what someone
means by "rename this heading", and the alternative - a hand-maintained id at every one
of the fifty-odd call sites - is a list that goes stale the first time a card moves.

A trailing live count is split off before keying, so "All Apps by Revenue (137)" keys on
"all apps by revenue" and keeps its count after the rename. Otherwise the key would
change every time the data did, and the name would appear to un-set itself.

WHAT IS STORED
--------------
Only the OVERRIDE. The built-in text stays in the code, so clearing a row restores it
exactly - including a later change to the default, which a copied-out value would have
silently frozen. Typing the built-in name back in clears the row rather than storing a
duplicate, for the same reason.

WHERE IT APPLIES
----------------
``CardTitle`` (every card and every table built on one - the chart cards and the shared
metric table both funnel their titles through it), the KPI cards, and the page headings.
A heading whose text is not plain text at the top level is left alone rather than
guessed at, and the run says so.

SECURITY
--------
The pencil is shown to admins; that is cosmetic. ``PUT``/``DELETE`` sit behind
``require_capability("admin_panel")`` server-side, the key is format-validated before it
reaches the database, the label is length-capped and stripped of control characters, and
both mutations are audit-logged like every other admin action.

Sections are independent - each either applies completely or is skipped and reported,
except that the frontend is not written at all unless the API it calls exists.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(".")
VERSIONS = ROOT / "backend/alembic/versions"
MIGRATION_ID = "d5f1a8c37b90"

report: list[str] = []
skipped: list[str] = []
pending: dict[Path, str] = {}


def window(text: str, needle: str, before: int = 3, after: int = 12) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(f"      | {ln}" for ln in lines[max(0, i - before) : i + after])
    return "      | (not found in this file)"


# ══ backend ════════════════════════════════════════════════════════════════════════
MODEL = '''"""Admin-set display names for dashboard headings (``ui_labels``).

Only the OVERRIDE is stored. Every heading's built-in text lives in the code, so
deleting a row here restores it exactly - including a later change to that default,
which a copied-out value would have frozen without anyone noticing.

The key is derived from the heading's own built-in text, not from where it appears, so
a card keeps its name when it moves and the same heading in two places is one name.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UiLabel(Base):
    __tablename__ = "ui_labels"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
'''

SCHEMA = '''"""Schemas for admin-set heading names."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# A heading is a heading, not a paragraph. The cap is enforced here AND in the service,
# because this schema guards one route and the service guards every caller.
MAX_LABEL_LEN = 80


class UiLabelOut(BaseModel):
    key: str
    label: str
    updated_at: datetime | None = None


class UiLabelUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=MAX_LABEL_LEN)
'''

SERVICE = '''"""Read/write admin-set heading names, backed by ``ui_labels``.

The key arrives from a URL path, so it is format-checked before it reaches a query -
not because the query could be injected (it is parameterised like everything else), but
because an unbounded key would let anyone write unbounded rows into a table the whole
application reads on every page load.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UiLabel
from app.schemas.ui_labels import MAX_LABEL_LEN, UiLabelOut

# Slug shape, matching what the frontend derives from a heading's own text.
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,190}$")
# Anything in this class would be invisible in a heading and is never wanted in one.
_CONTROL_RE = re.compile(r"[\\x00-\\x1f\\x7f]")


def validate_key(key: str) -> str:
    if not KEY_RE.match(key):
        raise ValueError("Unrecognised heading")
    return key


def clean_label(raw: str) -> str:
    """Strip, collapse whitespace, drop control characters, enforce the cap.

    The value is rendered as text by React, so this is not an escaping step - it is
    about what a heading is allowed to BE. A name with a newline in it is not a name.
    """
    label = _CONTROL_RE.sub("", raw).strip()
    label = re.sub(r"\\s+", " ", label)
    if not label:
        raise ValueError("A heading cannot be empty")
    if len(label) > MAX_LABEL_LEN:
        raise ValueError(f"A heading can be at most {MAX_LABEL_LEN} characters")
    return label


async def all_labels(db: AsyncSession) -> dict[str, str]:
    """Every override, as ``{key: label}``. Read by any authenticated user."""
    rows = (await db.scalars(select(UiLabel))).all()
    return {row.key: row.label for row in rows}


async def list_labels(db: AsyncSession) -> list[UiLabelOut]:
    rows = (await db.scalars(select(UiLabel).order_by(UiLabel.key))).all()
    return [UiLabelOut(key=row.key, label=row.label, updated_at=row.updated_at) for row in rows]


async def set_label(db: AsyncSession, key: str, raw_label: str, actor_id: uuid.UUID) -> UiLabelOut:
    validate_key(key)
    label = clean_label(raw_label)
    now = datetime.now(UTC)
    await db.execute(
        pg_insert(UiLabel)
        .values(key=key, label=label, updated_at=now, updated_by=actor_id)
        .on_conflict_do_update(
            index_elements=[UiLabel.key],
            set_={"label": label, "updated_at": now, "updated_by": actor_id},
        )
    )
    await db.commit()
    return UiLabelOut(key=key, label=label, updated_at=now)


async def clear_label(db: AsyncSession, key: str) -> bool:
    """Drop the override so the built-in name applies again. True if one existed.

    RETURNING rather than a row count: the count is untyped at this layer, and this says
    what was actually removed in the same round trip as removing it.
    """
    validate_key(key)
    removed = (
        await db.scalars(delete(UiLabel).where(UiLabel.key == key).returning(UiLabel.key))
    ).all()
    await db.commit()
    return bool(removed)
'''

ROUTES = '''"""Heading names: everyone reads them, admins change them.

Two routers rather than one, because the two halves have genuinely different audiences.
The read is on the hot path - every page asks for it once - and must be available to any
authenticated user, or the names simply would not render for anyone but an admin. The
writes are ordinary admin actions: capability-gated, validated, and audited.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import CurrentUser, DbSession, require_capability
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.schemas.ui_labels import UiLabelOut, UiLabelUpdate
from app.services import ui_label_service
from app.services.audit import AuditDep

router = APIRouter(prefix="/labels", tags=["labels"], dependencies=[Depends(enforce_rate_limit)])

admin_router = APIRouter(
    prefix="/admin/labels",
    tags=["labels"],
    dependencies=[Depends(enforce_rate_limit), Depends(require_capability("admin_panel"))],
)


@router.get("")
async def get_labels(context: CurrentUser, db: DbSession) -> dict[str, str]:
    """Every heading override, as ``{key: label}``. Non-secret, read by every page."""
    return await ui_label_service.all_labels(db)


@admin_router.get("", response_model=list[UiLabelOut])
async def list_labels(db: DbSession) -> list[UiLabelOut]:
    return await ui_label_service.list_labels(db)


@admin_router.put("/{key}", response_model=UiLabelOut)
async def set_label(
    key: str,
    body: UiLabelUpdate,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> UiLabelOut:
    try:
        label = await ui_label_service.set_label(db, key, body.label, context.user_id)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_rename_heading",
        resource=key,
        detail={"label": label.label},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return label


@admin_router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def reset_label(
    key: str,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> Response:
    """Restore the built-in name. Deleting one that was never set is not an error -
    the caller asked for 'no override', and afterwards there is none."""
    try:
        existed = await ui_label_service.clear_label(db, key)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_reset_heading",
        resource=key,
        detail={"existed": existed},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
'''

MIGRATION = '''"""add ui_labels (admin-set display names for dashboard headings)

Holds only the OVERRIDE for a heading; the built-in text stays in the application code,
so deleting a row restores it.

Revision ID: {rev}
Revises: {down}
Create Date: {created}
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "{rev}"
down_revision: str | tuple[str, ...] | None = "{down}"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ui_labels",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_ui_labels_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_ui_labels")),
    )


def downgrade() -> None:
    op.drop_table("ui_labels")
'''

TESTS = '''"""Heading names: who may read them, who may change them, and what is stored.

The interesting cases are not the happy path. A viewer must be able to READ the names
(otherwise nobody but an admin sees a renamed card) while being unable to change one;
the key is attacker-controlled path input and must be rejected on shape; and clearing an
override has to restore the built-in name rather than store an empty string.
"""

from typing import Any

from app.models import AuditLog
from sqlalchemy import select

from tests.conftest import MetricsEnv


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def test_everyone_reads_headings_only_admins_change_them(
    metrics_env: MetricsEnv,
) -> None:
    c = metrics_env.client

    readable = await c.get("/api/v1/labels", headers=_auth("viewer"))
    assert readable.status_code == 200
    assert readable.json() == {}

    for role in ("viewer", "finance", "marketing"):
        denied = await c.put(
            "/api/v1/admin/labels/gross-profit",
            json={"label": "Contribution"},
            headers=_auth(role),
        )
        assert denied.status_code == 403, f"{role} renamed a heading"
        assert (
            await c.delete("/api/v1/admin/labels/gross-profit", headers=_auth(role))
        ).status_code == 403


async def test_rename_is_visible_to_everyone_and_audited(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    resp = await c.put(
        "/api/v1/admin/labels/gross-profit",
        json={"label": "  Contribution   Margin  "},
        headers=_auth("admin"),
    )
    assert resp.status_code == 200
    # Whitespace is collapsed, not preserved: a heading is a name, not formatting.
    assert resp.json()["label"] == "Contribution Margin"

    seen = (await c.get("/api/v1/labels", headers=_auth("viewer"))).json()
    assert seen["gross-profit"] == "Contribution Margin"

    async with metrics_env.sessionmaker() as session:
        stmt = select(AuditLog.action).where(AuditLog.action == "admin_rename_heading")
        assert "admin_rename_heading" in (await session.execute(stmt)).scalars().all()


async def test_reset_restores_the_built_in_name(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    await c.put(
        "/api/v1/admin/labels/top-apps", json={"label": "Best sellers"}, headers=_auth("admin")
    )
    assert (
        await c.delete("/api/v1/admin/labels/top-apps", headers=_auth("admin"))
    ).status_code == 204
    assert (await c.get("/api/v1/labels", headers=_auth("admin"))).json() == {}

    # Clearing one that was never set is not an error - the caller asked for "no
    # override", and afterwards there is none.
    assert (
        await c.delete("/api/v1/admin/labels/never-set", headers=_auth("admin"))
    ).status_code == 204


async def test_malformed_keys_and_labels_are_refused(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    for key in ("Gross Profit", "-leading", "a" * 250, "../etc/passwd", "drop;table"):
        resp = await c.put(
            f"/api/v1/admin/labels/{key}", json={"label": "x"}, headers=_auth("admin")
        )
        assert resp.status_code in (400, 404), f"key {key!r} was accepted"

    for label in ("", "   ", "a" * 200):
        bad: dict[str, Any] = {"label": label}
        resp = await c.put("/api/v1/admin/labels/ok-key", json=bad, headers=_auth("admin"))
        assert resp.status_code == 422 or resp.status_code == 400, f"label {label!r} stored"
'''


def write_backend() -> bool:
    files = {
        ROOT / "backend/app/models/ui_labels.py": MODEL,
        ROOT / "backend/app/schemas/ui_labels.py": SCHEMA,
        ROOT / "backend/app/services/ui_label_service.py": SERVICE,
        ROOT / "backend/app/api/v1/ui_labels.py": ROUTES,
        ROOT / "backend/tests/test_ui_labels.py": TESTS,
    }
    for path in files:
        if not path.parent.is_dir():
            skipped.append(f"[backend] {path.parent} does not exist - nothing was written.")
            return False

    # models/__init__.py: register so Base.metadata (and therefore the test schema) has it.
    init = ROOT / "backend/app/models/__init__.py"
    init_text = init.read_text() if init.exists() else ""
    if "UiLabel" not in init_text:
        imports = list(re.finditer(r"^from app\.models\.[a-z_]+ import .+$", init_text, re.M))
        all_block = re.search(r"^__all__ = \[\n(?P<body>(?:.*\n)*?)\]", init_text, re.M)
        if not imports or all_block is None:
            skipped.append(
                f"[backend] {init} does not look the way this expects (a run of\n"
                "  `from app.models.x import Y` lines and an `__all__ = [...]` list), so\n"
                "  the model was not registered and nothing was written.\n"
                + window(init_text, "__all__")
            )
            return False
        last = imports[-1]
        init_text = (
            init_text[: last.end()]
            + "\nfrom app.models.ui_labels import UiLabel"
            + init_text[last.end() :]
        )
        all_block = re.search(r"^__all__ = \[\n(?P<body>(?:.*\n)*?)\]", init_text, re.M)
        assert all_block is not None
        insert_at = all_block.end() - 1
        init_text = init_text[:insert_at] + '    "UiLabel",\n' + init_text[insert_at:]
        pending[init] = init_text

    # main.py: import the module and mount both routers.
    main = ROOT / "backend/app/main.py"
    if not main.exists():
        skipped.append(f"[backend] {main} is missing - nothing was written.")
        return False
    main_text = main.read_text()
    if "ui_labels_routes" not in main_text:
        import_anchor = "from app.api.v1 import views as views_routes\n"
        mount_anchor = "app.include_router(meta_routes.router, prefix=settings.api_v1_prefix)\n"
        for label, anchor in (("import", import_anchor), ("include_router", mount_anchor)):
            if main_text.count(anchor) != 1:
                skipped.append(
                    f"[backend] {main}: expected exactly one {label} line to anchor on:\n"
                    f"      {anchor.strip()}\n" + window(main_text, "meta_routes")
                )
                return False
        main_text = main_text.replace(
            import_anchor,
            "from app.api.v1 import ui_labels as ui_labels_routes\n" + import_anchor,
            1,
        )
        main_text = main_text.replace(
            mount_anchor,
            mount_anchor
            + "app.include_router(ui_labels_routes.router, prefix=settings.api_v1_prefix)\n"
            + "app.include_router(ui_labels_routes.admin_router, prefix=settings.api_v1_prefix)\n",
            1,
        )
        pending[main] = main_text

    for path, content in files.items():
        if path.exists() and "ui_labels" in path.read_text() and path.name != "ui_labels.py":
            continue
        pending[path] = content
    return True


def detect_heads() -> list[str]:
    """Every revision nothing points at. Tuple down_revisions (merge points) count."""
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        rev = re.search(r'^revision(?::\s*[^=\n]+)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        if rev:
            revisions.add(rev.group(1))
        down = re.search(r"^down_revision(?::[^=\n]+)?\s*=\s*(.+)$", text, re.M)
        if down:
            parents.update(re.findall(r'["\']([^"\']+)["\']', down.group(1)))
    return sorted(revisions - parents)


def write_migration() -> bool:
    if not VERSIONS.is_dir():
        skipped.append(f"[migration] {VERSIONS} is missing - the table has no migration.")
        return False
    if list(VERSIONS.glob(f"*{MIGRATION_ID}*.py")):
        report.append(f"[migration] {MIGRATION_ID} already present - left alone")
        return True

    heads = detect_heads()
    if len(heads) != 1:
        skipped.append(
            f"[migration] expected exactly one alembic head, found {heads or 'none'}.\n"
            "  Creating a revision on top of a forked history would fork it again, and\n"
            "  `alembic upgrade head` refuses to guess - so nothing was written at all."
        )
        return False

    stamp = datetime.now(UTC)
    path = VERSIONS / f"{stamp:%Y%m%d_%H%M}_{MIGRATION_ID}_add_ui_labels.py"
    pending[path] = MIGRATION.format(rev=MIGRATION_ID, down=heads[0], created=stamp.isoformat())
    report.append(f"[migration] {path.name} (down_revision={heads[0]})")
    return True


# ══ frontend ═══════════════════════════════════════════════════════════════════════
LABEL_KEY_LIB = '''/** How a heading's stored key is derived from its own built-in text.
 *
 *  Deliberately in its own module with no React, no fetch and no Firebase in it: this is
 *  the half of the feature that has to agree exactly with the server, so it should be
 *  testable on its own rather than only through a component.
 */

/** A trailing "(137)" is a live count, not part of the name. It is split off before the
 *  key is derived, so a rename survives the data changing - otherwise the key would move
 *  every time a row appeared and the name would look as though it had un-set itself. */
const COUNT_SUFFIX = /\\s*\\(\\s*[\\d,.]+\\s*\\)\\s*$/;

export function splitTitle(text: string): { stem: string; suffix: string } {
  const match = text.match(COUNT_SUFFIX);
  if (!match || match.index === undefined) return { stem: text.trim(), suffix: "" };
  return { stem: text.slice(0, match.index).trim(), suffix: match[0] };
}

/** The key a heading is stored under: derived from its own built-in text, so no call
 *  site has to be edited to opt in and a card keeps its name when it moves page.
 *
 *  Must agree with KEY_RE in the backend service (`^[a-z0-9][a-z0-9._:-]{0,190}$`) - the
 *  server rejects anything else, so a heading that slugs to an empty or leading-hyphen
 *  key is treated as not renamable rather than sent and refused.
 */
export function labelKeyFor(text: string): string {
  return splitTitle(text)
    .stem.toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 190)
    .replace(/-+$/g, "");
}
'''

LABEL_KEY_TESTS = '''import { describe, expect, it } from "vitest";

import { labelKeyFor, splitTitle } from "@/lib/label-key";

// The key is what ties a renamed heading to the heading it renamed. If it moves, the
// name silently detaches and the card goes back to its built-in text with no error
// anywhere - so the derivation is pinned here rather than left to be discovered.
//
// It also has to satisfy the server's own KEY_RE (^[a-z0-9][a-z0-9._:-]{0,190}$). A key
// that fails it is refused at the API, so anything that cannot produce a valid one must
// produce an EMPTY string, which the component reads as "not renamable".
const SERVER_KEY_RE = /^[a-z0-9][a-z0-9._:-]{0,190}$/;

describe("labelKeyFor", () => {
  it("slugs an ordinary heading", () => {
    expect(labelKeyFor("Revenue vs Spend")).toBe("revenue-vs-spend");
    expect(labelKeyFor("Paid vs Organic by App")).toBe("paid-vs-organic-by-app");
  });

  it("keeps an ampersand readable instead of dropping it", () => {
    // "CPI & CTR" and "CPI CTR" would otherwise collide with each other.
    expect(labelKeyFor("CPI & CTR by Network")).toBe("cpi-and-ctr-by-network");
  });

  it("ignores a live count, so the key survives the data changing", () => {
    expect(labelKeyFor("All Apps by Revenue (137)")).toBe(labelKeyFor("All Apps by Revenue"));
    expect(labelKeyFor("Unmapped apps (0)")).toBe("unmapped-apps");
  });

  it("returns nothing for a heading with no usable text", () => {
    for (const text of ["", "   ", "***", "()"]) {
      expect(labelKeyFor(text)).toBe("");
    }
  });

  it("only ever produces keys the server will accept", () => {
    const headings = [
      "Revenue vs Spend",
      "CPI & CTR by Network",
      "All Apps by Revenue (1,204)",
      "  Data as of  ",
      "ROAS %",
      "100",
      "-".repeat(50),
      "A".repeat(300),
    ];
    for (const heading of headings) {
      const key = labelKeyFor(heading);
      if (key === "") continue; // not renamable - never sent
      expect(key, heading).toMatch(SERVER_KEY_RE);
    }
  });
});

describe("splitTitle", () => {
  it("separates a trailing count so it can be re-attached after a rename", () => {
    expect(splitTitle("Unmapped apps (12)")).toEqual({ stem: "Unmapped apps", suffix: " (12)" });
  });

  it("leaves a heading that merely contains brackets alone", () => {
    expect(splitTitle("Revenue (net) by pod")).toEqual({
      stem: "Revenue (net) by pod",
      suffix: "",
    });
  });
});
'''

LABELS_LIB = '''"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";

export { labelKeyFor, splitTitle } from "@/lib/label-key";

/** Every override, as { key: label }. One request per session, shared by every heading
 *  on the page - they all read the same cache entry. */
export function useUiLabels() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["ui-labels"],
    queryFn: () => apiFetch<Record<string, string>>("/api/v1/labels"),
    enabled: Boolean(user),
    staleTime: 5 * 60 * 1000,
  });
}

export function useSetUiLabel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, label }: { key: string; label: string }) =>
      apiFetch<{ key: string; label: string }>(
        `/api/v1/admin/labels/${encodeURIComponent(key)}`,
        { method: "PUT", body: JSON.stringify({ label }) },
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ui-labels"] }),
  });
}

export function useResetUiLabel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (key: string) =>
      apiFetch<void>(`/api/v1/admin/labels/${encodeURIComponent(key)}`, {
        method: "DELETE",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ui-labels"] }),
  });
}
'''

EDITABLE_TITLE = '''"use client";

import { Check, Pencil, RotateCcw, X } from "lucide-react";
import * as React from "react";

import { useMe } from "@/lib/api-hooks";
import {
  labelKeyFor,
  splitTitle,
  useResetUiLabel,
  useSetUiLabel,
  useUiLabels,
} from "@/lib/ui-labels";

const MAX_LABEL_LEN = 80;

/** The heading's own text, taken from the TOP LEVEL of its children only.
 *
 *  Deliberately not recursive. A heading assembled out of other components has no one
 *  obvious piece of text to rename, and swapping the wrong one out would quietly delete
 *  part of the header. Those headings are left exactly as they are instead. */
function topLevelText(children: React.ReactNode): string {
  return React.Children.toArray(children)
    .filter((child) => typeof child === "string" || typeof child === "number")
    .map(String)
    .join("")
    .trim();
}

/** The children with the first text node swapped for the override, and any other text
 *  nodes dropped - they were part of the same run of text. Elements (an icon, a badge)
 *  keep their place. */
function withText(children: React.ReactNode, replacement: string): React.ReactNode {
  let used = false;
  return React.Children.toArray(children)
    .map((child, index) => {
      if (typeof child !== "string" && typeof child !== "number") return child;
      if (used) return null;
      used = true;
      return <React.Fragment key={`label-${index}`}>{replacement}</React.Fragment>;
    })
    .filter((child) => child !== null);
}

/** A heading an admin can rename in place.
 *
 *  Wraps the text, not the layout: the surrounding element keeps its own classes, so
 *  every card, table and page heading looks exactly as it did until someone renames it.
 *  The pencil is admin-only, which is cosmetic - the server is what enforces it. */
export function EditableTitle({ children }: { children: React.ReactNode }) {
  const original = topLevelText(children);
  const { stem, suffix } = splitTitle(original);
  const key = original ? labelKeyFor(original) : "";

  const { data: me } = useMe();
  const { data: labels } = useUiLabels();
  const setLabel = useSetUiLabel();
  const resetLabel = useResetUiLabel();
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState("");

  const override = key ? labels?.[key] : undefined;
  const canEdit = Boolean(key) && (me?.capabilities ?? []).includes("admin_panel");

  // No usable text to key off - a heading built from other components. Rendered
  // untouched rather than guessed at.
  if (!key) return <>{children}</>;

  function save() {
    const next = draft.trim().slice(0, MAX_LABEL_LEN);
    if (!next || next === stem) {
      // Typing the built-in name back is a RESET, not an override that happens to
      // match: stored that way, a later change to the built-in name still reaches here.
      if (override) resetLabel.mutate(key);
      setEditing(false);
      return;
    }
    setLabel.mutate({ key, label: next }, { onSettled: () => setEditing(false) });
  }

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1 normal-case tracking-normal">
        <input
          autoFocus
          value={draft}
          maxLength={MAX_LABEL_LEN}
          aria-label={`Rename "${stem}"`}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              save();
            }
            if (event.key === "Escape") {
              event.preventDefault();
              setEditing(false);
            }
          }}
          className="h-6 w-44 rounded-[var(--radius-inner)] border border-input bg-background px-1.5 text-xs outline-none focus:ring-1 focus:ring-ring"
        />
        <button
          type="button"
          aria-label="Save this name"
          onClick={save}
          className="text-muted-foreground hover:text-foreground"
        >
          <Check className="h-3.5 w-3.5" aria-hidden />
        </button>
        <button
          type="button"
          aria-label="Cancel"
          onClick={() => setEditing(false)}
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
        {override && (
          <button
            type="button"
            aria-label="Restore the built-in name"
            title="Restore the built-in name"
            onClick={() => {
              resetLabel.mutate(key);
              setEditing(false);
            }}
            className="text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
          </button>
        )}
      </span>
    );
  }

  return (
    <span className="group/heading inline-flex items-center gap-1.5">
      {override ? withText(children, `${override}${suffix}`) : children}
      {canEdit && (
        <button
          type="button"
          aria-label={`Rename "${stem}"`}
          title="Rename this heading. Everyone sees the new name."
          onClick={() => {
            setDraft(override ?? stem);
            setEditing(true);
          }}
          className="opacity-0 transition-opacity group-hover/heading:opacity-100 focus-visible:opacity-100 print:hidden"
        >
          <Pencil className="h-3 w-3" aria-hidden />
        </button>
      )}
    </span>
  );
}
'''

CARD_TITLE_OLD = '''const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground",
        className,
      )}
      {...props}
    />
  ),
);'''

CARD_TITLE_NEW = '''const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground",
        className,
      )}
      {...props}
    >
      {/* Every card heading - and every table built on one - is renamable in place by
          an admin. EditableTitle decides whether it CAN be renamed (it needs plain text
          to key off) and whether this viewer may; the server enforces the second. */}
      <EditableTitle>{children}</EditableTitle>
    </div>
  ),
);'''

# The KPI label is matched by SHAPE, not by its exact classes: a KPI card's caption is
# "the element that renders {label}", and the class list on it is styling that moves.
# Anchoring on the full class string made this miss the moment the card was restyled.
KPI_LABEL_RE = re.compile(
    r"(?P<open><div[^>]*className=\"[^\"]*uppercase[^\"]*\"[^>]*>)"
    r"(?P<gap1>\s*)\{label\}(?P<gap2>\s*)"
    r"(?P<close></div>)"
)

PAGE_TITLE_OLD = '''      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>'''
PAGE_TITLE_NEW = '''      <h1 className="text-2xl font-semibold tracking-tight">
        <EditableTitle>{title}</EditableTitle>
      </h1>'''


def use_client(text: str) -> str:
    return text if text.lstrip().startswith('"use client"') else '"use client";\n\n' + text


_IMPORT_RE = re.compile(r'^import .+ from "(?P<path>[^"]+)";$', re.M)


def add_import(text: str, line: str, module: str) -> str:
    """Add an import, in the place this codebase would have put it.

    Below the "use client" directive (an import above it makes the directive inert), and
    in path order among the other ``@/`` imports rather than tacked on the end - so the
    diff reads like the file was always written that way.
    """
    if line in text:
        return text
    locals_ = [m for m in _IMPORT_RE.finditer(text) if m.group("path").startswith("@/")]
    after = next((m for m in locals_ if m.group("path") > module), None)
    if after is not None:
        return text[: after.start()] + line + "\n" + text[after.start() :]
    if locals_:
        end = locals_[-1].end()
        return text[:end] + "\n" + line + text[end:]
    imports = list(_IMPORT_RE.finditer(text))
    if imports:
        end = imports[-1].end()
        return text[:end] + "\n\n" + line + text[end:]
    directive = re.search(r'^"use client";\n', text, re.M)
    at = directive.end() + 1 if directive else 0
    return text[:at] + line + "\n\n" + text[at:]


def patch_host(label: str, path: Path, old: str, new: str, import_line: str) -> None:
    if not path.exists():
        skipped.append(f"[{label}] {path} does not exist here - that heading stays fixed.")
        return
    text = path.read_text()
    if "EditableTitle" in text:
        report.append(f"[{label}] already wired - left alone")
        return
    if text.count(old) != 1:
        skipped.append(
            f"[{label}] {path}: expected exactly one match, found {text.count(old)}.\n"
            "  Nothing was changed there; the other headings are unaffected. On disk:\n"
            + window(text, old.strip().splitlines()[0][:50])
        )
        return
    text = use_client(
        add_import(text.replace(old, new, 1), import_line, "@/components/ui/editable-title")
    )
    pending[path] = text
    report.append(f"[{label}] {path}: heading is renamable in place")


def patch_kpi(path: Path, import_line: str) -> None:
    """The KPI caption, found by shape rather than by its class list.

    If it cannot be found the file is PRINTED rather than guessed at - a KPI card is
    the one heading on the Overview somebody is most likely to want renamed, so
    "skipped, work it out next time" is not good enough on its own.
    """
    label = "kpi cards"
    if not path.exists():
        skipped.append(f"[{label}] {path} does not exist here - KPI captions stay fixed.")
        return
    text = path.read_text()
    if "EditableTitle" in text:
        report.append(f"[{label}] already wired - left alone")
        return

    hits = list(KPI_LABEL_RE.finditer(text))
    if len(hits) != 1:
        skipped.append(
            f"[{label}] {path}: found {len(hits)} elements rendering {{label}} with an\n"
            "  uppercase class, expected exactly one. Nothing was changed there; the other\n"
            "  headings are unaffected. The file, so the next edit can be exact:\n"
            + "\n".join(f"      | {ln}" for ln in text.splitlines())
        )
        return

    hit = hits[0]
    replacement = (
        hit.group("open")
        + hit.group("gap1")
        + "<EditableTitle>{label}</EditableTitle>"
        + hit.group("gap2")
        + hit.group("close")
    )
    text = text[: hit.start()] + replacement + text[hit.end() :]
    text = use_client(add_import(text, import_line, "@/components/ui/editable-title"))
    pending[path] = text
    report.append(f"[{label}] {path}: KPI captions are renamable in place")


def write_frontend() -> None:
    lib = ROOT / "frontend/lib/ui-labels.ts"
    component = ROOT / "frontend/components/ui/editable-title.tsx"
    if not lib.parent.is_dir() or not component.parent.is_dir():
        skipped.append("[frontend] frontend/lib or frontend/components/ui is missing.")
        return
    pending[ROOT / "frontend/lib/label-key.ts"] = LABEL_KEY_LIB
    pending[lib] = LABELS_LIB
    pending[component] = EDITABLE_TITLE
    tests = ROOT / "frontend/tests"
    if tests.is_dir():
        pending[tests / "ui-labels.test.ts"] = LABEL_KEY_TESTS
    else:
        report.append("[frontend] no frontend/tests directory - the key test was not added")

    import_line = 'import { EditableTitle } from "@/components/ui/editable-title";'
    patch_host(
        "cards+tables",
        ROOT / "frontend/components/ui/card.tsx",
        CARD_TITLE_OLD,
        CARD_TITLE_NEW,
        import_line,
    )
    patch_kpi(ROOT / "frontend/components/overview/kpi-card.tsx", import_line)
    patch_host(
        "page headings",
        ROOT / "frontend/components/layout/page-header.tsx",
        PAGE_TITLE_OLD,
        PAGE_TITLE_NEW,
        import_line,
    )


def main() -> int:
    if not (ROOT / "backend").is_dir() or not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    # The frontend calls an API. If the API cannot be written, the frontend is not
    # written either - a rename button that 404s is worse than no rename button.
    if write_backend() and write_migration():
        write_frontend()
    else:
        skipped.append(
            "[frontend] not written: the API it calls could not be added, and a rename\n"
            "  control that has nothing to call is worse than no control at all."
        )
        pending.clear()

    if not pending:
        print("NOTHING WAS WRITTEN.")
        for entry in skipped:
            print(f"\n  {entry}")
        return 0

    for path, content in pending.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    print(f"  - {len(pending)} file(s) written")
    for line in report:
        print(f"  - {line}")
    if skipped:
        print("\nSKIPPED (nothing written for these):")
        for entry in skipped:
            print(f"\n  {entry}")
    print(
        "\nHow it works: hover a card, table or page heading as an admin and a pencil\n"
        "appears. Enter saves, Escape cancels, and the circular arrow puts the built-in\n"
        "name back. Everyone sees the new name; the same heading elsewhere follows it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
