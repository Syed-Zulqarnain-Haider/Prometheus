#!/usr/bin/env python3
"""Promote the CSP from REPORT-ONLY back to ENFORCING, allowing any origins a real
sign-in proved it needs.

Background. The enforcing CSP shipped once with `Cross-Origin-Opener-Policy: same-origin`
and broke Google sign-in. COOP was fixed; the policy was then moved to
`Content-Security-Policy-Report-Only` so the browser would *report* what it would block
without blocking anything (scripts/csp-report-only.py). Report-only protects nothing - it
is a measuring instrument, not a destination.

This script ends that phase. It refuses to run blind: either the console from a real
sign-in was clean, or every origin it complained about is named on the command line. No
origin is ever guessed - guessing is what broke the login the first time.

    # console was clean, nothing was refused
    python3 scripts/csp-enforce.py --clean

    # console showed refusals - name each one, directive and origin
    python3 scripts/csp-enforce.py \
        --allow script-src=https://apis.google.com \
        --allow connect-src=https://securetoken.googleapis.com

Both forms may be combined; --allow on its own implies the console was read. Origins are
appended to the directive's existing origin list, never replacing it, and an origin that
is already present is left alone. Whatever is allowed here is also pinned by a test, so a
later edit cannot silently drop it and break sign-in again.

Anchored, idempotent, and all-or-nothing: if anything cannot be matched exactly, the
script reports every problem and writes NOTHING.
"""

import argparse
import re
import sys
from pathlib import Path

CONFIG = Path("frontend/next.config.mjs")
TESTS = Path("frontend/tests/security-headers.test.ts")

# Directives this script is willing to touch. Anything outside this list is far more
# likely to be a typo than a real finding, and a typo'd directive name is silently
# ignored by browsers - which is exactly the class of mistake this phase exists to end.
KNOWN_DIRECTIVES = (
    "default-src",
    "script-src",
    "style-src",
    "font-src",
    "img-src",
    "connect-src",
    "frame-src",
    "worker-src",
    "media-src",
    "manifest-src",
)

REPORT_ONLY_LINE = '  { key: "Content-Security-Policy-Report-Only", value: contentSecurityPolicy },'
ENFORCING_LINE = '  { key: "Content-Security-Policy", value: contentSecurityPolicy },'

REPORT_ONLY_COMMENT = (
    "  // REPORT-ONLY on purpose: the browser checks this policy and logs what it WOULD\n"
    "  // block, without blocking it. Promote to Content-Security-Policy once the console\n"
    "  // from a real sign-in is clean. See scripts/csp-report-only.py.\n"
)
ENFORCING_COMMENT = (
    "  // ENFORCING. Every origin below was proved necessary by a report-only pass against\n"
    "  // a real sign-in, not assumed. Adding one back without that evidence is how the\n"
    "  // login broke before - see docs/SECURITY-REMEDIATION.md.\n"
)


def parse_allow(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            f"expected directive=origin, got {value!r} "
            "(for example: script-src=https://apis.google.com)"
        )
    directive, origin = value.split("=", 1)
    directive, origin = directive.strip(), origin.strip()
    if directive not in KNOWN_DIRECTIVES:
        raise argparse.ArgumentTypeError(
            f"unknown directive {directive!r}. Browsers ignore a misspelled directive "
            f"silently. Known: {', '.join(KNOWN_DIRECTIVES)}"
        )
    if not origin:
        raise argparse.ArgumentTypeError(f"no origin given in {value!r}")
    if '"' in origin or ";" in origin:
        raise argparse.ArgumentTypeError(f"{origin!r} cannot contain a quote or semicolon")
    return directive, origin


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument(
    "--allow",
    type=parse_allow,
    action="append",
    default=[],
    metavar="DIRECTIVE=ORIGIN",
    help="an origin a real sign-in proved is needed. Repeatable.",
)
parser.add_argument(
    "--clean",
    action="store_true",
    help="the console from a real sign-in reported no refusals at all.",
)
args = parser.parse_args()

if not args.clean and not args.allow:
    sys.exit(
        "ABORTED: nothing was written.\n"
        "\n"
        "This script will not promote the CSP without evidence. Sign in with the console\n"
        "open (F12) and then re-run with either:\n"
        "  --clean                       if no '[Report Only] Refused to ...' line appeared\n"
        "  --allow <directive>=<origin>  once per origin that was refused\n"
    )

if not CONFIG.exists():
    sys.exit("ABORTED: run this from the repository root")

text = CONFIG.read_text()
problems: list[str] = []

