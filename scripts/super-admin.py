#!/usr/bin/env python3
"""Add a super_admin role: it manages admins, and only it can grant or remove itself.

The owner asked for an account above admin - one that can create and remove admins,
that no other account (admin OR super admin) can remove, and that only a super admin
can grant. This is a pure AUTHORIZATION change; it does not touch the Firebase login
itself (that is the MFA work, which is separate and depends on the Firebase console).

Every rule is enforced SERVER-SIDE in one place, admin_service.guard_target_management,
and called from update_user / delete_user / create_user in the admin router:
  1. A super admin is changed by nobody but themselves - "no one can remove him", literal.
  2. A plain admin is managed only by a super admin (editing your own profile excepted).
  3. The super_admin role is granted only by a super admin.
The last-active-admin lockout guard now counts a super admin as admin coverage, so the
two guards agree instead of fighting.

The migration seeds the role with admin-equal access (all metric groups, all
capabilities) - its power is structural, in the guards, not in extra capabilities, so no
CHECK constraint widens. It chains onto whatever the DEPLOYED alembic head is: the script
computes that head on the server (the reconstructed tree here is behind the server's),
and ABORTS rather than guess if the graph has zero or several heads.

Guard logic is unit-tested exhaustively - eight cases, one per boundary - because each is
a security decision that must fail loudly the day someone loosens it.

FIRST super admin is promoted once, by hand, from a trusted shell (no self-service
bootstrap exists, on purpose):
  UPDATE user_roles SET role_id=(SELECT id FROM roles WHERE name='super_admin')
  WHERE user_id=(SELECT id FROM users WHERE email='OWNER_EMAIL');
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

FOOTER = 'Run: alembic upgrade head, then the backend test suite.'

PAYLOAD = """
eyJuZXdfZmlsZXMiOiB7fSwgImdlbmVyYXRlZF9taWdyYXRpb24iOiB7InNsdWciOiAic3VwZXJfYWRtaW5fcm9sZSIsICJ0
ZW1wbGF0ZSI6ICJcIlwiXCJTdXBlciBhZG1pbiByb2xlIC0gbWFuYWdlcyBhZG1pbnMsIGdyYW50YWJsZSBvbmx5IGJ5IGEg
c3VwZXIgYWRtaW4uXG5cblJldmlzaW9uIElEOiB7cmV2fVxuUmV2aXNlczoge2Rvd259XG5cIlwiXCJcblxuZnJvbSBfX2Z1
dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9uc1xuXG5mcm9tIGFsZW1iaWMgaW1wb3J0IG9wXG5cbnJldmlzaW9uID0gXCJ7cmV2
fVwiXG5kb3duX3JldmlzaW9uID0gXCJ7ZG93bn1cIlxuYnJhbmNoX2xhYmVscyA9IE5vbmVcbmRlcGVuZHNfb24gPSBOb25l
XG5cblJPTEUgPSBcInN1cGVyX2FkbWluXCJcblxuXG5kZWYgdXBncmFkZSgpIC0+IE5vbmU6XG4gICAgIyBTYW1lIGFjY2Vz
cyBhcyBhZG1pbiAoYWxsIG1ldHJpYyBncm91cHMsIGFsbCBjYXBhYmlsaXRpZXMpOyBpdHMgcG93ZXIgaXMgc3RydWN0dXJh
bCAtXG4gICAgIyB3aG8gbWF5IG1hbmFnZSB3aG9tIC0gYW5kIGxpdmVzIGluIHRoZSBhcHBsaWNhdGlvbiBndWFyZHMsIG5v
dCBpbiBleHRyYSBjYXBhYmlsaXRpZXMsXG4gICAgIyBzbyBubyBDSEVDSyBjb25zdHJhaW50IG9uIHJvbGVfY2FwYWJpbGl0
aWVzIG5lZWRzIHdpZGVuaW5nLlxuICAgIG9wLmV4ZWN1dGUoXCJJTlNFUlQgSU5UTyByb2xlcyAobmFtZSkgVkFMVUVTICgn
c3VwZXJfYWRtaW4nKSBPTiBDT05GTElDVCAobmFtZSkgRE8gTk9USElORztcIilcbiAgICBvcC5leGVjdXRlKFxuICAgICAg
ICBcIlwiXCJcbiAgICAgICAgSU5TRVJUIElOVE8gcm9sZV9tZXRyaWNfcGVybWlzc2lvbnMgKHJvbGVfaWQsIG1ldHJpY19n
cm91cClcbiAgICAgICAgU0VMRUNUIHIuaWQsIGcuZyBGUk9NIHJvbGVzIHJcbiAgICAgICAgSk9JTiBMQVRFUkFMIChTRUxF
Q1QgdW5uZXN0KEFSUkFZW1xuICAgICAgICAgICdzdG9yZV9pbnN0YWxscycsJ3VhX3NwZW5kJywnYWRfcmV2ZW51ZScsJ2lh
cF9yZXZlbnVlJywnYXR0cmlidXRpb24nLCdwcm9maXRhYmlsaXR5J1xuICAgICAgICBdKSBBUyBnKSBnIE9OIHRydWVcbiAg
ICAgICAgV0hFUkUgci5uYW1lID0gJ3N1cGVyX2FkbWluJ1xuICAgICAgICBPTiBDT05GTElDVCBETyBOT1RISU5HO1xuICAg
ICAgICBcIlwiXCJcbiAgICApXG4gICAgb3AuZXhlY3V0ZShcbiAgICAgICAgXCJcIlwiXG4gICAgICAgIElOU0VSVCBJTlRP
IHJvbGVfY2FwYWJpbGl0aWVzIChyb2xlX2lkLCBjYXBhYmlsaXR5KVxuICAgICAgICBTRUxFQ1Qgci5pZCwgYy5jIEZST00g
cm9sZXMgclxuICAgICAgICBKT0lOIExBVEVSQUwgKFNFTEVDVCB1bm5lc3QoQVJSQVlbJ2V4cG9ydCcsJ3NoYXJlX3JlcG9y
dCcsJ2FkbWluX3BhbmVsJ10pIEFTIGMpIGMgT04gdHJ1ZVxuICAgICAgICBXSEVSRSByLm5hbWUgPSAnc3VwZXJfYWRtaW4n
XG4gICAgICAgIE9OIENPTkZMSUNUIERPIE5PVEhJTkc7XG4gICAgICAgIFwiXCJcIlxuICAgIClcblxuXG5kZWYgZG93bmdy
YWRlKCkgLT4gTm9uZTpcbiAgICBvcC5leGVjdXRlKFxuICAgICAgICBcIkRFTEVURSBGUk9NIHJvbGVfY2FwYWJpbGl0aWVz
IFdIRVJFIHJvbGVfaWQgSU4gKFNFTEVDVCBpZCBGUk9NIHJvbGVzIFdIRVJFIG5hbWU9J3N1cGVyX2FkbWluJyk7XCJcbiAg
ICApXG4gICAgb3AuZXhlY3V0ZShcbiAgICAgICAgXCJERUxFVEUgRlJPTSByb2xlX21ldHJpY19wZXJtaXNzaW9ucyBXSEVS
RSByb2xlX2lkIElOIChTRUxFQ1QgaWQgRlJPTSByb2xlcyBXSEVSRSBuYW1lPSdzdXBlcl9hZG1pbicpO1wiXG4gICAgKVxu
ICAgIG9wLmV4ZWN1dGUoXCJERUxFVEUgRlJPTSB1c2VyX3JvbGVzIFdIRVJFIHJvbGVfaWQgSU4gKFNFTEVDVCBpZCBGUk9N
IHJvbGVzIFdIRVJFIG5hbWU9J3N1cGVyX2FkbWluJyk7XCIpXG4gICAgb3AuZXhlY3V0ZShcIkRFTEVURSBGUk9NIHJvbGVz
IFdIRVJFIG5hbWUgPSAnc3VwZXJfYWRtaW4nO1wiKVxuIn0sICJuZXdfdGVzdCI6IHsicGF0aCI6ICJiYWNrZW5kL3Rlc3Rz
L3Rlc3Rfc3VwZXJfYWRtaW4ucHkiLCAiY29udGVudCI6ICJcIlwiXCJTdXBlci1hZG1pbiBtYW5hZ2VtZW50IGd1YXJkcyAt
IHRoZSBydWxlcyB0aGF0IGRlY2lkZSB3aG8gbWF5IG1hbmFnZSB3aG9tLlxuXG5UaGVzZSBhcmUgcHVyZSBkZWNpc2lvbnMg
KG5vIERCKSwgc28gdGhleSBhcmUgdGVzdGVkIGRpcmVjdGx5IGFuZCBleGhhdXN0aXZlbHk6IGV2ZXJ5XG5vbmUgaXMgYSBz
ZWN1cml0eSBib3VuZGFyeSwgYW5kIGEgc2VjdXJpdHkgYm91bmRhcnkgZGVzZXJ2ZXMgYSB0ZXN0IHRoYXQgZmFpbHMgbG91
ZGx5IHRoZVxuZGF5IHNvbWVvbmUgbG9vc2VucyBpdCBieSBhY2NpZGVudC5cblwiXCJcIlxuXG5mcm9tIF9fZnV0dXJlX18g
aW1wb3J0IGFubm90YXRpb25zXG5cbmltcG9ydCB1dWlkXG5cbmZyb20gYXBwLnNlcnZpY2VzLmFkbWluX3NlcnZpY2UgaW1w
b3J0IFNVUEVSX0FETUlOX1JPTEUsIGd1YXJkX3RhcmdldF9tYW5hZ2VtZW50XG5cbkFDVE9SID0gdXVpZC51dWlkNCgpXG5P
VEhFUiA9IHV1aWQudXVpZDQoKVxuXG5cbmRlZiB0ZXN0X2Ffc3VwZXJfYWRtaW5fY2Fubm90X2JlX3RvdWNoZWRfYnlfYV9w
bGFpbl9hZG1pbigpIC0+IE5vbmU6XG4gICAgcmVhc29uID0gZ3VhcmRfdGFyZ2V0X21hbmFnZW1lbnQoXG4gICAgICAgIGFj
dG9yX3JvbGVzPVtcImFkbWluXCJdLCBhY3Rvcl9pZD1BQ1RPUixcbiAgICAgICAgdGFyZ2V0X3JvbGVzPVtTVVBFUl9BRE1J
Tl9ST0xFXSwgdGFyZ2V0X2lkPU9USEVSLFxuICAgIClcbiAgICBhc3NlcnQgcmVhc29uIGFuZCBcInN1cGVyIGFkbWluXCIg
aW4gcmVhc29uLmxvd2VyKClcblxuXG5kZWYgdGVzdF9hX3N1cGVyX2FkbWluX2Nhbm5vdF9iZV90b3VjaGVkX2J5X2Fub3Ro
ZXJfc3VwZXJfYWRtaW4oKSAtPiBOb25lOlxuICAgICMgXCJubyBvdGhlciBwZXJzb24gY2FuIHJlbW92ZSBoaW1cIiAtIGxp
dGVyYWxseSBubyBvdGhlciBhY2NvdW50LCBzdXBlciBvciBub3QuXG4gICAgcmVhc29uID0gZ3VhcmRfdGFyZ2V0X21hbmFn
ZW1lbnQoXG4gICAgICAgIGFjdG9yX3JvbGVzPVtTVVBFUl9BRE1JTl9ST0xFXSwgYWN0b3JfaWQ9QUNUT1IsXG4gICAgICAg
IHRhcmdldF9yb2xlcz1bU1VQRVJfQURNSU5fUk9MRV0sIHRhcmdldF9pZD1PVEhFUixcbiAgICApXG4gICAgYXNzZXJ0IHJl
YXNvbiBpcyBub3QgTm9uZVxuXG5cbmRlZiB0ZXN0X2Ffc3VwZXJfYWRtaW5fbWF5X2NoYW5nZV90aGVtc2VsdmVzKCkgLT4g
Tm9uZTpcbiAgICBhc3NlcnQgZ3VhcmRfdGFyZ2V0X21hbmFnZW1lbnQoXG4gICAgICAgIGFjdG9yX3JvbGVzPVtTVVBFUl9B
RE1JTl9ST0xFXSwgYWN0b3JfaWQ9QUNUT1IsXG4gICAgICAgIHRhcmdldF9yb2xlcz1bU1VQRVJfQURNSU5fUk9MRV0sIHRh
cmdldF9pZD1BQ1RPUixcbiAgICApIGlzIE5vbmVcblxuXG5kZWYgdGVzdF9hX3BsYWluX2FkbWluX2Nhbm5vdF9tYW5hZ2Vf
YW5vdGhlcl9hZG1pbigpIC0+IE5vbmU6XG4gICAgcmVhc29uID0gZ3VhcmRfdGFyZ2V0X21hbmFnZW1lbnQoXG4gICAgICAg
IGFjdG9yX3JvbGVzPVtcImFkbWluXCJdLCBhY3Rvcl9pZD1BQ1RPUixcbiAgICAgICAgdGFyZ2V0X3JvbGVzPVtcImFkbWlu
XCJdLCB0YXJnZXRfaWQ9T1RIRVIsXG4gICAgKVxuICAgIGFzc2VydCByZWFzb24gYW5kIFwic3VwZXIgYWRtaW5cIiBpbiBy
ZWFzb24ubG93ZXIoKVxuXG5cbmRlZiB0ZXN0X2Ffc3VwZXJfYWRtaW5fY2FuX21hbmFnZV9hbl9hZG1pbigpIC0+IE5vbmU6
XG4gICAgYXNzZXJ0IGd1YXJkX3RhcmdldF9tYW5hZ2VtZW50KFxuICAgICAgICBhY3Rvcl9yb2xlcz1bU1VQRVJfQURNSU5f
Uk9MRV0sIGFjdG9yX2lkPUFDVE9SLFxuICAgICAgICB0YXJnZXRfcm9sZXM9W1wiYWRtaW5cIl0sIHRhcmdldF9pZD1PVEhF
UixcbiAgICApIGlzIE5vbmVcblxuXG5kZWYgdGVzdF9hX3BsYWluX2FkbWluX2Nhbm5vdF9ncmFudF9zdXBlcl9hZG1pbigp
IC0+IE5vbmU6XG4gICAgcmVhc29uID0gZ3VhcmRfdGFyZ2V0X21hbmFnZW1lbnQoXG4gICAgICAgIGFjdG9yX3JvbGVzPVtc
ImFkbWluXCJdLCBhY3Rvcl9pZD1BQ1RPUixcbiAgICAgICAgdGFyZ2V0X3JvbGVzPVtdLCB0YXJnZXRfaWQ9Tm9uZSxcbiAg
ICAgICAgaW5jb21pbmdfcm9sZXM9W1wiYWRtaW5cIiwgU1VQRVJfQURNSU5fUk9MRV0sXG4gICAgKVxuICAgIGFzc2VydCBy
ZWFzb24gYW5kIFwiZ3JhbnRcIiBpbiByZWFzb24ubG93ZXIoKVxuXG5cbmRlZiB0ZXN0X2Ffc3VwZXJfYWRtaW5fY2FuX2dy
YW50X3N1cGVyX2FkbWluKCkgLT4gTm9uZTpcbiAgICBhc3NlcnQgZ3VhcmRfdGFyZ2V0X21hbmFnZW1lbnQoXG4gICAgICAg
IGFjdG9yX3JvbGVzPVtTVVBFUl9BRE1JTl9ST0xFXSwgYWN0b3JfaWQ9QUNUT1IsXG4gICAgICAgIHRhcmdldF9yb2xlcz1b
XSwgdGFyZ2V0X2lkPU5vbmUsXG4gICAgICAgIGluY29taW5nX3JvbGVzPVtTVVBFUl9BRE1JTl9ST0xFXSxcbiAgICApIGlz
IE5vbmVcblxuXG5kZWYgdGVzdF9hbl9hZG1pbl9lZGl0aW5nX3RoZWlyX293bl9wcm9maWxlX2lzX2FsbG93ZWQoKSAtPiBO
b25lOlxuICAgICMgRWRpdGluZyB5b3Vyc2VsZiBpcyBub3QgXCJtYW5hZ2luZyBhbm90aGVyIGFkbWluXCI7IHRoZSBsYXN0
LWFkbWluIGxvY2tvdXQgZ3VhcmQgaXMgYVxuICAgICMgc2VwYXJhdGUgY2hlY2sgYW5kIHN0aWxsIGFwcGxpZXMgd2hlcmUg
cmVsZXZhbnQuXG4gICAgYXNzZXJ0IGd1YXJkX3RhcmdldF9tYW5hZ2VtZW50KFxuICAgICAgICBhY3Rvcl9yb2xlcz1bXCJh
ZG1pblwiXSwgYWN0b3JfaWQ9QUNUT1IsXG4gICAgICAgIHRhcmdldF9yb2xlcz1bXCJhZG1pblwiXSwgdGFyZ2V0X2lkPUFD
VE9SLFxuICAgICkgaXMgTm9uZVxuIn0sICJlZGl0cyI6IFt7InBhdGgiOiAiYmFja2VuZC9hcHAvc2VydmljZXMvYWRtaW5f
c2VydmljZS5weSIsICJhbmNob3IiOiAiZGVmIGlzX2FjdGl2ZV9hZG1pbihcbiAgICAqLCBpc19hY3RpdmU6IGJvb2wsIHJv
bGVzOiBsaXN0W3N0cl0sIGFjY2Vzc19leHBpcmVzX2F0OiBkYXRldGltZSB8IE5vbmVcbikgLT4gYm9vbDoiLCAicmVwbGFj
ZW1lbnQiOiAiIyBcdTI1MDBcdTI1MDAgU3VwZXIgYWRtaW46IHRoZSByb2xlIHRoYXQgbWFuYWdlcyBhZG1pbnMgYW5kIHRo
YXQgb25seSBpdCBjYW4gZ3JhbnQgXHUyNTAwXHUyNTAwXHUyNTAwXHUyNTAwXHUyNTAwXHUyNTAwXHUyNTAwXHUyNTAwXHUy
NTAwXHUyNTAwXG4jIE9uZSByb2xlIHNpdHMgYWJvdmUgYWRtaW4uIEl0IGNhbiBjcmVhdGUgYW5kIHJlbW92ZSBhZG1pbnM7
IGEgcGxhaW4gYWRtaW4gY2Fubm90IHRvdWNoXG4jIGl0LCBjYW5ub3QgZ3JhbnQgaXQsIGFuZCBjYW5ub3QgbWFuYWdlIGFu
b3RoZXIgYWRtaW4uIEV2ZXJ5IG9uZSBvZiB0aGVzZSBjaGVja3MgbGl2ZXNcbiMgSEVSRSBhbmQgaXMgY2FsbGVkIGZyb20g
dGhlIHJvdXRlciAtIG5ldmVyIGVuZm9yY2VkIGluIHRoZSBVSSwgd2hpY2ggb25seSBoaWRlcyBidXR0b25zLlxuU1VQRVJf
QURNSU5fUk9MRSA9IFwic3VwZXJfYWRtaW5cIlxuXG5cbmRlZiBndWFyZF90YXJnZXRfbWFuYWdlbWVudChcbiAgICAqLFxu
ICAgIGFjdG9yX3JvbGVzOiBsaXN0W3N0cl0sXG4gICAgYWN0b3JfaWQ6IHV1aWQuVVVJRCxcbiAgICB0YXJnZXRfcm9sZXM6
IGxpc3Rbc3RyXSxcbiAgICB0YXJnZXRfaWQ6IHV1aWQuVVVJRCB8IE5vbmUsXG4gICAgaW5jb21pbmdfcm9sZXM6IGxpc3Rb
c3RyXSB8IE5vbmUgPSBOb25lLFxuKSAtPiBzdHIgfCBOb25lOlxuICAgIFwiXCJcIlJlZnVzYWwgcmVhc29uIGlmIHRoaXMg
YWN0b3IgbWF5IE5PVCBtYW5hZ2UgdGhpcyB0YXJnZXQsIGVsc2UgTm9uZS5cblxuICAgIFRocmVlIHJ1bGVzLCBpbiBvcmRl
ciBvZiBzdHJlbmd0aDpcbiAgICAgIDEuIEEgc3VwZXIgYWRtaW4gaXMgY2hhbmdlZCBieSBOT0JPRFkgYnV0IHRoZW1zZWx2
ZXMgLSBub3QgYW5vdGhlciBhZG1pbiwgbm90IGV2ZW5cbiAgICAgICAgIGFub3RoZXIgc3VwZXIgYWRtaW4uIFRoaXMgaXMg
dGhlIG93bmVyJ3MgXCJubyBvbmUgY2FuIHJlbW92ZSBoaW1cIiBtYWRlIGxpdGVyYWwuXG4gICAgICAyLiBBIHBsYWluIGFk
bWluIGlzIG1hbmFnZWQgb25seSBieSBhIHN1cGVyIGFkbWluIChvciBieSB0aGVtc2VsdmVzIC0gZWRpdGluZyB5b3VyXG4g
ICAgICAgICBvd24gcHJvZmlsZSBpcyBub3QgbWFuYWdpbmcgYW5vdGhlciBhZG1pbjsgdGhlIGxhc3QtYWRtaW4gbG9ja291
dCBndWFyZCBpc1xuICAgICAgICAgc2VwYXJhdGUgYW5kIHN0aWxsIGFwcGxpZXMpLlxuICAgICAgMy4gVGhlIHN1cGVyLWFk
bWluIHJvbGUgaXMgR1JBTlRFRCBvbmx5IGJ5IGEgc3VwZXIgYWRtaW4gLSBzbyBub2JvZHkgY2FuIHByb21vdGVcbiAgICAg
ICAgIHRoZW1zZWx2ZXMgb3IgYSBjb25mZWRlcmF0ZSBpbnRvIGl0LlxuICAgIFwiXCJcIlxuICAgIGFjdG9yX2lzX3N1cGVy
ID0gU1VQRVJfQURNSU5fUk9MRSBpbiBhY3Rvcl9yb2xlc1xuICAgIGlzX3NlbGYgPSB0YXJnZXRfaWQgaXMgbm90IE5vbmUg
YW5kIHRhcmdldF9pZCA9PSBhY3Rvcl9pZFxuXG4gICAgaWYgU1VQRVJfQURNSU5fUk9MRSBpbiB0YXJnZXRfcm9sZXMgYW5k
IG5vdCBpc19zZWxmOlxuICAgICAgICByZXR1cm4gXCJBIHN1cGVyIGFkbWluIGNhbiBvbmx5IGJlIGNoYW5nZWQgYnkgdGhl
bXNlbHZlcy5cIlxuICAgIGlmIFwiYWRtaW5cIiBpbiB0YXJnZXRfcm9sZXMgYW5kIG5vdCBhY3Rvcl9pc19zdXBlciBhbmQg
bm90IGlzX3NlbGY6XG4gICAgICAgIHJldHVybiBcIk9ubHkgYSBzdXBlciBhZG1pbiBjYW4gbWFuYWdlIGFub3RoZXIgYWRt
aW4uXCJcbiAgICBpZiBpbmNvbWluZ19yb2xlcyBpcyBub3QgTm9uZSBhbmQgU1VQRVJfQURNSU5fUk9MRSBpbiBpbmNvbWlu
Z19yb2xlcyBhbmQgbm90IGFjdG9yX2lzX3N1cGVyOlxuICAgICAgICByZXR1cm4gXCJPbmx5IGEgc3VwZXIgYWRtaW4gY2Fu
IGdyYW50IHRoZSBzdXBlci1hZG1pbiByb2xlLlwiXG4gICAgcmV0dXJuIE5vbmVcblxuXG5kZWYgaXNfYWN0aXZlX2FkbWlu
KFxuICAgICosIGlzX2FjdGl2ZTogYm9vbCwgcm9sZXM6IGxpc3Rbc3RyXSwgYWNjZXNzX2V4cGlyZXNfYXQ6IGRhdGV0aW1l
IHwgTm9uZVxuKSAtPiBib29sOiIsICJtYXJrZXIiOiAiZGVmIGd1YXJkX3RhcmdldF9tYW5hZ2VtZW50KCJ9LCB7InBhdGgi
OiAiYmFja2VuZC9hcHAvc2VydmljZXMvYWRtaW5fc2VydmljZS5weSIsICJhbmNob3IiOiAiICAgIG5vdF9leHBpcmVkID0g
YWNjZXNzX2V4cGlyZXNfYXQgaXMgTm9uZSBvciBhY2Nlc3NfZXhwaXJlc19hdCA+IGRhdGV0aW1lLm5vdyhVVEMpXG4gICAg
cmV0dXJuIGlzX2FjdGl2ZSBhbmQgXCJhZG1pblwiIGluIHJvbGVzIGFuZCBub3RfZXhwaXJlZCIsICJyZXBsYWNlbWVudCI6
ICIgICAgbm90X2V4cGlyZWQgPSBhY2Nlc3NfZXhwaXJlc19hdCBpcyBOb25lIG9yIGFjY2Vzc19leHBpcmVzX2F0ID4gZGF0
ZXRpbWUubm93KFVUQylcbiAgICAjIHN1cGVyX2FkbWluIGNvdW50cyBhcyBhZG1pbiBjb3ZlcmFnZTogYSBzeXN0ZW0gd2l0
aCBhIGxpdmUgc3VwZXIgYWRtaW4gaXMgbmV2ZXJcbiAgICAjIFwib3JwaGFuZWQgb2YgYWRtaW5zXCIsIGFuZCB0aGUgbGFz
dC1hZG1pbiBsb2Nrb3V0IGd1YXJkIG11c3Qgc2VlIGl0IHRoYXQgd2F5LlxuICAgIHJldHVybiBpc19hY3RpdmUgYW5kIChc
ImFkbWluXCIgaW4gcm9sZXMgb3IgU1VQRVJfQURNSU5fUk9MRSBpbiByb2xlcykgYW5kIG5vdF9leHBpcmVkIiwgIm1hcmtl
ciI6ICIoXCJhZG1pblwiIGluIHJvbGVzIG9yIFNVUEVSX0FETUlOX1JPTEUgaW4gcm9sZXMpIn0sIHsicGF0aCI6ICJiYWNr
ZW5kL2FwcC9zZXJ2aWNlcy9hZG1pbl9zZXJ2aWNlLnB5IiwgImFuY2hvciI6ICIgICAgICAgIC53aGVyZShcbiAgICAgICAg
ICAgIFJvbGUubmFtZSA9PSBcImFkbWluXCIsXG4gICAgICAgICAgICBVc2VyLmlzX2FjdGl2ZS5pc18oVHJ1ZSksXG4gICAg
ICAgICAgICBVc2VyLmlkICE9IGV4Y2x1ZGVfdXNlcl9pZCwiLCAicmVwbGFjZW1lbnQiOiAiICAgICAgICAud2hlcmUoXG4g
ICAgICAgICAgICBSb2xlLm5hbWUuaW5fKChcImFkbWluXCIsIFNVUEVSX0FETUlOX1JPTEUpKSxcbiAgICAgICAgICAgIFVz
ZXIuaXNfYWN0aXZlLmlzXyhUcnVlKSxcbiAgICAgICAgICAgIFVzZXIuaWQgIT0gZXhjbHVkZV91c2VyX2lkLCIsICJtYXJr
ZXIiOiAiUm9sZS5uYW1lLmluXygoXCJhZG1pblwiLCBTVVBFUl9BRE1JTl9ST0xFKSksIn0sIHsicGF0aCI6ICJiYWNrZW5k
L2FwcC9hcGkvdjEvYWRtaW4ucHkiLCAiYW5jaG9yIjogIiAgICBjdXJyZW50X3JvbGVzID0gYXdhaXQgYWRtaW5fc2Vydmlj
ZS5yb2xlX25hbWVzKGRiLCB1c2VyLmlkKVxuICAgIG5ld19pc19hY3RpdmUgPSB1c2VyLmlzX2FjdGl2ZSBpZiBib2R5Lmlz
X2FjdGl2ZSBpcyBOb25lIGVsc2UgYm9keS5pc19hY3RpdmUiLCAicmVwbGFjZW1lbnQiOiAiICAgIGN1cnJlbnRfcm9sZXMg
PSBhd2FpdCBhZG1pbl9zZXJ2aWNlLnJvbGVfbmFtZXMoZGIsIHVzZXIuaWQpXG4gICAgcmVmdXNhbCA9IGFkbWluX3NlcnZp
Y2UuZ3VhcmRfdGFyZ2V0X21hbmFnZW1lbnQoXG4gICAgICAgIGFjdG9yX3JvbGVzPWNvbnRleHQucm9sZXMsXG4gICAgICAg
IGFjdG9yX2lkPWNvbnRleHQudXNlcl9pZCxcbiAgICAgICAgdGFyZ2V0X3JvbGVzPWN1cnJlbnRfcm9sZXMsXG4gICAgICAg
IHRhcmdldF9pZD11c2VyLmlkLFxuICAgICAgICBpbmNvbWluZ19yb2xlcz1ib2R5LnJvbGVzLFxuICAgIClcbiAgICBpZiBy
ZWZ1c2FsIGlzIG5vdCBOb25lOlxuICAgICAgICByYWlzZSBIVFRQRXhjZXB0aW9uKHN0YXR1cy5IVFRQXzQwM19GT1JCSURE
RU4sIHJlZnVzYWwpXG4gICAgbmV3X2lzX2FjdGl2ZSA9IHVzZXIuaXNfYWN0aXZlIGlmIGJvZHkuaXNfYWN0aXZlIGlzIE5v
bmUgZWxzZSBib2R5LmlzX2FjdGl2ZSIsICJtYXJrZXIiOiAicmVmdXNhbCA9IGFkbWluX3NlcnZpY2UuZ3VhcmRfdGFyZ2V0
X21hbmFnZW1lbnQoXG4gICAgICAgIGFjdG9yX3JvbGVzPWNvbnRleHQucm9sZXMsXG4gICAgICAgIGFjdG9yX2lkPWNvbnRl
eHQudXNlcl9pZCxcbiAgICAgICAgdGFyZ2V0X3JvbGVzPWN1cnJlbnRfcm9sZXMsXG4gICAgICAgIHRhcmdldF9pZD11c2Vy
LmlkLFxuICAgICAgICBpbmNvbWluZ19yb2xlcz1ib2R5LnJvbGVzLCJ9LCB7InBhdGgiOiAiYmFja2VuZC9hcHAvYXBpL3Yx
L2FkbWluLnB5IiwgImFuY2hvciI6ICIgICAgY3VycmVudF9yb2xlcyA9IGF3YWl0IGFkbWluX3NlcnZpY2Uucm9sZV9uYW1l
cyhkYiwgdXNlci5pZClcbiAgICBpZiBhZG1pbl9zZXJ2aWNlLmlzX2FjdGl2ZV9hZG1pbigiLCAicmVwbGFjZW1lbnQiOiAi
ICAgIGN1cnJlbnRfcm9sZXMgPSBhd2FpdCBhZG1pbl9zZXJ2aWNlLnJvbGVfbmFtZXMoZGIsIHVzZXIuaWQpXG4gICAgcmVm
dXNhbCA9IGFkbWluX3NlcnZpY2UuZ3VhcmRfdGFyZ2V0X21hbmFnZW1lbnQoXG4gICAgICAgIGFjdG9yX3JvbGVzPWNvbnRl
eHQucm9sZXMsXG4gICAgICAgIGFjdG9yX2lkPWNvbnRleHQudXNlcl9pZCxcbiAgICAgICAgdGFyZ2V0X3JvbGVzPWN1cnJl
bnRfcm9sZXMsXG4gICAgICAgIHRhcmdldF9pZD11c2VyLmlkLFxuICAgIClcbiAgICBpZiByZWZ1c2FsIGlzIG5vdCBOb25l
OlxuICAgICAgICByYWlzZSBIVFRQRXhjZXB0aW9uKHN0YXR1cy5IVFRQXzQwM19GT1JCSURERU4sIHJlZnVzYWwpXG4gICAg
aWYgYWRtaW5fc2VydmljZS5pc19hY3RpdmVfYWRtaW4oIiwgIm1hcmtlciI6ICIgICAgICAgIHRhcmdldF9pZD11c2VyLmlk
LFxuICAgIClcbiAgICBpZiByZWZ1c2FsIGlzIG5vdCBOb25lOlxuICAgICAgICByYWlzZSBIVFRQRXhjZXB0aW9uKHN0YXR1
cy5IVFRQXzQwM19GT1JCSURERU4sIHJlZnVzYWwpXG4gICAgaWYgYWRtaW5fc2VydmljZS5pc19hY3RpdmVfYWRtaW4oIn0s
IHsicGF0aCI6ICJiYWNrZW5kL2FwcC9hcGkvdjEvYWRtaW4ucHkiLCAiYW5jaG9yIjogIiAgICBfcmVqZWN0X2JvdGhfZXhw
aXJ5KGJvZHkuYWNjZXNzX2V4cGlyZXNfYXQsIGJvZHkuYWNjZXNzX2R1cmF0aW9uX2RheXMpXG4gICAgZXhwaXJ5ID0gX3Jl
c29sdmVfZXhwaXJ5KGJvZHkuYWNjZXNzX2V4cGlyZXNfYXQsIGJvZHkuYWNjZXNzX2R1cmF0aW9uX2RheXMpXG4gICAgdHJ5
OlxuICAgICAgICBzdW1tYXJ5ID0gYXdhaXQgYWRtaW5fc2VydmljZS5jcmVhdGVfdXNlcigiLCAicmVwbGFjZW1lbnQiOiAi
ICAgIF9yZWplY3RfYm90aF9leHBpcnkoYm9keS5hY2Nlc3NfZXhwaXJlc19hdCwgYm9keS5hY2Nlc3NfZHVyYXRpb25fZGF5
cylcbiAgICByZWZ1c2FsID0gYWRtaW5fc2VydmljZS5ndWFyZF90YXJnZXRfbWFuYWdlbWVudChcbiAgICAgICAgYWN0b3Jf
cm9sZXM9Y29udGV4dC5yb2xlcyxcbiAgICAgICAgYWN0b3JfaWQ9Y29udGV4dC51c2VyX2lkLFxuICAgICAgICB0YXJnZXRf
cm9sZXM9W10sXG4gICAgICAgIHRhcmdldF9pZD1Ob25lLFxuICAgICAgICBpbmNvbWluZ19yb2xlcz1ib2R5LnJvbGVzLFxu
ICAgIClcbiAgICBpZiByZWZ1c2FsIGlzIG5vdCBOb25lOlxuICAgICAgICByYWlzZSBIVFRQRXhjZXB0aW9uKHN0YXR1cy5I
VFRQXzQwM19GT1JCSURERU4sIHJlZnVzYWwpXG4gICAgZXhwaXJ5ID0gX3Jlc29sdmVfZXhwaXJ5KGJvZHkuYWNjZXNzX2V4
cGlyZXNfYXQsIGJvZHkuYWNjZXNzX2R1cmF0aW9uX2RheXMpXG4gICAgdHJ5OlxuICAgICAgICBzdW1tYXJ5ID0gYXdhaXQg
YWRtaW5fc2VydmljZS5jcmVhdGVfdXNlcigiLCAibWFya2VyIjogIiAgICAgICAgdGFyZ2V0X3JvbGVzPVtdLFxuICAgICAg
ICB0YXJnZXRfaWQ9Tm9uZSxcbiAgICAgICAgaW5jb21pbmdfcm9sZXM9Ym9keS5yb2xlcyxcbiAgICApXG4gICAgaWYgcmVm
dXNhbCBpcyBub3QgTm9uZToifSwgeyJwYXRoIjogImJhY2tlbmQvdGVzdHMvY29uZnRlc3QucHkiLCAiYW5jaG9yIjogIiAg
ICBcIklOU0VSVCBJTlRPIHJvbGVzIChuYW1lKSBWQUxVRVMgXCJcbiAgICBcIignYWRtaW4nKSwoJ2V4ZWN1dGl2ZScpLCgn
cG9kX293bmVyJyksKCdtYXJrZXRpbmcnKSwoJ2ZpbmFuY2UnKSwoJ3ZpZXdlcicpO1wiIiwgInJlcGxhY2VtZW50IjogIiAg
ICBcIklOU0VSVCBJTlRPIHJvbGVzIChuYW1lKSBWQUxVRVMgXCJcbiAgICBcIignYWRtaW4nKSwoJ3N1cGVyX2FkbWluJyks
KCdleGVjdXRpdmUnKSwoJ3BvZF9vd25lcicpLCgnbWFya2V0aW5nJyksKCdmaW5hbmNlJyksKCd2aWV3ZXInKTtcIiIsICJt
YXJrZXIiOiAiKCdhZG1pbicpLCgnc3VwZXJfYWRtaW4nKSwoJ2V4ZWN1dGl2ZScpIn0sIHsicGF0aCI6ICJiYWNrZW5kL3Rl
c3RzL2NvbmZ0ZXN0LnB5IiwgImFuY2hvciI6ICIgIFdIRU4gJ2FkbWluJyAgICAgVEhFTiBBUlJBWVsnc3RvcmVfaW5zdGFs
bHMnLCd1YV9zcGVuZCcsJ2FkX3JldmVudWUnLCdpYXBfcmV2ZW51ZScsJ2F0dHJpYnV0aW9uJywncHJvZml0YWJpbGl0eSdd
XG4gIFdIRU4gJ2V4ZWN1dGl2ZScgVEhFTiBBUlJBWVsnc3RvcmVfaW5zdGFsbHMnLCd1YV9zcGVuZCcsJ2FkX3JldmVudWUn
LCdpYXBfcmV2ZW51ZScsJ2F0dHJpYnV0aW9uJywncHJvZml0YWJpbGl0eSddIiwgInJlcGxhY2VtZW50IjogIiAgV0hFTiAn
YWRtaW4nICAgICBUSEVOIEFSUkFZWydzdG9yZV9pbnN0YWxscycsJ3VhX3NwZW5kJywnYWRfcmV2ZW51ZScsJ2lhcF9yZXZl
bnVlJywnYXR0cmlidXRpb24nLCdwcm9maXRhYmlsaXR5J11cbiAgV0hFTiAnc3VwZXJfYWRtaW4nIFRIRU4gQVJSQVlbJ3N0
b3JlX2luc3RhbGxzJywndWFfc3BlbmQnLCdhZF9yZXZlbnVlJywnaWFwX3JldmVudWUnLCdhdHRyaWJ1dGlvbicsJ3Byb2Zp
dGFiaWxpdHknXVxuICBXSEVOICdleGVjdXRpdmUnIFRIRU4gQVJSQVlbJ3N0b3JlX2luc3RhbGxzJywndWFfc3BlbmQnLCdh
ZF9yZXZlbnVlJywnaWFwX3JldmVudWUnLCdhdHRyaWJ1dGlvbicsJ3Byb2ZpdGFiaWxpdHknXSIsICJtYXJrZXIiOiAiV0hF
TiAnc3VwZXJfYWRtaW4nIFRIRU4gQVJSQVlbJ3N0b3JlX2luc3RhbGxzJywndWFfc3BlbmQnLCdhZF9yZXZlbnVlJywnaWFw
X3JldmVudWUnLCdhdHRyaWJ1dGlvbicsJ3Byb2ZpdGFiaWxpdHknXSJ9LCB7InBhdGgiOiAiYmFja2VuZC90ZXN0cy9jb25m
dGVzdC5weSIsICJhbmNob3IiOiAiICBXSEVOICdhZG1pbicgICAgIFRIRU4gQVJSQVlbJ2V4cG9ydCcsJ3NoYXJlX3JlcG9y
dCcsJ2FkbWluX3BhbmVsJ10iLCAicmVwbGFjZW1lbnQiOiAiICBXSEVOICdhZG1pbicgICAgIFRIRU4gQVJSQVlbJ2V4cG9y
dCcsJ3NoYXJlX3JlcG9ydCcsJ2FkbWluX3BhbmVsJ11cbiAgV0hFTiAnc3VwZXJfYWRtaW4nIFRIRU4gQVJSQVlbJ2V4cG9y
dCcsJ3NoYXJlX3JlcG9ydCcsJ2FkbWluX3BhbmVsJ10iLCAibWFya2VyIjogIldIRU4gJ3N1cGVyX2FkbWluJyBUSEVOIEFS
UkFZWydleHBvcnQnLCdzaGFyZV9yZXBvcnQnLCdhZG1pbl9wYW5lbCddIn1dfQ==
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



