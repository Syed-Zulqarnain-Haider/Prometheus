#!/usr/bin/env python3
"""Give the new step-up gate the break-glass exemption the 2FA gate already had.

THIS FIXES A REGRESSION I SHIPPED. admin-mfa-stepup.py appended enforce_admin_step_up to
the admin router's dependencies list - the same list that already carried
enforce_admin_2fa. But enforce_admin_2fa carries a deliberate, narrow escape hatch: GET
/admin/settings and PUT /admin/settings/require_admin_2fa are exempt, so an admin can
ALWAYS turn the requirement back off and can never lock themselves out. The new gate had
no such exemption, so it sat in front of the escape hatch and closed it. The backend
suite caught it immediately - test_admin_2fa.py::test_settings_route_is_breakglass went
403 where it must be 200 - and because the deploy chain runs the tests before
`docker compose up`, the broken build never started. Nothing reached production.

The fix is not "add two more `if path.endswith(...)` lines and hope the two gates stay in
step". The exempt set now lives in ONE place, app/core/step_up.py, as a named list of the
settings keys that can switch these gates back off, with a pure predicate over it that is
unit-tested directly. enforce_admin_step_up consults it FIRST, before any database read,
so the escape hatch survives even a degraded settings lookup.

Why three keys and not two: the step-up gate added two switches of its own
(require_email_verified, admin_step_up_minutes). A gate you cannot reach the off-switch
of is a one-way door - an admin whose session ages past the step-up window could no longer
open the page that shortens the window. enforce_admin_2fa keeps its own narrower pair
untouched; its gate only ever needs require_admin_2fa to escape, and I am not editing
code I did not write to fix a bug I did.

    python3 scripts/fix-stepup-breakglass.py
"""

from __future__ import annotations

import sys
from pathlib import Path

FOOTER = "Rebuild backend, then run the backend test suite."

STEP_UP_ANCHOR = '''EMAIL_UNVERIFIED = "EMAIL_UNVERIFIED"
MFA_REQUIRED = "MFA_REQUIRED"
STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
'''

STEP_UP_REPLACEMENT = '''EMAIL_UNVERIFIED = "EMAIL_UNVERIFIED"
MFA_REQUIRED = "MFA_REQUIRED"
STEP_UP_REQUIRED = "STEP_UP_REQUIRED"

# BREAK-GLASS. Each key below is the off-switch for one of the rules above. The admin
# routes that read and write them must therefore never be gated BY them, or the gate is a
# one-way door: an admin whose sign-in has aged past the step-up window could no longer
# reach the page that shortens or disables that window, and the only way back in would be
# a database console. enforce_admin_2fa in api/v1/admin.py exempts the same settings read
# and require_admin_2fa for exactly this reason; this is that set plus the two switches
# the step-up gate introduced. Keeping it here, named and tested, is what stops the two
# gates from drifting into disagreement about which door is the escape hatch.
BREAK_GLASS_SETTINGS = (
    "require_admin_2fa",
    "require_email_verified",
    "admin_step_up_minutes",
)


def is_break_glass_request(method: str, path: str) -> bool:
    """True for the admin-settings calls that must stay reachable from a session this gate
    would otherwise refuse.

    Deliberately narrow: reading the settings collection, and writing ONLY the three keys
    in BREAK_GLASS_SETTINGS. Every other admin route - including every other setting -
    stays fully gated, so this buys back exactly the ability to undo the lock and nothing
    else.
    """
    path = path.rstrip("/")
    if method == "GET":
        return path.endswith("/admin/settings")
    if method == "PUT":
        return any(path.endswith(f"/admin/settings/{key}") for key in BREAK_GLASS_SETTINGS)
    return False
'''

DEPS_ANCHOR = '''    from datetime import UTC, datetime

    from app.core.step_up import AuthClaims, evaluate_admin_gate
    from app.services import settings_service
'''

DEPS_REPLACEMENT = '''    from datetime import UTC, datetime

    from app.core.step_up import (
        AuthClaims,
        evaluate_admin_gate,
        is_break_glass_request,
    )
    from app.services import settings_service

    # BREAK-GLASS, for the same reason enforce_admin_2fa has one: the settings routes that
    # can switch these requirements back off are never gated by them. Checked FIRST, before
    # any settings lookup, so the escape hatch does not depend on the database answering.
    if is_break_glass_request(request.method, request.url.path):
        return
'''