# --- 1. the header itself -------------------------------------------------------------
already_enforcing = REPORT_ONLY_LINE not in text and ENFORCING_LINE in text
if not already_enforcing and text.count(REPORT_ONLY_LINE) != 1:
    problems.append(
        f"  frontend/next.config.mjs: expected exactly 1 report-only header line, "
        f"found {text.count(REPORT_ONLY_LINE)}"
    )

# --- 2. the origins -------------------------------------------------------------------
# Each directive lives in a string literal inside the policy array. Two shapes exist:
# a plain "script-src 'self' ..." literal, and connect-src's "connect-src 'self'" literal
# that is joined with computed origins. Appending inside the literal is correct for both.
wanted: dict[str, list[str]] = {}
for directive, origin in args.allow:
    wanted.setdefault(directive, []).append(origin)

edits: list[tuple[str, str]] = []
for directive, origins in wanted.items():
    pattern = re.compile(r'"(' + re.escape(directive) + r' [^"]*)"')
    matches = pattern.findall(text)
    if len(matches) != 1:
        problems.append(
            f"  frontend/next.config.mjs: expected exactly 1 {directive!r} literal in the "
            f"policy, found {len(matches)}"
        )
        continue
    current = matches[0]
    missing = [o for o in origins if o not in current.split()]
    if not missing:
        continue
    edits.append((f'"{current}"', '"' + current + " " + " ".join(missing) + '"'))

if problems:
    print("ABORTED - nothing was written:")
    for p in problems:
        print(p)
    print("\nSend me frontend/next.config.mjs and I will re-anchor.")
    raise SystemExit(1)

for old, new in edits:
    text = text.replace(old, new, 1)
    print(f"allowed: {new[1:-1].split()[0]} += {new[len(old) - 1:-1].strip()}")

if already_enforcing:
    print(f"{CONFIG}: CSP is already enforcing")
else:
    text = text.replace(REPORT_ONLY_COMMENT, ENFORCING_COMMENT, 1)
    text = text.replace(REPORT_ONLY_LINE, ENFORCING_LINE, 1)
    print(f"patched {CONFIG}: CSP is now ENFORCING")

if edits or not already_enforcing:
    CONFIG.write_text(text)

# --- 3. put the test back, and pin the new origins -------------------------------------
if TESTS.exists():
    t = TESTS.read_text()
    before = t

    # csp-report-only.py taught every read to accept either header name. Undo that: the
    # enforcing header is the only one that should carry a policy now.
    t = t.replace(
        '(get("Content-Security-Policy") ?? get("Content-Security-Policy-Report-Only"))',
        'get("Content-Security-Policy")',
    )

    todo_assert = (
        "    // TODO: once a real sign-in produces a clean console, move the policy back to\n"
        "    // the enforcing header and restore this assertion - report-only protects nothing.\n"
        '    expect(csp).not.toBe("");'
    )
    real_assert = (
        "    // Report-only would not protect anything; this must be the enforcing header.\n"
        '    expect(get("Content-Security-Policy-Report-Only")).toBeUndefined();'
    )
    if todo_assert in t:
        t = t.replace(todo_assert, real_assert, 1)

    # Pin whatever the sign-in proved it needs, so the next person tightening headers
    # gets a failing test instead of a broken login. Appended at the end of the file -
    # never spliced into an existing block.
    if args.allow and "sign-in origins proved by a report-only pass" not in t:
        pins = "\n".join(
            f'    expect(directive("{d}")).toContain("{o}");'
            for d, origins in wanted.items()
            for o in origins
        )
        t = t.rstrip("\n") + "\n\n" + (
            "describe(\"sign-in origins proved by a report-only pass\", () => {\n"
            "  // These are not guesses. Each one appeared as a '[Report Only] Refused to ...'\n"
            "  // line in the browser console during a real Google sign-in against this build.\n"
            "  // Removing one does not fail loudly - it fails as a login that silently does\n"
            "  // nothing. See scripts/csp-enforce.py and docs/SECURITY-REMEDIATION.md.\n"
            "  it(\"keeps every origin the sign-in flow needs\", async () => {\n"
            "    const { get } = await loadHeaders();\n"
            "    const csp = get(\"Content-Security-Policy\") ?? \"\";\n"
            "    const directive = (name: string) =>\n"
            "      csp.split(\";\").map((d) => d.trim()).find((d) => d.startsWith(`${name} `)) ?? \"\";\n"
            f"{pins}\n"
            "  });\n"
            "});\n"
        )

    if t != before:
        TESTS.write_text(t)
        print(f"patched {TESTS}")
    else:
        print(f"{TESTS}: no change needed")

print()
print("Rebuild the frontend, then sign in once more to confirm - this policy now BLOCKS.")
