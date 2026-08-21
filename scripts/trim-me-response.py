#!/usr/bin/env python3
"""Give /auth/me a deliberate wire format instead of dumping the internal context.

The owner spotted firebase_uid in the /me response in DevTools. It is NOT a leak - the
response is the caller's own record, over TLS, to a caller whose browser already holds
that uid in every Firebase ID token the SDK gives it - but the question it raises is the
right one: WHY is it there? Because the route returned the internal UserContext
wholesale, so every field the context grows for server-side enforcement (firebase_uid,
access expiry, session-revocation stamps) rode out to the wire with it automatically.

Now /me serializes MeOut: exactly the seven fields the UI actually consumes (checked
against every use of useMe() in the frontend - the frontend type never even declared the
internal fields). FastAPI's response_model does the trimming, the cached enforcement
object is untouched, and a test pins the wire format so the next internal field cannot
quietly ride out either. Admin endpoints keep firebase_uid: admins manage users by it,
behind the admin_panel capability, which is a different door.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

FOOTER = 'Rebuild the backend, then run its test suite.'

PAYLOAD = """
eyJuZXdfZmlsZXMiOiB7fSwgImVkaXRzIjogW3sicGF0aCI6ICJiYWNrZW5kL2FwcC9zY2hlbWFzL2F1dGgucHkiLCAiYW5j
aG9yIjogImNsYXNzIFVzZXJDb250ZXh0KEJhc2VNb2RlbCk6XG4gICAgXCJcIlwiVGhlIHJlc29sdmVkIGlkZW50aXR5ICsg
UkJBQyBmb3IgdGhlIGF1dGhlbnRpY2F0ZWQgY2FsbGVyLiIsICJyZXBsYWNlbWVudCI6ICJjbGFzcyBNZU91dChCYXNlTW9k
ZWwpOlxuICAgIFwiXCJcIldoYXQgL2F1dGgvbWUgc2VuZHMgdG8gdGhlIGJyb3dzZXIgLSBhIGRlbGliZXJhdGUgd2lyZSBm
b3JtYXQuXG5cbiAgICBVc2VyQ29udGV4dCBiZWxvdyBpcyB0aGUgSU5URVJOQUwgZW5mb3JjZW1lbnQgb2JqZWN0LCBhbmQg
c2VyaWFsaXppbmcgaXQgd2hvbGVzYWxlXG4gICAgbWVhbnQgZXZlcnkgZmllbGQgaXQgZ3Jvd3MgZm9yIHNlcnZlci1zaWRl
IGNoZWNrcyAoZmlyZWJhc2VfdWlkLCBleHBpcnkgYW5kXG4gICAgcmV2b2NhdGlvbiBzdGFtcHMpIHJvZGUgc3RyYWlnaHQg
b3V0IHRvIHRoZSB3aXJlIHdpdGggaXQuIE5vbmUgb2YgdGhhdCBpcyBzZWNyZXRcbiAgICBmcm9tIGl0cyBvd24gY2FsbGVy
IC0gdGhlIEZpcmViYXNlIFNESyBhbHJlYWR5IGhhbmRzIHRoZSBicm93c2VyIGl0cyBvd24gdWlkLCBhbmRcbiAgICBpdCBz
aXRzIGluIGV2ZXJ5IElEIHRva2VuIHRoZSBjbGllbnQgaG9sZHMgLSBidXQgYSB3aXJlIGZvcm1hdCB0aGF0IGlzIGV4YWN0
bHlcbiAgICB3aGF0IHRoZSBVSSBjb25zdW1lcyBtZWFucyBub2JvZHkgaGFzIHRvIHJlLWhhdmUgdGhhdCBhcmd1bWVudCBl
YWNoIHRpbWUgdGhlXG4gICAgY29udGV4dCBncm93cyBhIGZpZWxkIGZvciBlbmZvcmNlbWVudC5cbiAgICBcIlwiXCJcblxu
ICAgIHVzZXJfaWQ6IHV1aWQuVVVJRFxuICAgIGVtYWlsOiBzdHJcbiAgICBkaXNwbGF5X25hbWU6IHN0ciB8IE5vbmUgPSBO
b25lXG4gICAgcm9sZXM6IGxpc3Rbc3RyXVxuICAgIG1ldHJpY19ncm91cHM6IGxpc3Rbc3RyXVxuICAgIGNhcGFiaWxpdGll
czogbGlzdFtzdHJdXG4gICAgc2NvcGVzOiBsaXN0W1Njb3BlT3V0XVxuXG5cbmNsYXNzIFVzZXJDb250ZXh0KEJhc2VNb2Rl
bCk6XG4gICAgXCJcIlwiVGhlIHJlc29sdmVkIGlkZW50aXR5ICsgUkJBQyBmb3IgdGhlIGF1dGhlbnRpY2F0ZWQgY2FsbGVy
LiIsICJtYXJrZXIiOiAiY2xhc3MgTWVPdXQoQmFzZU1vZGVsKToifSwgeyJwYXRoIjogImJhY2tlbmQvYXBwL2FwaS92MS9h
dXRoLnB5IiwgImFuY2hvciI6ICJmcm9tIGFwcC5zY2hlbWFzLmF1dGggaW1wb3J0IERpcmVjdG9yeUVudHJ5LCBVc2VyQ29u
dGV4dCIsICJyZXBsYWNlbWVudCI6ICJmcm9tIGFwcC5zY2hlbWFzLmF1dGggaW1wb3J0IERpcmVjdG9yeUVudHJ5LCBNZU91
dCwgVXNlckNvbnRleHQiLCAibWFya2VyIjogIkRpcmVjdG9yeUVudHJ5LCBNZU91dCwgVXNlckNvbnRleHQifSwgeyJwYXRo
IjogImJhY2tlbmQvYXBwL2FwaS92MS9hdXRoLnB5IiwgImFuY2hvciI6ICJAcm91dGVyLmdldChcIi9tZVwiLCByZXNwb25z
ZV9tb2RlbD1Vc2VyQ29udGV4dClcbmFzeW5jIGRlZiByZWFkX21lKGNvbnRleHQ6IEN1cnJlbnRVc2VyKSAtPiBVc2VyQ29u
dGV4dDpcbiAgICBcIlwiXCJSZXR1cm4gdGhlIGNhbGxlcidzIHJvbGVzLCBtZXRyaWMgZ3JvdXBzLCBjYXBhYmlsaXRpZXMs
IGFuZCBzY29wZXMuXCJcIlwiXG4gICAgcmV0dXJuIGNvbnRleHQiLCAicmVwbGFjZW1lbnQiOiAiQHJvdXRlci5nZXQoXCIv
bWVcIiwgcmVzcG9uc2VfbW9kZWw9TWVPdXQpXG5hc3luYyBkZWYgcmVhZF9tZShjb250ZXh0OiBDdXJyZW50VXNlcikgLT4g
VXNlckNvbnRleHQ6XG4gICAgXCJcIlwiVGhlIGNhbGxlcidzIGlkZW50aXR5IGFuZCBSQkFDIC0gZXhhY3RseSB0aGUgZmll
bGRzIHRoZSBVSSBjb25zdW1lcy5cblxuICAgIFRoZSByZXR1cm5lZCBjb250ZXh0IGlzIHRoZSBpbnRlcm5hbCBlbmZvcmNl
bWVudCBvYmplY3Q7IHJlc3BvbnNlX21vZGVsIGRvZXMgdGhlXG4gICAgdHJpbW1pbmcsIHNvIGZpZWxkcyB0aGUgY29udGV4
dCBncm93cyBmb3Igc2VydmVyLXNpZGUgY2hlY2tzIG5ldmVyIHJpZGUgb3V0IHRvXG4gICAgdGhlIHdpcmUgYWdhaW4uXG4g
ICAgXCJcIlwiXG4gICAgcmV0dXJuIGNvbnRleHQiLCAibWFya2VyIjogIkByb3V0ZXIuZ2V0KFwiL21lXCIsIHJlc3BvbnNl
X21vZGVsPU1lT3V0KSJ9LCB7InBhdGgiOiAiYmFja2VuZC90ZXN0cy90ZXN0X2F1dGgucHkiLCAiYW5jaG9yIjogIiAgICBz
Y29wZXMgPSB7KHNbXCJzY29wZV90eXBlXCJdLCBzW1wic2NvcGVfdmFsdWVcIl0pIGZvciBzIGluIGRhdGFbXCJzY29wZXNc
Il19XG4gICAgYXNzZXJ0IHNjb3BlcyA9PSB7KFwicG9kXCIsIFwiUE9EX0FcIiksIChcInB1Ymxpc2hlclwiLCBcIlB1Ylhc
Iil9IiwgInJlcGxhY2VtZW50IjogIiAgICBzY29wZXMgPSB7KHNbXCJzY29wZV90eXBlXCJdLCBzW1wic2NvcGVfdmFsdWVc
Il0pIGZvciBzIGluIGRhdGFbXCJzY29wZXNcIl19XG4gICAgYXNzZXJ0IHNjb3BlcyA9PSB7KFwicG9kXCIsIFwiUE9EX0Fc
IiksIChcInB1Ymxpc2hlclwiLCBcIlB1YlhcIil9XG5cbiAgICAjIFRoZSB3aXJlIGZvcm1hdCBpcyBERUxJQkVSQVRFIC0g
ZXhhY3RseSB3aGF0IHRoZSBVSSBjb25zdW1lcywgbm90aGluZyBtb3JlLiBUaGVcbiAgICAjIGludGVybmFsIFVzZXJDb250
ZXh0IGdyb3dzIGZpZWxkcyBmb3Igc2VydmVyLXNpZGUgZW5mb3JjZW1lbnQgKGZpcmViYXNlX3VpZCxcbiAgICAjIGV4cGly
eSBhbmQgcmV2b2NhdGlvbiBzdGFtcHMpLCBhbmQgbm9uZSBvZiB0aGVtIG1heSByaWRlIG91dCB3aXRoIHRoZSByZXNwb25z
ZS5cbiAgICAjIElmIHRoaXMgZmFpbHMgYmVjYXVzZSBhIGZpZWxkIHdhcyBhZGRlZCBvbiBwdXJwb3NlLCBhZGQgaXQgdG8g
TWVPdXQgLSBuZXZlciBieVxuICAgICMgc2VyaWFsaXppbmcgdGhlIGNvbnRleHQgaXRzZWxmIGFnYWluLlxuICAgIGFzc2Vy
dCBzZXQoZGF0YSkgPT0ge1xuICAgICAgICBcInVzZXJfaWRcIixcbiAgICAgICAgXCJlbWFpbFwiLFxuICAgICAgICBcImRp
c3BsYXlfbmFtZVwiLFxuICAgICAgICBcInJvbGVzXCIsXG4gICAgICAgIFwibWV0cmljX2dyb3Vwc1wiLFxuICAgICAgICBc
ImNhcGFiaWxpdGllc1wiLFxuICAgICAgICBcInNjb3Blc1wiLFxuICAgIH1cbiAgICBhc3NlcnQgXCJmaXJlYmFzZV91aWRc
IiBub3QgaW4gZGF0YSIsICJtYXJrZXIiOiAiYXNzZXJ0IFwiZmlyZWJhc2VfdWlkXCIgbm90IGluIGRhdGEifV19
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