TESTS = '''

def test_settings_read_is_break_glass() -> None:
    # An admin the gate has locked out must still be able to SEE the switches.
    assert is_break_glass_request("GET", "/api/v1/admin/settings") is True


def test_every_switch_that_disables_this_gate_is_break_glass() -> None:
    # If a rule can lock you out, the write that turns that rule off must stay reachable.
    for key in BREAK_GLASS_SETTINGS:
        assert is_break_glass_request("PUT", f"/api/v1/admin/settings/{key}") is True


def test_break_glass_does_not_open_the_rest_of_the_admin_panel() -> None:
    assert is_break_glass_request("GET", "/api/v1/admin/users") is False
    assert is_break_glass_request("DELETE", "/api/v1/admin/users/7") is False
    assert is_break_glass_request("POST", "/api/v1/admin/settings") is False


def test_break_glass_does_not_extend_to_other_settings() -> None:
    # Writing a setting that has nothing to do with this gate is not an escape hatch.
    assert is_break_glass_request("PUT", "/api/v1/admin/settings/require_admin_2fa_x") is False
    assert is_break_glass_request("PUT", "/api/v1/admin/settings/business_time_zone") is False
    # ...and a longer path that merely CONTAINS an exempt one must not inherit the exemption.
    assert is_break_glass_request("PUT", "/api/v1/admin/settings/require_admin_2fa/history") is False
    assert is_break_glass_request("GET", "/api/v1/admin/settings/export") is False
'''

TEST_IMPORT_ANCHOR = '''from app.core.step_up import (
    EMAIL_UNVERIFIED,
    MFA_REQUIRED,
    STEP_UP_REQUIRED,
    AuthClaims,
    evaluate_admin_gate,
)
'''

TEST_IMPORT_REPLACEMENT = '''from app.core.step_up import (
    BREAK_GLASS_SETTINGS,
    EMAIL_UNVERIFIED,
    MFA_REQUIRED,
    STEP_UP_REQUIRED,
    AuthClaims,
    evaluate_admin_gate,
    is_break_glass_request,
)
'''

EDITS = [
    {
        "path": "backend/app/core/step_up.py",
        "anchor": STEP_UP_ANCHOR,
        "replacement": STEP_UP_REPLACEMENT,
        "marker": "def is_break_glass_request(",
    },
    {
        "path": "backend/app/api/deps.py",
        "anchor": DEPS_ANCHOR,
        "replacement": DEPS_REPLACEMENT,
        "marker": "if is_break_glass_request(request.method",
    },
    {
        "path": "backend/tests/test_step_up.py",
        "anchor": TEST_IMPORT_ANCHOR,
        "replacement": TEST_IMPORT_REPLACEMENT,
        "marker": "    BREAK_GLASS_SETTINGS,",
    },
]

APPENDS = [
    {
        "path": "backend/tests/test_step_up.py",
        "text": TESTS,
        "marker": "def test_settings_read_is_break_glass(",
    },
]


def resolve(text, anchor, replacement, marker):
    """Match against a file whose punctuation may have been normalised (em-dash -> hyphen).
    Flatten the replacement and marker with the anchor, or the patch reintroduces the very
    character the file was cleaned of."""
    if anchor in text:
        return anchor, replacement, marker
    flat = anchor.replace("—", "-")
    if flat != anchor and flat in text:
        return flat, replacement.replace("—", "-"), marker.replace("—", "-")
    return anchor, replacement, marker


def locate(lines, anchor):
    """Line index where the longest present run of the anchor's own lines begins."""
    wanted = anchor.splitlines()
    joined = "\n".join(lines)
    for take in range(len(wanted), 0, -1):
        for start in (0, len(wanted) - take):
            probe = "\n".join(wanted[start:start + take])
            if not probe.strip():
                continue
            index = joined.find(probe)
            if index != -1:
                return joined.count("\n", 0, index) - start
    for offset, line in sorted(enumerate(wanted), key=lambda p: len(p[1].strip()), reverse=True):
        if len(line.strip()) < 12:
            break
        index = joined.find(line)
        if index != -1:
            return joined.count("\n", 0, index) - offset
    return None


