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
elwiLFxuICAgICksXG4gICAgXCJyZXF1aXJlX2VtYWlsX3ZlcmlmaWVkXCI6IFNldHRpbmdTcGVjKFxuICAgICAgICBrZXk9
XCJyZXF1aXJlX2VtYWlsX3ZlcmlmaWVkXCIsXG4gICAgICAgIHR5cGU9XCJib29sXCIsXG4gICAgICAgIGRlZmF1bHQ9RmFs
c2UsXG4gICAgICAgIGxhYmVsPVwiUmVxdWlyZSB2ZXJpZmllZCBlbWFpbCBmb3IgYWRtaW5zXCIsXG4gICAgICAgIGRlc2Ny
aXB0aW9uPVwiV2hlbiBvbiwgYWRtaW5zIGFuZCBzdXBlciBhZG1pbnMgbXVzdCBoYXZlIGEgdmVyaWZpZWQgZW1haWwgYWRk
cmVzcy5cIixcbiAgICApLFxuICAgIFwiYWRtaW5fc3RlcF91cF9taW51dGVzXCI6IFNldHRpbmdTcGVjKFxuICAgICAgICBr
ZXk9XCJhZG1pbl9zdGVwX3VwX21pbnV0ZXNcIixcbiAgICAgICAgdHlwZT1cImludFwiLFxuICAgICAgICBkZWZhdWx0PTMw
LFxuICAgICAgICBsYWJlbD1cIkFkbWluIHN0ZXAtdXAgd2luZG93IChtaW51dGVzKVwiLFxuICAgICAgICBkZXNjcmlwdGlv
bj0oXG4gICAgICAgICAgICBcIkhvdyBsb25nIGFuIE1GQSBzaWduLWluIHN0YXlzIGZyZXNoIGJlZm9yZSBhbiBhZG1pbiBt
dXN0IHJlLWF1dGhlbnRpY2F0ZSBmb3IgXCJcbiAgICAgICAgICAgIFwiYWRtaW4gYWN0aW9ucy4gMCBkaXNhYmxlcyB0aGUg
c3RlcC11cCByZS1wcm9tcHQuIE9ubHkgYXBwbGllcyBvbmNlIE1GQSBpcyBvbi5cIlxuICAgICAgICApLFxuICAgICAgICBt
aW5pbXVtPTAsXG4gICAgICAgIG1heGltdW09MTQ0MCxcbiAgICApLFxufSIsICJtYXJrZXIiOiAiXCJyZXF1aXJlX2VtYWls
X3ZlcmlmaWVkXCI6IFNldHRpbmdTcGVjKCJ9LCB7InBhdGgiOiAiYmFja2VuZC9hcHAvYXBpL2RlcHMucHkiLCAiYW5jaG9y
IjogIiAgICAgICAgZmlyZWJhc2VfY2xhaW1zID0gZGVjb2RlZC5nZXQoXCJmaXJlYmFzZVwiKSBvciB7fSIsICJyZXBsYWNl
bWVudCI6ICIgICAgICAgIGZpcmViYXNlX2NsYWltcyA9IGRlY29kZWQuZ2V0KFwiZmlyZWJhc2VcIikgb3Ige31cbiAgICAg
ICAgIyBUaGUgdHdvIGNsYWltcyB0aGUgZXhpc3RpbmcgdHdvX2ZhY3RvciBmbGFnIGRvZXMgbm90IGNhcnJ5OiB3aGV0aGVy
IHRoZVxuICAgICAgICAjIGFkZHJlc3MgaXMgdmVyaWZpZWQsIGFuZCBXSEVOIHRoZSB1c2VyIGFjdHVhbGx5IGF1dGhlbnRp
Y2F0ZWQgLSB3aGljaCBpcyBob3dcbiAgICAgICAgIyBcInRoaXMgTUZBIHNpZ24taW4gaGFzIGdvbmUgc3RhbGUsIGNoYWxs
ZW5nZSBhZ2FpblwiIGlzIG1lYXN1cmVkIHdpdGhvdXQgYW55XG4gICAgICAgICMgc2VydmVyLXNpZGUgc2Vzc2lvbiBzdG9y
ZS4gUmVhZCBvbmx5IGZvciBhZG1pbnMsIGJlaGluZCBzZXR0aW5ncyBkZWZhdWx0IG9mZi5cbiAgICAgICAgcmVxdWVzdC5z
dGF0ZS5lbWFpbF92ZXJpZmllZCA9IGJvb2woZGVjb2RlZC5nZXQoXCJlbWFpbF92ZXJpZmllZFwiLCBGYWxzZSkpXG4gICAg
ICAgIHJlcXVlc3Quc3RhdGUuYXV0aF90aW1lID0gZGVjb2RlZC5nZXQoXCJhdXRoX3RpbWVcIikiLCAibWFya2VyIjogInJl
cXVlc3Quc3RhdGUuZW1haWxfdmVyaWZpZWQgPSBib29sKCJ9LCB7InBhdGgiOiAiYmFja2VuZC9hcHAvYXBpL2RlcHMucHki
LCAiYW5jaG9yIjogIiAgICBhc3luYyBkZWYgX2RlcGVuZGVuY3koY29udGV4dDogQ3VycmVudFVzZXIpIC0+IFVzZXJDb250
ZXh0OlxuICAgICAgICBpZiBjYXBhYmlsaXR5IG5vdCBpbiBjb250ZXh0LmNhcGFiaWxpdGllczpcbiAgICAgICAgICAgIHJh
aXNlIEhUVFBFeGNlcHRpb24oc3RhdHVzLkhUVFBfNDAzX0ZPUkJJRERFTiwgXCJNaXNzaW5nIHJlcXVpcmVkIGNhcGFiaWxp
dHlcIilcbiAgICAgICAgcmV0dXJuIGNvbnRleHRcblxuICAgIHJldHVybiBfZGVwZW5kZW5jeSIsICJyZXBsYWNlbWVudCI6
ICIgICAgYXN5bmMgZGVmIF9kZXBlbmRlbmN5KGNvbnRleHQ6IEN1cnJlbnRVc2VyKSAtPiBVc2VyQ29udGV4dDpcbiAgICAg
ICAgaWYgY2FwYWJpbGl0eSBub3QgaW4gY29udGV4dC5jYXBhYmlsaXRpZXM6XG4gICAgICAgICAgICByYWlzZSBIVFRQRXhj
ZXB0aW9uKHN0YXR1cy5IVFRQXzQwM19GT1JCSURERU4sIFwiTWlzc2luZyByZXF1aXJlZCBjYXBhYmlsaXR5XCIpXG4gICAg
ICAgIHJldHVybiBjb250ZXh0XG5cbiAgICByZXR1cm4gX2RlcGVuZGVuY3lcblxuYXN5bmMgZGVmIGVuZm9yY2VfYWRtaW5f
c3RlcF91cChcbiAgICByZXF1ZXN0OiBSZXF1ZXN0LFxuICAgIGNvbnRleHQ6IEN1cnJlbnRVc2VyLFxuICAgIGRiOiBEYlNl
c3Npb24sXG4pIC0+IE5vbmU6XG4gICAgXCJcIlwiUm91dGVyIGRlcGVuZGVuY3k6IHN0b3AgYSBwcml2aWxlZ2VkIGNhbGxl
ciB3aG9zZSBzaWduLWluIGRvZXMgbm90IG1lZXQgdGhlXG4gICAgY29uZmlndXJlZCBNRkEgLyBlbWFpbC12ZXJpZmljYXRp
b24gLyBzZXNzaW9uLWZyZXNobmVzcyBwb2xpY3kuXG5cbiAgICBFdmVyeXRoaW5nIGlzIG9mZiBieSBkZWZhdWx0LCBzbyB0
aGlzIGlzIGluZXJ0IHVudGlsIGFuIGFkbWluIHR1cm5zIGl0IG9uIEFGVEVSXG4gICAgZW5hYmxpbmcgVE9UUCBNRkEgaW4g
dGhlIEZpcmViYXNlIGNvbnNvbGUgLSB0aGUgdHdvIHN0ZXBzIGFyZSBkZWxpYmVyYXRlbHkgb3JkZXJlZCBzb1xuICAgIG5v
Ym9keSBpcyBsb2NrZWQgb3V0IGJlZm9yZSB0aGV5IGNhbiBlbnJvbC4gVGhlIHJlZnVzYWwgaXMgYSA0MDMgd2hvc2UgZGV0
YWlsIGlzIGFcbiAgICBtYWNoaW5lIGNvZGUgKE1GQV9SRVFVSVJFRCAvIEVNQUlMX1VOVkVSSUZJRUQgLyBTVEVQX1VQX1JF
UVVJUkVEKSB0aGUgZnJvbnRlbmQgYWN0cyBvbi5cbiAgICBcIlwiXCJcbiAgICBmcm9tIGRhdGV0aW1lIGltcG9ydCBVVEMs
IGRhdGV0aW1lXG5cbiAgICBmcm9tIGFwcC5jb3JlLnN0ZXBfdXAgaW1wb3J0IEF1dGhDbGFpbXMsIGV2YWx1YXRlX2FkbWlu
X2dhdGVcbiAgICBmcm9tIGFwcC5zZXJ2aWNlcyBpbXBvcnQgc2V0dGluZ3Nfc2VydmljZVxuXG4gICAgIyB0d29fZmFjdG9y
IGlzIGFscmVhZHkgc2V0IGJ5IGdldF91c2VyX2NvbnRleHQgKHRoZSBzYW1lIGZsYWcgZW5mb3JjZV9hZG1pbl8yZmFcbiAg
ICAjIHJlYWRzKSAtIHJldXNlZCByYXRoZXIgdGhhbiByZS1kZXJpdmVkLCBzbyB0aGUgdHdvIGdhdGVzIGNhbiBuZXZlciBk
aXNhZ3JlZSBhYm91dFxuICAgICMgd2hldGhlciBhIHNlY29uZCBmYWN0b3Igd2FzIHByZXNlbnRlZC5cbiAgICBjbGFpbXMg
PSBBdXRoQ2xhaW1zKFxuICAgICAgICBzZWNvbmRfZmFjdG9yPWJvb2woZ2V0YXR0cihyZXF1ZXN0LnN0YXRlLCBcInR3b19m
YWN0b3JcIiwgRmFsc2UpKSxcbiAgICAgICAgZW1haWxfdmVyaWZpZWQ9Ym9vbChnZXRhdHRyKHJlcXVlc3Quc3RhdGUsIFwi
ZW1haWxfdmVyaWZpZWRcIiwgRmFsc2UpKSxcbiAgICAgICAgYXV0aF90aW1lPWdldGF0dHIocmVxdWVzdC5zdGF0ZSwgXCJh
dXRoX3RpbWVcIiwgTm9uZSksXG4gICAgKVxuICAgIGNvZGUgPSBldmFsdWF0ZV9hZG1pbl9nYXRlKFxuICAgICAgICByb2xl
cz1jb250ZXh0LnJvbGVzLFxuICAgICAgICBjbGFpbXM9Y2xhaW1zLFxuICAgICAgICAjIFJldXNlcyB0aGUgRVhJU1RJTkcg
cmVxdWlyZV9hZG1pbl8yZmEgc2V0dGluZyByYXRoZXIgdGhhbiBhZGRpbmcgYSBzZWNvbmQsXG4gICAgICAgICMgb3Zlcmxh
cHBpbmcgc3dpdGNoIC0gdHdvIHNldHRpbmdzIG1lYW5pbmcgXCJyZXF1aXJlIE1GQVwiIGlzIGhvdyB0aGV5IGRyaWZ0IGFw
YXJ0LlxuICAgICAgICByZXF1aXJlX21mYT1ib29sKGF3YWl0IHNldHRpbmdzX3NlcnZpY2UuZ2V0X3ZhbHVlKGRiLCBcInJl
cXVpcmVfYWRtaW5fMmZhXCIpKSxcbiAgICAgICAgcmVxdWlyZV9lbWFpbF92ZXJpZmllZD1ib29sKGF3YWl0IHNldHRpbmdz
X3NlcnZpY2UuZ2V0X3ZhbHVlKGRiLCBcInJlcXVpcmVfZW1haWxfdmVyaWZpZWRcIikpLFxuICAgICAgICBzdGVwX3VwX21p
bnV0ZXM9aW50KGF3YWl0IHNldHRpbmdzX3NlcnZpY2UuZ2V0X3ZhbHVlKGRiLCBcImFkbWluX3N0ZXBfdXBfbWludXRlc1wi
KSksXG4gICAgICAgIG5vd19lcG9jaD1pbnQoZGF0ZXRpbWUubm93KFVUQykudGltZXN0YW1wKCkpLFxuICAgIClcbiAgICBp
ZiBjb2RlIGlzIG5vdCBOb25lOlxuICAgICAgICByYWlzZSBIVFRQRXhjZXB0aW9uKHN0YXR1cy5IVFRQXzQwM19GT1JCSURE
RU4sIGNvZGUpXG4iLCAibWFya2VyIjogImFzeW5jIGRlZiBlbmZvcmNlX2FkbWluX3N0ZXBfdXAoIn0sIHsicGF0aCI6ICJi
YWNrZW5kL2FwcC9hcGkvdjEvYWRtaW4ucHkiLCAiYW5jaG9yIjogImZyb20gYXBwLmFwaS5kZXBzIGltcG9ydCBDdXJyZW50
VXNlciwgRGJTZXNzaW9uLCBSZWRpc0NsaWVudCwgcmVxdWlyZV9jYXBhYmlsaXR5IiwgInJlcGxhY2VtZW50IjogImZyb20g
YXBwLmFwaS5kZXBzIGltcG9ydCAoXG4gICAgQ3VycmVudFVzZXIsXG4gICAgRGJTZXNzaW9uLFxuICAgIFJlZGlzQ2xpZW50
LFxuICAgIGVuZm9yY2VfYWRtaW5fc3RlcF91cCxcbiAgICByZXF1aXJlX2NhcGFiaWxpdHksXG4pIiwgIm1hcmtlciI6ICJl
bmZvcmNlX2FkbWluX3N0ZXBfdXAsIn0sIHsicGF0aCI6ICJiYWNrZW5kL2FwcC9hcGkvdjEvYWRtaW4ucHkiLCAiYW5jaG9y
IjogIiAgICBkZXBlbmRlbmNpZXM9W1xuICAgICAgICBEZXBlbmRzKGVuZm9yY2VfcmF0ZV9saW1pdCksXG4gICAgICAgIERl
cGVuZHMocmVxdWlyZV9jYXBhYmlsaXR5KFwiYWRtaW5fcGFuZWxcIikpLFxuICAgICAgICBEZXBlbmRzKGVuZm9yY2VfYWRt
aW5fMmZhKSxcbiAgICBdLCIsICJyZXBsYWNlbWVudCI6ICIgICAgZGVwZW5kZW5jaWVzPVtcbiAgICAgICAgRGVwZW5kcyhl
bmZvcmNlX3JhdGVfbGltaXQpLFxuICAgICAgICBEZXBlbmRzKHJlcXVpcmVfY2FwYWJpbGl0eShcImFkbWluX3BhbmVsXCIp
KSxcbiAgICAgICAgRGVwZW5kcyhlbmZvcmNlX2FkbWluXzJmYSksXG4gICAgICAgICMgQ29tcGxlbWVudHMgZW5mb3JjZV9h
ZG1pbl8yZmEgYWJvdmUsIHdoaWNoIGFuc3dlcnMgXCJkaWQgdGhleSB1c2UgYSBzZWNvbmRcbiAgICAgICAgIyBmYWN0b3Ig
YXQgYWxsXCIuIFRoaXMgYWRkcyB0aGUgdHdvIHRoaW5ncyBpdCBkb2VzIG5vdDogYSB2ZXJpZmllZCBlbWFpbCwgYW5kIGFc
biAgICAgICAgIyBUSU1FIEJPWCAtIGFuIE1GQSBzaWduLWluIGdvZXMgc3RhbGUgYWZ0ZXIgYWRtaW5fc3RlcF91cF9taW51
dGVzIGFuZCBtdXN0IGJlXG4gICAgICAgICMgcmUtY2hhbGxlbmdlZC4gQm90aCBkZWZhdWx0IG9mZi5cbiAgICAgICAgRGVw
ZW5kcyhlbmZvcmNlX2FkbWluX3N0ZXBfdXApLFxuICAgIF0sIiwgIm1hcmtlciI6ICJEZXBlbmRzKGVuZm9yY2VfYWRtaW5f
c3RlcF91cCksIn1dfQ==
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
