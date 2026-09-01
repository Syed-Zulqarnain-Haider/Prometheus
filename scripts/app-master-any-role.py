#!/usr/bin/env python3
"""Anyone with access to an app may propose a change to it. The grant becomes the gate.

THE DECISION THIS REVERSES
--------------------------
The approval workflow has been complete for a while - propose, admin approves or rejects,
nothing written until they do. It was restricted to one role by a line recorded as an
owner decision at the time:

    # Who may raise a request at all (owner decision): pod owners, plus admins ...
    PROPOSER_ROLES = frozenset({"pod_owner"})

The owner has now decided the opposite: every role should be able to propose, with the
admin approval step in place for all of them. So the allowlist comes out and the row scope
alone decides.

WHY THAT IS SAFE, AND WHERE THE WALL ACTUALLY IS
------------------------------------------------
Removing a role check sounds like widening. It is not, because the check it leaves behind
is the stronger one: ``build_scope_filter`` already fails closed -

    if not scopes: return false()

- so a user with no grants matches no apps and can propose nothing at all. Reach is
decided by what a person was granted, which is the thing an admin actually manages, rather
than by a role name that had to be kept in sync by hand.

Nothing else moves. Approve and reject stay admin-only. An app outside your scopes still
answers 404 rather than 403, so a proposal cannot be used to discover which apps exist.
Proposals still go through the same AppMasterUpdate validation as an admin's own edit, so
a bad value fails on the way in instead of months later when somebody approves it.

Two consequences worth naming rather than burying: a viewer holding an app grant can now
propose (the proposal is not the change - an admin still approves), and an executive with
'all' scope can propose for any app. Both follow directly from "the grant is the gate".

ANCHORING
---------
The deployed tree is ahead of the reconstructed one here, so nothing is assumed about file
contents. Every edit is located by what it IS - the constant, the function, the nav entry
whose href is /app-changes - and every miss is reported with the region as it exists on
disk. Nothing is written unless the backend edit, which is the actual change, matches.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
SERVICE = ROOT / "backend/app/services/app_master_request_service.py"
TEST = ROOT / "backend/tests/test_app_master_requests.py"
NAV = ROOT / "frontend/lib/nav.ts"
NAV_TEST = ROOT / "frontend/tests/nav.test.ts"

report: list[str] = []
skipped: list[str] = []


def region(path: Path, needle: str, before: int = 6, after: int = 20) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - before), min(len(lines), i + after)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: {needle!r} does not appear"


def span_of_def(text: str, name: str) -> tuple[int, int] | None:
    """(start, end) of a top-level function, from its `async def`/`def` to the next one.

    Used instead of matching the body, because the body is exactly the part that differs
    between this tree and the server's.
    """
    start = re.search(rf"^(?:async )?def {re.escape(name)}\b", text, re.M)
    if not start:
        return None
    nxt = re.search(r"^(?:async )?def \w+", text[start.end() :], re.M)
    end = start.end() + nxt.start() if nxt else len(text)
    return start.start(), end


# ── 1. the gate itself ─────────────────────────────────────────────────────────────

OLD_CONST = re.compile(
    r"\n# Who may raise a request at all[^\n]*\n(?:#[^\n]*\n)*"
    r"PROPOSER_ROLES = frozenset\([^\n]*\)\n"
)

NEW_CONST = '''
# Who may raise a request at all (owner decision, revised): ANY role, for the apps their
# row scopes already cover. There is deliberately no role allowlist here any more - the
# grant is the gate. That is not a widening: build_scope_filter fails closed on an empty
# scope list, so a user with no grants reaches no apps at all, and reach is decided by
# what an admin actually granted rather than by a role name kept in sync by hand.
# Proposing is not changing: every request still waits for an admin to approve it.
'''

OLD_GATE = """    if _is_admin(context):
        return True
    if not PROPOSER_ROLES.intersection(context.roles):
        return False
"""

NEW_GATE = """    if _is_admin(context):
        return True
