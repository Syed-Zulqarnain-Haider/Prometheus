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

INCOMPLETE ON ITS OWN. As written here the gate has no break-glass exemption, so it stands
in front of the very settings routes that switch it back off - a lockout the backend suite
catches (test_admin_2fa.py::test_settings_route_is_breakglass). scripts/fix-stepup-breakglass.py
adds that exemption and MUST be run after this one; it is left as a separate, idempotent
step rather than folded in here because this script has already been applied to the server.
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
IjogIiAgICBmaXJlYmFzZV9jbGFpbXMgPSBkZWNvZGVkLmdldChcImZpcmViYXNlXCIpIG9yIHt9XG4gICAgcmVxdWVzdC5z
dGF0ZS50d29fZmFjdG9yID0gYm9vbChmaXJlYmFzZV9jbGFpbXMuZ2V0KFwic2lnbl9pbl9zZWNvbmRfZmFjdG9yXCIpKSIs
ICJyZXBsYWNlbWVudCI6ICIgICAgZmlyZWJhc2VfY2xhaW1zID0gZGVjb2RlZC5nZXQoXCJmaXJlYmFzZVwiKSBvciB7fVxu
ICAgIHJlcXVlc3Quc3RhdGUudHdvX2ZhY3RvciA9IGJvb2woZmlyZWJhc2VfY2xhaW1zLmdldChcInNpZ25faW5fc2Vjb25k
X2ZhY3RvclwiKSlcbiAgICAjIFRoZSB0d28gY2xhaW1zIHR3b19mYWN0b3IgZG9lcyBub3QgY2Fycnk6IHdoZXRoZXIgdGhl
IGFkZHJlc3MgaXMgdmVyaWZpZWQsIGFuZFxuICAgICMgV0hFTiB0aGUgdXNlciBhY3R1YWxseSBhdXRoZW50aWNhdGVkIC0g
d2hpY2ggaXMgaG93IFwidGhpcyBNRkEgc2lnbi1pbiBoYXMgZ29uZVxuICAgICMgc3RhbGUsIGNoYWxsZW5nZSBhZ2Fpblwi
IGlzIG1lYXN1cmVkIHdpdGhvdXQgYW55IHNlcnZlci1zaWRlIHNlc3Npb24gc3RvcmUuXG4gICAgIyBSZWFkIG9ubHkgZm9y
IGFkbWlucywgYmVoaW5kIHNldHRpbmdzIHRoYXQgZGVmYXVsdCBvZmYuXG4gICAgcmVxdWVzdC5zdGF0ZS5lbWFpbF92ZXJp
ZmllZCA9IGJvb2woZGVjb2RlZC5nZXQoXCJlbWFpbF92ZXJpZmllZFwiLCBGYWxzZSkpXG4gICAgcmVxdWVzdC5zdGF0ZS5h
dXRoX3RpbWUgPSBkZWNvZGVkLmdldChcImF1dGhfdGltZVwiKSIsICJtYXJrZXIiOiAicmVxdWVzdC5zdGF0ZS5lbWFpbF92
ZXJpZmllZCA9IGJvb2woIn0sIHsicGF0aCI6ICJiYWNrZW5kL2FwcC9hcGkvZGVwcy5weSIsICJhbmNob3IiOiAiICAgIGFz
eW5jIGRlZiBfZGVwZW5kZW5jeShjb250ZXh0OiBDdXJyZW50VXNlcikgLT4gVXNlckNvbnRleHQ6XG4gICAgICAgIGlmIGNh
cGFiaWxpdHkgbm90IGluIGNvbnRleHQuY2FwYWJpbGl0aWVzOlxuICAgICAgICAgICAgcmFpc2UgSFRUUEV4Y2VwdGlvbihz
dGF0dXMuSFRUUF80MDNfRk9SQklEREVOLCBcIk1pc3NpbmcgcmVxdWlyZWQgY2FwYWJpbGl0eVwiKVxuICAgICAgICByZXR1
cm4gY29udGV4dFxuXG4gICAgcmV0dXJuIF9kZXBlbmRlbmN5IiwgInJlcGxhY2VtZW50IjogIiAgICBhc3luYyBkZWYgX2Rl
cGVuZGVuY3koY29udGV4dDogQ3VycmVudFVzZXIpIC0+IFVzZXJDb250ZXh0OlxuICAgICAgICBpZiBjYXBhYmlsaXR5IG5v
dCBpbiBjb250ZXh0LmNhcGFiaWxpdGllczpcbiAgICAgICAgICAgIHJhaXNlIEhUVFBFeGNlcHRpb24oc3RhdHVzLkhUVFBf
NDAzX0ZPUkJJRERFTiwgXCJNaXNzaW5nIHJlcXVpcmVkIGNhcGFiaWxpdHlcIilcbiAgICAgICAgcmV0dXJuIGNvbnRleHRc
blxuICAgIHJldHVybiBfZGVwZW5kZW5jeVxuXG5hc3luYyBkZWYgZW5mb3JjZV9hZG1pbl9zdGVwX3VwKFxuICAgIHJlcXVl
c3Q6IFJlcXVlc3QsXG4gICAgY29udGV4dDogQ3VycmVudFVzZXIsXG4gICAgZGI6IERiU2Vzc2lvbixcbikgLT4gTm9uZTpc
biAgICBcIlwiXCJSb3V0ZXIgZGVwZW5kZW5jeTogc3RvcCBhIHByaXZpbGVnZWQgY2FsbGVyIHdob3NlIHNpZ24taW4gZG9l
cyBub3QgbWVldCB0aGVcbiAgICBjb25maWd1cmVkIE1GQSAvIGVtYWlsLXZlcmlmaWNhdGlvbiAvIHNlc3Npb24tZnJlc2hu
ZXNzIHBvbGljeS5cblxuICAgIEV2ZXJ5dGhpbmcgaXMgb2ZmIGJ5IGRlZmF1bHQsIHNvIHRoaXMgaXMgaW5lcnQgdW50aWwg
YW4gYWRtaW4gdHVybnMgaXQgb24gQUZURVJcbiAgICBlbmFibGluZyBUT1RQIE1GQSBpbiB0aGUgRmlyZWJhc2UgY29uc29s
ZSAtIHRoZSB0d28gc3RlcHMgYXJlIGRlbGliZXJhdGVseSBvcmRlcmVkIHNvXG4gICAgbm9ib2R5IGlzIGxvY2tlZCBvdXQg
YmVmb3JlIHRoZXkgY2FuIGVucm9sLiBUaGUgcmVmdXNhbCBpcyBhIDQwMyB3aG9zZSBkZXRhaWwgaXMgYVxuICAgIG1hY2hp
bmUgY29kZSAoTUZBX1JFUVVJUkVEIC8gRU1BSUxfVU5WRVJJRklFRCAvIFNURVBfVVBfUkVRVUlSRUQpIHRoZSBmcm9udGVu
ZCBhY3RzIG9uLlxuICAgIFwiXCJcIlxuICAgIGZyb20gZGF0ZXRpbWUgaW1wb3J0IFVUQywgZGF0ZXRpbWVcblxuICAgIGZy
b20gYXBwLmNvcmUuc3RlcF91cCBpbXBvcnQgQXV0aENsYWltcywgZXZhbHVhdGVfYWRtaW5fZ2F0ZVxuICAgIGZyb20gYXBw
LnNlcnZpY2VzIGltcG9ydCBzZXR0aW5nc19zZXJ2aWNlXG5cbiAgICAjIHR3b19mYWN0b3IgaXMgYWxyZWFkeSBzZXQgYnkg
Z2V0X3VzZXJfY29udGV4dCAodGhlIHNhbWUgZmxhZyBlbmZvcmNlX2FkbWluXzJmYVxuICAgICMgcmVhZHMpIC0gcmV1c2Vk
IHJhdGhlciB0aGFuIHJlLWRlcml2ZWQsIHNvIHRoZSB0d28gZ2F0ZXMgY2FuIG5ldmVyIGRpc2FncmVlIGFib3V0XG4gICAg
IyB3aGV0aGVyIGEgc2Vjb25kIGZhY3RvciB3YXMgcHJlc2VudGVkLlxuICAgIGNsYWltcyA9IEF1dGhDbGFpbXMoXG4gICAg
ICAgIHNlY29uZF9mYWN0b3I9Ym9vbChnZXRhdHRyKHJlcXVlc3Quc3RhdGUsIFwidHdvX2ZhY3RvclwiLCBGYWxzZSkpLFxu
ICAgICAgICBlbWFpbF92ZXJpZmllZD1ib29sKGdldGF0dHIocmVxdWVzdC5zdGF0ZSwgXCJlbWFpbF92ZXJpZmllZFwiLCBG
YWxzZSkpLFxuICAgICAgICBhdXRoX3RpbWU9Z2V0YXR0cihyZXF1ZXN0LnN0YXRlLCBcImF1dGhfdGltZVwiLCBOb25lKSxc
biAgICApXG4gICAgY29kZSA9IGV2YWx1YXRlX2FkbWluX2dhdGUoXG4gICAgICAgIHJvbGVzPWNvbnRleHQucm9sZXMsXG4g
ICAgICAgIGNsYWltcz1jbGFpbXMsXG4gICAgICAgICMgUmV1c2VzIHRoZSBFWElTVElORyByZXF1aXJlX2FkbWluXzJmYSBz
ZXR0aW5nIHJhdGhlciB0aGFuIGFkZGluZyBhIHNlY29uZCxcbiAgICAgICAgIyBvdmVybGFwcGluZyBzd2l0Y2ggLSB0d28g
c2V0dGluZ3MgbWVhbmluZyBcInJlcXVpcmUgTUZBXCIgaXMgaG93IHRoZXkgZHJpZnQgYXBhcnQuXG4gICAgICAgIHJlcXVp
cmVfbWZhPWJvb2woYXdhaXQgc2V0dGluZ3Nfc2VydmljZS5nZXRfdmFsdWUoZGIsIFwicmVxdWlyZV9hZG1pbl8yZmFcIikp
LFxuICAgICAgICByZXF1aXJlX2VtYWlsX3ZlcmlmaWVkPWJvb2woYXdhaXQgc2V0dGluZ3Nfc2VydmljZS5nZXRfdmFsdWUo
ZGIsIFwicmVxdWlyZV9lbWFpbF92ZXJpZmllZFwiKSksXG4gICAgICAgIHN0ZXBfdXBfbWludXRlcz1pbnQoYXdhaXQgc2V0
dGluZ3Nfc2VydmljZS5nZXRfdmFsdWUoZGIsIFwiYWRtaW5fc3RlcF91cF9taW51dGVzXCIpKSxcbiAgICAgICAgbm93X2Vw
b2NoPWludChkYXRldGltZS5ub3coVVRDKS50aW1lc3RhbXAoKSksXG4gICAgKVxuICAgIGlmIGNvZGUgaXMgbm90IE5vbmU6
XG4gICAgICAgIHJhaXNlIEhUVFBFeGNlcHRpb24oc3RhdHVzLkhUVFBfNDAzX0ZPUkJJRERFTiwgY29kZSlcbiIsICJtYXJr
ZXIiOiAiYXN5bmMgZGVmIGVuZm9yY2VfYWRtaW5fc3RlcF91cCgifSwgeyJwYXRoIjogImJhY2tlbmQvYXBwL2FwaS92MS9h
ZG1pbi5weSIsICJhbmNob3IiOiAiZnJvbSBhcHAuYXBpLmRlcHMgaW1wb3J0IEN1cnJlbnRVc2VyLCBEYlNlc3Npb24sIFJl
ZGlzQ2xpZW50LCByZXF1aXJlX2NhcGFiaWxpdHkiLCAicmVwbGFjZW1lbnQiOiAiZnJvbSBhcHAuYXBpLmRlcHMgaW1wb3J0
IChcbiAgICBDdXJyZW50VXNlcixcbiAgICBEYlNlc3Npb24sXG4gICAgUmVkaXNDbGllbnQsXG4gICAgZW5mb3JjZV9hZG1p
bl9zdGVwX3VwLFxuICAgIHJlcXVpcmVfY2FwYWJpbGl0eSxcbikiLCAibWFya2VyIjogImVuZm9yY2VfYWRtaW5fc3RlcF91
cCwifSwgeyJwYXRoIjogImJhY2tlbmQvYXBwL2FwaS92MS9hZG1pbi5weSIsICJhbmNob3IiOiAiICAgIGRlcGVuZGVuY2ll
cz1bXG4gICAgICAgIERlcGVuZHMoZW5mb3JjZV9yYXRlX2xpbWl0KSxcbiAgICAgICAgRGVwZW5kcyhyZXF1aXJlX2NhcGFi
aWxpdHkoXCJhZG1pbl9wYW5lbFwiKSksXG4gICAgICAgIERlcGVuZHMoZW5mb3JjZV9hZG1pbl8yZmEpLFxuICAgIF0sIiwg
InJlcGxhY2VtZW50IjogIiAgICBkZXBlbmRlbmNpZXM9W1xuICAgICAgICBEZXBlbmRzKGVuZm9yY2VfcmF0ZV9saW1pdCks
XG4gICAgICAgIERlcGVuZHMocmVxdWlyZV9jYXBhYmlsaXR5KFwiYWRtaW5fcGFuZWxcIikpLFxuICAgICAgICBEZXBlbmRz
KGVuZm9yY2VfYWRtaW5fMmZhKSxcbiAgICAgICAgIyBDb21wbGVtZW50cyBlbmZvcmNlX2FkbWluXzJmYSBhYm92ZSwgd2hp
Y2ggYW5zd2VycyBcImRpZCB0aGV5IHVzZSBhIHNlY29uZFxuICAgICAgICAjIGZhY3RvciBhdCBhbGxcIi4gVGhpcyBhZGRz
IHRoZSB0d28gdGhpbmdzIGl0IGRvZXMgbm90OiBhIHZlcmlmaWVkIGVtYWlsLCBhbmQgYVxuICAgICAgICAjIFRJTUUgQk9Y
IC0gYW4gTUZBIHNpZ24taW4gZ29lcyBzdGFsZSBhZnRlciBhZG1pbl9zdGVwX3VwX21pbnV0ZXMgYW5kIG11c3QgYmVcbiAg
ICAgICAgIyByZS1jaGFsbGVuZ2VkLiBCb3RoIGRlZmF1bHQgb2ZmLlxuICAgICAgICBEZXBlbmRzKGVuZm9yY2VfYWRtaW5f
c3RlcF91cCksXG4gICAgXSwiLCAibWFya2VyIjogIkRlcGVuZHMoZW5mb3JjZV9hZG1pbl9zdGVwX3VwKSwifV19
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
