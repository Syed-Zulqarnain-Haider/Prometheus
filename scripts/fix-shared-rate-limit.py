#!/usr/bin/env python3
"""WITHDRAWN: the shared-rate-limit finding does not apply to the deployed code.

I reported a P1 denial of service - that every caller shared one pre-auth rate-limit
bucket, because client_ip() collapses to the proxy address when TRUSTED_PROXY is off.
The evidence chain was sound EXCEPT for its first link: it assumed a pre-auth limiter
keyed on client_ip, which is what my RECONSTRUCTION of the backend contained.

The deployed backend has no such limiter. Its rate_limit.py runs an atomic Lua
check-and-add and every bucket is keyed on the resolved user - rl:{user},
rl:export:{user}, rl:sync:{user}, rl:diag:{user}, rl:chat:{user}. Per-caller isolation
is correct and there is no shared bucket to exhaust. The finding was real about a tree
that is not the one running.

Kept as a record rather than deleted, because a withdrawn finding is itself a finding:
it is how a reconstruction diverging from production produces a confident, wrong answer.
Running this script now changes nothing.

WHAT REMAINS TRUE, unaffected: audit_log recorded the Docker gateway address on every
row because TRUSTED_PROXY defaulted off. It is now true on the server, which is safe
there specifically - nginx sets X-Real-IP from $remote_addr and the app binds 127.0.0.1
only, so nginx is the sole path in.

WHAT IS STILL WORTH CHECKING - not verified, not claimed: every limiter keys on a
resolved user, so they engage only AFTER token verification. Unauthenticated traffic,
each request costing a full RSA signature check, may therefore be unbounded. That is a
DIFFERENT question from the one I raised, and it needs the real file read end to end
before anyone acts on it.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(__doc__.strip())
    print()
    print("Nothing to apply - this finding was withdrawn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