import re as _re

REV_RE = _re.compile(r"^revision(?::\s*str)?\s*=\s*[\"']([^\"']+)[\"']", _re.M)
DOWN_RE = _re.compile(r"^down_revision(?::[^=\n]+)?\s*=\s*(.+)$", _re.M)


def _parents(text):
    m = DOWN_RE.search(text)
    if not m:
        return []
    raw = m.group(1).strip()
    if raw == "None":
        return []
    return [p.strip().strip("\"'") for p in raw.strip("()").split(",") if p.strip()]


def detect_head():
    versions = Path("backend/alembic/versions")
    if not versions.is_dir():
        return None, "backend/alembic/versions not found"
    ids, referenced, dupes = {}, set(), set()
    for f in versions.glob("*.py"):
        t = f.read_text()
        m = REV_RE.search(t)
        if not m:
            continue
        rev = m.group(1)
        if rev in ids:
            dupes.add(rev)
        ids[rev] = f.name
        referenced.update(_parents(t))
    if dupes:
        return None, f"duplicate revision id(s): {sorted(dupes)}"
    heads = [r for r in ids if r not in referenced]
    if len(heads) != 1:
        return None, f"expected exactly one head, found {len(heads)}: {sorted(heads)}"
    return heads[0], None


def write_migration(data):
    gen = data.get("generated_migration")
    if not gen:
        return None
    versions = Path("backend/alembic/versions")
    slug = gen["slug"]
    # Deterministic revision id from the slug (no clock in this sandbox); ON CONFLICT keeps
    # the migration itself idempotent regardless.
    rev = "sa" + "".join(c for c in slug if c.isalnum())[:10]
    existing = list(versions.glob(f"*_{slug}.py"))
    if existing:
        return f"skip  migration already present: {existing[0].name}"
    head, err = detect_head()
    if err:
        return f"MIGRATION-ABORT: {err}"
    body = gen["template"].format(rev=rev, down=head)
    out = versions / f"20260821_0000_{rev}_{slug}.py"
    out.write_text(body)
    return f"wrote {out.as_posix()}  (chained onto {head})"


