#!/usr/bin/env python3
"""Restrict "sign out of all devices" to administrators (owner decision).

The endpoint stamps ``sessions_revoked_at``, which invalidates EVERY token issued before
that instant. Making it admin-only means an ordinary user can no longer force a global
sign-out, deliberately or by accident.

Worth stating plainly: this also removes a self-service security control. A user who thinks
their account is compromised can no longer cut their own sessions off and must ask an admin.
That is the trade the owner asked for; the mitigation is that admins can still do it for
anyone, and the account security page still shows every user their own device activity.

Run from the repository root:  python3 scripts/patch-revoke-admin-only.py
"""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("backend/app/api/v1/account.py")
MARKER = "Only administrators"

EDITS: list[tuple[str, str]] = [
    (
        "from fastapi import APIRouter, Depends, Request",
        "from fastapi import APIRouter, Depends, HTTPException, Request, status",
    ),
    (
        '    """Sign out of all devices. Stamps the revoke instant (tokens issued earlier '
        "are rejected\n"
        "    live) and best-effort revokes Firebase refresh tokens. This request's own token "
        "was issued\n"
        '    before \'now\', so the caller is signed out too and must re-authenticate."""\n'
        "    revoked_at = await account_service.revoke_sessions(db, context.user_id)",
        '    """Sign out of all devices. Stamps the revoke instant (tokens issued earlier '
        "are rejected\n"
        "    live) and best-effort revokes Firebase refresh tokens. This request's own token "
        "was issued\n"
        "    before 'now', so the caller is signed out too and must re-authenticate.\n"
        "\n"
        "    ADMIN ONLY (owner decision): revoking sessions invalidates every token issued\n"
        "    before this instant, so it is an administrative action rather than a\n"
        '    self-service one."""\n'
        '    if "admin_panel" not in context.capabilities:\n'
        "        raise HTTPException(\n"
        "            status.HTTP_403_FORBIDDEN,\n"
        '            "Only administrators can sign out all devices",\n'
        "        )\n"
        "    revoked_at = await account_service.revoke_sessions(db, context.user_id)",
    ),
]


def main() -> None:
    if not TARGET.exists():
        print(f"ABORTED: {TARGET} not found - run from the repository root", file=sys.stderr)
        raise SystemExit(1)

    text = TARGET.read_text()
    if MARKER in text:
        print(f"skipped  {TARGET} (already admin-only)")
        return

    for anchor, _ in EDITS:
        count = text.count(anchor)
        if count != 1:
            print(
                f"ABORTED: anchor matched {count} times, expected 1:\n    {anchor[:80]}...",
                file=sys.stderr,
            )
            print("Nothing was written.", file=sys.stderr)
            raise SystemExit(1)

    for anchor, replacement in EDITS:
        text = text.replace(anchor, replacement, 1)
    TARGET.write_text(text)
    print(f"patched  {TARGET} (sign-out-everywhere now requires the admin_panel capability)")


if __name__ == "__main__":
    main()
