#!/usr/bin/env python3
"""Pod Owner Performance — the HOU table, grouped by the person instead of the unit.

Same columns, same order, same derived Net Rev and ROAS, because it INHERITS the shared
column definitions rather than restating them. Two tables that are meant to match and are
written twice do not stay matching.

ADMIN ONLY, and that had to mean more than a hidden page. `pod_owner` is deliberately NOT
added to the public /metrics/breakdown whitelist: if it were, anyone holding an `all` row
scope could pull every named person's numbers straight from the API while the page merely
failed to render for them. CLAUDE.md is explicit that frontend hiding is cosmetic, so the
data lives behind the admin router's own capability check and there is no second door. A
test pins that absence, because the day somebody adds the token "for convenience" is the
day the gate quietly becomes decoration.

Two smaller decisions worth the words:

  * Rows with no pod owner collapse into one visible "Unassigned" bucket rather than being
    dropped. Dropping them would make this table disagree with every other page, and would
    hide exactly the work that belongs to nobody - which is the thing worth seeing.
  * A measure the caller is not permitted is REFUSED, not silently omitted. A table quietly
    missing a column reads as "that number is zero".

Net Rev and ROAS are recomputed by the frontend from the totals, never averaged from
per-row ratios: averaging a ratio across people with different volumes gives a number that
is nobody's.

Verified: ruff, mypy --strict, 9 new backend tests (including an executive with full row
scope being refused), 456 backend tests overall, 75 frontend tests, tsc, eslint.

ALL-OR-NOTHING: every anchor checked before anything is written; any failure reports every
problem and writes nothing. Idempotent.
"""

import base64
import json
import sys
from pathlib import Path

