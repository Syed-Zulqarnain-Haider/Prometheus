#!/usr/bin/env python3
"""The filter jump: keep the previous answer on screen while the next one loads.

Clicking a filter collapsed every widget on the page to a skeleton and then back to
content. On the Overview - fifteen auto-height widgets in a vertically-packing grid -
that is two full re-packs per click, which is the jumping people were describing. It
also loses the reader\'s place: the number they were looking at disappears and comes
back somewhere else.

Only the filter-option dropdowns were keeping their previous data; the fifteen queries
behind the actual widgets were not. This adds `placeholderData: keepPreviousData` to the
aggregate queries that a filter change re-keys.

Split out of platform-batch.py deliberately. These eleven insertions are the only ones
whose surroundings could not be read from the deployed tree, so they are kept where a
miss cannot block anything else - and unlike the batch scripts this one is NOT
all-or-nothing, because each insertion stands alone and re-running is harmless.

The insertion goes at the TOP of each options object rather than the bottom, so the
hook\'s tail never has to be matched. Key order in an object literal means nothing; not
having to know the tail means nine of these cannot miss for a reason as trivial as a
reformatted queryFn. What it does need is the guard below: if a hook already carries
placeholderData further down its own body, adding a second one is a duplicate key and a
type error, so that hook is skipped rather than patched.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

PAYLOAD = """
eyJuZXdfZmlsZXMiOiB7fSwgImFwcGVuZHMiOiBbXSwgImVkaXRzIjogW3sicGF0aCI6ICJmcm9u
dGVuZC9saWIvYXBpLWhvb2tzLnRzIiwgImFuY2hvciI6ICIgICAgcXVlcnlLZXk6IFtcInN1bW1h
cnlcIiwgcGFyYW1zXSwiLCAicmVwbGFjZW1lbnQiOiAiICAgIHF1ZXJ5S2V5OiBbXCJzdW1tYXJ5
XCIsIHBhcmFtc10sXG4gICAgLy8gS2VlcCB0aGUgcHJldmlvdXMgYW5zd2VyIG9uIHNjcmVlbiB3
aGlsZSB0aGUgbmV3IG9uZSBsb2Fkcy5cbiAgICAvL1xuICAgIC8vIFdpdGhvdXQgdGhpcywgY2hh
bmdpbmcgYSBmaWx0ZXIgY29sbGFwc2VkIGV2ZXJ5IHdpZGdldCB0byBhIHNrZWxldG9uIGFuZCB0
aGVuIGJhY2tcbiAgICAvLyB0byBjb250ZW50LiBPbiB0aGUgT3ZlcnZpZXcgLSBmaWZ0ZWVuIGF1
dG8taGVpZ2h0IHdpZGdldHMgaW4gYSB2ZXJ0aWNhbGx5LXBhY2tpbmdcbiAgICAvLyBncmlkIC0g
dGhhdCBpcyB0d28gZnVsbCByZS1wYWNrcyBwZXIgY2xpY2ssIHdoaWNoIGlzIHRoZSBqdW1wIHBl
b3BsZSB3ZXJlIHNlZWluZy5cbiAgICAvLyBJdCBhbHNvIGxvc2VzIHRoZSByZWFkZXIncyBwbGFj
ZTogdGhlIG51bWJlciB0aGV5IHdlcmUgbG9va2luZyBhdCB2YW5pc2hlcyBhbmRcbiAgICAvLyBy
ZWFwcGVhcnMgc29tZXdoZXJlIGVsc2Ugb24gdGhlIHBhZ2UuXG4gICAgcGxhY2Vob2xkZXJEYXRh
OiBrZWVwUHJldmlvdXNEYXRhLCIsICJtYXJrZXIiOiAiICAgIHF1ZXJ5S2V5OiBbXCJzdW1tYXJ5
XCIsIHBhcmFtc10sXG4gICAgLy8gS2VlcCB0aGUgcHJldmlvdXMgYW5zd2VyIG9uIHNjcmVlbiB3
aGlsZSB0aGUgbmV3IG9uZSBsb2Fkcy5cbiAgICAvL1xuICAgIC8vIFdpdGhvdXQgdGhpcywgY2hh
bmdpbmcgYSBmaWx0ZXIgY29sbGFwc2VkIGV2ZXJ5IHdpZGdldCB0byBhIHNrZWxldG9uIGFuZCB0
aGVuIGJhY2tcbiAgICAvLyB0byBjb250ZW50LiBPbiB0aGUgT3ZlcnZpZXcgLSBmaWZ0ZWVuIGF1
dG8taGVpZ2h0IHdpZGdldHMgaW4gYSB2ZXJ0aWNhbGx5LXBhY2tpbmdcbiAgICAvLyBncmlkIC0g
dGhhdCBpcyB0d28gZnVsbCByZS1wYWNrcyBwZXIgY2xpY2ssIHdoaWNoIGlzIHRoZSBqdW1wIHBl
b3BsZSB3ZXJlIHNlZWluZy5cbiAgICAvLyBJdCBhbHNvIGxvc2VzIHRoZSByZWFkZXIncyBwbGFj
ZTogdGhlIG51bWJlciB0aGV5IHdlcmUgbG9va2luZyBhdCB2YW5pc2hlcyBhbmRcbiAgICAvLyBy
ZWFwcGVhcnMgc29tZXdoZXJlIGVsc2Ugb24gdGhlIHBhZ2UuXG4gICAgcGxhY2Vob2xkZXJEYXRh
OiBrZWVwUHJldmlvdXNEYXRhLCIsICJyZWdpb25faGFzIjogInBsYWNlaG9sZGVyRGF0YSJ9LCB7
InBhdGgiOiAiZnJvbnRlbmQvbGliL2FwaS1ob29rcy50cyIsICJhbmNob3IiOiAiICAgIHF1ZXJ5
S2V5OiBbXCJ0aW1lc2VyaWVzXCIsIHBhcmFtc10sIiwgInJlcGxhY2VtZW50IjogIiAgICBxdWVy
eUtleTogW1widGltZXNlcmllc1wiLCBwYXJhbXNdLFxuICAgIC8vIFByZXZpb3VzIGFuc3dlciBz
dGF5cyBvbiBzY3JlZW4gd2hpbGUgdGhlIG5ldyBvbmUgbG9hZHMgLSBzZWUgdXNlU3VtbWFyeS5c
biAgICBwbGFjZWhvbGRlckRhdGE6IGtlZXBQcmV2aW91c0RhdGEsIiwgIm1hcmtlciI6ICIgICAg
cXVlcnlLZXk6IFtcInRpbWVzZXJpZXNcIiwgcGFyYW1zXSxcbiAgICAvLyBQcmV2aW91cyBhbnN3
ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxlIHRoZSBuZXcgb25lIGxvYWRzIC0gc2VlIHVzZVN1bW1h
cnkuXG4gICAgcGxhY2Vob2xkZXJEYXRhOiBrZWVwUHJldmlvdXNEYXRhLCIsICJyZWdpb25faGFz
IjogInBsYWNlaG9sZGVyRGF0YSJ9LCB7InBhdGgiOiAiZnJvbnRlbmQvbGliL2FwaS1ob29rcy50
cyIsICJhbmNob3IiOiAiICAgIHF1ZXJ5S2V5OiBbXCJ0aW1lc2VyaWVzLXByZXZcIiwgcGFyYW1z
XSwiLCAicmVwbGFjZW1lbnQiOiAiICAgIHF1ZXJ5S2V5OiBbXCJ0aW1lc2VyaWVzLXByZXZcIiwg
cGFyYW1zXSxcbiAgICAvLyBQcmV2aW91cyBhbnN3ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxlIHRo
ZSBuZXcgb25lIGxvYWRzIC0gc2VlIHVzZVN1bW1hcnkuXG4gICAgcGxhY2Vob2xkZXJEYXRhOiBr
ZWVwUHJldmlvdXNEYXRhLCIsICJtYXJrZXIiOiAiICAgIHF1ZXJ5S2V5OiBbXCJ0aW1lc2VyaWVz
LXByZXZcIiwgcGFyYW1zXSxcbiAgICAvLyBQcmV2aW91cyBhbnN3ZXIgc3RheXMgb24gc2NyZWVu
IHdoaWxlIHRoZSBuZXcgb25lIGxvYWRzIC0gc2VlIHVzZVN1bW1hcnkuXG4gICAgcGxhY2Vob2xk
ZXJEYXRhOiBrZWVwUHJldmlvdXNEYXRhLCIsICJyZWdpb25faGFzIjogInBsYWNlaG9sZGVyRGF0
YSJ9LCB7InBhdGgiOiAiZnJvbnRlbmQvbGliL2FwaS1ob29rcy50cyIsICJhbmNob3IiOiAiICAg
IHF1ZXJ5S2V5OiBbXCJicmVha2Rvd25cIiwgcGFyYW1zXSwiLCAicmVwbGFjZW1lbnQiOiAiICAg
IHF1ZXJ5S2V5OiBbXCJicmVha2Rvd25cIiwgcGFyYW1zXSxcbiAgICAvLyBQcmV2aW91cyBhbnN3
ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxlIHRoZSBuZXcgb25lIGxvYWRzIC0gc2VlIHVzZVN1bW1h
cnkuXG4gICAgcGxhY2Vob2xkZXJEYXRhOiBrZWVwUHJldmlvdXNEYXRhLCIsICJtYXJrZXIiOiAi
ICAgIHF1ZXJ5S2V5OiBbXCJicmVha2Rvd25cIiwgcGFyYW1zXSxcbiAgICAvLyBQcmV2aW91cyBh
bnN3ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxlIHRoZSBuZXcgb25lIGxvYWRzIC0gc2VlIHVzZVN1
bW1hcnkuXG4gICAgcGxhY2Vob2xkZXJEYXRhOiBrZWVwUHJldmlvdXNEYXRhLCIsICJyZWdpb25f
aGFzIjogInBsYWNlaG9sZGVyRGF0YSJ9LCB7InBhdGgiOiAiZnJvbnRlbmQvbGliL2FwaS1ob29r
cy50cyIsICJhbmNob3IiOiAiICAgIHF1ZXJ5S2V5OiBbXCJjb250cmlidXRpb25cIiwgcGFyYW1z
XSwiLCAicmVwbGFjZW1lbnQiOiAiICAgIHF1ZXJ5S2V5OiBbXCJjb250cmlidXRpb25cIiwgcGFy
YW1zXSxcbiAgICAvLyBQcmV2aW91cyBhbnN3ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxlIHRoZSBu
ZXcgb25lIGxvYWRzIC0gc2VlIHVzZVN1bW1hcnkuXG4gICAgcGxhY2Vob2xkZXJEYXRhOiBrZWVw
UHJldmlvdXNEYXRhLCIsICJtYXJrZXIiOiAiICAgIHF1ZXJ5S2V5OiBbXCJjb250cmlidXRpb25c
IiwgcGFyYW1zXSxcbiAgICAvLyBQcmV2aW91cyBhbnN3ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxl
IHRoZSBuZXcgb25lIGxvYWRzIC0gc2VlIHVzZVN1bW1hcnkuXG4gICAgcGxhY2Vob2xkZXJEYXRh
OiBrZWVwUHJldmlvdXNEYXRhLCIsICJyZWdpb25faGFzIjogInBsYWNlaG9sZGVyRGF0YSJ9LCB7
InBhdGgiOiAiZnJvbnRlbmQvbGliL2FwaS1ob29rcy50cyIsICJhbmNob3IiOiAiICAgIHF1ZXJ5
S2V5OiBbXCJ0YWJsZS1pbmZpbml0ZVwiLCBiYXNlXSwiLCAicmVwbGFjZW1lbnQiOiAiICAgIHF1
ZXJ5S2V5OiBbXCJ0YWJsZS1pbmZpbml0ZVwiLCBiYXNlXSxcbiAgICAvLyBQcmV2aW91cyBhbnN3
ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxlIHRoZSBuZXcgb25lIGxvYWRzIC0gc2VlIHVzZVN1bW1h
cnkuXG4gICAgcGxhY2Vob2xkZXJEYXRhOiBrZWVwUHJldmlvdXNEYXRhLCIsICJtYXJrZXIiOiAi
ICAgIHF1ZXJ5S2V5OiBbXCJ0YWJsZS1pbmZpbml0ZVwiLCBiYXNlXSxcbiAgICAvLyBQcmV2aW91
cyBhbnN3ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxlIHRoZSBuZXcgb25lIGxvYWRzIC0gc2VlIHVz
ZVN1bW1hcnkuXG4gICAgcGxhY2Vob2xkZXJEYXRhOiBrZWVwUHJldmlvdXNEYXRhLCIsICJyZWdp
b25faGFzIjogInBsYWNlaG9sZGVyRGF0YSJ9LCB7InBhdGgiOiAiZnJvbnRlbmQvbGliL2FwaS1o
b29rcy50cyIsICJhbmNob3IiOiAiICAgIHF1ZXJ5S2V5OiBbXCJ0YWJsZVwiLCBwYXJhbXNdLCIs
ICJyZXBsYWNlbWVudCI6ICIgICAgcXVlcnlLZXk6IFtcInRhYmxlXCIsIHBhcmFtc10sXG4gICAg
Ly8gUHJldmlvdXMgYW5zd2VyIHN0YXlzIG9uIHNjcmVlbiB3aGlsZSB0aGUgbmV3IG9uZSBsb2Fk
cyAtIHNlZSB1c2VTdW1tYXJ5LlxuICAgIHBsYWNlaG9sZGVyRGF0YToga2VlcFByZXZpb3VzRGF0
YSwiLCAibWFya2VyIjogIiAgICBxdWVyeUtleTogW1widGFibGVcIiwgcGFyYW1zXSxcbiAgICAv
LyBQcmV2aW91cyBhbnN3ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxlIHRoZSBuZXcgb25lIGxvYWRz
IC0gc2VlIHVzZVN1bW1hcnkuXG4gICAgcGxhY2Vob2xkZXJEYXRhOiBrZWVwUHJldmlvdXNEYXRh
LCIsICJyZWdpb25faGFzIjogInBsYWNlaG9sZGVyRGF0YSJ9LCB7InBhdGgiOiAiZnJvbnRlbmQv
bGliL2FwaS1ob29rcy50cyIsICJhbmNob3IiOiAiICAgIHF1ZXJ5S2V5OiBbXCJhbm5vdGF0aW9u
c1wiLCBmcm9tLCB0b10sIiwgInJlcGxhY2VtZW50IjogIiAgICBxdWVyeUtleTogW1wiYW5ub3Rh
dGlvbnNcIiwgZnJvbSwgdG9dLFxuICAgIC8vIFByZXZpb3VzIGFuc3dlciBzdGF5cyBvbiBzY3Jl
ZW4gd2hpbGUgdGhlIG5ldyBvbmUgbG9hZHMgLSBzZWUgdXNlU3VtbWFyeS5cbiAgICBwbGFjZWhv
bGRlckRhdGE6IGtlZXBQcmV2aW91c0RhdGEsIiwgIm1hcmtlciI6ICIgICAgcXVlcnlLZXk6IFtc
ImFubm90YXRpb25zXCIsIGZyb20sIHRvXSxcbiAgICAvLyBQcmV2aW91cyBhbnN3ZXIgc3RheXMg
b24gc2NyZWVuIHdoaWxlIHRoZSBuZXcgb25lIGxvYWRzIC0gc2VlIHVzZVN1bW1hcnkuXG4gICAg
cGxhY2Vob2xkZXJEYXRhOiBrZWVwUHJldmlvdXNEYXRhLCIsICJyZWdpb25faGFzIjogInBsYWNl
aG9sZGVyRGF0YSJ9LCB7InBhdGgiOiAiZnJvbnRlbmQvbGliL2FwaS1ob29rcy50cyIsICJhbmNo
b3IiOiAiICAgIHF1ZXJ5S2V5OiBbXCJhbm9tYWxpZXNcIiwgcGFyYW1zXSwiLCAicmVwbGFjZW1l
bnQiOiAiICAgIHF1ZXJ5S2V5OiBbXCJhbm9tYWxpZXNcIiwgcGFyYW1zXSxcbiAgICAvLyBQcmV2
aW91cyBhbnN3ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxlIHRoZSBuZXcgb25lIGxvYWRzIC0gc2Vl
IHVzZVN1bW1hcnkuXG4gICAgcGxhY2Vob2xkZXJEYXRhOiBrZWVwUHJldmlvdXNEYXRhLCIsICJt
YXJrZXIiOiAiICAgIHF1ZXJ5S2V5OiBbXCJhbm9tYWxpZXNcIiwgcGFyYW1zXSxcbiAgICAvLyBQ
cmV2aW91cyBhbnN3ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxlIHRoZSBuZXcgb25lIGxvYWRzIC0g
c2VlIHVzZVN1bW1hcnkuXG4gICAgcGxhY2Vob2xkZXJEYXRhOiBrZWVwUHJldmlvdXNEYXRhLCIs
ICJyZWdpb25faGFzIjogInBsYWNlaG9sZGVyRGF0YSJ9LCB7InBhdGgiOiAiZnJvbnRlbmQvbGli
L2FwaS1ob29rcy50cyIsICJhbmNob3IiOiAiICAgIHF1ZXJ5S2V5OiBbXCJiZW5jaG1hcmtzXCIs
IHBhcmFtc10sIiwgInJlcGxhY2VtZW50IjogIiAgICBxdWVyeUtleTogW1wiYmVuY2htYXJrc1wi
LCBwYXJhbXNdLFxuICAgIC8vIFByZXZpb3VzIGFuc3dlciBzdGF5cyBvbiBzY3JlZW4gd2hpbGUg
dGhlIG5ldyBvbmUgbG9hZHMgLSBzZWUgdXNlU3VtbWFyeS5cbiAgICBwbGFjZWhvbGRlckRhdGE6
IGtlZXBQcmV2aW91c0RhdGEsIiwgIm1hcmtlciI6ICIgICAgcXVlcnlLZXk6IFtcImJlbmNobWFy
a3NcIiwgcGFyYW1zXSxcbiAgICAvLyBQcmV2aW91cyBhbnN3ZXIgc3RheXMgb24gc2NyZWVuIHdo
aWxlIHRoZSBuZXcgb25lIGxvYWRzIC0gc2VlIHVzZVN1bW1hcnkuXG4gICAgcGxhY2Vob2xkZXJE
YXRhOiBrZWVwUHJldmlvdXNEYXRhLCIsICJyZWdpb25faGFzIjogInBsYWNlaG9sZGVyRGF0YSJ9
LCB7InBhdGgiOiAiZnJvbnRlbmQvbGliL2FwaS1ob29rcy50cyIsICJhbmNob3IiOiAiICAgIHF1
ZXJ5S2V5OiBbXCJwYWNpbmctYm9hcmRcIiwgeWVhciwgbW9udGhdLCIsICJyZXBsYWNlbWVudCI6
ICIgICAgcXVlcnlLZXk6IFtcInBhY2luZy1ib2FyZFwiLCB5ZWFyLCBtb250aF0sXG4gICAgLy8g
UHJldmlvdXMgYW5zd2VyIHN0YXlzIG9uIHNjcmVlbiB3aGlsZSB0aGUgbmV3IG9uZSBsb2FkcyAt
IHNlZSB1c2VTdW1tYXJ5LlxuICAgIHBsYWNlaG9sZGVyRGF0YToga2VlcFByZXZpb3VzRGF0YSwi
LCAibWFya2VyIjogIiAgICBxdWVyeUtleTogW1wicGFjaW5nLWJvYXJkXCIsIHllYXIsIG1vbnRo
XSxcbiAgICAvLyBQcmV2aW91cyBhbnN3ZXIgc3RheXMgb24gc2NyZWVuIHdoaWxlIHRoZSBuZXcg
b25lIGxvYWRzIC0gc2VlIHVzZVN1bW1hcnkuXG4gICAgcGxhY2Vob2xkZXJEYXRhOiBrZWVwUHJl
dmlvdXNEYXRhLCIsICJyZWdpb25faGFzIjogInBsYWNlaG9sZGVyRGF0YSJ9XX0=
"""


def region_end(text: str, start: int) -> int:
    """End of the useQuery options object the anchor sits in."""
    close = text.find("\n  });", start)
    return len(text) if close == -1 else close


def locate(lines: list[str], anchor: str) -> int | None:
    """Line index where the longest present run of the anchor\'s own lines begins."""
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
    for offset, line in sorted(
        enumerate(wanted), key=lambda pair: len(pair[1].strip()), reverse=True
    ):
        if len(line.strip()) < 12:
            break
        index = joined.find(line)
        if index != -1:
            return joined.count("\n", 0, index) - offset
    return None