def main() -> int:
    if not Path("backend/app").is_dir():
        print("ABORTED: run this from the repository root")
        return 1
    data = json.loads(base64.b64decode(PAYLOAD.strip()).decode())

    # 1) generated migration (head detected on THIS tree = the deployed one)
    mig = write_migration(data)

    # 2) the standalone new test file
    test = data.get("new_test")
    test_note = None
    if test:
        p = Path(test["path"])
        if p.exists() and p.read_text() == test["content"]:
            test_note = f"skip  {test['path']}: already present"
        else:
            p.write_text(test["content"])
            test_note = f"wrote {test['path']}"

    # 3) anchored edits (same all-or-nothing runner as every other script)
    problems, failures, planned, skipped = [], [], {}, []
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
                lo, hi = 0, min(len(lines), 120); note = "nothing from this anchor is on disk - head of file"
            else:
                lo, hi = max(0, hit - 30), min(len(lines), hit + 30); note = f"nearest partial match at line {hit + 1}"
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
        Path(rel).write_text(content)
        print(f"wrote {rel}")
    for note in skipped:
        print(f"skip  {note}")
    if test_note:
        print(test_note)
    if mig:
        print(mig)
        if mig.startswith("MIGRATION-ABORT"):
            print("The edits applied, but the migration could not be generated - fix the")
            print("revision graph (run scripts/check-migrations.py) and re-run this.")
            return 1
    print()
    print(FOOTER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