PAYLOAD = """
eyJuZXdfZmlsZXMiOiB7ImJhY2tlbmQvdGVzdHMvdGVzdF9wb2Rfb3duZXJfcGVyZm9ybWFuY2UucHkiOiAiXCJcIlwiUG9kIE93
bmVyIFBlcmZvcm1hbmNlIFx1MjAxNCB0aGUgSE9VIHRhYmxlLCBncm91cGVkIGJ5IHRoZSBwZXJzb24gaW5zdGVhZCBvZiB0aGUg
dW5pdC5cblxuQWRtaW4gb25seSwgYW5kIHRoYXQgaGFzIHRvIG1lYW4gYWRtaW4gb25seS4gVGhlIGludGVyZXN0aW5nIHRlc3Qg
aGVyZSBpcyBub3QgdGhhdCB0aGVcbnBhZ2UgaXMgaGlkZGVuIGZyb20gYSBub24tYWRtaW47IGl0IGlzIHRoYXQgdGhlcmUgaXMg
bm8gU0VDT05EIGRvb3IuIGBwb2Rfb3duZXJgIGlzXG5kZWxpYmVyYXRlbHkgYWJzZW50IGZyb20gdGhlIHB1YmxpYyBicmVha2Rv
d24gd2hpdGVsaXN0LCBzbyBhbiBleGVjdXRpdmUgaG9sZGluZyBhbiBgYWxsYFxucm93IHNjb3BlIGNhbm5vdCBwdWxsIHRoZSBz
YW1lIG51bWJlcnMgb3V0IG9mIC9tZXRyaWNzL2JyZWFrZG93biB3aGlsZSB0aGUgcGFnZSBtZXJlbHlcbmRvZXMgbm90IHJlbmRl
ciBmb3IgdGhlbS4gQ0xBVURFLm1kOiBmcm9udGVuZCBoaWRpbmcgaXMgY29zbWV0aWMuXG5cIlwiXCJcblxuZnJvbSBfX2Z1dHVy
ZV9fIGltcG9ydCBhbm5vdGF0aW9uc1xuXG5mcm9tIHR5cGluZyBpbXBvcnQgQW55XG5cbmZyb20gYXBwLnNjaGVtYXMubWV0cmlj
cyBpbXBvcnQgR3JvdXBCeVxuZnJvbSBhcHAuc2VydmljZXMuYWRtaW5fc2VydmljZSBpbXBvcnQgVU5BU1NJR05FRFxuXG5fV0lO
RE9XID0gXCJkYXRlX2Zyb209MjAyNi0wNi0wMSZkYXRlX3RvPTIwMjYtMDYtMzBcIlxuX01FVFJJQ1MgPSBcIiZcIi5qb2luKFxu
ICAgIGZcIm1ldHJpY3M9e219XCIgZm9yIG0gaW4gKFwidG90YWxfcmV2ZW51ZV91c2RcIiwgXCJzdG9yZV90b3RhbF9pbnN0YWxs
c1wiLCBcInRvdGFsX3VhX3NwZW5kX3VzZFwiKVxuKVxuX1BBVEggPSBmXCIvYXBpL3YxL2FkbWluL3BvZC1vd25lci1wZXJmb3Jt
YW5jZT97X1dJTkRPV30me19NRVRSSUNTfVwiXG5cblxuZGVmIF9hdXRoKHJvbGU6IHN0cikgLT4gZGljdFtzdHIsIHN0cl06XG4g
ICAgcmV0dXJuIHtcIkF1dGhvcml6YXRpb25cIjogZlwiQmVhcmVyIHZhbGlkLXtyb2xlfVwifVxuXG5cbmRlZiB0ZXN0X3BvZF9v
d25lcl9pc19ub3Rfb25fdGhlX3B1YmxpY19icmVha2Rvd25fd2hpdGVsaXN0KCkgLT4gTm9uZTpcbiAgICAjIElmIHRoaXMgZXZl
ciBiZWNvbWVzIHRydWUsIHRoZSBhZG1pbiBnYXRlIGJlbG93IGlzIGRlY29yYXRpb246IGFueW9uZSB3aXRoIGFuIGBhbGxgXG4g
ICAgIyBzY29wZSBjYW4gZ3JvdXAgYnkgcG9kX293bmVyIHRocm91Z2ggL21ldHJpY3MvYnJlYWtkb3duIGluc3RlYWQuXG4gICAg
YXNzZXJ0IFwicG9kX293bmVyXCIgbm90IGluIEdyb3VwQnkuX19hcmdzX18gICMgdHlwZTogaWdub3JlW2F0dHItZGVmaW5lZF1c
blxuXG5hc3luYyBkZWYgdGVzdF9hbl9hZG1pbl9nZXRzX3RoZV90YWJsZShtZXRyaWNzX2VudjogQW55KSAtPiBOb25lOlxuICAg
IHJlc3BvbnNlID0gYXdhaXQgbWV0cmljc19lbnYuY2xpZW50LmdldChfUEFUSCwgaGVhZGVycz1fYXV0aChcImFkbWluXCIpKVxu
ICAgIGFzc2VydCByZXNwb25zZS5zdGF0dXNfY29kZSA9PSAyMDBcbiAgICBib2R5ID0gcmVzcG9uc2UuanNvbigpXG4gICAgYXNz
ZXJ0IFwidG90YWxfcmV2ZW51ZV91c2RcIiBpbiBib2R5W1wibWVhc3VyZXNcIl1cbiAgICBhc3NlcnQgYm9keVtcInJvd3NcIl0s
IFwidGhlIHNlZWRlZCBmaXh0dXJlIGhhcyBwb2Qtb3duZXIgcm93c1wiXG5cblxuYXN5bmMgZGVmIHRlc3Rfcm93c19hcmVfb3Jk
ZXJlZF9ieV9yZXZlbnVlKG1ldHJpY3NfZW52OiBBbnkpIC0+IE5vbmU6XG4gICAgYm9keSA9IChhd2FpdCBtZXRyaWNzX2Vudi5j
bGllbnQuZ2V0KF9QQVRILCBoZWFkZXJzPV9hdXRoKFwiYWRtaW5cIikpKS5qc29uKClcbiAgICByZXZlbnVlcyA9IFtyb3dbXCJ0
b3RhbF9yZXZlbnVlX3VzZFwiXSBmb3Igcm93IGluIGJvZHlbXCJyb3dzXCJdXVxuICAgIGFzc2VydCByZXZlbnVlcyA9PSBzb3J0
ZWQocmV2ZW51ZXMsIHJldmVyc2U9VHJ1ZSlcblxuXG5hc3luYyBkZWYgdGVzdF9hbl9leGVjdXRpdmVfaXNfcmVmdXNlZF9ldmVu
X3dpdGhfZnVsbF9yb3dfc2NvcGUobWV0cmljc19lbnY6IEFueSkgLT4gTm9uZTpcbiAgICAjIEFuIGV4ZWN1dGl2ZSBjYW4gc2Vl
IGV2ZXJ5IFJPVyBpbiB0aGUgcG9ydGZvbGlvLiBUaGF0IGlzIG5vdCB0aGUgc2FtZSBwZXJtaXNzaW9uIGFzXG4gICAgIyBzZWVp
bmcgaG93IGVhY2ggbmFtZWQgcGVyc29uIGlzIHBlcmZvcm1pbmcsIHdoaWNoIGlzIHdoYXQgdGhpcyB0YWJsZSBpcy5cbiAgICBy
ZXNwb25zZSA9IGF3YWl0IG1ldHJpY3NfZW52LmNsaWVudC5nZXQoX1BBVEgsIGhlYWRlcnM9X2F1dGgoXCJleGVjdXRpdmVcIikp
XG4gICAgYXNzZXJ0IHJlc3BvbnNlLnN0YXR1c19jb2RlID09IDQwM1xuXG5cbmFzeW5jIGRlZiB0ZXN0X2Ffdmlld2VyX2lzX3Jl
ZnVzZWQobWV0cmljc19lbnY6IEFueSkgLT4gTm9uZTpcbiAgICBhc3NlcnQgKGF3YWl0IG1ldHJpY3NfZW52LmNsaWVudC5nZXQo
X1BBVEgsIGhlYWRlcnM9X2F1dGgoXCJ2aWV3ZXJcIikpKS5zdGF0dXNfY29kZSA9PSA0MDNcblxuXG5hc3luYyBkZWYgdGVzdF9p
dF9uZWVkc19hdXRoZW50aWNhdGlvbihtZXRyaWNzX2VudjogQW55KSAtPiBOb25lOlxuICAgIGFzc2VydCAoYXdhaXQgbWV0cmlj
c19lbnYuY2xpZW50LmdldChfUEFUSCkpLnN0YXR1c19jb2RlID09IDQwMVxuXG5cbmFzeW5jIGRlZiB0ZXN0X2FuX2ltcG9zc2li
bGVfZGF0ZV9yYW5nZV9pc19hXzQwMF9ub3RfYV9jcmFzaChtZXRyaWNzX2VudjogQW55KSAtPiBOb25lOlxuICAgIHJlc3BvbnNl
ID0gYXdhaXQgbWV0cmljc19lbnYuY2xpZW50LmdldChcbiAgICAgICAgZlwiL2FwaS92MS9hZG1pbi9wb2Qtb3duZXItcGVyZm9y
bWFuY2U/ZGF0ZV9mcm9tPTIwMjYtMDYtMzAmZGF0ZV90bz0yMDI2LTA2LTAxJntfTUVUUklDU31cIixcbiAgICAgICAgaGVhZGVy
cz1fYXV0aChcImFkbWluXCIpLFxuICAgIClcbiAgICBhc3NlcnQgcmVzcG9uc2Uuc3RhdHVzX2NvZGUgPT0gNDAwXG5cblxuYXN5
bmMgZGVmIHRlc3RfdW5vd25lZF9yb3dzX2NvbGxhcHNlX2ludG9fb25lX3Zpc2libGVfYnVja2V0KG1ldHJpY3NfZW52OiBBbnkp
IC0+IE5vbmU6XG4gICAgIyBEcm9wcGluZyByb3dzIHdpdGggbm8gcG9kIG93bmVyIHdvdWxkIG1ha2UgdGhlIHRhYmxlJ3MgdG90
YWxzIGRpc2FncmVlIHdpdGggZXZlcnlcbiAgICAjIG90aGVyIHBhZ2UsIGFuZCB3b3VsZCBoaWRlIGV4YWN0bHkgdGhlIHdvcmsg
dGhhdCBiZWxvbmdzIHRvIG5vYm9keS5cbiAgICBhc3NlcnQgVU5BU1NJR05FRCA9PSBcIlVuYXNzaWduZWRcIlxuICAgIGJvZHkg
PSAoYXdhaXQgbWV0cmljc19lbnYuY2xpZW50LmdldChfUEFUSCwgaGVhZGVycz1fYXV0aChcImFkbWluXCIpKSkuanNvbigpXG4g
ICAgb3duZXJzID0gW3Jvd1tcInBvZF9vd25lclwiXSBmb3Igcm93IGluIGJvZHlbXCJyb3dzXCJdXVxuICAgIGFzc2VydCBsZW4o
b3duZXJzKSA9PSBsZW4oc2V0KG93bmVycykpLCBcIm9uZSByb3cgcGVyIG93bmVyLCBibGFua3MgbWVyZ2VkXCJcblxuXG5hc3lu
YyBkZWYgdGVzdF9hX2ZvcmJpZGRlbl9tZWFzdXJlX2lzX3JlZnVzZWRfbm90X3NpbGVudGx5X2Ryb3BwZWQobWV0cmljc19lbnY6
IEFueSkgLT4gTm9uZTpcbiAgICAjIEEgdGFibGUgcXVpZXRseSBtaXNzaW5nIGEgY29sdW1uIHJlYWRzIGFzIFwidGhhdCBudW1i
ZXIgaXMgemVyb1wiLiBJZiBhIG1lYXN1cmUgaXMgbm90XG4gICAgIyBwZXJtaXR0ZWQsIHNheSBzbyAtIGRvIG5vdCBoYW5kIGJh
Y2sgYSBuYXJyb3dlciB0YWJsZSB0aGF0IGxvb2tzIGNvbXBsZXRlLlxuICAgIHJlc3BvbnNlID0gYXdhaXQgbWV0cmljc19lbnYu
Y2xpZW50LmdldChcbiAgICAgICAgZlwiL2FwaS92MS9hZG1pbi9wb2Qtb3duZXItcGVyZm9ybWFuY2U/e19XSU5ET1d9Jm1ldHJp
Y3M9bm90X2FfcmVhbF9tZWFzdXJlXCIsXG4gICAgICAgIGhlYWRlcnM9X2F1dGgoXCJhZG1pblwiKSxcbiAgICApXG4gICAgYXNz
ZXJ0IHJlc3BvbnNlLnN0YXR1c19jb2RlID09IDQwMFxuIiwgImZyb250ZW5kL2NvbXBvbmVudHMvcG9kLW93bmVycy9wb2Qtb3du
ZXItdGFibGUudHN4IjogIlwidXNlIGNsaWVudFwiO1xuXG5pbXBvcnQgeyB1c2VNZW1vIH0gZnJvbSBcInJlYWN0XCI7XG5cbmlt
cG9ydCB7IFBhZ2VIZWFkZXIgfSBmcm9tIFwiQC9jb21wb25lbnRzL2xheW91dC9wYWdlLWhlYWRlclwiO1xuaW1wb3J0IHtcbiAg
dHlwZSBDb2x1bW5EZWYsXG4gIE1FVFJJQ19DT0xVTU5TLFxuICBNZXRyaWNUYWJsZSxcbiAgdHlwZSBSb3csXG4gIHBlcm1pdHRl
ZE1lYXN1cmVzLFxufSBmcm9tIFwiQC9jb21wb25lbnRzL292ZXJ2aWV3L3JldmVudWUtdGFibGVcIjtcbmltcG9ydCB7IHVzZVBv
ZE93bmVyUGVyZm9ybWFuY2UsIHVzZU1lIH0gZnJvbSBcIkAvbGliL2FwaS1ob29rc1wiO1xuaW1wb3J0IHsgdXNlRmlsdGVycyB9
IGZyb20gXCJAL2xpYi91c2UtZmlsdGVyc1wiO1xuXG5jb25zdCBVTkFTU0lHTkVEID0gXCJVbmFzc2lnbmVkXCI7XG5cbmZ1bmN0
aW9uIG93bmVyS2V5KHJvdzogUm93KTogc3RyaW5nIHtcbiAgY29uc3QgdmFsdWUgPSByb3cucG9kX293bmVyO1xuICByZXR1cm4g
dmFsdWUgPT0gbnVsbCB8fCBTdHJpbmcodmFsdWUpLnRyaW0oKSA9PT0gXCJcIlxuICAgID8gVU5BU1NJR05FRFxuICAgIDogU3Ry
aW5nKHZhbHVlKTtcbn1cblxuLyoqIFRoZSBpZGVudGl0eSBjb2x1bW46IHRoZSBwb2Qgb3duZXIncyBuYW1lLiBObyBsaW5rIFx1
MjAxNCB1bmxpa2UgSE9VIHRoZXJlIGlzIG5vIHBlci1wZXJzb25cbiAqICBhbmFseXRpY3MgcGFnZSwgYW5kIGludmVudGluZyBv
bmUgd291bGQgaW1wbHkgYSBkcmlsbC1kb3duIHRoYXQgZG9lcyBub3QgZXhpc3QuICovXG5jb25zdCBPV05FUl9JREVOVElUWTog
Q29sdW1uRGVmID0ge1xuICBpZDogXCJwb2Rfb3duZXJcIixcbiAgbGFiZWw6IFwiUG9kIE93bmVyXCIsXG4gIHJlcXVpcmVzOiBb
XSxcbiAgYWxpZ246IFwibGVmdFwiLFxuICBmbXQ6IFwidGV4dFwiLFxuICB2YWx1ZTogb3duZXJLZXksXG4gIHJlbmRlcjogKHJv
dykgPT4ge1xuICAgIGNvbnN0IGtleSA9IG93bmVyS2V5KHJvdyk7XG4gICAgcmV0dXJuIGtleSA9PT0gVU5BU1NJR05FRCA/IChc
biAgICAgIDxzcGFuIGNsYXNzTmFtZT1cInRleHQtbXV0ZWQtZm9yZWdyb3VuZFwiPntVTkFTU0lHTkVEfTwvc3Bhbj5cbiAgICAp
IDogKFxuICAgICAgPHNwYW4gY2xhc3NOYW1lPVwiZm9udC1tZWRpdW1cIj57a2V5fTwvc3Bhbj5cbiAgICApO1xuICB9LFxufTtc
blxuLyoqIFBvZCBPd25lciBQZXJmb3JtYW5jZSBcdTIwMTQgdGhlIEhPVSB0YWJsZSBncm91cGVkIGJ5IHRoZSBwZXJzb24gaW5z
dGVhZCBvZiB0aGUgdW5pdC5cbiAqXG4gKiAgQURNSU4gT05MWSwgYW5kIHRoZSBlbmZvcmNlbWVudCBpcyBzZXJ2ZXItc2lkZTog
YHBvZF9vd25lcmAgaXMgZGVsaWJlcmF0ZWx5IG5vdCBvbiB0aGVcbiAqICBwdWJsaWMgYnJlYWtkb3duIHdoaXRlbGlzdCwgc28g
dGhlcmUgaXMgbm8gc2Vjb25kIGRvb3IgdGhyb3VnaCAvbWV0cmljcy9icmVha2Rvd24gZm9yXG4gKiAgc29tZW9uZSB3aG9zZSBy
b3cgc2NvcGUgaXMgYGFsbGAuIFRoaXMgY29tcG9uZW50IHNpbXBseSB3aWxsIG5vdCBnZXQgZGF0YSB3aXRob3V0IHRoZVxuICog
IGFkbWluX3BhbmVsIGNhcGFiaWxpdHkgXHUyMDE0IHRoZSBoaWRpbmcgaGVyZSBpcyB0aGUgY29zbWV0aWMgaGFsZiwgYXMgaXQg
c2hvdWxkIGJlLlxuICpcbiAqICBJdCBpbmhlcml0cyBNRVRSSUNfQ09MVU1OUyB3aG9sZXNhbGUgc28gaXQgY2Fubm90IGRyaWZ0
IGZyb20gdGhlIEhPVSB0YWJsZSBpdCBtaXJyb3JzOlxuICogIHNhbWUgY29sdW1ucywgc2FtZSBvcmRlciwgc2FtZSBkZXJpdmVk
IE5ldCBSZXYgYW5kIFJPQVMgcmVjb21wdXRlZCBmcm9tIHRvdGFscyByYXRoZXJcbiAqICB0aGFuIGF2ZXJhZ2VkIGFjcm9zcyBw
ZW9wbGUgb2YgZGlmZmVyZW50IHNpemVzLiAqL1xuZXhwb3J0IGZ1bmN0aW9uIFBvZE93bmVyVGFibGUoKSB7XG4gIGNvbnN0IHsg
ZmlsdGVycyB9ID0gdXNlRmlsdGVycygpO1xuICBjb25zdCB7IGRhdGE6IG1lIH0gPSB1c2VNZSgpO1xuICBjb25zdCBpc0FkbWlu
ID0gQm9vbGVhbihtZT8uY2FwYWJpbGl0aWVzLmluY2x1ZGVzKFwiYWRtaW5fcGFuZWxcIikpO1xuICBjb25zdCBwZXJtaXR0ZWQg
PSB1c2VNZW1vKFxuICAgICgpID0+IHBlcm1pdHRlZE1lYXN1cmVzKG1lPy5tZXRyaWNfZ3JvdXBzID8/IFtdKSxcbiAgICBbbWVd
LFxuICApO1xuXG4gIGNvbnN0IGNvbHVtbnMgPSB1c2VNZW1vKFxuICAgICgpID0+XG4gICAgICBbT1dORVJfSURFTlRJVFksIC4u
Lk1FVFJJQ19DT0xVTU5TXS5maWx0ZXIoKGMpID0+XG4gICAgICAgIGMucmVxdWlyZXMuZXZlcnkoKG0pID0+IHBlcm1pdHRlZC5o
YXMobSkpLFxuICAgICAgKSxcbiAgICBbcGVybWl0dGVkXSxcbiAgKTtcblxuICBjb25zdCBtZWFzdXJlcyA9IHVzZU1lbW8oXG4g
ICAgKCkgPT4gWy4uLm5ldyBTZXQoY29sdW1ucy5mbGF0TWFwKChjKSA9PiBjLnJlcXVpcmVzKSldLFxuICAgIFtjb2x1bW5zXSxc
biAgKTtcblxuICBjb25zdCBxdWVyeSA9IHVzZVBvZE93bmVyUGVyZm9ybWFuY2UoZmlsdGVycywgbWVhc3VyZXMsIGlzQWRtaW4p
O1xuICBjb25zdCByb3dzID0gdXNlTWVtbzxSb3dbXT4oXG4gICAgKCkgPT4gKHF1ZXJ5LmRhdGE/LnJvd3MgPz8gW10pIGFzIFJv
d1tdLFxuICAgIFtxdWVyeS5kYXRhXSxcbiAgKTtcblxuICBpZiAobWUgJiYgIWlzQWRtaW4pIHtcbiAgICByZXR1cm4gKFxuICAg
ICAgPGRpdiBjbGFzc05hbWU9XCJzcGFjZS15LTZcIj5cbiAgICAgICAgPFBhZ2VIZWFkZXIgdGl0bGU9XCJQb2QgT3duZXIgUGVy
Zm9ybWFuY2VcIiAvPlxuICAgICAgICA8cCBjbGFzc05hbWU9XCJ0ZXh0LXNtIHRleHQtbXV0ZWQtZm9yZWdyb3VuZFwiPlxuICAg
ICAgICAgIFRoaXMgdmlldyBpcyBsaW1pdGVkIHRvIGFkbWluaXN0cmF0b3JzLlxuICAgICAgICA8L3A+XG4gICAgICA8L2Rpdj5c
biAgICApO1xuICB9XG5cbiAgcmV0dXJuIChcbiAgICA8ZGl2IGNsYXNzTmFtZT1cInNwYWNlLXktNlwiPlxuICAgICAgPFBhZ2VI
ZWFkZXIgdGl0bGU9XCJQb2QgT3duZXIgUGVyZm9ybWFuY2VcIiAvPlxuICAgICAgPE1ldHJpY1RhYmxlXG4gICAgICAgIHRpdGxl
PVwiUG9kIE93bmVyIFBlcmZvcm1hbmNlXCJcbiAgICAgICAgY29sdW1ucz17Y29sdW1uc31cbiAgICAgICAgcm93cz17cm93c31c
biAgICAgICAgcm93S2V5PXtvd25lcktleX1cbiAgICAgICAgaXNMb2FkaW5nPXtxdWVyeS5pc0xvYWRpbmd9XG4gICAgICAgIGlz
RXJyb3I9e3F1ZXJ5LmlzRXJyb3J9XG4gICAgICAvPlxuICAgIDwvZGl2PlxuICApO1xufVxuIiwgImZyb250ZW5kL2FwcC8oYXBw
KS9wb2Qtb3duZXJzL3BhZ2UudHN4IjogImltcG9ydCB7IFBvZE93bmVyVGFibGUgfSBmcm9tIFwiQC9jb21wb25lbnRzL3BvZC1v
d25lcnMvcG9kLW93bmVyLXRhYmxlXCI7XG5cbmV4cG9ydCBkZWZhdWx0IGZ1bmN0aW9uIFBvZE93bmVyc1BhZ2UoKSB7XG4gIHJl
dHVybiA8UG9kT3duZXJUYWJsZSAvPjtcbn1cbiJ9LCAiYXBwZW5kcyI6IFt7InBhdGgiOiAiYmFja2VuZC9hcHAvYXBpL3YxL2Fk
bWluLnB5IiwgImNvbnRlbnQiOiAiXG5cbkByb3V0ZXIuZ2V0KFwiL3BvZC1vd25lci1wZXJmb3JtYW5jZVwiKVxuYXN5bmMgZGVm
IHBvZF9vd25lcl9wZXJmb3JtYW5jZShcbiAgICBjb250ZXh0OiBDdXJyZW50VXNlcixcbiAgICBkYjogRGJTZXNzaW9uLFxuICAg
IGRhdGVfZnJvbTogQW5ub3RhdGVkW2RhdGUsIFF1ZXJ5KCldLFxuICAgIGRhdGVfdG86IEFubm90YXRlZFtkYXRlLCBRdWVyeSgp
XSxcbiAgICBtZXRyaWNzOiBBbm5vdGF0ZWRbbGlzdFtzdHJdLCBRdWVyeShtaW5fbGVuZ3RoPTEpXSxcbikgLT4gZGljdFtzdHIs
IEFueV06XG4gICAgXCJcIlwiUGVyLXBvZC1vd25lciB0b3RhbHMgXHUyMDE0IEFETUlOIE9OTFkuXG5cbiAgICBUaGUgZ2F0ZSBp
cyB0aGlzIHJvdXRlcidzIGBgcmVxdWlyZV9jYXBhYmlsaXR5KFwiYWRtaW5fcGFuZWxcIilgYCwgbm90IHRoZSBwYWdlIHRoYXRc
biAgICBjYWxscyBpdC4gYHBvZF9vd25lcmAgaXMgZGVsaWJlcmF0ZWx5IGFic2VudCBmcm9tIHRoZSBwdWJsaWMgYnJlYWtkb3du
IHdoaXRlbGlzdCwgc29cbiAgICB0aGVyZSBpcyBubyBzZWNvbmQgZG9vcjogYW4gZXhlY3V0aXZlIHdpdGggYW4gYGFsbGAgcm93
IHNjb3BlIGNhbm5vdCBwdWxsIHRoZSBzYW1lXG4gICAgbnVtYmVycyBmcm9tIC9tZXRyaWNzL2JyZWFrZG93biB3aXRoIHRoZSBw
YWdlIG1lcmVseSBoaWRkZW4uIENMQVVERS5tZCBpcyBleHBsaWNpdFxuICAgIHRoYXQgZnJvbnRlbmQgaGlkaW5nIGlzIGNvc21l
dGljLlxuXG4gICAgUm93IHNjb3BlIHN0aWxsIGFwcGxpZXMgb24gdG9wLCBhcyBldmVyeXdoZXJlIGVsc2UuXG4gICAgXCJcIlwi
XG4gICAgdHJ5OlxuICAgICAgICBwYXJhbXMgPSBNZXRyaWNGaWx0ZXJzKGRhdGVfZnJvbT1kYXRlX2Zyb20sIGRhdGVfdG89ZGF0
ZV90bylcbiAgICBleGNlcHQgVmFsaWRhdGlvbkVycm9yIGFzIGV4YzpcbiAgICAgICAgcmFpc2UgSFRUUEV4Y2VwdGlvbihzdGF0
dXMuSFRUUF80MDBfQkFEX1JFUVVFU1QsIFwiSW52YWxpZCBkYXRlIHJhbmdlXCIpIGZyb20gZXhjXG4gICAgdHJ5OlxuICAgICAg
ICByZXR1cm4gYXdhaXQgYWRtaW5fc2VydmljZS5wb2Rfb3duZXJfcGVyZm9ybWFuY2UoZGIsIFF1ZXJ5QnVpbGRlcihjb250ZXh0
KSwgcGFyYW1zLCBtZXRyaWNzKVxuICAgIGV4Y2VwdCBWYWx1ZUVycm9yIGFzIGV4YzpcbiAgICAgICAgcmFpc2UgSFRUUEV4Y2Vw
dGlvbihzdGF0dXMuSFRUUF80MDBfQkFEX1JFUVVFU1QsIHN0cihleGMpKSBmcm9tIGV4Y1xuIiwgIm1hcmtlciI6ICJAcm91dGVy
LmdldChcIi9wb2Qtb3duZXItcGVyZm9ybWFuY2VcIikifV0sICJlZGl0cyI6IFt7InBhdGgiOiAiYmFja2VuZC9hcHAvc2Vydmlj
ZXMvcXVlcnlfYnVpbGRlci5weSIsICJhbmNob3IiOiAiICAgIGRlZiBicmVha2Rvd24oXG4gICAgICAgIHNlbGYsXG4gICAgICAg
IHBhcmFtczogTWV0cmljRmlsdGVycyxcbiAgICAgICAgZ3JvdXBfYnk6IEdyb3VwQnksIiwgInJlcGxhY2VtZW50IjogIiAgICBk
ZWYgcG9kX293bmVyX2JyZWFrZG93bihzZWxmLCBwYXJhbXM6IE1ldHJpY0ZpbHRlcnMsIG1ldHJpY3M6IGxpc3Rbc3RyXSkgLT4g
U2VsZWN0W0FueV06XG4gICAgICAgIFwiXCJcIkFkZGl0aXZlIG1lYXN1cmVzIGdyb3VwZWQgYnkgcG9kIG93bmVyLCBmb3IgdGhl
IGFkbWluLW9ubHkgcGVyZm9ybWFuY2UgdGFibGUuXG5cbiAgICAgICAgYHBvZF9vd25lcmAgaXMgZGVsaWJlcmF0ZWx5IE5PVCBh
IHRva2VuIGluIGBgX0dST1VQX0JZX0NPTFVNTmBgLiBBZGRpbmcgaXQgdGhlcmVcbiAgICAgICAgd291bGQgcHV0IGl0IG9uIHRo
ZSBwdWJsaWMgL21ldHJpY3MvYnJlYWtkb3duIHdoaXRlbGlzdCwgYW5kIGFueW9uZSBob2xkaW5nIGFuXG4gICAgICAgIGBhbGxg
IHJvdyBzY29wZSBjb3VsZCB0aGVuIHB1bGwgZXZlcnkgcG9kIG93bmVyJ3MgbnVtYmVycyBzdHJhaWdodCBmcm9tIHRoZSBBUEkg
LVxuICAgICAgICB3aXRoIHRoZSBwYWdlIG1lcmVseSBoaWRkZW4gZnJvbSB0aGVtLiBDTEFVREUubWQgaXMgZXhwbGljaXQgdGhh
dCBmcm9udGVuZCBoaWRpbmdcbiAgICAgICAgaXMgY29zbWV0aWMgYW5kIHRoZSBlbmZvcmNlbWVudCBoYXMgdG8gYmUgc2VydmVy
LXNpZGUsIHNvIHRoZSBjYXBhYmlsaXR5IGNoZWNrXG4gICAgICAgIGxpdmVzIG9uIHRoZSBhZG1pbiByb3V0ZSB0aGF0IGlzIHRo
ZSBvbmx5IGNhbGxlciBvZiB0aGlzLlxuXG4gICAgICAgIFJvdyBzY29wZSBzdGlsbCBhcHBsaWVzIG9uIHRvcCwgZXhhY3RseSBh
cyBpdCBkb2VzIGV2ZXJ5d2hlcmUgZWxzZS5cbiAgICAgICAgXCJcIlwiXG4gICAgICAgIHNlbGYuX3ZhbGlkYXRlX21ldHJpY3Mo
bWV0cmljcylcbiAgICAgICAgZ3JvdXBfY29sID0gRkFDVF9UQUJMRS5jLnBvZF9vd25lclxuICAgICAgICBjb2x1bW5zOiBsaXN0
W0FueV0gPSBbZ3JvdXBfY29sLmxhYmVsKFwicG9kX293bmVyXCIpXVxuICAgICAgICBjb2x1bW5zLmV4dGVuZChzZWxmLl9zdW0o
bSkubGFiZWwobSkgZm9yIG0gaW4gbWV0cmljcylcbiAgICAgICAgd2hlcmUgPSBzZWxmLl93aW5kb3dlZF9maWx0ZXJzKHBhcmFt
cywgcGFyYW1zLmRhdGVfZnJvbSwgcGFyYW1zLmRhdGVfdG8pXG4gICAgICAgIHJldHVybiAoXG4gICAgICAgICAgICBzZWxlY3Qo
KmNvbHVtbnMpXG4gICAgICAgICAgICAud2hlcmUoYW5kXygqd2hlcmUpKVxuICAgICAgICAgICAgLmdyb3VwX2J5KGdyb3VwX2Nv
bClcbiAgICAgICAgICAgIC5vcmRlcl9ieShzZWxmLl9zdW0obWV0cmljc1swXSkuZGVzYygpKVxuICAgICAgICApXG5cbiAgICBk
ZWYgYnJlYWtkb3duKFxuICAgICAgICBzZWxmLFxuICAgICAgICBwYXJhbXM6IE1ldHJpY0ZpbHRlcnMsXG4gICAgICAgIGdyb3Vw
X2J5OiBHcm91cEJ5LCIsICJtYXJrZXIiOiAiZGVmIHBvZF9vd25lcl9icmVha2Rvd24oIiwgImNvdW50IjogIm9uZSJ9LCB7InBh
dGgiOiAiYmFja2VuZC9hcHAvc2VydmljZXMvYWRtaW5fc2VydmljZS5weSIsICJhbmNob3IiOiAiaW1wb3J0IHV1aWRcbmZyb20g
ZGF0ZXRpbWUgaW1wb3J0IFVUQywgZGF0ZXRpbWUsIHRpbWVkZWx0YSIsICJyZXBsYWNlbWVudCI6ICJpbXBvcnQgdXVpZFxuZnJv
bSBkYXRldGltZSBpbXBvcnQgVVRDLCBkYXRldGltZSwgdGltZWRlbHRhXG5mcm9tIHR5cGluZyBpbXBvcnQgQW55IiwgIm1hcmtl
ciI6ICJmcm9tIHR5cGluZyBpbXBvcnQgQW55IiwgImNvdW50IjogIm9uZSJ9LCB7InBhdGgiOiAiYmFja2VuZC9hcHAvc2Vydmlj
ZXMvYWRtaW5fc2VydmljZS5weSIsICJhbmNob3IiOiAiZnJvbSBhcHAuc2NoZW1hcy5hdXRoIGltcG9ydCBTY29wZU91dCIsICJy
ZXBsYWNlbWVudCI6ICJmcm9tIGFwcC5zY2hlbWFzLmF1dGggaW1wb3J0IFNjb3BlT3V0XG5mcm9tIGFwcC5zY2hlbWFzLm1ldHJp
Y3MgaW1wb3J0IE1ldHJpY0ZpbHRlcnMiLCAibWFya2VyIjogImZyb20gYXBwLnNjaGVtYXMubWV0cmljcyBpbXBvcnQgTWV0cmlj
RmlsdGVycyIsICJjb3VudCI6ICJvbmUifSwgeyJwYXRoIjogImJhY2tlbmQvYXBwL3NlcnZpY2VzL2FkbWluX3NlcnZpY2UucHki
LCAiYW5jaG9yIjogImZyb20gYXBwLnNlcnZpY2VzIGltcG9ydCBzZXR0aW5nc19zZXJ2aWNlIiwgInJlcGxhY2VtZW50IjogImZy
b20gYXBwLnNlcnZpY2VzIGltcG9ydCBzZXR0aW5nc19zZXJ2aWNlXG5mcm9tIGFwcC5zZXJ2aWNlcy5xdWVyeV9idWlsZGVyIGlt
cG9ydCBRdWVyeUJ1aWxkZXIiLCAibWFya2VyIjogImZyb20gYXBwLnNlcnZpY2VzLnF1ZXJ5X2J1aWxkZXIgaW1wb3J0IFF1ZXJ5
QnVpbGRlciIsICJjb3VudCI6ICJvbmUifSwgeyJwYXRoIjogImJhY2tlbmQvYXBwL3NlcnZpY2VzL2FkbWluX3NlcnZpY2UucHki
LCAiYW5jaG9yIjogImFzeW5jIGRlZiBkYXRhX2hlYWx0aChkYjogQXN5bmNTZXNzaW9uKSAtPiBEYXRhSGVhbHRoOiIsICJyZXBs
YWNlbWVudCI6ICIjIFJvd3Mgd2hvc2UgcG9kX293bmVyIGlzIE5VTEwgb3IgYmxhbmsgY29sbGFwc2UgaW50byBPTkUgYnVja2V0
IHJhdGhlciB0aGFuIGJlaW5nIGRyb3BwZWQsXG4jIHNvIHRoZSB0YWJsZSdzIHRvdGFscyBzdGlsbCByZWNvbmNpbGUgd2l0aCB0
aGUgcmVzdCBvZiB0aGUgZGFzaGJvYXJkIC0gYW5kIHNvIHRoZSB3b3JrXG4jIHRoYXQgYmVsb25ncyB0byBub2JvZHkgaXMgdmlz
aWJsZSBpbnN0ZWFkIG9mIHF1aWV0bHkgYWJzZW50LlxuVU5BU1NJR05FRCA9IFwiVW5hc3NpZ25lZFwiXG5cblxuYXN5bmMgZGVm
IHBvZF9vd25lcl9wZXJmb3JtYW5jZShcbiAgICBkYjogQXN5bmNTZXNzaW9uLCBxYjogUXVlcnlCdWlsZGVyLCBwYXJhbXM6IE1l
dHJpY0ZpbHRlcnMsIG1ldHJpY3M6IGxpc3Rbc3RyXVxuKSAtPiBkaWN0W3N0ciwgQW55XTpcbiAgICBcIlwiXCJQZXItcG9kLW93
bmVyIHRvdGFscy4gQURNSU4gT05MWSAtIGVuZm9yY2VkIGJ5IHRoZSByb3V0ZSdzIGNhcGFiaWxpdHkgY2hlY2suXG5cbiAgICBU
aGUgY2FsbGVyIGFza3MgZm9yIHRoZSBtZWFzdXJlcyBpdHMgY29sdW1ucyBuZWVkLCBleGFjdGx5IGFzIHRoZSBIT1UgdGFibGUg
ZG9lcywgc29cbiAgICB0aGUgdHdvIHRhYmxlcyBjYW5ub3QgZHJpZnQgaW50byBzaG93aW5nIGRpZmZlcmVudCB0aGluZ3MuIEFu
eXRoaW5nIG5vdCBwZXJtaXR0ZWQgaXNcbiAgICByZWplY3RlZCBieSB0aGUgcXVlcnkgYnVpbGRlciByYXRoZXIgdGhhbiBzaWxl
bnRseSBkcm9wcGVkOiBhIHRhYmxlIHF1aWV0bHkgbWlzc2luZyBhXG4gICAgY29sdW1uIHJlYWRzIGFzIFwidGhhdCBudW1iZXIg
aXMgemVyb1wiLlxuXG4gICAgT25seSBBRERJVElWRSBtZWFzdXJlcyBhcmUgc3VtbWVkIGhlcmUuIE5ldCByZXZlbnVlIGFuZCBS
T0FTIGFyZSByZWNvbXB1dGVkIGJ5IHRoZVxuICAgIGZyb250ZW5kJ3Mgc2hhcmVkIGNvbHVtbiBkZWZpbml0aW9ucyBmcm9tIHRo
ZXNlIHRvdGFscyAtIGF2ZXJhZ2luZyBhIHJhdGlvIGFjcm9zc1xuICAgIHBlb3BsZSB3aXRoIGRpZmZlcmVudCB2b2x1bWVzIHBy
b2R1Y2VzIGEgbnVtYmVyIHRoYXQgaXMgbm9ib2R5J3MuXG4gICAgXCJcIlwiXG4gICAgcmVzdWx0ID0gKGF3YWl0IGRiLmV4ZWN1
dGUocWIucG9kX293bmVyX2JyZWFrZG93bihwYXJhbXMsIG1ldHJpY3MpKSkubWFwcGluZ3MoKS5hbGwoKVxuXG4gICAgbWVyZ2Vk
OiBkaWN0W3N0ciwgZGljdFtzdHIsIEFueV1dID0ge31cbiAgICBmb3Igcm93IGluIHJlc3VsdDpcbiAgICAgICAgcmF3ID0gcm93
W1wicG9kX293bmVyXCJdXG4gICAgICAgIGtleSA9IFVOQVNTSUdORUQgaWYgcmF3IGlzIE5vbmUgb3Igc3RyKHJhdykuc3RyaXAo
KSA9PSBcIlwiIGVsc2Ugc3RyKHJhdylcbiAgICAgICAgYnVja2V0ID0gbWVyZ2VkLnNldGRlZmF1bHQoa2V5LCB7XCJwb2Rfb3du
ZXJcIjoga2V5LCAqKmRpY3QuZnJvbWtleXMobWV0cmljcywgMC4wKX0pXG4gICAgICAgIGZvciBtZWFzdXJlIGluIG1ldHJpY3M6
XG4gICAgICAgICAgICBidWNrZXRbbWVhc3VyZV0gKz0gZmxvYXQocm93W21lYXN1cmVdIG9yIDApXG5cbiAgICBzb3J0X2tleSA9
IFwidG90YWxfcmV2ZW51ZV91c2RcIiBpZiBcInRvdGFsX3JldmVudWVfdXNkXCIgaW4gbWV0cmljcyBlbHNlIG1ldHJpY3NbMF1c
biAgICByb3dzID0gc29ydGVkKG1lcmdlZC52YWx1ZXMoKSwga2V5PWxhbWJkYSByOiBmbG9hdChyLmdldChzb3J0X2tleSwgMCkg
b3IgMCksIHJldmVyc2U9VHJ1ZSlcbiAgICByZXR1cm4ge1wibWVhc3VyZXNcIjogbWV0cmljcywgXCJyb3dzXCI6IHJvd3N9XG5c
blxuYXN5bmMgZGVmIGRhdGFfaGVhbHRoKGRiOiBBc3luY1Nlc3Npb24pIC0+IERhdGFIZWFsdGg6IiwgIm1hcmtlciI6ICJhc3lu
YyBkZWYgcG9kX293bmVyX3BlcmZvcm1hbmNlKCIsICJjb3VudCI6ICJvbmUifSwgeyJwYXRoIjogImJhY2tlbmQvYXBwL2FwaS92
MS9hZG1pbi5weSIsICJhbmNob3IiOiAiZnJvbSBkYXRldGltZSBpbXBvcnQgVVRDLCBkYXRldGltZSwgdGltZWRlbHRhIiwgInJl
cGxhY2VtZW50IjogImZyb20gZGF0ZXRpbWUgaW1wb3J0IFVUQywgZGF0ZSwgZGF0ZXRpbWUsIHRpbWVkZWx0YSIsICJtYXJrZXIi
OiAiZnJvbSBkYXRldGltZSBpbXBvcnQgVVRDLCBkYXRlLCBkYXRldGltZSwgdGltZWRlbHRhIiwgImNvdW50IjogIm9uZSJ9LCB7
InBhdGgiOiAiYmFja2VuZC9hcHAvYXBpL3YxL2FkbWluLnB5IiwgImFuY2hvciI6ICJmcm9tIHJlZGlzLmFzeW5jaW8gaW1wb3J0
IFJlZGlzIiwgInJlcGxhY2VtZW50IjogImZyb20gcHlkYW50aWMgaW1wb3J0IFZhbGlkYXRpb25FcnJvclxuZnJvbSByZWRpcy5h
c3luY2lvIGltcG9ydCBSZWRpcyIsICJtYXJrZXIiOiAiZnJvbSBweWRhbnRpYyBpbXBvcnQgVmFsaWRhdGlvbkVycm9yIiwgImNv
dW50IjogIm9uZSJ9LCB7InBhdGgiOiAiYmFja2VuZC9hcHAvYXBpL3YxL2FkbWluLnB5IiwgImFuY2hvciI6ICJmcm9tIGFwcC5z
Y2hlbWFzLnNtdHAgaW1wb3J0IFNtdHBDb25maWdPdXQsIFNtdHBDb25maWdVcGRhdGUsIFNtdHBUZXN0UmVzdWx0IiwgInJlcGxh
Y2VtZW50IjogImZyb20gYXBwLnNjaGVtYXMubWV0cmljcyBpbXBvcnQgTWV0cmljRmlsdGVyc1xuZnJvbSBhcHAuc2NoZW1hcy5z
bXRwIGltcG9ydCBTbXRwQ29uZmlnT3V0LCBTbXRwQ29uZmlnVXBkYXRlLCBTbXRwVGVzdFJlc3VsdCIsICJtYXJrZXIiOiAiZnJv
bSBhcHAuc2NoZW1hcy5tZXRyaWNzIGltcG9ydCBNZXRyaWNGaWx0ZXJzIiwgImNvdW50IjogIm9uZSJ9LCB7InBhdGgiOiAiYmFj
a2VuZC9hcHAvYXBpL3YxL2FkbWluLnB5IiwgImFuY2hvciI6ICJmcm9tIGFwcC5zZXJ2aWNlcy5hdXRoIGltcG9ydCB1c2VyX2Nv
bnRleHRfY2FjaGVfa2V5IiwgInJlcGxhY2VtZW50IjogImZyb20gYXBwLnNlcnZpY2VzLmF1dGggaW1wb3J0IHVzZXJfY29udGV4
dF9jYWNoZV9rZXlcbmZyb20gYXBwLnNlcnZpY2VzLnF1ZXJ5X2J1aWxkZXIgaW1wb3J0IFF1ZXJ5QnVpbGRlciIsICJtYXJrZXIi
OiAiZnJvbSBhcHAuc2VydmljZXMucXVlcnlfYnVpbGRlciBpbXBvcnQgUXVlcnlCdWlsZGVyIiwgImNvdW50IjogIm9uZSJ9LCB7
InBhdGgiOiAiZnJvbnRlbmQvbGliL2FwaS1ob29rcy50cyIsICJhbmNob3IiOiAiZXhwb3J0IGZ1bmN0aW9uIHVzZVNwb3RsaWdo
dCgpIHsiLCAicmVwbGFjZW1lbnQiOiAiZXhwb3J0IGludGVyZmFjZSBQb2RPd25lclBlcmZvcm1hbmNlIHtcbiAgbWVhc3VyZXM6
IHN0cmluZ1tdO1xuICByb3dzOiBSZWNvcmQ8c3RyaW5nLCBzdHJpbmcgfCBudW1iZXIgfCBudWxsPltdO1xufVxuXG4vKiogQWRt
aW4tb25seSBwZXItcG9kLW93bmVyIHRvdGFscy4gYGVuYWJsZWRgIGlzIHBhc3NlZCBpbiByYXRoZXIgdGhhbiBhc3N1bWVkOiBm
aXJpbmcgYVxuICogIHJlcXVlc3QgdGhhdCBpcyBnb2luZyB0byA0MDMgcHV0cyBhIHJlZCBsaW5lIGluIGV2ZXJ5IG5vbi1hZG1p
bidzIGNvbnNvbGUgZm9yIGEgcGFnZVxuICogIHRoZXkgd2VyZSBuZXZlciBtZWFudCB0byBvcGVuLiAqL1xuZXhwb3J0IGZ1bmN0
aW9uIHVzZVBvZE93bmVyUGVyZm9ybWFuY2UoXG4gIGZpbHRlcnM6IEZpbHRlcnMsXG4gIG1ldHJpY3M6IHN0cmluZ1tdLFxuICBl
bmFibGVkOiBib29sZWFuLFxuKSB7XG4gIGNvbnN0IHsgdXNlciB9ID0gdXNlQXV0aCgpO1xuICBjb25zdCBwYXJhbXMgPSB7IC4u
LmZpbHRlcnNUb0FwaVF1ZXJ5KGZpbHRlcnMpLCBtZXRyaWNzIH07XG4gIHJldHVybiB1c2VRdWVyeSh7XG4gICAgcXVlcnlLZXk6
IFtcInBvZC1vd25lci1wZXJmb3JtYW5jZVwiLCBwYXJhbXNdLFxuICAgIHF1ZXJ5Rm46ICgpID0+XG4gICAgICBhcGlGZXRjaDxQ
b2RPd25lclBlcmZvcm1hbmNlPihcbiAgICAgICAgYC9hcGkvdjEvYWRtaW4vcG9kLW93bmVyLXBlcmZvcm1hbmNlJHtidWlsZFF1
ZXJ5KHBhcmFtcyl9YCxcbiAgICAgICksXG4gICAgZW5hYmxlZDogQm9vbGVhbih1c2VyKSAmJiBlbmFibGVkICYmIG1ldHJpY3Mu
bGVuZ3RoID4gMCxcbiAgICBzdGFsZVRpbWU6IEFHR19TVEFMRSxcbiAgfSk7XG59XG5cbmV4cG9ydCBmdW5jdGlvbiB1c2VTcG90
bGlnaHQoKSB7IiwgIm1hcmtlciI6ICJleHBvcnQgZnVuY3Rpb24gdXNlUG9kT3duZXJQZXJmb3JtYW5jZSgiLCAiY291bnQiOiAi
b25lIn0sIHsicGF0aCI6ICJmcm9udGVuZC9saWIvbmF2LnRzIiwgImFuY2hvciI6ICIgIFVzZXIsXG4gIENsaXBib2FyZENoZWNr
LFxufSBmcm9tIFwibHVjaWRlLXJlYWN0XCI7IiwgInJlcGxhY2VtZW50IjogIiAgVXNlcixcbiAgVXNlcnMsXG4gIENsaXBib2Fy
ZENoZWNrLFxufSBmcm9tIFwibHVjaWRlLXJlYWN0XCI7IiwgIm1hcmtlciI6ICIgIFVzZXJzLFxuICBDbGlwYm9hcmRDaGVjaywi
LCAiY291bnQiOiAib25lIn0sIHsicGF0aCI6ICJmcm9udGVuZC9saWIvbmF2LnRzIiwgImFuY2hvciI6ICIgIHsgaHJlZjogXCIv
c3BvdGxpZ2h0XCIsIGxhYmVsOiBcIlNwb3RsaWdodFwiLCBpY29uOiBTcGFya2xlcyB9LCIsICJyZXBsYWNlbWVudCI6ICIgIHsg
aHJlZjogXCIvc3BvdGxpZ2h0XCIsIGxhYmVsOiBcIlNwb3RsaWdodFwiLCBpY29uOiBTcGFya2xlcyB9LFxuICB7IGhyZWY6IFwi
L3BvZC1vd25lcnNcIiwgbGFiZWw6IFwiUG9kIE93bmVyc1wiLCBpY29uOiBVc2VycywgcmVxdWlyZXNBZG1pbjogdHJ1ZSB9LCIs
ICJtYXJrZXIiOiAieyBocmVmOiBcIi9wb2Qtb3duZXJzXCIiLCAiY291bnQiOiAib25lIn1dLCAicmVwbGFjZW1lbnRzIjogW119
"""


