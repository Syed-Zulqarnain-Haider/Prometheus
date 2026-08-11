#!/usr/bin/env python3
"""Add the edge security headers to an ALREADY-INSTALLED nginx site config.

`docs/nginx-prometheus.conf` carries these headers, but a server whose config was
installed before they were added - and then rewritten in place by certbot - never got
them. Copying the doc file over the live one would destroy certbot's TLS block, so this
patches the live file instead.

Run it on the server, as root:

    sudo python3 scripts/patch-nginx-headers.py

What it does, in order:
  1. Resolves /etc/nginx/sites-enabled/prometheus through its symlink so the real file
     in sites-available is edited (writing through the link would replace it with a
     regular file).
  2. Exits successfully and changes nothing if the headers are already present.
  3. Requires the anchor to appear EXACTLY once; anything else aborts before writing.
  4. Backs up, writes, then runs `nginx -t`. If the test fails the backup is restored
     and nginx is left running its old, working config.
  5. Reloads nginx only after a passing test.

HSTS is included uncommented: this patches a live HTTPS server (certbot has issued the
certificate), which is the precondition the doc file warns about.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

LINK = Path("/etc/nginx/sites-enabled/prometheus")

# Present in the live file exactly once, inside the TLS server block, and untouched by
# certbot - which makes it a stable insertion point.
ANCHOR = "    client_max_body_size 10m;\n"

# Marker proving the patch already ran (also true if someone added the headers by hand).
MARKER = "X-Frame-Options"

HEADERS = """
    # ── Security headers ──────────────────────────────────────────────────────
    # Set at the edge so they cover BOTH apps, including /api/ JSON responses which
    # never pass through Next.js. `always` is required - without it nginx omits them
    # on error responses (4xx/5xx), which is exactly when they still matter.
    # Next.js sets the same headers for its own responses (frontend/next.config.mjs);
    # duplicates are harmless and the redundancy is deliberate.
    add_header X-Frame-Options            "DENY"                                  always;
    add_header Content-Security-Policy    "frame-ancestors 'none'"                always;
    add_header X-Content-Type-Options     "nosniff"                               always;
    add_header Referrer-Policy            "strict-origin-when-cross-origin"       always;
    add_header Permissions-Policy         "camera=(), microphone=(), geolocation=(), payment=(), usb=()" always;
    # Safe here: this server already serves HTTPS with a certbot certificate.
    add_header Strict-Transport-Security  "max-age=63072000; includeSubDomains"   always;

    # Don't advertise the nginx version to scanners.
    server_tokens off;
"""


def fail(message: str) -> None:
    """Abort loudly. Every caller has already left the live config in its ORIGINAL
    state - either by never writing, or by restoring the backup first."""
    print(f"ABORTED: {message}", file=sys.stderr)
    print("No change is in effect; nginx still serves its previous config.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not LINK.exists():
        fail(f"{LINK} does not exist - is the site installed under a different name?")

    conf = LINK.resolve()  # edit the real file, never the symlink
    text = conf.read_text()

    if MARKER in text:
        print(f"skipped  {conf} (security headers already present)")
        return

    count = text.count(ANCHOR)
    if count != 1:
        fail(
            f"expected the anchor {ANCHOR.strip()!r} exactly once in {conf}, found {count}. "
            "The file has drifted - patch it by hand."
        )

    backup = conf.with_suffix(f"{conf.suffix}.bak.{int(time.time())}")
    shutil.copy2(conf, backup)
    conf.write_text(text.replace(ANCHOR, ANCHOR + HEADERS))
    print(f"patched  {conf}")
    print(f"backup   {backup}")

    test = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
    if test.returncode != 0:
        shutil.copy2(backup, conf)
        print(test.stderr, file=sys.stderr)
        fail("`nginx -t` rejected the patched config - the backup has been restored")

    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    print("nginx -t passed; nginx reloaded. Security headers are live on /api/ too.")


if __name__ == "__main__":
    main()
