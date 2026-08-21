#!/usr/bin/env python3
"""Keep the navigation on screen.

The sidebar and top bar scrolled away with the page (`aside` was position: relative), so
on every long page the user lost the map - and on short windows the last nav items
(Security, Data Health) sat below the fold with no way to reach them except scrolling
the whole page. Navigation that disappears is the single most disorienting defect the
audit found, and the cheapest to fix.

The aside becomes sticky at full viewport height; the nav LIST scrolls inside it (the
aside itself keeps overflow visible, because the edge chevron deliberately rides outside
the border). The header sticks with a z-index above the charts."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

FOOTER = 'Rebuild the frontend, then run its test suite.'

PAYLOAD = """
eyJuZXdfZmlsZXMiOiB7fSwgImVkaXRzIjogW3sicGF0aCI6ICJmcm9udGVuZC9jb21wb25lbnRzL2xheW91dC9zaWRlYmFy
LnRzeCIsICJhbmNob3IiOiAiICAgICAgICBcInJlbGF0aXZlIGhpZGRlbiBzaHJpbmstMCBib3JkZXItciBiZy1jYXJkIG1k
OmJsb2NrXCIsIiwgInJlcGxhY2VtZW50IjogIiAgICAgICAgLy8gU3RpY2t5LCBub3QgcmVsYXRpdmU6IG5hdmlnYXRpb24g
dGhhdCBzY3JvbGxzIGF3YXkgd2l0aCB0aGUgcGFnZSBsb3NlcyB0aGVcbiAgICAgICAgLy8gdXNlciBvbiBldmVyeSBsb25n
IHBhZ2UuIHNlbGYtc3RhcnQga2VlcHMgc3RpY2t5IHdvcmtpbmcgaW5zaWRlIHRoZSBmbGV4IHJvdy5cbiAgICAgICAgXCJz
dGlja3kgdG9wLTAgaC1zY3JlZW4gc2VsZi1zdGFydCBoaWRkZW4gc2hyaW5rLTAgYm9yZGVyLXIgYmctY2FyZCBtZDpibG9j
a1wiLCIsICJtYXJrZXIiOiAiXCJzdGlja3kgdG9wLTAgaC1zY3JlZW4gc2VsZi1zdGFydCBoaWRkZW4gc2hyaW5rLTAgYm9y
ZGVyLXIgYmctY2FyZCBtZDpibG9ja1wiLCJ9LCB7InBhdGgiOiAiZnJvbnRlbmQvY29tcG9uZW50cy9sYXlvdXQvc2lkZWJh
ci50c3giLCAiYW5jaG9yIjogIiAgICAgICAgPG5hdiBjbGFzc05hbWU9XCJzcGFjZS15LTEgb3ZlcmZsb3cteC1oaWRkZW4g
cC0yXCIgZGF0YS10b3VyPVwibmF2XCI+IiwgInJlcGxhY2VtZW50IjogIiAgICAgICAgPG5hdlxuICAgICAgICAgIC8vIENh
cHBlZCB1bmRlciB0aGUgaC0xNCBoZWFkZXIgYW5kIHNjcm9sbGFibGUsIHNvIHRoZSBsYXN0IGl0ZW1zIChTZWN1cml0eSxc
biAgICAgICAgICAvLyBEYXRhIEhlYWx0aCkgc3RheSByZWFjaGFibGUgb24gc2hvcnQgd2luZG93cyBpbnN0ZWFkIG9mIGZh
bGxpbmcgb2ZmIHNjcmVlbi5cbiAgICAgICAgICBjbGFzc05hbWU9XCJtYXgtaC1bY2FsYygxMDB2aC0zLjVyZW0pXSBzcGFj
ZS15LTEgb3ZlcmZsb3cteS1hdXRvIG92ZXJmbG93LXgtaGlkZGVuIHAtMlwiXG4gICAgICAgICAgZGF0YS10b3VyPVwibmF2
XCJcbiAgICAgICAgPiIsICJtYXJrZXIiOiAiY2xhc3NOYW1lPVwibWF4LWgtW2NhbGMoMTAwdmgtMy41cmVtKV0gc3BhY2Ut
eS0xIG92ZXJmbG93LXktYXV0byBvdmVyZmxvdy14LWhpZGRlbiBwLTJcIiJ9LCB7InBhdGgiOiAiZnJvbnRlbmQvY29tcG9u
ZW50cy9sYXlvdXQvc2lkZWJhci50c3giLCAiYW5jaG9yIjogIiAgICAgICAgPG5hdiBjbGFzc05hbWU9e2NuKFwic3BhY2Ut
eS00IG92ZXJmbG93LXktYXV0byBvdmVyZmxvdy14LWhpZGRlbiBwLTJcIiwgY29sbGFwc2VkICYmIFwic3BhY2UteS0zIHB5
LTNcIil9IGRhdGEtdG91cj1cIm5hdlwiPiIsICJyZXBsYWNlbWVudCI6ICIgICAgICAgIDxuYXZcbiAgICAgICAgICBjbGFz
c05hbWU9e2NuKFxuICAgICAgICAgICAgLy8gQ2FwcGVkIHVuZGVyIHRoZSBoLTE0IGhlYWRlciBzbyB0aGUgbGlzdCBzY3Jv
bGxzIElOU0lERSB0aGUgc3RpY2t5IGFzaWRlXG4gICAgICAgICAgICAvLyBhbmQgdGhlIGxhc3QgaXRlbXMgc3RheSByZWFj
aGFibGUgb24gc2hvcnQgd2luZG93cy5cbiAgICAgICAgICAgIFwibWF4LWgtW2NhbGMoMTAwdmgtMy41cmVtKV0gc3BhY2Ut
eS00IG92ZXJmbG93LXktYXV0byBvdmVyZmxvdy14LWhpZGRlbiBwLTJcIixcbiAgICAgICAgICAgIGNvbGxhcHNlZCAmJiBc
InNwYWNlLXktMyBweS0zXCIsXG4gICAgICAgICAgKX1cbiAgICAgICAgICBkYXRhLXRvdXI9XCJuYXZcIlxuICAgICAgICA+
IiwgIm1hcmtlciI6ICJcIm1heC1oLVtjYWxjKDEwMHZoLTMuNXJlbSldIHNwYWNlLXktNCBvdmVyZmxvdy15LWF1dG8gb3Zl
cmZsb3cteC1oaWRkZW4gcC0yXCIsIn0sIHsicGF0aCI6ICJmcm9udGVuZC9jb21wb25lbnRzL2xheW91dC9oZWFkZXIudHN4
IiwgImFuY2hvciI6ICIgICAgPGhlYWRlciBjbGFzc05hbWU9XCJmbGV4IGgtMTQgaXRlbXMtY2VudGVyIGdhcC0yIGJvcmRl
ci1iIGJnLWNhcmQgcHgtMyBzbTpweC00XCI+IiwgInJlcGxhY2VtZW50IjogIiAgICAvLyBTdGlja3kgd2l0aCBhIHotaW5k
ZXggYWJvdmUgdGhlIGNoYXJ0cywgZm9yIHRoZSBzYW1lIHJlYXNvbiB0aGUgc2lkZWJhciBpczpcbiAgICAvLyB0aGUgY29u
dHJvbHMgdGhhdCBvcmllbnQgdGhlIHVzZXIgbXVzdCBub3Qgc2Nyb2xsIGF3YXkgd2l0aCB0aGUgY29udGVudC5cbiAgICA8
aGVhZGVyIGNsYXNzTmFtZT1cInN0aWNreSB0b3AtMCB6LTMwIGZsZXggaC0xNCBpdGVtcy1jZW50ZXIgZ2FwLTIgYm9yZGVy
LWIgYmctY2FyZCBweC0zIHNtOnB4LTRcIj4iLCAibWFya2VyIjogIlwic3RpY2t5IHRvcC0wIHotMzAgZmxleCBoLTE0IGl0
ZW1zLWNlbnRlciBnYXAtMiBib3JkZXItYiBiZy1jYXJkIHB4LTMgc206cHgtNFwiIn1dfQ==
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
