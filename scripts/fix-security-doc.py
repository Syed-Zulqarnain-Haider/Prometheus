#!/usr/bin/env python3
"""Correct docs/SECURITY-REMEDIATION.md so it describes the headers actually served.

The document was written when the CSP was enforcing and COOP was `same-origin`. Both
statements are now false: COOP had to become `same-origin-allow-popups` because
`same-origin` severs `window.opener` and killed `signInWithPopup`, and the policy is
temporarily on `Content-Security-Policy-Report-Only` while a real sign-in proves which
origins it needs.

A security document that describes protection the server is not serving is worse than no
document - it is the thing someone reads instead of checking. This makes it match.

Anchored, idempotent, all-or-nothing.
"""

import sys
from pathlib import Path

DOC = Path("docs/SECURITY-REMEDIATION.md")

EDITS: list[tuple[str, str]] = [
    (
        "| CSP is not implemented | 19 / 25 | **CODE — fixed** |\n",
        "| CSP is not implemented | 19 / 25 | **CODE — report-only**, see below |\n",
    ),
    (
        "Cross-Origin-Opener-Policy   same-origin\n",
        "Cross-Origin-Opener-Policy   same-origin-allow-popups\n",
    ),
    (
        "`poweredByHeader: false` removes `X-Powered-By: Next.js`.\n",
        "`poweredByHeader: false` removes `X-Powered-By: Next.js`.\n"
        "\n"
        "**COOP is `same-origin-allow-popups`, not `same-origin`, and that is deliberate.**\n"
        "`same-origin` severs `window.opener`. This app signs in with `signInWithPopup`, and\n"
        "the popup returns the credential *through* that reference — so the stricter value\n"
        "produced a silent \"Google sign-in failed\" for every user. The shipped value still\n"
        "isolates this page from anything that opens **it**, which is the protection that\n"
        "matters here. Do not tighten it without testing an actual sign-in.\n",
    ),
    (
        "### CSP — what is enforced, and the one thing that is not\n"
        "\n"
        "Enforced today:\n",
        "### CSP — current state: REPORT-ONLY (a diagnostic phase, not the destination)\n"
        "\n"
        "The policy below is currently served as `Content-Security-Policy-Report-Only`. The\n"
        "browser evaluates it and logs every violation to the console; it blocks **nothing**.\n"
        "That is on purpose and it is temporary: the enforcing version shipped once with the\n"
        "COOP mistake above, and rather than guess a second time at which origins the Firebase\n"
        "sign-in flow needs, the policy is being *measured* against a real login.\n"
        "\n"
        "**Report-only protects nothing.** To finish:\n"
        "\n"
        "1. Sign in with the console open and collect every `[Report Only] Refused to …` line.\n"
        "2. `python3 scripts/csp-enforce.py --allow <directive>=<origin>` once per refused\n"
        "   origin — or `--clean` if there were none. The script refuses to promote the header\n"
        "   without one of those two, and pins whatever it allows with a test.\n"
        "3. Rebuild and sign in again to confirm, because the policy now blocks.\n"
        "\n"
        "The policy itself:\n",
    ),
    (
        "default-src 'self'; script-src 'self' 'unsafe-inline';\n",
        "default-src 'self';\n"
        "script-src 'self' 'unsafe-inline' https://apis.google.com https://www.gstatic.com;\n",
    ),
    (
        "frame-src 'self' https://*.firebaseapp.com https://*.google.com;\n",
        "frame-src 'self' https://*.firebaseapp.com https://*.google.com https://accounts.google.com;\n",
    ),
    (
        "5. **Deploy the frontend header change** (section 1) — ships with any normal deploy.\n",
        "5. **Deploy the frontend header change** (section 1) — ships with any normal deploy.\n"
        "6. **Promote the CSP off report-only** (section 1) — needs one real sign-in with the\n"
        "   console open first. Until this is done the CSP findings are only half closed.\n",
    ),
]

if not DOC.exists():
    sys.exit("ABORTED: run this from the repository root")

text = DOC.read_text()

if "REPORT-ONLY (a diagnostic phase" in text:
    print(f"{DOC}: already corrected")
    raise SystemExit(0)

problems = [
    f"    expected 1, found {text.count(a)}:  {a.splitlines()[0][:74]!r}"
    for a, _ in EDITS
    if text.count(a) != 1
]
if problems:
    print("ABORTED - nothing was written:")
    for p in problems:
        print(p)
    raise SystemExit(1)

for anchor, replacement in EDITS:
    text = text.replace(anchor, replacement, 1)
DOC.write_text(text)
print(f"patched {DOC}: it now describes the headers the server actually sends")
