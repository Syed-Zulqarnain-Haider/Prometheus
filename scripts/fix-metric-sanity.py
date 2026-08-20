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
Y2UucHkiLCAiYW5jaG9yIjogIiAgICBzY29yZSA9IF9NQURfVE9fU0lHTUEgKiBkZXZpYXRpb24gLyBtYWRcbiAgICByZXR1
cm4gc2NvcmUsIG1hdGVyaWFsIGFuZCBhYnMoc2NvcmUpID49IHpfdGhyZXNob2xkIiwgInJlcGxhY2VtZW50IjogIiAgICBz
Y29yZSA9IF9NQURfVE9fU0lHTUEgKiBkZXZpYXRpb24gLyBtYWRcbiAgICAjIERldGVjdGlvbiB1c2VzIHRoZSBSQVcgc2Nv
cmUsIHNvIHRocmVzaG9sZHMgYmVoYXZlIGV4YWN0bHkgYXMgYmVmb3JlOyBvbmx5IHRoZVxuICAgICMgUkVQT1JURUQgc2Nv
cmUgaXMgY2FwcGVkLiBCZXlvbmQgdGVuIHJvYnVzdCBzaWdtYXMgdGhlIG51bWJlciBjYXJyaWVzIG5vIG1vcmVcbiAgICAj
IGluZm9ybWF0aW9uLCBhbmQgdGhlIGF1ZGl0IGZvdW5kIHJlYWwgcm93cyBwcmludGluZyAyNS4wXHUwM2MzIC0gd2hpY2gg
cmVhZHMgYXMgYnJva2VuXG4gICAgIyBtYXRoIGV2ZW4gd2hlbiB0aGUgZGV0ZWN0aW9uIGJlaGluZCBpdCBpcyByaWdodC5c
biAgICBpc19hbm9tYWx5ID0gbWF0ZXJpYWwgYW5kIGFicyhzY29yZSkgPj0gel90aHJlc2hvbGRcbiAgICByZXR1cm4gbWF4
KC0xMC4wLCBtaW4oMTAuMCwgc2NvcmUpKSwgaXNfYW5vbWFseSIsICJtYXJrZXIiOiAicmV0dXJuIG1heCgtMTAuMCwgbWlu
KDEwLjAsIHNjb3JlKSksIGlzX2Fub21hbHkifSwgeyJwYXRoIjogImZyb250ZW5kL2NvbXBvbmVudHMvb3ZlcnZpZXcvd2F0
Y2hsaXN0LXBhbmVsLnRzeCIsICJhbmNob3IiOiAiICAgICAgICAgICAgICAgICAgICA8c3BhbiBjbGFzc05hbWU9XCJzaHJp
bmstMCB0ZXh0LXNtIGZvbnQtc2VtaWJvbGQgdGFidWxhci1udW1zXCIgc3R5bGU9e3sgY29sb3IgfX0+XG4gICAgICAgICAg
ICAgICAgICAgICAge3Jvdy5jaGFuZ2VfcGN0ICE9IG51bGwgPyBmb3JtYXRQZXJjZW50KHJvdy5jaGFuZ2VfcGN0KSA6IFwi
XHUyMDE0XCJ9XG4gICAgICAgICAgICAgICAgICAgIDwvc3Bhbj4iLCAicmVwbGFjZW1lbnQiOiAiICAgICAgICAgICAgICAg
ICAgICA8c3BhbiBjbGFzc05hbWU9XCJzaHJpbmstMCB0ZXh0LXNtIGZvbnQtc2VtaWJvbGQgdGFidWxhci1udW1zXCIgc3R5
bGU9e3sgY29sb3IgfX0+XG4gICAgICAgICAgICAgICAgICAgICAgey8qIEEgZm91ci1kaWdpdCBwZXJjZW50YWdlIG1lYW5z
IHRoZSBiYXNlbGluZSB3YXMgbmVhciB6ZXJvIC0gdGhlXG4gICAgICAgICAgICAgICAgICAgICAgICAgIG51bWJlciBpcyBh
IGRpdmlzaW9uIGFydGVmYWN0LCBzbyBzYXkgd2hhdCBoYXBwZW5lZCBpbnN0ZWFkLiAqL31cbiAgICAgICAgICAgICAgICAg
ICAgICB7cm93LmNoYW5nZV9wY3QgIT0gbnVsbFxuICAgICAgICAgICAgICAgICAgICAgICAgPyBNYXRoLmFicyhyb3cuY2hh
bmdlX3BjdCkgPiAxMFxuICAgICAgICAgICAgICAgICAgICAgICAgICA/IFwiZnJvbSB+MFwiXG4gICAgICAgICAgICAgICAg
ICAgICAgICAgIDogZm9ybWF0UGVyY2VudChyb3cuY2hhbmdlX3BjdClcbiAgICAgICAgICAgICAgICAgICAgICAgIDogXCJc
dTIwMTRcIn1cbiAgICAgICAgICAgICAgICAgICAgPC9zcGFuPiIsICJtYXJrZXIiOiAiXCJmcm9tIH4wXCIifSwgeyJwYXRo
IjogImJhY2tlbmQvYXBwL3NlcnZpY2VzL2JlbmNobWFya19zZXJ2aWNlLnB5IiwgImFuY2hvciI6ICIgICAgaGlnaGVyX2lz
X2JldHRlcjogYm9vbFxuICAgIHVuaXQ6IHN0ciAgIyBcInJhdGlvXCIgfCBcInVzZFwiIHwgXCJwZXJjZW50XCIiLCAicmVw
bGFjZW1lbnQiOiAiICAgIGhpZ2hlcl9pc19iZXR0ZXI6IGJvb2xcbiAgICB1bml0OiBzdHIgICMgXCJyYXRpb1wiIHwgXCJ1
c2RcIiB8IFwicGVyY2VudFwiXG4gICAgIyBCZWxvdyB0aGlzIHRoZSByYXRpbyBpcyBhbiBvdXRsaWVyIGZhY3Rvcnk6ICQz
IG9mIHNwZW5kIFwiZWFybmluZ1wiICQ5OSBwcmludHMgYSAzM3hcbiAgICAjIFJPQVMgYW5kIHRvcHMgZXZlcnkgbGVhZGVy
Ym9hcmQsIGJ1cnlpbmcgdGhlIHJlYWwgYmVzdCBwZXJmb3JtZXJzIHVuZGVyIGRpdmlzaW9uXG4gICAgIyBub2lzZS4gQXBw
cyB1bmRlciB0aGUgZmxvb3IgYXJlIEVYQ0xVREVEIGZyb20gdGhpcyByYW5raW5nLCBleGFjdGx5IGFzIGFwcHMgd2l0aCBh
XG4gICAgIyB6ZXJvIGRlbm9taW5hdG9yIGFscmVhZHkgYXJlLCBhbmQgZm9yIHRoZSBzYW1lIHJlYXNvbi5cbiAgICBtaW5f
ZGVub21pbmF0b3I6IGZsb2F0ID0gMC4wIiwgIm1hcmtlciI6ICJtaW5fZGVub21pbmF0b3I6IGZsb2F0ID0gMC4wIn0sIHsi
cGF0aCI6ICJiYWNrZW5kL2FwcC9zZXJ2aWNlcy9iZW5jaG1hcmtfc2VydmljZS5weSIsICJhbmNob3IiOiAiQkVOQ0hNQVJL
UzogdHVwbGVbQmVuY2htYXJrRGVmLCAuLi5dID0gKFxuICAgIEJlbmNobWFya0RlZihcInJvYXNcIiwgXCJST0FTXCIsIFwi
cnB0X2dyb3NzX3JldmVudWVfdXNkXCIsIFwicnB0X3VhX2Nvc3RfdXNkXCIsIFRydWUsIFwicmF0aW9cIiksXG4gICAgQmVu
Y2htYXJrRGVmKFxuICAgICAgICBcIm1hcmdpblwiLCBcIlByb2ZpdCBtYXJnaW5cIiwgXCJycHRfdGZfcHJvZml0X3VzZFwi
LCBcInJwdF9ncm9zc19yZXZlbnVlX3VzZFwiLCBUcnVlLCBcInBlcmNlbnRcIlxuICAgICksXG4gICAgQmVuY2htYXJrRGVm
KFwiY3BpXCIsIFwiQ1BJXCIsIFwicnB0X3VhX2Nvc3RfdXNkXCIsIFwidG90YWxfcGFpZF9pbnN0YWxsc1wiLCBGYWxzZSwg
XCJ1c2RcIiksXG4gICAgQmVuY2htYXJrRGVmKFxuICAgICAgICBcImFycGlcIiwgXCJSZXZlbnVlIHBlciBpbnN0YWxsXCIs
IFwicnB0X2dyb3NzX3JldmVudWVfdXNkXCIsIFwic3RvcmVfdG90YWxfaW5zdGFsbHNcIiwgVHJ1ZSwgXCJ1c2RcIlxuICAg
ICksXG4pIiwgInJlcGxhY2VtZW50IjogIkJFTkNITUFSS1M6IHR1cGxlW0JlbmNobWFya0RlZiwgLi4uXSA9IChcbiAgICBC
ZW5jaG1hcmtEZWYoXG4gICAgICAgIFwicm9hc1wiLCBcIlJPQVNcIiwgXCJycHRfZ3Jvc3NfcmV2ZW51ZV91c2RcIiwgXCJy
cHRfdWFfY29zdF91c2RcIiwgVHJ1ZSwgXCJyYXRpb1wiLFxuICAgICAgICBtaW5fZGVub21pbmF0b3I9MTAwLjAsICAjICQx
MDAgb2Ygc3BlbmQgYmVmb3JlIGEgUk9BUyBpcyB3b3J0aCByYW5raW5nXG4gICAgKSxcbiAgICBCZW5jaG1hcmtEZWYoXG4g
ICAgICAgIFwibWFyZ2luXCIsIFwiUHJvZml0IG1hcmdpblwiLCBcInJwdF90Zl9wcm9maXRfdXNkXCIsIFwicnB0X2dyb3Nz
X3JldmVudWVfdXNkXCIsIFRydWUsIFwicGVyY2VudFwiLFxuICAgICAgICBtaW5fZGVub21pbmF0b3I9MTAwLjAsICAjICQx
MDAgb2YgcmV2ZW51ZSBiZWZvcmUgYSBtYXJnaW4gbWVhbnMgYW55dGhpbmdcbiAgICApLFxuICAgIEJlbmNobWFya0RlZihc
biAgICAgICAgXCJjcGlcIiwgXCJDUElcIiwgXCJycHRfdWFfY29zdF91c2RcIiwgXCJ0b3RhbF9wYWlkX2luc3RhbGxzXCIs
IEZhbHNlLCBcInVzZFwiLFxuICAgICAgICBtaW5fZGVub21pbmF0b3I9MTAwLjAsICAjIDEwMCBwYWlkIGluc3RhbGxzIGJl
Zm9yZSBhIENQSSBpcyB3b3J0aCByYW5raW5nXG4gICAgKSxcbiAgICBCZW5jaG1hcmtEZWYoXG4gICAgICAgIFwiYXJwaVwi
LCBcIlJldmVudWUgcGVyIGluc3RhbGxcIiwgXCJycHRfZ3Jvc3NfcmV2ZW51ZV91c2RcIiwgXCJzdG9yZV90b3RhbF9pbnN0
YWxsc1wiLCBUcnVlLFxuICAgICAgICBcInVzZFwiLCBtaW5fZGVub21pbmF0b3I9MTAwLjAsICAjIDEwMCBpbnN0YWxscyBi
ZWZvcmUgcmV2ZW51ZS1wZXItaW5zdGFsbCBtZWFucyBhbnl0aGluZ1xuICAgICksXG4pIiwgIm1hcmtlciI6ICJtaW5fZGVu
b21pbmF0b3I9MTAwLjAsICAjICQxMDAgb2Ygc3BlbmQifSwgeyJwYXRoIjogImJhY2tlbmQvYXBwL3NlcnZpY2VzL2JlbmNo
bWFya19zZXJ2aWNlLnB5IiwgImFuY2hvciI6ICIgICAgICAgICAgICBkZW5vbWluYXRvciA9IGZsb2F0KHJvd1tiZW5jaG1h
cmsuZGVub21pbmF0b3JdIG9yIDAuMClcbiAgICAgICAgICAgIGlmIGRlbm9taW5hdG9yID09IDA6XG4gICAgICAgICAgICAg
ICAgIyBObyBzcGVuZCBtZWFucyBubyBST0FTLiBSYW5raW5nIGl0IGFzIHRoZSB3b3JzdCB3b3VsZCBwdXNoIGV2ZXJ5IHJl
YWxcbiAgICAgICAgICAgICAgICAjIGFwcCB1cCBhIHF1YXJ0aWxlIGFuZCBxdWlldGx5IGZsYXR0ZXIgdGhlIHBvcnRmb2xp
by5cbiAgICAgICAgICAgICAgICBjb250aW51ZSIsICJyZXBsYWNlbWVudCI6ICIgICAgICAgICAgICBkZW5vbWluYXRvciA9
IGZsb2F0KHJvd1tiZW5jaG1hcmsuZGVub21pbmF0b3JdIG9yIDAuMClcbiAgICAgICAgICAgIGlmIGRlbm9taW5hdG9yIDw9
IGJlbmNobWFyay5taW5fZGVub21pbmF0b3I6XG4gICAgICAgICAgICAgICAgIyBObyBzcGVuZCBtZWFucyBubyBST0FTIC0g
YW5kIE5FR0xJR0lCTEUgc3BlbmQgbWVhbnMgYSBST0FTIG1hZGUgb2ZcbiAgICAgICAgICAgICAgICAjIGRpdmlzaW9uIG5v
aXNlLiBSYW5raW5nIGVpdGhlciB3b3VsZCBwdXNoIGV2ZXJ5IHJlYWwgYXBwIHVwIGEgcXVhcnRpbGVcbiAgICAgICAgICAg
ICAgICAjIGFuZCBxdWlldGx5IGZsYXR0ZXIgdGhlIHBvcnRmb2xpby5cbiAgICAgICAgICAgICAgICBjb250aW51ZSIsICJt
YXJrZXIiOiAiaWYgZGVub21pbmF0b3IgPD0gYmVuY2htYXJrLm1pbl9kZW5vbWluYXRvcjoifV19
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
