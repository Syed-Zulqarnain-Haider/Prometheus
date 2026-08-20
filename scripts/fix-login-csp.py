#!/usr/bin/env python3
"""Hotfix: the CSP/COOP added for the security scan broke Google sign-in.

Two separate mistakes, both mine:

1. `Cross-Origin-Opener-Policy: same-origin` severs `window.opener`. This app signs in
   with `signInWithPopup`, and the popup hands the credential back THROUGH that reference,
   so the flow died silently with "Google sign-in failed". The correct value for a site
   that uses OAuth popups is `same-origin-allow-popups` - it still isolates the page from
   anything that opens IT, which is the actual protection, while letting a popup this page
   opened talk back.

2. `script-src 'self' 'unsafe-inline'` blocked https://apis.google.com/js/api.js, which
   the Firebase popup flow loads. Google's sign-in also pulls from gstatic.

Anchored and idempotent. Nothing else in next.config.mjs is touched.
"""

import sys
from pathlib import Path

CONFIG = Path("frontend/next.config.mjs")

EDITS = [
    (
        '  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },',
        '  // NOT "same-origin": that severs window.opener and kills signInWithPopup.\n'
        '  { key: "Cross-Origin-Opener-Policy", value: "same-origin-allow-popups" },',
    ),
    (
        '  "script-src \'self\' \'unsafe-inline\'",',
        '  // apis.google.com + gstatic are what the Firebase popup sign-in loads.\n'
        '  "script-src \'self\' \'unsafe-inline\' https://apis.google.com https://www.gstatic.com",',
    ),
    (
        '  "frame-src \'self\' https://*.firebaseapp.com https://*.google.com",',
        '  "frame-src \'self\' https://*.firebaseapp.com https://*.google.com https://accounts.google.com",',
    ),
]

if not CONFIG.exists():
    sys.exit("ABORTED: run this from the repository root")

text = CONFIG.read_text()

if "same-origin-allow-popups" in text:
    print(f"{CONFIG}: already fixed")
    raise SystemExit(0)

problems = []
for anchor, _ in EDITS:
    n = text.count(anchor)
    if n != 1:
        problems.append(f"    expected 1, found {n}:  {anchor.strip()[:78]!r}")

if problems:
    print("ABORTED - nothing was written:")
    for p in problems:
        print(p)
    raise SystemExit(1)

for anchor, replacement in EDITS:
    text = text.replace(anchor, replacement, 1)
CONFIG.write_text(text)

# The header test pins COOP, so it has to move too - and it should say WHY, or the next
# person tightening headers breaks the login again.
TESTS = Path("frontend/tests/security-headers.test.ts")
if TESTS.exists():
    t = TESTS.read_text()
    old_line = '    expect(get("Cross-Origin-Opener-Policy")).toBe("same-origin");'
    new_line = (
        '    // NOT "same-origin". That severs window.opener, and this app signs in with\n'
        '    // signInWithPopup - the popup hands the credential back through exactly that\n'
        '    // reference. This value still isolates the page from whatever opened IT.\n'
        '    expect(get("Cross-Origin-Opener-Policy")).toBe("same-origin-allow-popups");\n'
        '    // Firebase\'s popup flow loads these; blocking them is a silent login failure.\n'
        '    expect(get("Content-Security-Policy")).toContain("https://apis.google.com");'
    )
    if "same-origin-allow-popups" in t:
        print(f"{TESTS}: already fixed")
    elif t.count(old_line) != 1:
        print(f"WARNING: {TESTS} could not be updated - its COOP assertion will now fail.")
    else:
        TESTS.write_text(t.replace(old_line, new_line, 1))
        print(f"patched {TESTS}")
print(f"patched {CONFIG}: COOP allows popups, Google's sign-in scripts allowed")
print()
print("Rebuild the frontend for this to take effect.")