def main() -> int:
    if not Path("backend/app").is_dir():
        print("ABORTED: run this from the repository root")
        return 1
    if not Path("backend/app/core/step_up.py").exists():
        print("ABORTED: backend/app/core/step_up.py is not present - run")
        print("scripts/admin-mfa-stepup.py first; this only fixes what that one wrote.")
        return 1

    problems, failures, planned, skipped = [], [], {}, []
    for index, item in enumerate(EDITS, start=1):
        rel = item["path"]
        path = Path(rel)
        if not path.exists():
            problems.append(f"  [{index}] {rel}: file not found")
            continue
        text = planned.get(rel, path.read_text())
        anchor, replacement, marker = resolve(
            text, item["anchor"], item["replacement"], item["marker"]
        )
        if marker in text:
            skipped.append(f"{rel} [{index}]: already applied")
            continue
        found = text.count(anchor)
        if found != 1:
            problems.append(
                f"  [{index}] {rel}: expected exactly 1 match, found {found}\n"
                f"        anchor starts: {anchor.splitlines()[0][:76]!r}"
            )
            failures.append((rel, anchor))
            continue
        planned[rel] = text.replace(anchor, replacement, 1)

    # Test files are APPENDED to, never anchored into - a test file grows, and an anchor
    # inside one is a bet on nobody having added a case since.
    for item in APPENDS:
        rel = item["path"]
        path = Path(rel)
        if not path.exists():
            problems.append(f"  [append] {rel}: file not found")
            continue
        text = planned.get(rel, path.read_text())
        if item["marker"] in text:
            skipped.append(f"{rel} [append]: already applied")
            continue
        planned[rel] = text.rstrip("\n") + "\n" + item["text"]

    if problems:
        print("ABORTED - NOTHING was written. Every problem, so one round-trip fixes all:")
        print()
        for pr in problems:
            print(pr)
        shown = {}
        for rel, anchor in failures:
            lines = Path(rel).read_text().splitlines()
            hit = locate(lines, anchor)
            if hit is None:
                lo, hi = 0, min(len(lines), 120)
                note = "nothing from this anchor is on disk - head of file"
            else:
                lo, hi = max(0, hit - 30), min(len(lines), hit + 30)
                note = f"nearest partial match at line {hit + 1}"
            if any(lo >= a and hi <= b for a, b in shown.get(rel, [])):
                continue
            shown.setdefault(rel, []).append((lo, hi))
            print()
            print(f"----- {rel} lines {lo + 1}-{hi} of {len(lines)} ({note}) -----")
            for n, l in enumerate(lines[lo:hi], start=lo + 1):
                print(f"{n:6d}\t{l}")
        print()
        print("The regions above are what is actually on disk; I re-anchor from them.")
        return 1

    # A check that does not check the thing that broke is decoration. What broke was the
    # gate standing in front of its own off-switch, so verify the escape hatch is wired:
    # the predicate must exist AND enforce_admin_step_up must actually consult it.
    step_up_text = planned.get(
        "backend/app/core/step_up.py", Path("backend/app/core/step_up.py").read_text()
    )
    deps_text = planned.get("backend/app/api/deps.py", Path("backend/app/api/deps.py").read_text())
    gate = deps_text.split("async def enforce_admin_step_up(", 1)
    if len(gate) != 2:
        print("ABORTED - NOTHING was written: enforce_admin_step_up is not in deps.py.")
        return 1
    body = gate[1].split("\nasync def ", 1)[0].split("\ndef ", 1)[0]
    if "def is_break_glass_request(" not in step_up_text:
        print("ABORTED - NOTHING was written: is_break_glass_request was not created.")
        return 1
    if "is_break_glass_request(request.method" not in body:
        print("ABORTED - NOTHING was written: enforce_admin_step_up never calls the")
        print("break-glass check, so the escape hatch would still be closed.")
        return 1
    if body.index("is_break_glass_request(request.method") > body.index("settings_service.get_value"):
        print("ABORTED - NOTHING was written: the break-glass check must run BEFORE the")
        print("settings lookups, so a degraded database cannot close the escape hatch.")
        return 1

    for rel, content in sorted(planned.items()):
        Path(rel).write_text(content)
        print(f"wrote {rel}")
    for n in skipped:
        print(f"skip  {n}")
    if not planned:
        print("nothing to do - already applied")
    print()
    print("Regression guard: tests/test_admin_2fa.py::test_settings_route_is_breakglass")
    print("is the test that caught this; it must go green again.")
    print()
    print(FOOTER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
