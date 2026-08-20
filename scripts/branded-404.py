#!/usr/bin/env python3
"""Give the app a branded 404 instead of Next.js's bare default.

The default not-found page is an unbranded dead end: no navigation, no way back, and it
looks nothing like the product around it. Worse, in THIS product a 404 is common for
signed-in users by design - an out-of-scope app answers 404 exactly like a nonexistent
one - so the page people hit on a mistyped or out-of-scope URL is part of the product,
not an edge case.

The copy deliberately says the page "does not exist or is outside your access" WITHOUT
distinguishing the two, because not distinguishing them is the whole point of the 404
policy. One file, additive, no anchors: App Router picks up app/not-found.tsx by
convention.
"""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("frontend/app/not-found.tsx")

CONTENT = '''import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm rounded-lg border bg-card p-6 text-center shadow-sm">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          404
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Prometheus</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          This page does not exist, or it is outside your access &mdash; the two look the
          same here on purpose.
        </p>
        <Link
          href="/overview"
          className="mt-6 inline-block rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted"
        >
          Back to Overview
        </Link>
      </div>
    </main>
  );
}
'''


def main() -> int:
    if not Path("frontend/app").is_dir():
        print("ABORTED: run this from the repository root")
        return 1
    if TARGET.exists():
        if TARGET.read_text() == CONTENT:
            print("nothing to do - already applied")
            return 0
        print(f"ABORTED: {TARGET} already exists with different content - not overwriting")
        print("-" * 60)
        print(TARGET.read_text())
        return 1
    TARGET.write_text(CONTENT)
    print(f"wrote {TARGET}")
    print()
    print("Rebuild the frontend to pick it up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
