#!/usr/bin/env python3
"""Stop the analytics from printing numbers that read as broken math.

Three real findings from the live audit, one cause each:

25.0-SIGMA ROWS. The robust z is unbounded, and on a tight baseline a big move prints
20+ sigma - statistically true, informationally empty, and it reads as a bug. Detection
keeps the raw score; the REPORTED score is capped at +/-10.

+179,950% CHANGES. A percentage against a near-zero baseline is a division artefact,
not a fact about the business (the same rule the contribution panel already applies to
a zero baseline). Beyond 1000% the panel now says "from ~0" instead of the number.

3304x ROAS LEADERBOARDS. A ratio over $3 of spend is an outlier factory: division noise
tops every leaderboard and buries the real best performers. Each benchmark now carries a
minimum-denominator floor ($100 spend / $100 revenue / 100 installs); below it an app is
EXCLUDED from that ranking, exactly as zero-denominator apps already were, and for the
same reason - ranking them flatters noise."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

FOOTER = 'Rebuild backend + frontend, then run both test suites.'

PAYLOAD = """
eyJuZXdfZmlsZXMiOiB7fSwgImVkaXRzIjogW3sicGF0aCI6ICJiYWNrZW5kL2FwcC9zZXJ2aWNlcy9hbm9tYWx5X3NlcnZp
Y2UucHkiLCAiYW5jaG9yIjogIiAgICAjIENsYW1wIGZvciByZXBvcnRpbmcuIFRoZSBjb21wYXJpc29uIGFnYWluc3QgdGhl
IHRocmVzaG9sZCB1c2VzIHRoZSBDTEFNUEVEIHZhbHVlIG9uXG4gICAgIyBwdXJwb3NlOiB0aGUgY2FwIHNpdHMgZmFyIGFi
b3ZlIGFueSBzYW5lIHRocmVzaG9sZCwgc28gbm90aGluZyB0aGF0IHNob3VsZCBmaXJlIHN0b3BzXG4gICAgIyBmaXJpbmcs
IGFuZCBub3RoaW5nIHRoYXQgZmlyZXMgY2FuIHByaW50IGFuIGFic3VyZCBudW1iZXIuXG4gICAgc2NvcmUgPSBtYXgoLV9N
QVhfU0NPUkUsIG1pbihfTUFYX1NDT1JFLCBzY29yZSkpIiwgInJlcGxhY2VtZW50IjogIiAgICAjIENsYW1wIGZvciByZXBv
cnRpbmcuIFRoZSBjb21wYXJpc29uIGFnYWluc3QgdGhlIHRocmVzaG9sZCB1c2VzIHRoZSBDTEFNUEVEIHZhbHVlIG9uXG4g
ICAgIyBwdXJwb3NlOiB0aGUgY2FwIHNpdHMgZmFyIGFib3ZlIGFueSBzYW5lIHRocmVzaG9sZCwgc28gbm90aGluZyB0aGF0
IHNob3VsZCBmaXJlIHN0b3BzXG4gICAgIyBmaXJpbmcsIGFuZCBub3RoaW5nIHRoYXQgZmlyZXMgY2FuIHByaW50IGFuIGFi
c3VyZCBudW1iZXIuIFRlbiwgbm90IDI1OiB0aGUgbGl2ZVxuICAgICMgYXVkaXQgZm91bmQgbW9zdCB3YXRjaGxpc3Qgcm93
cyBwaW5uZWQgYXQgZXhhY3RseSAyNS4wXHUwM2MzLCBhbmQgcGFzdCB0ZW4gcm9idXN0XG4gICAgIyBzaWdtYXMgdGhlIG51
bWJlciBjYXJyaWVzIG5vdGhpbmcgYSByZWFkZXIgY2FuIHVzZSAtIGl0IGp1c3QgcmVhZHMgYXMgYnJva2VuIG1hdGguXG4g
ICAgIyBUaGUgcGFuZWwgcmVuZGVycyB0aGUgY2FwcGVkIHZhbHVlIGFzIFwiXHUyMjY1MTBcdTAzYzNcIiwgbmV2ZXIgYXMg
YSBwcmVjaXNlIG1lYXN1cmVtZW50LlxuICAgIHNjb3JlID0gbWF4KC0xMC4wLCBtaW4oMTAuMCwgc2NvcmUpKSIsICJtYXJr
ZXIiOiAic2NvcmUgPSBtYXgoLTEwLjAsIG1pbigxMC4wLCBzY29yZSkpIn0sIHsicGF0aCI6ICJmcm9udGVuZC9jb21wb25l
bnRzL292ZXJ2aWV3L3dhdGNobGlzdC1wYW5lbC50c3giLCAiYW5jaG9yIjogIiAgICAgICAgICAgICAgICAgICAgPHNwYW4g
Y2xhc3NOYW1lPVwic2hyaW5rLTAgdGV4dC1zbSBmb250LXNlbWlib2xkIHRhYnVsYXItbnVtc1wiIHN0eWxlPXt7IGNvbG9y
IH19PlxuICAgICAgICAgICAgICAgICAgICAgIHtyb3cuY2hhbmdlX3BjdCAhPSBudWxsID8gZm9ybWF0UGVyY2VudChyb3cu
Y2hhbmdlX3BjdCkgOiBcIlx1MjAxNFwifVxuICAgICAgICAgICAgICAgICAgICA8L3NwYW4+IiwgInJlcGxhY2VtZW50Ijog
IiAgICAgICAgICAgICAgICAgICAgPHNwYW4gY2xhc3NOYW1lPVwic2hyaW5rLTAgdGV4dC1zbSBmb250LXNlbWlib2xkIHRh
YnVsYXItbnVtc1wiIHN0eWxlPXt7IGNvbG9yIH19PlxuICAgICAgICAgICAgICAgICAgICAgIHsvKiBBIGZvdXItZGlnaXQg
cGVyY2VudGFnZSBtZWFucyB0aGUgYmFzZWxpbmUgd2FzIG5lYXIgemVybyAtIHRoZVxuICAgICAgICAgICAgICAgICAgICAg
ICAgICBudW1iZXIgaXMgYSBkaXZpc2lvbiBhcnRlZmFjdCwgc28gc2F5IHdoYXQgaGFwcGVuZWQgaW5zdGVhZC4gKi99XG4g
ICAgICAgICAgICAgICAgICAgICAge3Jvdy5jaGFuZ2VfcGN0ICE9IG51bGxcbiAgICAgICAgICAgICAgICAgICAgICAgID8g
TWF0aC5hYnMocm93LmNoYW5nZV9wY3QpID4gMTBcbiAgICAgICAgICAgICAgICAgICAgICAgICAgPyBcImZyb20gfjBcIlxu
ICAgICAgICAgICAgICAgICAgICAgICAgICA6IGZvcm1hdFBlcmNlbnQocm93LmNoYW5nZV9wY3QpXG4gICAgICAgICAgICAg
ICAgICAgICAgICA6IFwiXHUyMDE0XCJ9XG4gICAgICAgICAgICAgICAgICAgIDwvc3Bhbj4iLCAibWFya2VyIjogIlwiZnJv
bSB+MFwiIn0sIHsicGF0aCI6ICJiYWNrZW5kL2FwcC9zZXJ2aWNlcy9iZW5jaG1hcmtfc2VydmljZS5weSIsICJhbmNob3Ii
OiAiICAgIGhpZ2hlcl9pc19iZXR0ZXI6IGJvb2xcbiAgICB1bml0OiBzdHIgICMgXCJyYXRpb1wiIHwgXCJ1c2RcIiB8IFwi
cGVyY2VudFwiIiwgInJlcGxhY2VtZW50IjogIiAgICBoaWdoZXJfaXNfYmV0dGVyOiBib29sXG4gICAgdW5pdDogc3RyICAj
IFwicmF0aW9cIiB8IFwidXNkXCIgfCBcInBlcmNlbnRcIlxuICAgICMgQmVsb3cgdGhpcyB0aGUgcmF0aW8gaXMgYW4gb3V0
bGllciBmYWN0b3J5OiAkMyBvZiBzcGVuZCBcImVhcm5pbmdcIiAkOTkgcHJpbnRzIGEgMzN4XG4gICAgIyBST0FTIGFuZCB0
b3BzIGV2ZXJ5IGxlYWRlcmJvYXJkLCBidXJ5aW5nIHRoZSByZWFsIGJlc3QgcGVyZm9ybWVycyB1bmRlciBkaXZpc2lvblxu
ICAgICMgbm9pc2UuIEFwcHMgdW5kZXIgdGhlIGZsb29yIGFyZSBFWENMVURFRCBmcm9tIHRoaXMgcmFua2luZywgZXhhY3Rs
eSBhcyBhcHBzIHdpdGggYVxuICAgICMgemVybyBkZW5vbWluYXRvciBhbHJlYWR5IGFyZSwgYW5kIGZvciB0aGUgc2FtZSBy
ZWFzb24uXG4gICAgbWluX2Rlbm9taW5hdG9yOiBmbG9hdCA9IDAuMCIsICJtYXJrZXIiOiAibWluX2Rlbm9taW5hdG9yOiBm
bG9hdCA9IDAuMCJ9LCB7InBhdGgiOiAiYmFja2VuZC9hcHAvc2VydmljZXMvYmVuY2htYXJrX3NlcnZpY2UucHkiLCAiYW5j
aG9yIjogIkJFTkNITUFSS1M6IHR1cGxlW0JlbmNobWFya0RlZiwgLi4uXSA9IChcbiAgICBCZW5jaG1hcmtEZWYoXCJyb2Fz
XCIsIFwiUk9BU1wiLCBcInJwdF9ncm9zc19yZXZlbnVlX3VzZFwiLCBcInJwdF91YV9jb3N0X3VzZFwiLCBUcnVlLCBcInJh
dGlvXCIpLFxuICAgIEJlbmNobWFya0RlZihcbiAgICAgICAgXCJtYXJnaW5cIiwgXCJQcm9maXQgbWFyZ2luXCIsIFwicnB0
X3RmX3Byb2ZpdF91c2RcIiwgXCJycHRfZ3Jvc3NfcmV2ZW51ZV91c2RcIiwgVHJ1ZSwgXCJwZXJjZW50XCJcbiAgICApLFxu
ICAgIEJlbmNobWFya0RlZihcImNwaVwiLCBcIkNQSVwiLCBcInJwdF91YV9jb3N0X3VzZFwiLCBcInRvdGFsX3BhaWRfaW5z
dGFsbHNcIiwgRmFsc2UsIFwidXNkXCIpLFxuICAgIEJlbmNobWFya0RlZihcbiAgICAgICAgXCJhcnBpXCIsIFwiUmV2ZW51
ZSBwZXIgaW5zdGFsbFwiLCBcInJwdF9ncm9zc19yZXZlbnVlX3VzZFwiLCBcInN0b3JlX3RvdGFsX2luc3RhbGxzXCIsIFRy
dWUsIFwidXNkXCJcbiAgICApLFxuKSIsICJyZXBsYWNlbWVudCI6ICJCRU5DSE1BUktTOiB0dXBsZVtCZW5jaG1hcmtEZWYs
IC4uLl0gPSAoXG4gICAgQmVuY2htYXJrRGVmKFxuICAgICAgICBcInJvYXNcIiwgXCJST0FTXCIsIFwicnB0X2dyb3NzX3Jl
dmVudWVfdXNkXCIsIFwicnB0X3VhX2Nvc3RfdXNkXCIsIFRydWUsIFwicmF0aW9cIixcbiAgICAgICAgbWluX2Rlbm9taW5h
dG9yPTEwMC4wLCAgIyAkMTAwIG9mIHNwZW5kIGJlZm9yZSBhIFJPQVMgaXMgd29ydGggcmFua2luZ1xuICAgICksXG4gICAg
QmVuY2htYXJrRGVmKFxuICAgICAgICBcIm1hcmdpblwiLCBcIlByb2ZpdCBtYXJnaW5cIiwgXCJycHRfdGZfcHJvZml0X3Vz
ZFwiLCBcInJwdF9ncm9zc19yZXZlbnVlX3VzZFwiLCBUcnVlLCBcInBlcmNlbnRcIixcbiAgICAgICAgbWluX2Rlbm9taW5h
dG9yPTEwMC4wLCAgIyAkMTAwIG9mIHJldmVudWUgYmVmb3JlIGEgbWFyZ2luIG1lYW5zIGFueXRoaW5nXG4gICAgKSxcbiAg
ICBCZW5jaG1hcmtEZWYoXG4gICAgICAgIFwiY3BpXCIsIFwiQ1BJXCIsIFwicnB0X3VhX2Nvc3RfdXNkXCIsIFwidG90YWxf
cGFpZF9pbnN0YWxsc1wiLCBGYWxzZSwgXCJ1c2RcIixcbiAgICAgICAgbWluX2Rlbm9taW5hdG9yPTEwMC4wLCAgIyAxMDAg
cGFpZCBpbnN0YWxscyBiZWZvcmUgYSBDUEkgaXMgd29ydGggcmFua2luZ1xuICAgICksXG4gICAgQmVuY2htYXJrRGVmKFxu
ICAgICAgICBcImFycGlcIiwgXCJSZXZlbnVlIHBlciBpbnN0YWxsXCIsIFwicnB0X2dyb3NzX3JldmVudWVfdXNkXCIsIFwi
c3RvcmVfdG90YWxfaW5zdGFsbHNcIiwgVHJ1ZSxcbiAgICAgICAgXCJ1c2RcIiwgbWluX2Rlbm9taW5hdG9yPTEwMC4wLCAg
IyAxMDAgaW5zdGFsbHMgYmVmb3JlIHJldmVudWUtcGVyLWluc3RhbGwgbWVhbnMgYW55dGhpbmdcbiAgICApLFxuKSIsICJt
YXJrZXIiOiAibWluX2Rlbm9taW5hdG9yPTEwMC4wLCAgIyAkMTAwIG9mIHNwZW5kIn0sIHsicGF0aCI6ICJiYWNrZW5kL2Fw
cC9zZXJ2aWNlcy9iZW5jaG1hcmtfc2VydmljZS5weSIsICJhbmNob3IiOiAiICAgICAgICAgICAgZGVub21pbmF0b3IgPSBm
bG9hdChyb3dbYmVuY2htYXJrLmRlbm9taW5hdG9yXSBvciAwLjApXG4gICAgICAgICAgICBpZiBkZW5vbWluYXRvciA9PSAw
OlxuICAgICAgICAgICAgICAgICMgTm8gc3BlbmQgbWVhbnMgbm8gUk9BUy4gUmFua2luZyBpdCBhcyB0aGUgd29yc3Qgd291
bGQgcHVzaCBldmVyeSByZWFsXG4gICAgICAgICAgICAgICAgIyBhcHAgdXAgYSBxdWFydGlsZSBhbmQgcXVpZXRseSBmbGF0
dGVyIHRoZSBwb3J0Zm9saW8uXG4gICAgICAgICAgICAgICAgY29udGludWUiLCAicmVwbGFjZW1lbnQiOiAiICAgICAgICAg
ICAgZGVub21pbmF0b3IgPSBmbG9hdChyb3dbYmVuY2htYXJrLmRlbm9taW5hdG9yXSBvciAwLjApXG4gICAgICAgICAgICBp
ZiBkZW5vbWluYXRvciA8PSBiZW5jaG1hcmsubWluX2Rlbm9taW5hdG9yOlxuICAgICAgICAgICAgICAgICMgTm8gc3BlbmQg
bWVhbnMgbm8gUk9BUyAtIGFuZCBORUdMSUdJQkxFIHNwZW5kIG1lYW5zIGEgUk9BUyBtYWRlIG9mXG4gICAgICAgICAgICAg
ICAgIyBkaXZpc2lvbiBub2lzZS4gUmFua2luZyBlaXRoZXIgd291bGQgcHVzaCBldmVyeSByZWFsIGFwcCB1cCBhIHF1YXJ0
aWxlXG4gICAgICAgICAgICAgICAgIyBhbmQgcXVpZXRseSBmbGF0dGVyIHRoZSBwb3J0Zm9saW8uXG4gICAgICAgICAgICAg
ICAgY29udGludWUiLCAibWFya2VyIjogImlmIGRlbm9taW5hdG9yIDw9IGJlbmNobWFyay5taW5fZGVub21pbmF0b3I6In0s
IHsicGF0aCI6ICJmcm9udGVuZC9jb21wb25lbnRzL292ZXJ2aWV3L3dhdGNobGlzdC1wYW5lbC50c3giLCAiYW5jaG9yIjog
IiAgICAgICAgICAgICAgICAgICAgPHNwYW4gY2xhc3NOYW1lPVwiaGlkZGVuIHctMTYgc2hyaW5rLTAgdGV4dC1yaWdodCB0
ZXh0LXhzIHRhYnVsYXItbnVtcyB0ZXh0LVt2YXIoLS1jb2xvci10ZXh0LW11dGVkKV0gc206YmxvY2tcIj5cbiAgICAgICAg
ICAgICAgICAgICAgICB7cm93LnNjb3JlICE9IG51bGwgPyBgJHtyb3cuc2NvcmUudG9GaXhlZCgxKX1cdTAzYzNgIDogXCJm
bGF0XCJ9XG4gICAgICAgICAgICAgICAgICAgIDwvc3Bhbj4iLCAicmVwbGFjZW1lbnQiOiAiICAgICAgICAgICAgICAgICAg
ICA8c3BhbiBjbGFzc05hbWU9XCJoaWRkZW4gdy0xNiBzaHJpbmstMCB0ZXh0LXJpZ2h0IHRleHQteHMgdGFidWxhci1udW1z
IHRleHQtW3ZhcigtLWNvbG9yLXRleHQtbXV0ZWQpXSBzbTpibG9ja1wiPlxuICAgICAgICAgICAgICAgICAgICAgIHsvKiBU
aGUgc2VydmVyIGNhcHMgdGhlIHJlcG9ydGVkIHNjb3JlIGF0IFx1MDBiMTEwOyBhdCB0aGUgY2FwIHRoaXMgaXMgYVxuICAg
ICAgICAgICAgICAgICAgICAgICAgICBmbG9vciwgbm90IGEgbWVhc3VyZW1lbnQsIGFuZCBwcmludGluZyBpdCBiYXJlIHJl
YWRzIGFzIG9uZS4gKi99XG4gICAgICAgICAgICAgICAgICAgICAge3Jvdy5zY29yZSAhPSBudWxsXG4gICAgICAgICAgICAg
ICAgICAgICAgICA/IGAke3Jvdy5zY29yZSA+PSAxMCA/IFwiXHUyMjY1MTBcIiA6IHJvdy5zY29yZSA8PSAtMTAgPyBcIlx1
MjI2NC0xMFwiIDogcm93LnNjb3JlLnRvRml4ZWQoMSl9XHUwM2MzYFxuICAgICAgICAgICAgICAgICAgICAgICAgOiBcImZs
YXRcIn1cbiAgICAgICAgICAgICAgICAgICAgPC9zcGFuPiIsICJtYXJrZXIiOiAiZmxvb3IsIG5vdCBhIG1lYXN1cmVtZW50
In1dfQ==
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