def main():
    if not Path("frontend/app").is_dir() or not Path("backend/app").is_dir():
        print("ABORTED: run this from the repository root")
        return 1
    data = json.loads(base64.b64decode(PAYLOAD.strip()).decode())
    problems, failures, planned, skipped = [], [], {}, []

    for rel, content in data.get("new_files", {}).items():
        path = Path(rel)
        if path.exists() and path.read_text() == content:
            skipped.append(f"{rel}: already present and identical")
            continue
        planned[rel] = content

    for index, item in enumerate(data["edits"], start=1):
        rel = item["path"]
        path = Path(rel)
        if not path.exists():
            problems.append(f"  [{index}] {rel}: file not found")
            continue
        text = planned.get(rel, path.read_text())
        anchor, replacement, marker = resolve(text, item["anchor"], item["replacement"], item["marker"])
        if marker in text:
            skipped.append(f"{rel} [{index}]: already applied")
            continue
        found = text.count(anchor)
        if found != 1:
            head = anchor.splitlines()[0][:76]
            problems.append(f"  [{index}] {rel}: expected exactly 1 match, found {found}\n"
                            f"        anchor starts: {head!r}")
            failures.append((rel, anchor))
            continue
        planned[rel] = text.replace(anchor, replacement, 1)

    if problems:
        print("ABORTED - NOTHING was written. Every problem, so one round-trip fixes all:")
        print()
        for problem in problems:
            print(problem)
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
            for number, line in enumerate(lines[lo:hi], start=lo + 1):
                print(f"{number:6d}\t{line}")
        print()
        print("The regions above are what is actually on disk; I re-anchor from them.")
        return 1

    for rel, content in sorted(planned.items()):
        Path(rel).parent.mkdir(parents=True, exist_ok=True)
        Path(rel).write_text(content)
        print(f"wrote {rel}")
    for note in skipped:
        print(f"skip  {note}")
    if not planned:
        print("nothing to do - already applied")
    print()
    print(FOOTER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
