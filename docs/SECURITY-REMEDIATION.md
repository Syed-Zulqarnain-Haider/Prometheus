# External security scan — remediation status

Source: UpGuard vendor report for **terafort.com**, generated 18 Aug 2026. Overall
rating 613/950.

Read the scope first, because it decides who fixes what. That report scans the
**entire terafort.com external footprint** — the mail servers, the DNS zone, the
registrar, the PHP sites, the GitLab instance — not the Prometheus dashboard's source
code. It is a network/infrastructure assessment, not a code audit. Most findings are
therefore not fixable in this repository at all, and a handful are not about this
application in any way.

Nothing here overlaps with the code-level audits already run against this app (RBAC,
SQL injection, XSS, secret handling, cache isolation) — those are tracked separately
and were clean at last pass.

---

## 1. Fixed in this repository

Applied by `scripts/harden-web-headers.py`. Verified against a real response from a
running build.

| Scan finding | Assets | What was done |
|---|---|---|
| X-Powered-By header exposed | 2 | `poweredByHeader: false` in `frontend/next.config.mjs` — Next.js no longer advertises itself. nginx also strips it from upstreams. |
| X-Frame-Options is not deny or sameorigin | 5 | Next.js now sends `X-Frame-Options: DENY` on every page, plus `frame-ancestors 'none'` in CSP. |
| CSP implemented unsafely | 3 | Frontend had **no** CSP. Now enforces the directives that cannot break the app (`frame-ancestors`, `object-src`, `base-uri`, `form-action`) and ships the full policy as **report-only** — see §4 to promote it. |
| Server information header exposed | 4 | `server_tokens off` in the nginx template. |
| HSTS not enforced | 7 | `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` on the TLS block. Read the warning in §3 before preloading. |
| HTTP does not redirect to HTTPS / HTTPS redirect not supported | 1 each | Port-80 block now 301s everything to HTTPS (ACME path excepted so renewals keep working). |
| Weak cipher suites supported in TLS 1.2 | 5 | TLS 1.2/1.3 only, forward-secret AEAD suites only — NULL/RC4/DES/3DES/IDEA all gone. |

**Already correct before this scan, stated so nobody "fixes" it twice:** the FastAPI
backend stamps `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`,
a locked CSP, COOP/CORP, `Permissions-Policy` and HSTS on every response
(`backend/app/core/security_headers.py`).

**"Secure cookies not used" (1 asset) is not this dashboard.** The application sets no
cookies anywhere — auth is a bearer token in the `Authorization` header. That finding
belongs to another terafort.com property.

---

## 2. Requires action on the host — I cannot do these

These need root on the servers or access to the DNS registrar. Ranked by real risk,
not by the scanner's severity label.

### Highest value first

1. **Close FTP, IMAP, POP3, SMTP and SSH to the internet** (Network, 1 critical + 4
   medium). FTP, IMAP and POP3 transmit **credentials in plaintext** — that is the
   single worst item in the whole report. Replace FTP with SFTP, move IMAP/POP3 to
   their TLS ports (993/995) and disable the plaintext ones, and restrict SSH to a
   VPN or an allow-list. These are the mail/file hosts, not the dashboard server.

2. **Patch nginx and OpenSSH** (Vulnerability Management, 1 high). Both nginx 1.18.0
   and 1.24.0 are flagged, and 1.18.0 is past end of life; OpenSSH 8.0 has published
   CVEs. `server_tokens off` (done) only hides the version from scanners — it does
   **not** patch anything. On Ubuntu: `sudo apt update && sudo apt upgrade nginx
   openssh-server`, then verify with `nginx -v`.

3. **Fix the certificate coverage** (Encryption, 1 critical + 1 high). "SSL not
   available" on one asset and "Hostname does not match SSL certificate" on another —
   some host is serving a certificate that does not carry its name, which trains
   people to click through browser warnings. Issue certificates covering every
   hostname actually in use.

4. **DMARC and SPF** (Email, 1 high + 1 low). `p=none` means DMARC is in
   monitor-only mode and blocks nothing; `~all` soft-fails SPF. Anyone can currently
   spoof mail from terafort.com with a reasonable chance of delivery. Move to
   `p=quarantine` for a fortnight, review the reports, then `p=reject`; change SPF
   `~all` to `-all` once you are certain every legitimate sender is listed.

### Lower urgency

5. **DNSSEC** on the two flagged domains — enable at the registrar and the DNS host.
6. **Registrar deletion protection** — set `clientDeleteProhibited` / 
   `serverDeleteProhibited`. Free, one setting, prevents a catastrophic mistake.
7. **CAA records** — pin which CAs may issue for the domain,
   e.g. `terafort.com. IN CAA 0 issue "letsencrypt.org"`.
8. **PHP 8.2.31 / 8.3.31 CVEs** — patch the PHP hosts. Unrelated to this dashboard,
   which runs no PHP.
9. **GitLab detected** (informational) — keep it patched and watch for zero-days.
10. **"Operates in a country with low political freedom"** — a jurisdictional note
    about where the company operates. Nothing to remediate technically.

---

## 3. Before you enable HSTS preload — read this

The nginx template includes `preload` in the HSTS header, but **submitting the domain
to the preload list is a separate, deliberate act**, and it is close to irreversible:
removal takes months to propagate through browser releases.

`includeSubDomains` means **every** subdomain of terafort.com must serve valid HTTPS.
Any subdomain still on plain HTTP becomes unreachable in every modern browser — not
degraded, unreachable. Given this report already found one asset with no SSL and one
with a mismatched certificate, fix §2.3 **first**, inventory every subdomain, confirm
each one works over HTTPS, and only then submit at <https://hstspreload.org>.

If you would rather not take that risk, drop the word `preload` from the header. You
keep the full HSTS protection and lose only the preload-list line item.

---

## 4. Promoting the CSP from report-only to enforced

The full Content-Security-Policy currently ships as `Content-Security-Policy-Report-Only`.
Browsers evaluate it and log violations to the console **without blocking anything**,
so a wrong origin cannot take the dashboard down. Shipping a full CSP blind is how a
login page goes dark at 9am.

To promote it:

1. Open the dashboard in Chrome with DevTools → Console. Sign out and back in, load
   Overview, Apps Explorer, Reports, Admin, and the chat.
2. Collect every `[Report Only] Refused to …` message. Each names the directive and
   the origin it blocked.
3. Add those origins to the matching directive in `frontend/next.config.mjs`.
4. When a full pass produces no violations, move the `reportOnlyCsp` value onto the
   `Content-Security-Policy` header and delete the report-only entry.

The one directive that will need work before enforcing is `script-src`: it still
carries `'unsafe-inline'` because Next.js emits inline bootstrap scripts. Removing it
requires threading a per-request nonce through the app — worth doing, but a separate
change with its own testing, not something to bundle into a header patch.

---

## 5. What this scan does not tell you

An external scan sees only what is reachable from the internet. It cannot see RBAC,
SQL construction, secret handling, audit-log integrity or cache isolation — the things
that actually protect the numbers in this dashboard. Those are covered by the code
audits tracked separately. A clean external rating and a sound application are two
different claims; do not let a better UpGuard score be read as evidence of the second.
