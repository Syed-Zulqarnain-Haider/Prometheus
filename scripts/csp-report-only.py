#!/usr/bin/env python3
"""Put the CSP back, but in REPORT-ONLY mode so it cannot break anything.

Context: the enforcing CSP shipped with `Cross-Origin-Opener-Policy: same-origin` and
broke Google sign-in. COOP was fixed separately; the CSP was then switched off entirely
to confirm login worked. It did.

What is unknown is whether the CSP itself blocks anything the login flow needs. Rather
than guess a second time, this sends the policy as `Content-Security-Policy-Report-Only`:
the browser evaluates it and logs every violation to the console, and blocks NOTHING.

Sign in with the console open, collect the "[Report Only] Refused to ..." lines, and the
exact origins to allow are then known rather than assumed. After that the header goes back
to enforcing.

This is a DIAGNOSTIC state, not a destination - report-only protects nothing.

Anchored and idempotent.
"""

import re
import sys
from pathlib import Path

CONFIG = Path("frontend/next.config.mjs")
TESTS = Path("frontend/tests/security-headers.test.ts")

TEMP_OFF = "  // TEMP off while sign-in is debugged"
ENFORCING = '  { key: "Content-Security-Policy", value: contentSecurityPolicy },'
REPORT_ONLY = (
    "  // REPORT-ONLY on purpose: the browser checks this policy and logs what it WOULD\n"
    "  // block, without blocking it. Promote to Content-Security-Policy once the console\n"
    "  // from a real sign-in is clean. See scripts/csp-report-only.py.\n"
    '  { key: "Content-Security-Policy-Report-Only", value: contentSecurityPolicy },'
)

if not CONFIG.exists():
    sys.exit("ABORTED: run this from the repository root")

text = CONFIG.read_text()

if "Content-Security-Policy-Report-Only" in text:
    # Do NOT exit here: the test file may still be unpatched, and leaving a red suite
    # behind is how a "done" step quietly is not.
    print(f"{CONFIG}: already in report-only mode")
elif TEMP_OFF in text:
    CONFIG.write_text(text.replace(TEMP_OFF, REPORT_ONLY, 1))
    print(f"patched {CONFIG}: CSP is now REPORT-ONLY - it cannot block anything")
elif ENFORCING in text:
    CONFIG.write_text(text.replace(ENFORCING, REPORT_ONLY, 1))
    print(f"patched {CONFIG}: CSP is now REPORT-ONLY - it cannot block anything")
else:
    sys.exit(
        "ABORTED: could not find the CSP header line in frontend/next.config.mjs.\n"
        "Nothing was written. Send me that file and I will re-anchor."
    )

# The test pins which header carries the policy. Teach EVERY read to accept either name
# while this diagnostic phase lasts, rather than leaving a red suite behind.
if TESTS.exists():
    t = TESTS.read_text()
    before = t
    # Any read of the enforcing header that is not already guarded gets the fallback.
    t = re.sub(
        r'get\("Content-Security-Policy"\)(?!\s*\?\?\s*get\()',
        '(get("Content-Security-Policy") ?? get("Content-Security-Policy-Report-Only"))',
        t,
    )
    # This one reads the REPORT-ONLY header, which the regex above deliberately leaves
    # alone - so it is matched in its original form.
    old_assert = (
        "    // Report-only would not protect anything; this must be the enforcing header.\n"
        '    expect(get("Content-Security-Policy-Report-Only")).toBeUndefined();'
    )
    new_assert = (
        "    // TODO: once a real sign-in produces a clean console, move the policy back to\n"
        "    // the enforcing header and restore this assertion - report-only protects nothing.\n"
        '    expect(csp).not.toBe("");'
    )
    if old_assert in t:
        t = t.replace(old_assert, new_assert, 1)
    if t != before:
        TESTS.write_text(t)
        print(f"patched {TESTS}")
    else:
        print(f"{TESTS}: no change needed")

print()
print("Rebuild the frontend, then sign in WITH THE CONSOLE OPEN (F12).")
print("Send me every '[Report Only] Refused to ...' line. Login will not break.")
