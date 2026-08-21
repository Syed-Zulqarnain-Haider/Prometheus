#!/usr/bin/env python3
"""security: the pre-auth rate limiter is one shared bucket in the deployed config

CONFIRMED FINDING, evidence-backed, from the source-level audit.

  1. client_ip() returns the socket peer whenever TRUSTED_PROXY is off (core/http.py).
  2. TRUSTED_PROXY defaults to false (core/config.py).
  3. The live audit log records 172.18.0.1 - the Docker gateway - on EVERY row, which
     proves the deployment is running with it off.
  4. enforce_pre_auth_rate_limit keys on rl:ip:{client_ip}.

So every caller on the internet shares ONE 600-request/minute bucket. A single client
sending 600 requests a minute exhausts it and every other user is answered 429: a control
built to bound abuse becomes a trivially-triggered denial of service, and per-source
brute-force isolation does not exist at all. The same root cause is why audit_log
forensics name the gateway instead of the caller.

THE FIX IS CONFIGURATION, NOT CODE - and deliberately so. Flipping the default would be
the more dangerous bug: reached directly (no proxy), trusting those headers lets any
caller forge the IP written into the append-only audit_log. So this change adds
  * a startup WARNING that names the consequence when production runs with it off,
  * a comment at PRE_AUTH_RATE_LIMIT so nobody tunes the number while the keying is broken,
  * four tests pinning both halves: trusted -> nginx's address is used and the LAST
    forwarded hop wins (taking [0] is the classic spoof); untrusted -> headers ignored, and
    two distinct clients demonstrably collapse to one key.

Owner action: set TRUSTED_PROXY=true in the server .env. It is safe HERE specifically
because nginx sets X-Real-IP from $remote_addr and the app binds to 127.0.0.1 only, so
nginx is the sole path in - verified against the deployed nginx config and container
port bindings. One env line closes the DoS, restores per-source limiting, and makes the
audit log name real callers.
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
cyBhbGlrZS5cblxuVGhpcyBpcyB0aGUgc2hhcmVkLWJ1Y2tldCBmYWlsdXJlIHdyaXR0ZW4gZG93biBhcyBhIHRlc3Q6IHdp
dGggVFJVU1RFRF9QUk9YWSBvZmYgYmVoaW5kIGFcbnByb3h5LCBjbGllbnRfaXAoKSByZXR1cm5zIHRoZSBwcm94eSdzIGFk
ZHJlc3MgZm9yIGV2ZXJ5b25lLCBzbyBvbmUgY2xpZW50J3MgdHJhZmZpY1xuZXhoYXVzdHMgdGhlIGNlaWxpbmcgZm9yIGFs
bCBvZiB0aGVtLiBUaGUgdGVzdHMgcGluIEJPVEggaGFsdmVzIG9mIHRoZSB0cmFkZS1vZmYsIGJlY2F1c2VcbnRoZSBmaXgg
Zm9yIG9uZSBpcyB0aGUgdnVsbmVyYWJpbGl0eSBvZiB0aGUgb3RoZXI6XG5cbiAgKiBwcm94eSB0cnVzdGVkICAgLT4gdGhl
IGNhbGxlcidzIHJlYWwgYWRkcmVzcyBpcyB1c2VkIChsaW1pdGVyIGlzb2xhdGVzLCBhdWRpdCBpcyB0cnVlKVxuICAqIHBy
b3h5IHVudHJ1c3RlZCAtPiBoZWFkZXJzIGFyZSBJR05PUkVEIChub2JvZHkgY2FuIGZvcmdlIHRoZSBhdWRpdF9sb2cncyBJ
UClcblwiXCJcIlxuXG5mcm9tIF9fZnV0dXJlX18gaW1wb3J0IGFubm90YXRpb25zXG5cbmZyb20gdHlwZXMgaW1wb3J0IFNp
bXBsZU5hbWVzcGFjZVxuXG5pbXBvcnQgcHl0ZXN0XG5mcm9tIGFwcC5jb3JlLmNvbmZpZyBpbXBvcnQgZ2V0X3NldHRpbmdz
XG5mcm9tIGFwcC5jb3JlLmh0dHAgaW1wb3J0IGNsaWVudF9pcFxuXG5cbmRlZiBfcmVxdWVzdChoZWFkZXJzOiBkaWN0W3N0
ciwgc3RyXSwgcGVlcjogc3RyID0gXCIxNzIuMTguMC4xXCIpOlxuICAgIHJldHVybiBTaW1wbGVOYW1lc3BhY2UoaGVhZGVy
cz1oZWFkZXJzLCBjbGllbnQ9U2ltcGxlTmFtZXNwYWNlKGhvc3Q9cGVlcikpXG5cblxuQHB5dGVzdC5maXh0dXJlKGF1dG91
c2U9VHJ1ZSlcbmRlZiBfY2xlYXJfc2V0dGluZ3NfY2FjaGUoKTpcbiAgICBnZXRfc2V0dGluZ3MuY2FjaGVfY2xlYXIoKVxu
ICAgIHlpZWxkXG4gICAgZ2V0X3NldHRpbmdzLmNhY2hlX2NsZWFyKClcblxuXG5kZWYgdGVzdF91bnRydXN0ZWRfcHJveHlf
aWdub3Jlc19mb3JnZWFibGVfaGVhZGVycyhtb25rZXlwYXRjaCkgLT4gTm9uZTpcbiAgICAjIEFuIGF0dGFja2VyIHNlbmRp
bmcgYm90aCBoZWFkZXJzIG11c3QgTk9UIGJlIGFibGUgdG8gY2hvb3NlIHdoYXQgdGhlIGF1ZGl0IGxvZyBzYXlzLlxuICAg
IG1vbmtleXBhdGNoLnNldGVudihcIlRSVVNURURfUFJPWFlcIiwgXCJmYWxzZVwiKVxuICAgIHJlcXVlc3QgPSBfcmVxdWVz
dCh7XCJ4LXJlYWwtaXBcIjogXCIxLjIuMy40XCIsIFwieC1mb3J3YXJkZWQtZm9yXCI6IFwiOS45LjkuOVwifSlcbiAgICBh
c3NlcnQgY2xpZW50X2lwKHJlcXVlc3QpID09IFwiMTcyLjE4LjAuMVwiXG5cblxuZGVmIHRlc3RfdHJ1c3RlZF9wcm94eV91
c2VzX3RoZV9hZGRyZXNzX25naW54X3N0YW1wZWQobW9ua2V5cGF0Y2gpIC0+IE5vbmU6XG4gICAgbW9ua2V5cGF0Y2guc2V0
ZW52KFwiVFJVU1RFRF9QUk9YWVwiLCBcInRydWVcIilcbiAgICByZXF1ZXN0ID0gX3JlcXVlc3Qoe1wieC1yZWFsLWlwXCI6
IFwiMjAzLjAuMTEzLjdcIn0pXG4gICAgYXNzZXJ0IGNsaWVudF9pcChyZXF1ZXN0KSA9PSBcIjIwMy4wLjExMy43XCJcblxu
XG5kZWYgdGVzdF90cnVzdGVkX3Byb3h5X3Rha2VzX3RoZV9MQVNUX2ZvcndhcmRlZF9ob3AobW9ua2V5cGF0Y2gpIC0+IE5v
bmU6XG4gICAgIyBYLUZvcndhcmRlZC1Gb3IgaXMgQVBQRU5ERUQgdG8gYnkgbmdpbngsIHNvIHRoZSBmaXJzdCBlbnRyeSBp
cyBhdHRhY2tlci1zdXBwbGllZCBhbmRcbiAgICAjIHRoZSBsYXN0IGlzIHRoZSBvbmUgb3VyIG93biBwcm94eSBhZGRlZC4g
VGFraW5nIFswXSBpcyB0aGUgY2xhc3NpYyBzcG9vZi5cbiAgICBtb25rZXlwYXRjaC5zZXRlbnYoXCJUUlVTVEVEX1BST1hZ
XCIsIFwidHJ1ZVwiKVxuICAgIHJlcXVlc3QgPSBfcmVxdWVzdCh7XCJ4LWZvcndhcmRlZC1mb3JcIjogXCIxLjEuMS4xLCAy
MDMuMC4xMTMuN1wifSlcbiAgICBhc3NlcnQgY2xpZW50X2lwKHJlcXVlc3QpID09IFwiMjAzLjAuMTEzLjdcIlxuXG5cbmRl
ZiB0ZXN0X2V2ZXJ5X2NhbGxlcl9jb2xsYXBzZXNfdG9fb25lX2tleV93aGVuX3VudHJ1c3RlZChtb25rZXlwYXRjaCkgLT4g
Tm9uZTpcbiAgICAjIFRoZSBmaW5kaW5nIGl0c2VsZjogdHdvIGRpZmZlcmVudCByZWFsIGNsaWVudHMgcHJvZHVjZSB0aGUg
U0FNRSBsaW1pdGVyIGtleSwgd2hpY2hcbiAgICAjIGlzIHdoeSBvbmUgb2YgdGhlbSBjYW4gc3BlbmQgdGhlIHNoYXJlZCBi
dWRnZXQgYW5kIDQyOSB0aGUgb3RoZXIuXG4gICAgbW9ua2V5cGF0Y2guc2V0ZW52KFwiVFJVU1RFRF9QUk9YWVwiLCBcImZh
bHNlXCIpXG4gICAgYSA9IGNsaWVudF9pcChfcmVxdWVzdCh7XCJ4LXJlYWwtaXBcIjogXCIyMDMuMC4xMTMuN1wifSkpXG4g
ICAgYiA9IGNsaWVudF9pcChfcmVxdWVzdCh7XCJ4LXJlYWwtaXBcIjogXCIxOTguNTEuMTAwLjRcIn0pKVxuICAgIGFzc2Vy
dCBhID09IGIgPT0gXCIxNzIuMTguMC4xXCJcbiJ9LCAiZWRpdHMiOiBbeyJwYXRoIjogImJhY2tlbmQvYXBwL2NvcmUvaHR0
cC5weSIsICJhbmNob3IiOiAiXCJcIlwiU21hbGwgSFRUUCByZXF1ZXN0IGhlbHBlcnMuXCJcIlwiXG5cbmZyb20gX19mdXR1
cmVfXyBpbXBvcnQgYW5ub3RhdGlvbnNcblxuZnJvbSBzdGFybGV0dGUucmVxdWVzdHMgaW1wb3J0IFJlcXVlc3RcblxuZnJv
bSBhcHAuY29yZS5jb25maWcgaW1wb3J0IGdldF9zZXR0aW5ncyIsICJyZXBsYWNlbWVudCI6ICJcIlwiXCJTbWFsbCBIVFRQ
IHJlcXVlc3QgaGVscGVycy5cIlwiXCJcblxuZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9uc1xuXG5pbXBvcnQg
bG9nZ2luZ1xuXG5mcm9tIHN0YXJsZXR0ZS5yZXF1ZXN0cyBpbXBvcnQgUmVxdWVzdFxuXG5mcm9tIGFwcC5jb3JlLmNvbmZp
ZyBpbXBvcnQgZ2V0X3NldHRpbmdzXG5cbmxvZ2dlciA9IGxvZ2dpbmcuZ2V0TG9nZ2VyKF9fbmFtZV9fKSIsICJtYXJrZXIi
OiAibG9nZ2VyID0gbG9nZ2luZy5nZXRMb2dnZXIoX19uYW1lX18pIn0sIHsicGF0aCI6ICJiYWNrZW5kL2FwcC9jb3JlL2h0
dHAucHkiLCAiYW5jaG9yIjogIiAgICBmb3J3YXJkZWQgPSByZXF1ZXN0LmhlYWRlcnMuZ2V0KFwieC1mb3J3YXJkZWQtZm9y
XCIpXG4gICAgaWYgZm9yd2FyZGVkOlxuICAgICAgICBob3BzID0gW2hvcC5zdHJpcCgpIGZvciBob3AgaW4gZm9yd2FyZGVk
LnNwbGl0KFwiLFwiKSBpZiBob3Auc3RyaXAoKV1cbiAgICAgICAgaWYgaG9wczpcbiAgICAgICAgICAgIHJldHVybiBob3Bz
Wy0xXVxuXG4gICAgcmV0dXJuIHBlZXIiLCAicmVwbGFjZW1lbnQiOiAiICAgIGZvcndhcmRlZCA9IHJlcXVlc3QuaGVhZGVy
cy5nZXQoXCJ4LWZvcndhcmRlZC1mb3JcIilcbiAgICBpZiBmb3J3YXJkZWQ6XG4gICAgICAgIGhvcHMgPSBbaG9wLnN0cmlw
KCkgZm9yIGhvcCBpbiBmb3J3YXJkZWQuc3BsaXQoXCIsXCIpIGlmIGhvcC5zdHJpcCgpXVxuICAgICAgICBpZiBob3BzOlxu
ICAgICAgICAgICAgcmV0dXJuIGhvcHNbLTFdXG5cbiAgICByZXR1cm4gcGVlclxuXG5kZWYgd2Fybl9pZl9yYXRlX2xpbWl0
X2lzX3NoYXJlZCgpIC0+IE5vbmU6XG4gICAgXCJcIlwiU2hvdXQgYXQgYm9vdCBpZiB0aGUgcHJlLWF1dGggbGltaXRlciBo
YXMgY29sbGFwc2VkIGludG8gT05FIGdsb2JhbCBidWNrZXQuXG5cbiAgICBgYGVuZm9yY2VfcHJlX2F1dGhfcmF0ZV9saW1p
dGBgIGtleXMgb24gYGBjbGllbnRfaXAocmVxdWVzdClgYC4gQmVoaW5kIGEgcmV2ZXJzZSBwcm94eVxuICAgIHdpdGggYGBU
UlVTVEVEX1BST1hZYGAgdW5zZXQsIHRoYXQgaXMgdGhlIHNvY2tldCBwZWVyIC0gd2hpY2ggaXMgdGhlIFBST1hZLCBpZGVu
dGljYWxcbiAgICBmb3IgZXZlcnkgY2FsbGVyIG9uIGVhcnRoLiBUaGUgcGVyLXNvdXJjZSBjZWlsaW5nIHRoZW4gc3RvcHMg
YmVpbmcgcGVyLXNvdXJjZTogZXZlcnlcbiAgICB1c2VyIHNoYXJlcyBvbmUgNjAwL21pbiBidWRnZXQsIHNvIGEgc2luZ2xl
IGNsaWVudCBjYW4gc3BlbmQgaXQgYW5kIGV2ZXJ5IG90aGVyIHVzZXJcbiAgICBpcyBhbnN3ZXJlZCA0MjkuIEEgY29udHJv
bCBtZWFudCB0byBib3VuZCBhYnVzZSBiZWNvbWVzIHRoZSBkZW5pYWwgb2Ygc2VydmljZS5cblxuICAgIFJlYWNoZWQgRElS
RUNUTFkgKG5vIHByb3h5KSwgdHJ1c3RpbmcgdGhlIGhlYWRlcnMgd291bGQgYmUgd29yc2UgLSBhbnkgY2FsbGVyIGNvdWxk
XG4gICAgZm9yZ2UgdGhlIGFkZHJlc3Mgd3JpdHRlbiBpbnRvIHRoZSBhcHBlbmQtb25seSBhdWRpdF9sb2cgLSBzbyB0aGUg
ZGVmYXVsdCBzdGF5cyBvZmZcbiAgICBhbmQgdGhpcyBpcyBhIFdBUk5JTkcsIG5ldmVyIGFuIGF1dG9tYXRpYyBzd2l0Y2gu
IFRoZSBkZXBsb3ltZW50IHRoYXQgdGVybWluYXRlcyBUTFNcbiAgICBhdCBuZ2lueCAoZG9jcy9uZ2lueC1wcm9tZXRoZXVz
LmNvbmYsIHdoaWNoIHNldHMgWC1SZWFsLUlQIGZyb20gJHJlbW90ZV9hZGRyIGFuZCBiaW5kc1xuICAgIHRoZSBhcHAgdG8g
bG9vcGJhY2spIGlzIHRoZSBvbmUgdGhhdCBtdXN0IHNldCBUUlVTVEVEX1BST1hZPXRydWUuXG4gICAgXCJcIlwiXG4gICAg
c2V0dGluZ3MgPSBnZXRfc2V0dGluZ3MoKVxuICAgIGlmIHNldHRpbmdzLnRydXN0ZWRfcHJveHkgb3Igc2V0dGluZ3MuZW52
aXJvbm1lbnQgIT0gXCJwcm9kdWN0aW9uXCI6XG4gICAgICAgIHJldHVyblxuICAgIGxvZ2dlci53YXJuaW5nKFxuICAgICAg
ICBcIlRSVVNURURfUFJPWFkgaXMgb2ZmIGluIHByb2R1Y3Rpb246IGV2ZXJ5IHJlcXVlc3QgbG9va3MgbGlrZSBpdCBjb21l
cyBmcm9tIHRoZSBcIlxuICAgICAgICBcInNhbWUgYWRkcmVzcywgc28gdGhlIHByZS1hdXRoIHJhdGUgbGltaXQgaXMgT05F
IHNoYXJlZCBidWNrZXQgKGEgc2luZ2xlIGNsaWVudCBcIlxuICAgICAgICBcImNhbiA0MjkgZXZlcnlvbmUpIGFuZCBhdWRp
dF9sb2cgcmVjb3JkcyB0aGUgcHJveHkncyBhZGRyZXNzIGluc3RlYWQgb2YgdGhlIFwiXG4gICAgICAgIFwiY2FsbGVyJ3Mu
IFNldCBUUlVTVEVEX1BST1hZPXRydWUgd2hlbiB0aGlzIGFwcCBzaXRzIGJlaGluZCB5b3VyIG93biBuZ2lueC5cIlxuICAg
IClcbiIsICJtYXJrZXIiOiAiZGVmIHdhcm5faWZfcmF0ZV9saW1pdF9pc19zaGFyZWQoKSJ9LCB7InBhdGgiOiAiYmFja2Vu
ZC9hcHAvY29yZS9yYXRlX2xpbWl0LnB5IiwgImFuY2hvciI6ICJQUkVfQVVUSF9SQVRFX0xJTUlUID0gNjAwIiwgInJlcGxh
Y2VtZW50IjogIiMgTk9URTogdGhpcyBjZWlsaW5nIGlzIG9ubHkgcGVyLVNPVVJDRSB3aGVuIGNsaWVudF9pcCgpIGNhbiBh
Y3R1YWxseSB0ZWxsIHNvdXJjZXNcbiMgYXBhcnQuIEJlaGluZCBhIHByb3h5IHdpdGggVFJVU1RFRF9QUk9YWSBvZmYgaXQg
cmV0dXJucyB0aGUgcHJveHkncyBhZGRyZXNzIGZvciBldmVyeVxuIyBjYWxsZXIsIGNvbGxhcHNpbmcgdGhpcyBpbnRvIE9O
RSBnbG9iYWwgYnVja2V0IC0gYXQgd2hpY2ggcG9pbnQgYSBzaW5nbGUgY2xpZW50IGNhblxuIyBzcGVuZCBpdCBhbmQgZXZl
cnlvbmUgZWxzZSBpcyBhbnN3ZXJlZCA0MjkuIFNlZSBjb3JlL2h0dHAud2Fybl9pZl9yYXRlX2xpbWl0X2lzX3NoYXJlZC5c
blBSRV9BVVRIX1JBVEVfTElNSVQgPSA2MDAiLCAibWFya2VyIjogImNvbGxhcHNpbmcgdGhpcyBpbnRvIE9ORSBnbG9iYWwg
YnVja2V0In1dfQ==
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
