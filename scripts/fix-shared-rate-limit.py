#!/usr/bin/env python3
"""
WITHDRAWN: the shared-rate-limit finding does not apply to the deployed code.

I reported a P1 denial of service: that every caller shared one pre-auth rate-limit
bucket because client_ip() collapses to the proxy address. The evidence chain was sound
EXCEPT for its first link - it assumed a pre-auth limiter keyed on client_ip, which is
what my reconstruction of the backend contained.

The deployed backend has no such limiter. Its rate_limit.py runs an atomic Lua
check-and-add and every bucket is keyed on context.user_id - rl:{user}, rl:export:{user},
rl:sync:{user}, rl:diag:{user}, rl:chat:{user}. Per-caller isolation is correct, and there
is no shared bucket to exhaust. The finding was real about a tree that is not the one
running.

Kept as a record rather than deleted, because a withdrawn finding is itself a finding:
it is how a reconstruction diverging from production produces a confident, wrong answer.
The payload is emptied so running this changes nothing.

WHAT REMAINS TRUE, and is unaffected: audit_log recorded the Docker gateway on every row
because TRUSTED_PROXY defaulted off. That is now set true on the server, which is safe
there specifically - nginx sets X-Real-IP from $remote_addr and the app binds 127.0.0.1
only, so nginx is the sole path in.

WHAT IS STILL WORTH CHECKING (not verified, not claimed): every limiter keys on a
resolved user, so they engage only AFTER token verification. Unauthenticated traffic -
each request costing a full RSA signature check - may therefore be unbounded. That is a
different question from the one I raised, and it needs the real file read end to end
before anyone acts on it.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

FOOTER = 'Set TRUSTED_PROXY=true in the server .env, then rebuild + restart the backend.'

PAYLOAD = """
eyJuZXdfZmlsZXMiOiB7ImJhY2tlbmQvdGVzdHMvdGVzdF9jbGllbnRfaXBfaXNvbGF0aW9uLnB5IjogIlwiXCJcIlRoZSBw
cmUtYXV0aCBsaW1pdGVyIG11c3QgaXNvbGF0ZSBjYWxsZXJzIC0gYW5kIGNhbm5vdCB3aGVuIGV2ZXJ5IGNhbGxlciBsb29r
cyBhbGlrZS5cblxuVGhpcyBpcyB0aGUgc2hhcmVkLWJ1Y2tldCBmYWlsdXJlIHdyaXR0ZW4gZG93biBeyJuZXdfZmlsZXMiOiB7fSwgImVkaXRzIjogW119 very character the file was cleaned of."""
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


def main() -> int:
    if not Path("backend/app").is_dir():
        print("ABORTED: run this from the repository root")
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
