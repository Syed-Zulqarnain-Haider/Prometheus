#!/usr/bin/env python3
"""Mount the SMTP settings card on the admin System tab.

``components/admin/smtp-panel.tsx`` is checked out alongside this script; this adds its
import and renders it as its own section between "Operational settings" and "Sync & data
health". It also amends the settings footnote, which currently says credentials are
"never stored in the database" - true for app_settings, but the SMTP password now IS
stored there (encrypted, write-only), and a footnote that contradicts the card above it
reads as a bug.

Anchored: every anchor must appear EXACTLY once or nothing is written. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

PANEL = Path("frontend/components/admin/system-panel.tsx")
SMTP = Path("frontend/components/admin/smtp-panel.tsx")

IMPORT_ANCHOR = 'import { DataHealthClient } from "@/components/admin/data-health-client";\n'
IMPORT_ADD = 'import { SmtpPanel } from "@/components/admin/smtp-panel";\n'

MOUNT_ANCHOR = """      {/* A) Sync / data health (reuses the existing Data Health view) */}
"""
MOUNT_ADD = """      {/* Mail settings - the digest, alerts and scheduled reports all send through
          this. The password is write-only end to end. */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Email delivery
        </h2>
        <SmtpPanel />
      </section>

"""

FOOTNOTE_ANCHOR = """          Only non-secret operational settings are shown here. Credentials and connection
          strings are never stored in the database or displayed — they live in the
          environment / Secret Manager.
"""
FOOTNOTE_NEW = """          Only non-secret operational settings are shown here. Credentials and connection
          strings are never displayed; the one stored credential (the SMTP password below)
          is encrypted at rest and write-only.
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not PANEL.exists():
        die(f"{PANEL} not found - run from the repository root")
    if not SMTP.exists():
        die(f"{SMTP} not found - check it out before running this")

    text = PANEL.read_text()
    if "SmtpPanel" in text:
        print("already mounted - nothing to do")
        return

    for anchor in (IMPORT_ANCHOR, MOUNT_ANCHOR, FOOTNOTE_ANCHOR):
        if text.count(anchor) != 1:
            first = anchor.splitlines()[0].strip()
            die(f"{PANEL}: expected exactly one {first!r}, found {text.count(anchor)}")

    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_ADD, 1)
    text = text.replace(MOUNT_ANCHOR, MOUNT_ADD + MOUNT_ANCHOR, 1)
    text = text.replace(FOOTNOTE_ANCHOR, FOOTNOTE_NEW, 1)
    PANEL.write_text(text)
    print(f"patched {PANEL}: Email delivery section mounted")


if __name__ == "__main__":
    main()