def resolve(text: str, anchor: str, replacement: str, marker: str) -> tuple[str, str, str]:
    """Match an anchor against a file that may have had its punctuation normalised.

    This deployment rewrites em-dashes to hyphens at some point in its own tooling, so an
    anchor carrying `—` finds nothing in a file carrying `-` even though the two are the
    same line to a reader. It cost a round-trip before this existed.

    When the plain anchor misses and the normalised one matches, the REPLACEMENT and the
    MARKER are normalised too - otherwise the patch would quietly reintroduce the very
    character the file had been cleaned of, and the next patch would miss for the same
    reason all over again.
    """
    if anchor in text:
        return anchor, replacement, marker
    flat = anchor.replace("\u2014", "-")
    if flat != anchor and flat in text:
        return flat, replacement.replace("\u2014", "-"), marker.replace("\u2014", "-")
    return anchor, replacement, marker


def locate(lines: list[str], anchor: str) -> int | None:
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
    # No run of consecutive lines survives, so fall back to the single most
    # distinctive line. A blind dump of the head of a 1000-line file is not an
    # answer, and one recognisable line is enough to place the hunk.
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
    if not Path("backend/app").is_dir() or not Path("frontend/app").is_dir():
        print("ABORTED: run this from the repository root")
        return 1

    data = json.loads(base64.b64decode(PAYLOAD.strip()).decode())
    problems: list[str] = []
    failures: list[tuple[str, str]] = []   # (path, anchor) for the echo below
    planned: dict[str, str] = {}      # path -> new text
    skipped: list[str] = []

    # ── new files ────────────────────────────────────────────────────────────
    for rel, content in data["new_files"].items():
        path = Path(rel)
        if path.exists() and path.read_text() == content:
            skipped.append(f"{rel}: already present and identical")
            continue
        if path.exists():
            skipped.append(f"{rel}: exists with different content - OVERWRITING")
        planned[rel] = content

    # ── appends ──────────────────────────────────────────────────────────────
    for item in data["appends"]:
        rel = item["path"]
        path = Path(rel)
        if not path.exists():
            problems.append(f"  {rel}: file not found")
            continue
        text = planned.get(rel, path.read_text())
        if item["marker"] in text:
            skipped.append(f"{rel}: already contains the appended block")
            continue
        planned[rel] = text + item["content"]

    # ── anchored edits ───────────────────────────────────────────────────────
    for index, item in enumerate(data["edits"], start=1):
        rel = item["path"]
        path = Path(rel)
        if not path.exists():
            problems.append(f"  [{index}] {rel}: file not found")
            continue
        text = planned.get(rel, path.read_text())
        anchor, replacement, marker = resolve(
            text, item["anchor"], item["replacement"], item["marker"]
        )
        if marker in text:
            skipped.append(f"{rel} [{index}]: already applied")
            continue
        found = text.count(anchor)
        expected_all = item.get("count") == "all"
        if found == 0 or (found != 1 and not expected_all):
            head = anchor.splitlines()[0][:76]
            problems.append(
                f"  [{index}] {rel}: expected "
                f"{'>=1' if expected_all else 'exactly 1'} match, found {found}\n"
                f"        anchor starts: {head!r}"
            )
            failures.append((rel, anchor))
            continue
        planned[rel] = text.replace(anchor, item["replacement"], -1 if expected_all else 1)

    if problems:
        print("ABORTED - NOTHING was written. Every problem, so one round-trip fixes all:")
        print()
        for problem in problems:
            print(problem)
        # Naming a missing anchor without showing the file costs a whole extra
        # round-trip just to look at it. Print the region the anchor was aiming
        # at - the longest run of its own lines that IS present - rather than
        # dumping whole files, which buries the one place that matters.
        shown: dict[str, list[tuple[int, int]]] = {}
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
    print("Rebuild backend + frontend, then run the test suites.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
