#!/usr/bin/env python3
"""fix(tests): teach the drift guards about super_admin, and bump the migration head

The deploy's test gate refused the build, correctly, on three assertions - all of
them guards I tripped by adding a role without updating the tables that pin what
roles may exist:

  * test_migrations._HEAD was still the pre-super_admin revision.
  * test_rbac_matrix.ROLE_METRIC_GROUPS / ROLE_CAPABILITIES enumerate every role's
    access, and super_admin was absent.

That is exactly what those guards are for: a role appearing in the database that
nobody declared is how privilege creeps in unnoticed, so the suite refuses to pass
until a human writes down what the new role may see and do. Declared now, with the
same data access as admin - super_admin's power is structural (who may manage whom,
via guard_target_management), never extra metric groups or capabilities.

Nothing reached production: the gate is && -chained ahead of the restart, so the
containers stayed on the previous image. The migration itself DID apply
(f62c9d57a3e8 -> sasuperadmin), which is safe on its own - the role exists and
nobody holds it.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PincMDojwqvXykhwiJYjwL
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

FOOTER = 'Re-run the backend test suite.'

PAYLOAD = """
eyJuZXdfZmlsZXMiOiB7fSwgImVkaXRzIjogW3sicGF0aCI6ICJiYWNrZW5kL3Rlc3RzL3Rlc3RfcmJhY19tYXRyaXgucHki
LCAiYW5jaG9yIjogIlJPTEVfTUVUUklDX0dST1VQUzogZGljdFtzdHIsIHNldFtHcm91cF1dID0ge1xuICAgIFwiYWRtaW5c
IjogRlVMTCwiLCAicmVwbGFjZW1lbnQiOiAiUk9MRV9NRVRSSUNfR1JPVVBTOiBkaWN0W3N0ciwgc2V0W0dyb3VwXV0gPSB7
XG4gICAgXCJhZG1pblwiOiBGVUxMLFxuICAgICMgU2FtZSBEQVRBIGFjY2VzcyBhcyBhZG1pbi4gV2hhdCBzZXRzIHN1cGVy
X2FkbWluIGFwYXJ0IGlzIHN0cnVjdHVyYWwgLSB3aG8gbWF5XG4gICAgIyBtYW5hZ2Ugd2hvbSAoYWRtaW5fc2VydmljZS5n
dWFyZF90YXJnZXRfbWFuYWdlbWVudCkgLSBub3QgZXh0cmEgbWV0cmljIGdyb3Vwcy5cbiAgICBcInN1cGVyX2FkbWluXCI6
IEZVTEwsIiwgIm1hcmtlciI6ICJcInN1cGVyX2FkbWluXCI6IEZVTEwsIn0sIHsicGF0aCI6ICJiYWNrZW5kL3Rlc3RzL3Rl
c3RfcmJhY19tYXRyaXgucHkiLCAiYW5jaG9yIjogIlJPTEVfQ0FQQUJJTElUSUVTOiBkaWN0W3N0ciwgc2V0W3N0cl1dID0g
e1xuICAgIFwiYWRtaW5cIjoge1wiZXhwb3J0XCIsIFwic2hhcmVfcmVwb3J0XCIsIFwiYWRtaW5fcGFuZWxcIn0sIiwgInJl
cGxhY2VtZW50IjogIlJPTEVfQ0FQQUJJTElUSUVTOiBkaWN0W3N0ciwgc2V0W3N0cl1dID0ge1xuICAgIFwiYWRtaW5cIjog
e1wiZXhwb3J0XCIsIFwic2hhcmVfcmVwb3J0XCIsIFwiYWRtaW5fcGFuZWxcIn0sXG4gICAgXCJzdXBlcl9hZG1pblwiOiB7
XCJleHBvcnRcIiwgXCJzaGFyZV9yZXBvcnRcIiwgXCJhZG1pbl9wYW5lbFwifSwiLCAibWFya2VyIjogIlwic3VwZXJfYWRt
aW5cIjoge1wiZXhwb3J0XCIsIFwic2hhcmVfcmVwb3J0XCIsIFwiYWRtaW5fcGFuZWxcIn0sIn1dfQ==
"""


def resolve(text, anchor, replacement, marker):
    """Match against a file whose punctuation may have been normalised (em-dash -> hyphen).
    When the flattened form is the one that matches, flatten the replacement and marker
    too, or the patch reintroduces the very character the file was cleaned of."""
    if anchor in text:
        return anchor, replacement, marker
    flat = anchor.replace("\u2014", "-")
    if flat != anchor and flat in text:
        return flat, replacement.replace("\u2014", "-"), marker.replace("\u2014", "-")
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



_REV_RE = re.compile(r"^revision(?::\s*str)?\s*=\s*[\"']([^\"']+)[\"']", re.M)
_DOWN_RE = re.compile(r"^down_revision(?::[^=\n]+)?\s*=\s*(.+)$", re.M)
_HEAD_LINE_RE = re.compile(r'^_HEAD\s*=\s*"[^"]*".*$', re.M)


def _parents(text: str) -> list[str]:
    match = _DOWN_RE.search(text)
    if not match:
        return []
    raw = match.group(1).strip()
    if raw == "None":
        return []
    return [p.strip().strip("\"'") for p in raw.strip("()").split(",") if p.strip()]


def sync_migration_head() -> str:
    """Point test_migrations._HEAD at the head the migration files ACTUALLY declare.

    It was a hand-typed constant, so every migration silently invalidated it until
    somebody remembered - which is how this script failed its own deploy once already.
    Reading the graph instead means the guard keeps guarding (a chain that forks or
    loses its head still fails) without needing a human to retype a revision id.
    """
    versions = Path("backend/alembic/versions")
    target = Path("backend/tests/test_migrations.py")
    if not versions.is_dir() or not target.exists():
        return "alembic versions or test_migrations.py not found"
    ids, referenced = {}, set()
    for f in versions.glob("*.py"):
        text = f.read_text()
        match = _REV_RE.search(text)
        if not match:
            continue
        ids[match.group(1)] = f.name
        referenced.update(_parents(text))
    heads = [r for r in ids if r not in referenced]
    if len(heads) != 1:
        return f"expected exactly one head, found {len(heads)}: {sorted(heads)}"
    head = heads[0]
    source = target.read_text()
    line = _HEAD_LINE_RE.search(source)
    if not line:
        return "no _HEAD assignment found in test_migrations.py"
    current = re.search(r'"([^"]*)"', line.group(0))
    if current and current.group(1) == head:
        print(f"skip  test_migrations._HEAD already {head}")
        return ""
    slug = ids[head].split("_", 3)[-1].removesuffix(".py")
    replacement = f'_HEAD = "{head}"  # {slug} (current head)'
    target.write_text(source[: line.start()] + replacement + source[line.end() :])
    print(f"wrote backend/tests/test_migrations.py  (_HEAD -> {head})")
    return ""

def main() -> int:
    if not Path("backend/app").is_dir():
        print("ABORTED: run this from the repository root")
        return 1
    problem = sync_migration_head()
    if problem:
        print(f"ABORTED: {problem}")
        return 1
    data = json.loads(base64.b64decode(PAYLOAD.strip()).decode())
    problems, failures, planned, skipped = [], [], {}, []
    for rel, content in data.get("new_files", {}).items():
        p = Path(rel)
        if p.exists() and p.read_text() == content:
            skipped.append(f"{rel}: already present")
            continue
        planned[rel] = content
    for index, item in enumerate(data["edits"], start=1):
        rel = item["path"]; path = Path(rel)
        if not path.exists():
            problems.append(f"  [{index}] {rel}: file not found"); continue
        text = planned.get(rel, path.read_text())
        anchor, replacement, marker = resolve(text, item["anchor"], item["replacement"], item["marker"])
        if marker in text:
            skipped.append(f"{rel} [{index}]: already applied"); continue
        found = text.count(anchor)
        if found != 1:
            problems.append(f"  [{index}] {rel}: expected exactly 1 match, found {found}\n        anchor starts: {anchor.splitlines()[0][:76]!r}")
            failures.append((rel, anchor)); continue
        planned[rel] = text.replace(anchor, replacement, 1)
    if problems:
        print("ABORTED - NOTHING was written. Every problem, so one round-trip fixes all:"); print()
        for pr in problems: print(pr)
        shown = {}
        for rel, anchor in failures:
            lines = Path(rel).read_text().splitlines(); hit = locate(lines, anchor)
            if hit is None: lo, hi = 0, min(len(lines),120); note="nothing from this anchor is on disk - head of file"
            else: lo, hi = max(0,hit-30), min(len(lines),hit+30); note=f"nearest partial match at line {hit+1}"
            if any(lo>=a and hi<=b for a,b in shown.get(rel,[])): continue
            shown.setdefault(rel,[]).append((lo,hi))
            print(); print(f"----- {rel} lines {lo+1}-{hi} of {len(lines)} ({note}) -----")
            for n,l in enumerate(lines[lo:hi], start=lo+1): print(f"{n:6d}\t{l}")
        print(); print("The regions above are what is actually on disk; I re-anchor from them.")
        return 1
    for rel, content in sorted(planned.items()):
        Path(rel).parent.mkdir(parents=True, exist_ok=True); Path(rel).write_text(content); print(f"wrote {rel}")
    for n in skipped: print(f"skip  {n}")
    if not planned: print("nothing to do - already applied")
    print(); print(FOOTER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