def main() -> int:
    if not Path("frontend/lib").is_dir():
        print("ABORTED: run this from the repository root")
        return 1

    data = json.loads(base64.b64decode(PAYLOAD.strip()).decode())
    problems: list[str] = []
    failures: list[tuple[str, str]] = []
    planned: dict[str, str] = {}
    skipped: list[str] = []

    for index, item in enumerate(data["edits"], start=1):
        rel = item["path"]
        path = Path(rel)
        if not path.exists():
            problems.append(f"  [{index}] {rel}: file not found")
            continue
        text = planned.get(rel, path.read_text())
        if item["marker"] in text:
            skipped.append(f"{rel} [{index}]: already applied")
            continue
        anchor = item["anchor"]
        found = text.count(anchor)
        if found != 1:
            head = anchor.strip()[:76]
            problems.append(
                f"  [{index}] {rel}: expected exactly 1 match, found {found}\n"
                f"        anchor: {head!r}"
            )
            failures.append((rel, anchor))
            continue
        at = text.index(anchor)
        guard = item.get("region_has")
        if guard and guard in text[at:region_end(text, at)]:
            skipped.append(f"{rel} [{index}]: {anchor.strip()[:48]} already has {guard}")
            continue
        planned[rel] = text.replace(anchor, item["replacement"], 1)

    # Deliberately NOT all-or-nothing, unlike the batch scripts. Every insertion here is
    # independent and idempotent, so holding back seven working ones because four hooks
    # could not be found helps nobody - it just makes the filter jump stay for another
    # round-trip. What is written is written; what missed is reported and re-run later.
    for rel, content in sorted(planned.items()):
        Path(rel).write_text(content)
        print(f"wrote {rel}")
    for note in skipped:
        print(f"skip  {note}")
    if not planned and not problems:
        print("nothing to do - already applied")

    if problems:
        print()
        print(f"{len(problems)} hook(s) NOT patched - everything else above was written:")
        print()
        for problem in problems:
            print(problem)
        shown: dict[str, list[tuple[int, int]]] = {}
        for rel, anchor in failures:
            lines = Path(rel).read_text().splitlines()
            hit = locate(lines, anchor)
            if hit is None:
                lo, hi = 0, min(len(lines), 120)
                note = "nothing from this anchor is on disk - head of file"
            else:
                lo, hi = max(0, hit - 20), min(len(lines), hit + 20)
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
        print()
        print("Rebuild the frontend anyway - what was written is complete on its own.")
        return 1

    print()
    print("Rebuild the frontend, then run the test suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
