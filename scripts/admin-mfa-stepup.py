#!/usr/bin/env python3
"""Enforce MFA, verified email and a step-up window for admins - Firebase-native, off by default.

The owner asked that a privileged sign-in demand an authenticator, and that after ~30
minutes the session re-prompt. Firebase Auth (the locked identity provider) already mints
every claim needed - sign_in_second_factor, email_verified, auth_time - so this is pure
ENFORCEMENT, not a second auth system: no passwords, no TOTP secrets, no session store
live in this codebase.

app/core/step_up.py is a pure decision - evaluate_admin_gate(roles, claims, settings) ->
a machine code or None - and is unit-tested exhaustively (8 cases). deps.py stashes the
three claims off the verified token and a thin router dependency, enforce_admin_step_up,
turns the decision into a 403 whose detail is the code the frontend acts on
(MFA_REQUIRED / EMAIL_UNVERIFIED / STEP_UP_REQUIRED). It is wired onto the whole admin
router, so it covers every admin action including the new super-admin management.

Three settings drive it, all default OFF: require_admin_mfa, require_email_verified,
admin_step_up_minutes (30). Off-by-default is the safety interlock: enabling TOTP in the
Firebase console and enforcing it here are two deliberate, ordered steps, so no admin is
locked out before they enrol. The gate only ever applies to admin / super_admin; ordinary
users are never touched, and the existing suite stays green because nothing fires until an
admin turns it on.

What still needs the owner (cannot be done from code): enable TOTP MFA in the Firebase
console, then the frontend re-auth prompt that reacts to STEP_UP_REQUIRED. This change is
the backend half - the half that actually enforces.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

FOOTER = 'Rebuild backend, then run the backend test suite.'

PAYLOAD = """
eyJuZXdfZmlsZXMiOiB7ImJhY2tlbmQvYXBwL2NvcmUvc3RlcF91cC5weSI6ICJcIlwiXCJTdGVwLXVwIC8gTUZBIGdhdGUg
Zm9yIHByaXZpbGVnZWQgcm9sZXMgLSBhIHB1cmUgZGVjaXNpb24sIHRlc3RlZCBpbiBpc29sYXRpb24uXG5cbkZpcmViYXNl
IEF1dGggaXMgdGhlIGlkZW50aXR5IHByb3ZpZGVyIChsb2NrZWQpLiBJdCBhbHJlYWR5IG1pbnRzIGV2ZXJ5dGhpbmcgbmVl
ZGVkOlxuICAqIGBgZmlyZWJhc2Uuc2lnbl9pbl9zZWNvbmRfZmFjdG9yYGAgLSBwcmVzZW50IHdoZW4gdGhlIHVzZXIgcGFz
c2VkIGEgc2Vjb25kIGZhY3RvclxuICAgIChUT1RQIGF1dGhlbnRpY2F0b3IgLyBTTVMpIGR1cmluZyB0aGlzIHNpZ24taW4u
XG4gICogYGBlbWFpbF92ZXJpZmllZGBgIC0gdGhlIHZlcmlmaWVkLWVtYWlsIGNsYWltLlxuICAqIGBgYXV0aF90aW1lYGAg
LSBlcG9jaCBzZWNvbmRzIG9mIHRoZSBsYXN0IGFjdHVhbCBhdXRoZW50aWNhdGlvbiwgd2hpY2ggaXMgaG93XG4gICAgXCJ0
aGUgc2Vzc2lvbiBpcyAzMCBtaW51dGVzIG9sZCwgcmUtYXV0aGVudGljYXRlXCIgaXMgbWVhc3VyZWQgd2l0aG91dCBhbnkg
c2VydmVyLXNpZGVcbiAgICBzZXNzaW9uIHN0b3JlLlxuXG5UaGlzIG1vZHVsZSBkZWNpZGVzLCBmcm9tIHRob3NlIGNsYWlt
cyBwbHVzIHRoZSBhZG1pbi1jb25maWd1cmVkIHNldHRpbmdzLCB3aGV0aGVyIGFcbnByaXZpbGVnZWQgY2FsbGVyIG11c3Qg
YmUgc3RvcHBlZCBhbmQgdG9sZCB0byByZS1hdXRoZW50aWNhdGUuIEl0IGlzIGRlbGliZXJhdGVseSBwdXJlOlxubm8gREIs
IG5vIHJlcXVlc3QsIG5vIEZpcmViYXNlIC0gc28gZXZlcnkgcnVsZSBpcyB1bml0LXRlc3RlZCBleGhhdXN0aXZlbHksIGFu
ZCB0aGVcbmVuZm9yY2VtZW50IGRlcGVuZGVuY3kgaW4gZGVwcy5weSBpcyBhIHRoaW4gd3JhcHBlciB0aGF0IG9ubHkgZmV0
Y2hlcyBjbGFpbXMgKyBzZXR0aW5nc1xuYW5kIHJhaXNlcy4gVGhlIGdhdGUgYXBwbGllcyBPTkxZIHRvIGFkbWluIC8gc3Vw
ZXJfYWRtaW47IG9yZGluYXJ5IHVzZXJzIGFyZSBuZXZlclxuYWZmZWN0ZWQsIGFuZCBldmVyeSBydWxlIGlzIGJlaGluZCBh
IHNldHRpbmcgdGhhdCBkZWZhdWx0cyBPRkYgc28gZW5hYmxpbmcgTUZBIGluIHRoZVxuRmlyZWJhc2UgY29uc29sZSBhbmQg
ZW5mb3JjaW5nIGl0IGhlcmUgYXJlIHR3byBkZWxpYmVyYXRlLCBvcmRlcmVkIHN0ZXBzIC0gbm9ib2R5IGNhblxubG9jayB0
aGVtc2VsdmVzIG91dCBiZWZvcmUgZW5yb2xsaW5nLlxuXCJcIlwiXG5cbmZyb20gX19mdXR1cmVfXyBpbXBvcnQgYW5ub3Rh
dGlvbnNcblxuZnJvbSBkYXRhY2xhc3NlcyBpbXBvcnQgZGF0YWNsYXNzXG5cblBSSVZJTEVHRURfUk9MRVMgPSBmcm96ZW5z
ZXQoe1wiYWRtaW5cIiwgXCJzdXBlcl9hZG1pblwifSlcblxuIyBNYWNoaW5lIGNvZGVzIHRoZSBmcm9udGVuZCBzd2l0Y2hl
cyBvbjogRU1BSUxfVU5WRVJJRklFRCAtPiBzaG93IFwidmVyaWZ5IHlvdXIgZW1haWxcIjtcbiMgTUZBX1JFUVVJUkVEIC0+
IHNlbmQgdGhlIHVzZXIgdG8gZW5yb2xsIGEgc2Vjb25kIGZhY3RvcjsgU1RFUF9VUF9SRVFVSVJFRCAtPiByZS1wcm9tcHRc
biMgZm9yIHRoZSBhdXRoZW50aWNhdG9yIGNvZGUgKHRoZSBzZXNzaW9uIGhhcyBhZ2VkIHBhc3QgdGhlIHdpbmRvdykuXG5F
TUFJTF9VTlZFUklGSUVEID0gXCJFTUFJTF9VTlZFUklGSUVEXCJcbk1GQV9SRVFVSVJFRCA9IFwiTUZBX1JFUVVJUkVEXCJc
blNURVBfVVBfUkVRVUlSRUQgPSBcIlNURVBfVVBfUkVRVUlSRURcIlxuXG5cbkBkYXRhY2xhc3MoZnJvemVuPVRydWUpXG5j
bGFzcyBBdXRoQ2xhaW1zOlxuICAgIFwiXCJcIlRoZSBzdWJzZXQgb2YgRmlyZWJhc2UgSUQtdG9rZW4gY2xhaW1zIHRoZSBn
YXRlIHJlYWRzLiBFdmVyeSBmaWVsZCBpcyBvcHRpb25hbCBhbmRcbiAgICBzYWZlbHkgZGVmYXVsdGVkLCBiZWNhdXNlIGEg
bW9ja2VkIG9yIG9sZGVyIHRva2VuIG1heSBjYXJyeSBub25lIG9mIHRoZW0uXCJcIlwiXG5cbiAgICBzZWNvbmRfZmFjdG9y
OiBib29sID0gRmFsc2VcbiAgICBlbWFpbF92ZXJpZmllZDogYm9vbCA9IEZhbHNlXG4gICAgYXV0aF90aW1lOiBpbnQgfCBO
b25lID0gTm9uZSAgIyBlcG9jaCBzZWNvbmRzXG5cblxuZGVmIGV2YWx1YXRlX2FkbWluX2dhdGUoXG4gICAgKixcbiAgICBy
b2xlczogbGlzdFtzdHJdLFxuICAgIGNsYWltczogQXV0aENsYWltcyxcbiAgICByZXF1aXJlX21mYTogYm9vbCxcbiAgICBy
ZXF1aXJlX2VtYWlsX3ZlcmlmaWVkOiBib29sLFxuICAgIHN0ZXBfdXBfbWludXRlczogaW50LFxuICAgIG5vd19lcG9jaDog
aW50LFxuKSAtPiBzdHIgfCBOb25lOlxuICAgIFwiXCJcIlJldHVybiBhIHJlZnVzYWwgY29kZSBpZiB0aGlzIHByaXZpbGVn
ZWQgY2FsbGVyIG11c3QgcmUtYXV0aGVudGljYXRlLCBlbHNlIE5vbmUuXG5cbiAgICBPcmRlciBtYXR0ZXJzOiBlbWFpbC12
ZXJpZmljYXRpb24gaXMgdGhlIGNoZWFwZXN0IGZpeCwgdGhlbiBNRkEgZW5yb2xtZW50LCB0aGVuIHRoZVxuICAgIHRpbWUt
Ym94ZWQgc3RlcC11cC4gQSBub24tcHJpdmlsZWdlZCBjYWxsZXIgaXMgbmV2ZXIgZ2F0ZWQuXG4gICAgXCJcIlwiXG4gICAg
aWYgUFJJVklMRUdFRF9ST0xFUy5pc2Rpc2pvaW50KHJvbGVzKTpcbiAgICAgICAgcmV0dXJuIE5vbmVcbiAgICBpZiByZXF1
aXJlX2VtYWlsX3ZlcmlmaWVkIGFuZCBub3QgY2xhaW1zLmVtYWlsX3ZlcmlmaWVkOlxuICAgICAgICByZXR1cm4gRU1BSUxf
VU5WRVJJRklFRFxuICAgIGlmIHJlcXVpcmVfbWZhIGFuZCBub3QgY2xhaW1zLnNlY29uZF9mYWN0b3I6XG4gICAgICAgIHJl
dHVybiBNRkFfUkVRVUlSRURcbiAgICAjIFN0ZXAtdXA6IG9ubHkgbWVhbmluZ2Z1bCBvbmNlIE1GQSBpcyBhY3R1YWxseSBp
biB1c2UgKGEgc2Vjb25kIGZhY3RvciB3YXMgcHJlc2VudGVkKS5cbiAgICAjIFdpdGhvdXQgTUZBIHRoZXJlIGlzIG5vIHNl
Y29uZCBmYWN0b3IgdG8gcmUtY2hhbGxlbmdlLCBzbyB0aGUgd2luZG93IGRvZXMgbm90IGFwcGx5LlxuICAgIGlmIHN0ZXBf
dXBfbWludXRlcyA+IDAgYW5kIGNsYWltcy5zZWNvbmRfZmFjdG9yIGFuZCBjbGFpbXMuYXV0aF90aW1lIGlzIG5vdCBOb25l
OlxuICAgICAgICBhZ2VfbWludXRlcyA9IChub3dfZXBvY2ggLSBjbGFpbXMuYXV0aF90aW1lKSAvIDYwXG4gICAgICAgIGlm
IGFnZV9taW51dGVzID4gc3RlcF91cF9taW51dGVzOlxuICAgICAgICAgICAgcmV0dXJuIFNURVBfVVBfUkVRVUlSRURcbiAg
ICByZXR1cm4gTm9uZVxuIiwgImJhY2tlbmQvdGVzdHMvdGVzdF9zdGVwX3VwLnB5IjogIlwiXCJcIlRoZSBhZG1pbiBzdGVw
LXVwIC8gTUZBIGdhdGUgLSBwdXJlIGRlY2lzaW9ucywgb25lIHRlc3QgcGVyIGJvdW5kYXJ5LlxuXG5FYWNoIG9mIHRoZXNl
IGlzIGEgc2VjdXJpdHkgY29udHJvbDsgYSB0ZXN0IHRoYXQgZmFpbHMgbG91ZGx5IHRoZSBkYXkgaXQgaXMgbG9vc2VuZWQg
aXNcbnRoZSBwb2ludC4gVGhlIGdhdGUgaXMgb2ZmIGJ5IGRlZmF1bHQgKGFsbCB0aHJlZSBzZXR0aW5ncyksIHNvIHRoZXNl
IHBhc3MgdGhlIGV4YWN0IGZsYWdzXG5hIGNvbmZpZ3VyZWQgZGVwbG95bWVudCB3b3VsZC5cblwiXCJcIlxuXG5mcm9tIF9f
ZnV0dXJlX18gaW1wb3J0IGFubm90YXRpb25zXG5cbmZyb20gYXBwLmNvcmUuc3RlcF91cCBpbXBvcnQgKFxuICAgIEVNQUlM
X1VOVkVSSUZJRUQsXG4gICAgTUZBX1JFUVVJUkVELFxuICAgIFNURVBfVVBfUkVRVUlSRUQsXG4gICAgQXV0aENsYWltcyxc
biAgICBldmFsdWF0ZV9hZG1pbl9nYXRlLFxuKVxuXG5OT1cgPSAxXzAwMF8wMDAgICMgZml4ZWQgZXBvY2g7IG5vIGNsb2Nr
IGluIHRlc3RzXG5cblxuZGVmIF9nYXRlKHJvbGVzLCBjbGFpbXMsICosIG1mYT1UcnVlLCBlbWFpbD1UcnVlLCBtaW51dGVz
PTMwKTpcbiAgICByZXR1cm4gZXZhbHVhdGVfYWRtaW5fZ2F0ZShcbiAgICAgICAgcm9sZXM9cm9sZXMsIGNsYWltcz1jbGFp
bXMsIHJlcXVpcmVfbWZhPW1mYSxcbiAgICAgICAgcmVxdWlyZV9lbWFpbF92ZXJpZmllZD1lbWFpbCwgc3RlcF91cF9taW51
dGVzPW1pbnV0ZXMsIG5vd19lcG9jaD1OT1csXG4gICAgKVxuXG5cbmRlZiB0ZXN0X29yZGluYXJ5X3VzZXJzX2FyZV9uZXZl
cl9nYXRlZCgpIC0+IE5vbmU6XG4gICAgIyBFdmVuIHdpdGggZXZlcnkgc3dpdGNoIG9uIGFuZCBhbiBlbXB0eSB0b2tlbiwg
YSB2aWV3ZXIgc2FpbHMgdGhyb3VnaC5cbiAgICBhc3NlcnQgX2dhdGUoW1widmlld2VyXCJdLCBBdXRoQ2xhaW1zKCkpIGlz
IE5vbmVcblxuXG5kZWYgdGVzdF9hZG1pbl93aXRob3V0X3ZlcmlmaWVkX2VtYWlsX2lzX2Jsb2NrZWQoKSAtPiBOb25lOlxu
ICAgIGFzc2VydCBfZ2F0ZShbXCJhZG1pblwiXSwgQXV0aENsYWltcyhzZWNvbmRfZmFjdG9yPVRydWUsIGVtYWlsX3Zlcmlm
aWVkPUZhbHNlKSkgPT0gRU1BSUxfVU5WRVJJRklFRFxuXG5cbmRlZiB0ZXN0X2FkbWluX3dpdGhvdXRfc2Vjb25kX2ZhY3Rv
cl9pc19ibG9ja2VkKCkgLT4gTm9uZTpcbiAgICBhc3NlcnQgX2dhdGUoW1wiYWRtaW5cIl0sIEF1dGhDbGFpbXMoc2Vjb25k
X2ZhY3Rvcj1GYWxzZSwgZW1haWxfdmVyaWZpZWQ9VHJ1ZSkpID09IE1GQV9SRVFVSVJFRFxuXG5cbmRlZiB0ZXN0X3N1cGVy
X2FkbWluX2lzX2dhdGVkX3RvbygpIC0+IE5vbmU6XG4gICAgYXNzZXJ0IF9nYXRlKFtcInN1cGVyX2FkbWluXCJdLCBBdXRo
Q2xhaW1zKGVtYWlsX3ZlcmlmaWVkPVRydWUpKSA9PSBNRkFfUkVRVUlSRURcblxuXG5kZWYgdGVzdF9hX2ZyZXNoX21mYV9z
ZXNzaW9uX3Bhc3NlcygpIC0+IE5vbmU6XG4gICAgY2xhaW1zID0gQXV0aENsYWltcyhzZWNvbmRfZmFjdG9yPVRydWUsIGVt
YWlsX3ZlcmlmaWVkPVRydWUsIGF1dGhfdGltZT1OT1cgLSA2MClcbiAgICBhc3NlcnQgX2dhdGUoW1wiYWRtaW5cIl0sIGNs
YWltcykgaXMgTm9uZVxuXG5cbmRlZiB0ZXN0X2FuX2FnZWRfbWZhX3Nlc3Npb25fbmVlZHNfc3RlcF91cCgpIC0+IE5vbmU6
XG4gICAgY2xhaW1zID0gQXV0aENsYWltcyhzZWNvbmRfZmFjdG9yPVRydWUsIGVtYWlsX3ZlcmlmaWVkPVRydWUsIGF1dGhf
dGltZT1OT1cgLSAzMSAqIDYwKVxuICAgIGFzc2VydCBfZ2F0ZShbXCJhZG1pblwiXSwgY2xhaW1zKSA9PSBTVEVQX1VQX1JF
UVVJUkVEXG5cblxuZGVmIHRlc3RfZXZlcnl0aGluZ19vZmZfaXNfYV9ub19vcCgpIC0+IE5vbmU6XG4gICAgYXNzZXJ0IF9n
YXRlKFtcImFkbWluXCJdLCBBdXRoQ2xhaW1zKCksIG1mYT1GYWxzZSwgZW1haWw9RmFsc2UsIG1pbnV0ZXM9MCkgaXMgTm9u
ZVxuXG5cbmRlZiB0ZXN0X3N0ZXBfdXBfbmVlZHNfbm9fcmVwcm9tcHRfd2l0aG91dF9tZmEoKSAtPiBOb25lOlxuICAgICMg
Tm8gc2Vjb25kIGZhY3RvciBtZWFucyB0aGVyZSBpcyBub3RoaW5nIHRvIHJlLWNoYWxsZW5nZTsgdGhlIHdpbmRvdyBkb2Vz
IG5vdCBhcHBseVxuICAgICMgKE1GQV9SRVFVSVJFRCwgaWYgb24sIGlzIHRoZSByZWxldmFudCBjb250cm9sIGluc3RlYWQg
LSBoZXJlIG1mYSBpcyBvZmYpLlxuICAgIGNsYWltcyA9IEF1dGhDbGFpbXMoc2Vjb25kX2ZhY3Rvcj1GYWxzZSwgZW1haWxf
dmVyaWZpZWQ9VHJ1ZSwgYXV0aF90aW1lPU5PVyAtIDk5OSAqIDYwKVxuICAgIGFzc2VydCBfZ2F0ZShbXCJhZG1pblwiXSwg
Y2xhaW1zLCBtZmE9RmFsc2UsIGVtYWlsPUZhbHNlLCBtaW51dGVzPTMwKSBpcyBOb25lXG4ifSwgImVkaXRzIjogW3sicGF0
aCI6ICJiYWNrZW5kL2FwcC9jb3JlL3NldHRpbmdzX3JlZ2lzdHJ5LnB5IiwgImFuY2hvciI6ICIgICAgICAgIHN0cl9mb3Jt
YXQ9XCJpYW5hX3R6XCIsXG4gICAgKSxcbn0iLCAicmVwbGFjZW1lbnQiOiAiICAgICAgICBzdHJfZm9ybWF0PVwiaWFuYV90
elwiLFxuICAgICksXG4gICAgXCJyZXF1aXJlX2FkbWluX21mYVwiOiBTZXR0aW5nU3BlYyhcbiAgICAgICAga2V5PVwicmVx
dWlyZV9hZG1pbl9tZmFcIixcbiAgICAgICAgdHlwZT1cImJvb2xcIixcbiAgICAgICAgZGVmYXVsdD1GYWxzZSxcbiAgICAg
ICAgbGFiZWw9XCJSZXF1aXJlIE1GQSBmb3IgYWRtaW5zXCIsXG4gICAgICAgIGRlc2NyaXB0aW9uPShcbiAgICAgICAgICAg
IFwiV2hlbiBvbiwgYWRtaW5zIGFuZCBzdXBlciBhZG1pbnMgbXVzdCBoYXZlIHNpZ25lZCBpbiB3aXRoIGEgc2Vjb25kIGZh
Y3RvciBcIlxuICAgICAgICAgICAgXCIoYXV0aGVudGljYXRvci9TTVMpLiBFbmFibGUgVE9UUCBNRkEgaW4gdGhlIEZpcmVi
YXNlIGNvbnNvbGUgRklSU1QsIG9yIGFkbWlucyBcIlxuICAgICAgICAgICAgXCJ3aWxsIGJlIGxvY2tlZCBvdXQgb2YgdGhl
IGFkbWluIHBhbmVsIHVudGlsIHRoZXkgZW5yb2wuXCJcbiAgICAgICAgKSxcbiAgICApLFxuICAgIFwicmVxdWlyZV9lbWFp
bF92ZXJpZmllZFwiOiBTZXR0aW5nU3BlYyhcbiAgICAgICAga2V5PVwicmVxdWlyZV9lbWFpbF92ZXJpZmllZFwiLFxuICAg
ICAgICB0eXBlPVwiYm9vbFwiLFxuICAgICAgICBkZWZhdWx0PUZhbHNlLFxuICAgICAgICBsYWJlbD1cIlJlcXVpcmUgdmVy
aWZpZWQgZW1haWwgZm9yIGFkbWluc1wiLFxuICAgICAgICBkZXNjcmlwdGlvbj1cIldoZW4gb24sIGFkbWlucyBhbmQgc3Vw
ZXIgYWRtaW5zIG11c3QgaGF2ZSBhIHZlcmlmaWVkIGVtYWlsIGFkZHJlc3MuXCIsXG4gICAgKSxcbiAgICBcImFkbWluX3N0
ZXBfdXBfbWludXRlc1wiOiBTZXR0aW5nU3BlYyhcbiAgICAgICAga2V5PVwiYWRtaW5fc3RlcF91cF9taW51dGVzXCIsXG4g
ICAgICAgIHR5cGU9XCJpbnRcIixcbiAgICAgICAgZGVmYXVsdD0zMCxcbiAgICAgICAgbGFiZWw9XCJBZG1pbiBzdGVwLXVw
IHdpbmRvdyAobWludXRlcylcIixcbiAgICAgICAgZGVzY3JpcHRpb249KFxuICAgICAgICAgICAgXCJIb3cgbG9uZyBhbiBN
RkEgc2lnbi1pbiBzdGF5cyBmcmVzaCBiZWZvcmUgYW4gYWRtaW4gbXVzdCByZS1hdXRoZW50aWNhdGUgZm9yIFwiXG4gICAg
ICAgICAgICBcImFkbWluIGFjdGlvbnMuIDAgZGlzYWJsZXMgdGhlIHN0ZXAtdXAgcmUtcHJvbXB0LiBPbmx5IGFwcGxpZXMg
b25jZSBNRkEgaXMgb24uXCJcbiAgICAgICAgKSxcbiAgICAgICAgbWluaW11bT0wLFxuICAgICAgICBtYXhpbXVtPTE0NDAs
XG4gICAgKSxcbn0iLCAibWFya2VyIjogIlwicmVxdWlyZV9hZG1pbl9tZmFcIjogU2V0dGluZ1NwZWMoIn0sIHsicGF0aCI6
ICJiYWNrZW5kL2FwcC9hcGkvZGVwcy5weSIsICJhbmNob3IiOiAiICAgIGZpcmViYXNlX3VpZCA9IGRlY29kZWQuZ2V0KFwi
dWlkXCIpXG4gICAgaWYgbm90IGZpcmViYXNlX3VpZDpcbiAgICAgICAgcmFpc2UgSFRUUEV4Y2VwdGlvbihzdGF0dXMuSFRU
UF80MDFfVU5BVVRIT1JJWkVELCBcIkludmFsaWQgYXV0aGVudGljYXRpb24gdG9rZW5cIilcblxuICAgIGNhY2hlX2tleSA9
IHVzZXJfY29udGV4dF9jYWNoZV9rZXkoZmlyZWJhc2VfdWlkKVxuIiwgInJlcGxhY2VtZW50IjogIiAgICBmaXJlYmFzZV91
aWQgPSBkZWNvZGVkLmdldChcInVpZFwiKVxuICAgIGlmIG5vdCBmaXJlYmFzZV91aWQ6XG4gICAgICAgIHJhaXNlIEhUVFBF
eGNlcHRpb24oc3RhdHVzLkhUVFBfNDAxX1VOQVVUSE9SSVpFRCwgXCJJbnZhbGlkIGF1dGhlbnRpY2F0aW9uIHRva2VuXCIp
XG5cbiAgICAjIFN0YXNoIHRoZSBGaXJlYmFzZSBjbGFpbXMgdGhlIHByaXZpbGVnZWQtYWNjZXNzIGdhdGUgcmVhZHMgKE1G
QSAvIGVtYWlsIC8gc2Vzc2lvblxuICAgICMgYWdlKS4gRGVmYXVsdGVkIGRlZmVuc2l2ZWx5IC0gYW4gb2xkZXIgb3IgbW9j
a2VkIHRva2VuIG1heSBjYXJyeSBub25lIG9mIHRoZW0gLSBhbmRcbiAgICAjIG9ubHkgZXZlciBjb25zdW1lZCBmb3IgYWRt
aW4vc3VwZXJfYWRtaW4sIGJlaGluZCBzZXR0aW5ncyB0aGF0IGRlZmF1bHQgb2ZmLlxuICAgIF9mYiA9IGRlY29kZWQuZ2V0
KFwiZmlyZWJhc2VcIikgb3Ige31cbiAgICByZXF1ZXN0LnN0YXRlLmF1dGhfY2xhaW1zID0ge1xuICAgICAgICBcInNlY29u
ZF9mYWN0b3JcIjogYm9vbChfZmIuZ2V0KFwic2lnbl9pbl9zZWNvbmRfZmFjdG9yXCIpKSxcbiAgICAgICAgXCJlbWFpbF92
ZXJpZmllZFwiOiBib29sKGRlY29kZWQuZ2V0KFwiZW1haWxfdmVyaWZpZWRcIiwgRmFsc2UpKSxcbiAgICAgICAgXCJhdXRo
X3RpbWVcIjogZGVjb2RlZC5nZXQoXCJhdXRoX3RpbWVcIiksXG4gICAgfVxuXG4gICAgY2FjaGVfa2V5ID0gdXNlcl9jb250
ZXh0X2NhY2hlX2tleShmaXJlYmFzZV91aWQpXG4iLCAibWFya2VyIjogInJlcXVlc3Quc3RhdGUuYXV0aF9jbGFpbXMgPSB7
In0sIHsicGF0aCI6ICJiYWNrZW5kL2FwcC9hcGkvZGVwcy5weSIsICJhbmNob3IiOiAiICAgIGFzeW5jIGRlZiBfZGVwZW5k
ZW5jeShjb250ZXh0OiBDdXJyZW50VXNlcikgLT4gVXNlckNvbnRleHQ6XG4gICAgICAgIGlmIGNhcGFiaWxpdHkgbm90IGlu
IGNvbnRleHQuY2FwYWJpbGl0aWVzOlxuICAgICAgICAgICAgcmFpc2UgSFRUUEV4Y2VwdGlvbihzdGF0dXMuSFRUUF80MDNf
Rk9SQklEREVOLCBcIk1pc3NpbmcgcmVxdWlyZWQgY2FwYWJpbGl0eVwiKVxuICAgICAgICByZXR1cm4gY29udGV4dFxuXG4g
ICAgcmV0dXJuIF9kZXBlbmRlbmN5IiwgInJlcGxhY2VtZW50IjogIiAgICBhc3luYyBkZWYgX2RlcGVuZGVuY3koY29udGV4
dDogQ3VycmVudFVzZXIpIC0+IFVzZXJDb250ZXh0OlxuICAgICAgICBpZiBjYXBhYmlsaXR5IG5vdCBpbiBjb250ZXh0LmNh
cGFiaWxpdGllczpcbiAgICAgICAgICAgIHJhaXNlIEhUVFBFeGNlcHRpb24oc3RhdHVzLkhUVFBfNDAzX0ZPUkJJRERFTiwg
XCJNaXNzaW5nIHJlcXVpcmVkIGNhcGFiaWxpdHlcIilcbiAgICAgICAgcmV0dXJuIGNvbnRleHRcblxuICAgIHJldHVybiBf
ZGVwZW5kZW5jeVxuXG5hc3luYyBkZWYgZW5mb3JjZV9hZG1pbl9zdGVwX3VwKFxuICAgIHJlcXVlc3Q6IFJlcXVlc3QsXG4g
ICAgY29udGV4dDogQ3VycmVudFVzZXIsXG4gICAgZGI6IERiU2Vzc2lvbixcbikgLT4gTm9uZTpcbiAgICBcIlwiXCJSb3V0
ZXIgZGVwZW5kZW5jeTogc3RvcCBhIHByaXZpbGVnZWQgY2FsbGVyIHdob3NlIHNpZ24taW4gZG9lcyBub3QgbWVldCB0aGVc
biAgICBjb25maWd1cmVkIE1GQSAvIGVtYWlsLXZlcmlmaWNhdGlvbiAvIHNlc3Npb24tZnJlc2huZXNzIHBvbGljeS5cblxu
ICAgIEV2ZXJ5dGhpbmcgaXMgb2ZmIGJ5IGRlZmF1bHQsIHNvIHRoaXMgaXMgaW5lcnQgdW50aWwgYW4gYWRtaW4gdHVybnMg
aXQgb24gQUZURVJcbiAgICBlbmFibGluZyBUT1RQIE1GQSBpbiB0aGUgRmlyZWJhc2UgY29uc29sZSAtIHRoZSB0d28gc3Rl
cHMgYXJlIGRlbGliZXJhdGVseSBvcmRlcmVkIHNvXG4gICAgbm9ib2R5IGlzIGxvY2tlZCBvdXQgYmVmb3JlIHRoZXkgY2Fu
IGVucm9sLiBUaGUgcmVmdXNhbCBpcyBhIDQwMyB3aG9zZSBkZXRhaWwgaXMgYVxuICAgIG1hY2hpbmUgY29kZSAoTUZBX1JF
UVVJUkVEIC8gRU1BSUxfVU5WRVJJRklFRCAvIFNURVBfVVBfUkVRVUlSRUQpIHRoZSBmcm9udGVuZCBhY3RzIG9uLlxuICAg
IFwiXCJcIlxuICAgIGZyb20gZGF0ZXRpbWUgaW1wb3J0IFVUQywgZGF0ZXRpbWVcblxuICAgIGZyb20gYXBwLmNvcmUuc3Rl
cF91cCBpbXBvcnQgQXV0aENsYWltcywgZXZhbHVhdGVfYWRtaW5fZ2F0ZVxuICAgIGZyb20gYXBwLnNlcnZpY2VzIGltcG9y
dCBzZXR0aW5nc19zZXJ2aWNlXG5cbiAgICByYXcgPSBnZXRhdHRyKHJlcXVlc3Quc3RhdGUsIFwiYXV0aF9jbGFpbXNcIiwg
e30pIG9yIHt9XG4gICAgY2xhaW1zID0gQXV0aENsYWltcyhcbiAgICAgICAgc2Vjb25kX2ZhY3Rvcj1ib29sKHJhdy5nZXQo
XCJzZWNvbmRfZmFjdG9yXCIpKSxcbiAgICAgICAgZW1haWxfdmVyaWZpZWQ9Ym9vbChyYXcuZ2V0KFwiZW1haWxfdmVyaWZp
ZWRcIikpLFxuICAgICAgICBhdXRoX3RpbWU9cmF3LmdldChcImF1dGhfdGltZVwiKSxcbiAgICApXG4gICAgY29kZSA9IGV2
YWx1YXRlX2FkbWluX2dhdGUoXG4gICAgICAgIHJvbGVzPWNvbnRleHQucm9sZXMsXG4gICAgICAgIGNsYWltcz1jbGFpbXMs
XG4gICAgICAgIHJlcXVpcmVfbWZhPWJvb2woYXdhaXQgc2V0dGluZ3Nfc2VydmljZS5nZXRfdmFsdWUoZGIsIFwicmVxdWly
ZV9hZG1pbl9tZmFcIikpLFxuICAgICAgICByZXF1aXJlX2VtYWlsX3ZlcmlmaWVkPWJvb2woYXdhaXQgc2V0dGluZ3Nfc2Vy
dmljZS5nZXRfdmFsdWUoZGIsIFwicmVxdWlyZV9lbWFpbF92ZXJpZmllZFwiKSksXG4gICAgICAgIHN0ZXBfdXBfbWludXRl
cz1pbnQoYXdhaXQgc2V0dGluZ3Nfc2VydmljZS5nZXRfdmFsdWUoZGIsIFwiYWRtaW5fc3RlcF91cF9taW51dGVzXCIpKSxc
biAgICAgICAgbm93X2Vwb2NoPWludChkYXRldGltZS5ub3coVVRDKS50aW1lc3RhbXAoKSksXG4gICAgKVxuICAgIGlmIGNv
ZGUgaXMgbm90IE5vbmU6XG4gICAgICAgIHJhaXNlIEhUVFBFeGNlcHRpb24oc3RhdHVzLkhUVFBfNDAzX0ZPUkJJRERFTiwg
Y29kZSlcbiIsICJtYXJrZXIiOiAiYXN5bmMgZGVmIGVuZm9yY2VfYWRtaW5fc3RlcF91cCgifSwgeyJwYXRoIjogImJhY2tl
bmQvYXBwL2FwaS92MS9hZG1pbi5weSIsICJhbmNob3IiOiAiZnJvbSBhcHAuYXBpLmRlcHMgaW1wb3J0IEN1cnJlbnRVc2Vy
LCBEYlNlc3Npb24sIFJlZGlzQ2xpZW50LCByZXF1aXJlX2NhcGFiaWxpdHkiLCAicmVwbGFjZW1lbnQiOiAiZnJvbSBhcHAu
YXBpLmRlcHMgaW1wb3J0IChcbiAgICBDdXJyZW50VXNlcixcbiAgICBEYlNlc3Npb24sXG4gICAgUmVkaXNDbGllbnQsXG4g
ICAgZW5mb3JjZV9hZG1pbl9zdGVwX3VwLFxuICAgIHJlcXVpcmVfY2FwYWJpbGl0eSxcbikiLCAibWFya2VyIjogImVuZm9y
Y2VfYWRtaW5fc3RlcF91cCwifSwgeyJwYXRoIjogImJhY2tlbmQvYXBwL2FwaS92MS9hZG1pbi5weSIsICJhbmNob3IiOiAi
ICAgIGRlcGVuZGVuY2llcz1bRGVwZW5kcyhlbmZvcmNlX3JhdGVfbGltaXQpLCBEZXBlbmRzKHJlcXVpcmVfY2FwYWJpbGl0
eShcImFkbWluX3BhbmVsXCIpKV0sIiwgInJlcGxhY2VtZW50IjogIiAgICBkZXBlbmRlbmNpZXM9W1xuICAgICAgICBEZXBl
bmRzKGVuZm9yY2VfcmF0ZV9saW1pdCksXG4gICAgICAgIERlcGVuZHMocmVxdWlyZV9jYXBhYmlsaXR5KFwiYWRtaW5fcGFu
ZWxcIikpLFxuICAgICAgICAjIE1GQSAvIGVtYWlsLXZlcmlmaWVkIC8gc2Vzc2lvbi1mcmVzaG5lc3MgcG9saWN5IGZvciBh
ZG1pbnMgKGFsbCBkZWZhdWx0IG9mZikuXG4gICAgICAgIERlcGVuZHMoZW5mb3JjZV9hZG1pbl9zdGVwX3VwKSxcbiAgICBd
LCIsICJtYXJrZXIiOiAiRGVwZW5kcyhlbmZvcmNlX2FkbWluX3N0ZXBfdXApLCJ9XX0=
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
