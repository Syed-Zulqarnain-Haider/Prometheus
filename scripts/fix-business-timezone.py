#!/usr/bin/env python3
"""Pin "today" to the business clock instead of the viewer's machine.

Every preset date range starts from `const today = new Date()` - the browser's clock.
A viewer in another timezone (or with a wrong clock) got a different "Last 30 days"
than the person at the next desk, and the audit's browser proved it: running at a
far-east offset it saw tomorrow's date in the greeting, date ranges ending "tomorrow",
and every timestamp shifted. The platform's math was right; the clock it trusted wasn't.

`businessToday()` computes the calendar date in Asia/Karachi regardless of where the
viewer sits. The greeting keeps the LOCAL hour for its "Working late" phrase - that is
about the person - but prints the BUSINESS date, because that is about the data."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

FOOTER = 'Rebuild the frontend, then run its test suite.'

PAYLOAD = """
eyJuZXdfZmlsZXMiOiB7ImZyb250ZW5kL2xpYi9idXNpbmVzcy10aW1lLnRzIjogIi8qKiBUaGUgYnVzaW5lc3MgcnVucyBv
biBvbmUgY2xvY2suXG4gKlxuICogIE1ldHJpY3MgYXJlIGRhaWx5IHJvd3MgaW4gdGhlIHdhcmVob3VzZSdzIGRheSwgYW5k
IFwidG9kYXlcIiBkZWNpZGVzIGV2ZXJ5IHByZXNldCBkYXRlXG4gKiAgcmFuZ2Ugb24gdGhlIHBsYXRmb3JtLiBMZWZ0IHRv
IHRoZSBicm93c2VyLCBhIHZpZXdlciB3aG9zZSBtYWNoaW5lIGlzIHNldCB0byBhbm90aGVyXG4gKiAgdGltZXpvbmUgLSBv
ciBzaW1wbHkgdG8gdGhlIHdyb25nIHRpbWUgLSBxdWlldGx5IHNlZXMgYSBkaWZmZXJlbnQgXCJ0b2RheVwiIHRoYW4gdGhl
XG4gKiAgcGVyc29uIGF0IHRoZSBuZXh0IGRlc2ssIGFuZCB0aGVpciBcIkxhc3QgMzAgZGF5c1wiIGVuZHMgb24gYSBkaWZm
ZXJlbnQgZGF5LiBUaGF0IGlzXG4gKiAgZXhhY3RseSB3aGF0IGEgZnVsbC1wbGF0Zm9ybSBhdWRpdCByZXBvcnRlZCBhcyBh
IHRpbWV6b25lIGJ1ZzogdGhlIGF1ZGl0aW5nIGJyb3dzZXJcbiAqICB3YXMgb24gYW5vdGhlciBjbG9jaywgYW5kIGV2ZXJ5
IGRhdGUgaXQgc2F3IHNoaWZ0ZWQgd2l0aCBpdC5cbiAqL1xuZXhwb3J0IGNvbnN0IEJVU0lORVNTX1RJTUVfWk9ORSA9IFwi
QXNpYS9LYXJhY2hpXCI7XG5cbi8qKiBUb2RheSdzIGNhbGVuZGFyIGRhdGUgb24gdGhlIGJ1c2luZXNzIGNsb2NrLCBhcyBh
IERhdGUgYXQgbG9jYWwgbWlkbmlnaHQgLSBzYWZlIGZvclxuICogIGRhdGUtZm5zIGhlbHBlcnMsIHdoaWNoIG9ubHkgcmVh
ZCB0aGUgY2FsZW5kYXIgZmllbGRzLiBlbi1DQSBmb3JtYXRzIGFzIFlZWVktTU0tREQuICovXG5leHBvcnQgZnVuY3Rpb24g
YnVzaW5lc3NUb2RheSgpOiBEYXRlIHtcbiAgY29uc3QgZGF5ID0gbmV3IEludGwuRGF0ZVRpbWVGb3JtYXQoXCJlbi1DQVwi
LCB7XG4gICAgdGltZVpvbmU6IEJVU0lORVNTX1RJTUVfWk9ORSxcbiAgICB5ZWFyOiBcIm51bWVyaWNcIixcbiAgICBtb250
aDogXCIyLWRpZ2l0XCIsXG4gICAgZGF5OiBcIjItZGlnaXRcIixcbiAgfSkuZm9ybWF0KG5ldyBEYXRlKCkpO1xuICByZXR1
cm4gbmV3IERhdGUoYCR7ZGF5fVQwMDowMDowMGApO1xufVxuIn0sICJlZGl0cyI6IFt7InBhdGgiOiAiZnJvbnRlbmQvbGli
L2ZpbHRlcnMudHMiLCAiYW5jaG9yIjogImltcG9ydCB7IGVuZE9mTW9udGgsIGZvcm1hdCwgc3RhcnRPZk1vbnRoLCBzdWJE
YXlzLCBzdWJNb250aHMgfSBmcm9tIFwiZGF0ZS1mbnNcIjsiLCAicmVwbGFjZW1lbnQiOiAiaW1wb3J0IHsgZW5kT2ZNb250
aCwgZm9ybWF0LCBzdGFydE9mTW9udGgsIHN1YkRheXMsIHN1Yk1vbnRocyB9IGZyb20gXCJkYXRlLWZuc1wiO1xuXG5pbXBv
cnQgeyBidXNpbmVzc1RvZGF5IH0gZnJvbSBcIkAvbGliL2J1c2luZXNzLXRpbWVcIjsiLCAibWFya2VyIjogImltcG9ydCB7
IGJ1c2luZXNzVG9kYXkgfSBmcm9tIFwiQC9saWIvYnVzaW5lc3MtdGltZVwiOyJ9LCB7InBhdGgiOiAiZnJvbnRlbmQvbGli
L2ZpbHRlcnMudHMiLCAiYW5jaG9yIjogIiAgY29uc3QgdG9kYXkgPSBuZXcgRGF0ZSgpOyIsICJyZXBsYWNlbWVudCI6ICIg
IC8vIFRoZSBCVVNJTkVTUyBjbG9jaywgbm90IHRoZSBicm93c2VyJ3MgLSBzZWUgbGliL2J1c2luZXNzLXRpbWUudHMgZm9y
IHdoeS5cbiAgY29uc3QgdG9kYXkgPSBidXNpbmVzc1RvZGF5KCk7IiwgIm1hcmtlciI6ICJjb25zdCB0b2RheSA9IGJ1c2lu
ZXNzVG9kYXkoKTsifSwgeyJwYXRoIjogImZyb250ZW5kL2NvbXBvbmVudHMvb3ZlcnZpZXcvZ3JlZXRpbmctaGVyby50c3gi
LCAiYW5jaG9yIjogIlwidXNlIGNsaWVudFwiO1xuIiwgInJlcGxhY2VtZW50IjogIlwidXNlIGNsaWVudFwiO1xuXG5pbXBv
cnQgeyBCVVNJTkVTU19USU1FX1pPTkUgfSBmcm9tIFwiQC9saWIvYnVzaW5lc3MtdGltZVwiO1xuIiwgIm1hcmtlciI6ICJp
bXBvcnQgeyBCVVNJTkVTU19USU1FX1pPTkUgfSBmcm9tIFwiQC9saWIvYnVzaW5lc3MtdGltZVwiOyJ9LCB7InBhdGgiOiAi
ZnJvbnRlbmQvY29tcG9uZW50cy9vdmVydmlldy9ncmVldGluZy1oZXJvLnRzeCIsICJhbmNob3IiOiAiICAgICAgICAgICAg
YCBcdTAwYjcgJHtub3cudG9Mb2NhbGVEYXRlU3RyaW5nKHVuZGVmaW5lZCwge1xuICAgICAgICAgICAgICB3ZWVrZGF5OiBc
ImxvbmdcIixcbiAgICAgICAgICAgICAgbW9udGg6IFwibG9uZ1wiLFxuICAgICAgICAgICAgICBkYXk6IFwibnVtZXJpY1wi
LFxuICAgICAgICAgICAgfSl9YH0iLCAicmVwbGFjZW1lbnQiOiAiICAgICAgICAgICAgYCBcdTAwYjcgJHtub3cudG9Mb2Nh
bGVEYXRlU3RyaW5nKHVuZGVmaW5lZCwge1xuICAgICAgICAgICAgICB3ZWVrZGF5OiBcImxvbmdcIixcbiAgICAgICAgICAg
ICAgbW9udGg6IFwibG9uZ1wiLFxuICAgICAgICAgICAgICBkYXk6IFwibnVtZXJpY1wiLFxuICAgICAgICAgICAgICAvLyBU
aGUgZ3JlZXRpbmcncyBIT1VSIGlzIHRoZSB2aWV3ZXIncyAtIHRoYXQgbGluZSBpcyBhYm91dCB0aGUgcGVyc29uLlxuICAg
ICAgICAgICAgICAvLyBUaGUgREFURSBpcyB0aGUgYnVzaW5lc3MgZGF5LCBiZWNhdXNlIGl0IHNpdHMgb3ZlciBidXNpbmVz
cyBudW1iZXJzLlxuICAgICAgICAgICAgICB0aW1lWm9uZTogQlVTSU5FU1NfVElNRV9aT05FLFxuICAgICAgICAgICAgfSl9
YH0iLCAibWFya2VyIjogInRpbWVab25lOiBCVVNJTkVTU19USU1FX1pPTkUsIn1dfQ==
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
