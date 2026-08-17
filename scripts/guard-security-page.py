#!/usr/bin/env python3
"""Block non-admins from the Security page itself, not just its nav link.

``restrict-security-page.py`` hid the sidebar entry, but hiding a link restricts
nothing: /security typed into the address bar still rendered. This adds the guard to
the component - a non-admin sees a "not available" panel instead of the page, and the
security queries never run for them.

The check uses ``useMe().capabilities`` - the same capability set the admin panel and
chat oversight already gate on - so there is one notion of "admin" in the app, not two.

Anchored: every anchor must appear EXACTLY once or nothing is written. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

CLIENT = Path("frontend/components/account/security-client.tsx")

IMPORT_ANCHOR = 'import { useRevokeSessions, useSecurity } from "@/lib/api-hooks";\n'
IMPORT_ADD = 'import { useMe } from "@/lib/api-hooks";\n'

BODY_ANCHOR = """export function SecurityClient() {
  const security = useSecurity();
"""
BODY_ADD = """export function SecurityClient() {
  // Admin-only (owner decision). The hook order is unconditional - the early return
  // below happens AFTER every hook has run, so React's rules are respected.
  const me = useMe();
  const isAdmin = me.data?.capabilities.includes("admin_panel") ?? false;
  const security = useSecurity();
"""

GUARD_ANCHOR = "  const [confirming, setConfirming] = useState(false);\n"
GUARD_ADD = """
  // Wait for the profile before deciding - rendering "no access" while it loads would
  // flash a denial at an admin on every page load.
  if (me.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }
  if (!isAdmin) {
    return (
      <div className="space-y-4">
        <PageHeader title="Security" description="Administrator access only." />
        <Card>
          <CardContent className="py-10 text-center">
            <ShieldAlert className="mx-auto h-8 w-8 text-muted-foreground" />
            <p className="mt-3 text-sm font-medium">This page is restricted</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Security settings are managed by an administrator. Contact one if you need a
              session ended or your sign-in reviewed.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not CLIENT.exists():
        die(f"{CLIENT} not found - run from the repository root")
    text = CLIENT.read_text()

    if "This page is restricted" in text:
        print("already guarded - nothing to do")
        return

    for anchor in (IMPORT_ANCHOR, BODY_ANCHOR, GUARD_ANCHOR):
        if text.count(anchor) != 1:
            die(f"{CLIENT}: expected exactly one {anchor.splitlines()[0]!r}, found {text.count(anchor)}")

    text = text.replace(IMPORT_ANCHOR, IMPORT_ADD + IMPORT_ANCHOR, 1)
    text = text.replace(BODY_ANCHOR, BODY_ADD, 1)
    text = text.replace(GUARD_ANCHOR, GUARD_ANCHOR + GUARD_ADD, 1)
    CLIENT.write_text(text)

    print(f"patched {CLIENT}: non-admins are turned away from /security")
    print("\nNOTE: the backend /security endpoints still answer any authenticated caller")
    print("with THEIR OWN session data (no cross-user leak). Gate them server-side too if")
    print("the API surface itself must be admin-only.")


if __name__ == "__main__":
    main()