"""

OLD_DOC = """    Admins: any app. Pod owners: only apps their row scopes already cover - the same
    filter the apps endpoints use. Proposing for an app you cannot see would otherwise be
    an existence probe wearing a workflow's clothes, so a refusal here is reported as 404.
    Any other role: no, whatever their scopes say.
"""

NEW_DOC = """\
    Admins: any app. Everybody else: only apps their row scopes already cover - the same
    filter the apps endpoints use, whatever their role. Proposing for an app you cannot see
    would otherwise be an existence probe wearing a workflow's clothes, so a refusal here is
    reported as 404.

    A user with no scopes reaches nothing: build_scope_filter returns false() for an empty
    list, so the absence of a grant is a wall rather than an omission.
"""


def patch_service() -> bool:
    if not SERVICE.exists():
        skipped.append(f"[gate] missing {SERVICE} - nothing written anywhere.")
        return False
    text = SERVICE.read_text()

    if "PROPOSER_ROLES" not in text:
        report.append("[gate] already applied - the role allowlist is gone")
        return True

    problems = []
    if len(OLD_CONST.findall(text)) != 1:
        found = len(OLD_CONST.findall(text))
        problems.append(f"  the PROPOSER_ROLES block: expected 1, found {found}")
    if text.count(OLD_GATE) != 1:
        n = text.count(OLD_GATE)
        problems.append(f"  the role check in may_propose_for: expected 1, found {n}")
    if problems:
        skipped.append(
            "[gate] NOTHING WAS WRITTEN - the gate is the whole change, so a partial apply\n"
            "  is worse than none. Mismatches:\n"
            + "\n".join(problems)
            + "\n  On disk:\n"
            + region(SERVICE, "PROPOSER_ROLES")
        )
        return False

    text = OLD_CONST.sub(NEW_CONST, text, count=1)
    text = text.replace(OLD_GATE, NEW_GATE, 1)
    if text.count(OLD_DOC) == 1:
        text = text.replace(OLD_DOC, NEW_DOC, 1)
        report.append("[gate] may_propose_for's docstring now describes the rule it enforces")
    else:
        report.append("[gate] NOTE: the docstring differs from expected and was left alone.")

    left = text.count("PROPOSER_ROLES")
    if left:
        skipped.append(
            f"[gate] NOTHING WRITTEN - {left} reference(s) to PROPOSER_ROLES would be left\n"
            "  dangling, which would not even import. On disk:\n"
            + region(SERVICE, "PROPOSER_ROLES")
        )
        return False

    SERVICE.write_text(text)
    report.append(f"[gate] {SERVICE}: any role may propose for the apps their grants cover")
    return True


# ── 2. the test that asserts the old rule ──────────────────────────────────────────

OLD_TEST = "test_other_roles_cannot_propose_even_with_full_scope"
NEW_TEST = "test_every_role_may_propose_for_apps_their_grants_cover"

NEW_BODY = '''\
    """Every role may raise a request; the grant decides which apps, not the role name.

    This inverts a test that asserted the opposite, because the rule itself changed - the
    owner's decision is now that anyone with access to an app may propose a change to it.
    Inverting rather than deleting keeps the boundary covered: if proposing ever silently
    stops working for these roles, this fails.

    The old test noted that these four roles all carry scope_type='all' in the fixture, so
    "a pure scope check would let them through - the role gate is what stops them". The role
    gate is exactly what was removed, so they now go through, which is the intended change.

    What did NOT relax, and is still proven next door by
    test_propose_outside_scope_is_404_not_403: an app outside the caller's scopes answers
    404, so a proposal cannot be used to discover which apps exist. Nor is anything written
    here - every one of these requests waits for an admin to approve it.
    """
    await _seed(metrics_env)
    _no_bq(monkeypatch)
    created: set[str] = set()
    for role in ("viewer", "executive", "finance", "marketing"):
        resp = await metrics_env.client.post(
            REQ, json={"canonical_key": "appA", "changes": {"hou": "H9"}}, headers=_auth(role)
        )
        assert resp.status_code == 201, (role, resp.status_code, resp.text)
        created.add(resp.json()["id"])
    # Four distinct pending requests, not one 201 handed back four times.
    assert len(created) == 4
'''


def patch_test() -> None:
    if not TEST.exists():
        skipped.append(f"[test] missing {TEST}")
        return
    text = TEST.read_text()
    if NEW_TEST in text:
        report.append("[test] already applied - left alone")
        return
    found = span_of_def(text, OLD_TEST)
    if not found:
        skipped.append(
            f"[test] {TEST}: no `{OLD_TEST}` to invert. The suite will fail on the old\n"
            "  assertion if it is still there under another name. On disk:\n"
            + region(TEST, "cannot_propose")
        )
        return
    start, end = found
    old = text[start:end]
    # Keep the ORIGINAL signature verbatim - the fixture parameters are the server's, not
    # something to guess at - and replace only the name and the body.
    sig = re.match(r"(?:async )?def \w+\((?:[^)]*\n)*?[^)]*\)[^:]*:\n", old)
    if not sig:
        skipped.append(f"[test] {TEST}: could not read the signature of {OLD_TEST}. On disk:\n"
                       + region(TEST, OLD_TEST))
        return
    header = sig.group(0).replace(OLD_TEST, NEW_TEST, 1)
    print("  REPLACED, for the record - the test as it stood:")
    for line in old.rstrip().splitlines():
        print(f"      | {line}")
    TEST.write_text(text[:start] + header + NEW_BODY + "\n\n" + text[end:])
    report.append(f"[test] {TEST}: {OLD_TEST}\n           -> {NEW_TEST}")


# ── 3. the sidebar (cosmetic - the server is the boundary) ─────────────────────────

def patch_nav() -> None:
    if not NAV.exists():
        skipped.append(f"[nav] missing {NAV} - the page still works, it is just not linked.")
        return
    text = NAV.read_text()
    if "/app-changes" not in text:
        skipped.append(
            f"[nav] {NAV}: no /app-changes entry found. On disk:\n"
            + region(NAV, "NAV_ITEMS")
        )
        return

    lines = text.splitlines(keepends=True)
    hits = [i for i, ln in enumerate(lines) if "/app-changes" in ln]
    if len(hits) != 1:
        skipped.append(f"[nav] {NAV}: expected one /app-changes entry, found {len(hits)}.")
        return
    line = lines[hits[0]]
    stripped = re.sub(r"\s*roles?:\s*\[[^\]]*\]\s*,?", "", line)
    stripped = re.sub(r"\s*roles?:\s*\"[^\"]*\"\s*,?", "", stripped)
    if stripped == line:
        report.append(
            "[nav] the /app-changes entry carries no role restriction on its own line - it\n"
            "         may already be visible to everyone, or gated elsewhere. Left alone:\n"
            + region(NAV, "/app-changes", before=3, after=4)
        )
        return
    lines[hits[0]] = stripped
    NAV.write_text("".join(lines))
    report.append(f"[nav] {NAV}: App Changes is no longer hidden from non-pod-owners")


def patch_nav_test() -> None:
    if not NAV_TEST.exists():
        return
    text = NAV_TEST.read_text()
    negative = re.compile(r'^\s*expect\([^)]*\)\.not\.toContain\("/app-changes"\);?\s*$\n', re.M)
    hits = negative.findall(text)
    if not hits:
        report.append("[nav] nav.test.ts asserts nothing negative about /app-changes - unchanged")
        return
    text = negative.sub("", text)
    NAV_TEST.write_text(text)
    report.append(
        f"[nav] {NAV_TEST}: dropped {len(hits)} assertion(s) that /app-changes is hidden -\n"
        "         it is deliberately visible to every role now"
    )


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    if patch_service():
        patch_test()
        patch_nav()
        patch_nav_test()

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    if skipped:
        print("\nSKIPPED (nothing written for these):")
        for entry in skipped:
            print(f"\n  {entry}")
    print(
        "\nIf the suite fails on the inverted test, send me the failure: it means those\n"
        "fixture roles do not hold a scope covering appA, and the right assertion is\n"
        "different - not that the rule is wrong."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
