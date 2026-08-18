#!/usr/bin/env python3
"""Close the web-header findings from the UpGuard external scan (Aug 18, 2026).

The scan covers ALL of terafort.com. These are the findings that are actually fixable
in THIS repository - everything else in that report is DNS, registrar, firewall or
server-patching work and is written up in docs/SECURITY-REMEDIATION.md instead.

Already correct before this patch, worth stating so nobody "fixes" it twice: the
FastAPI backend stamps X-Content-Type-Options, X-Frame-Options: DENY, Referrer-Policy,
a locked CSP, COOP/CORP, Permissions-Policy and HSTS on every response
(app/core/security_headers.py), and the app sets NO cookies anywhere - so the scan's
"Secure cookies not used" finding (1 asset) is a different terafort.com property, not
this dashboard. The gap was the FRONTEND: Next.js served the dashboard's HTML with no
security headers at all, and advertised itself in X-Powered-By.

  frontend/next.config.mjs
      * poweredByHeader: false  -> removes "X-Powered-By: Next.js"
        (scan finding: "X-Powered-By header exposed", 2 assets)
      * headers() -> X-Frame-Options: DENY, X-Content-Type-Options, Referrer-Policy,
        Permissions-Policy on every page response
        (scan finding: "X-Frame-Options is not deny or sameorigin", 5 assets)
      * CSP in TWO parts, deliberately:
          - ENFORCED: only directives that cannot break a working dashboard -
            frame-ancestors, object-src, base-uri, form-action. Clickjacking and
            base-tag injection are closed today, with no risk of a white screen.
          - REPORT-ONLY: the full policy including script-src/connect-src. Browsers
            report violations to the console without blocking, so the remaining
            origins (Firebase auth, Google Fonts) can be confirmed against the REAL
            app before it is enforced. Shipping a full CSP blind is how a login page
            goes dark at 9am; the report-only pass is one browser console away from
            being safe to promote, and docs/SECURITY-REMEDIATION.md says how.

  docs/nginx-prometheus.conf
      Rewritten with the TLS server block the scan wants and the deployment already
      needs: HTTP->HTTPS redirect, HSTS with includeSubDomains + preload, TLS 1.2/1.3
      only with the weak 1.2 suites removed, server_tokens off, and
      proxy_hide_header for the upstream Server/X-Powered-By.
      (scan findings: HSTS not enforced (7 assets), HTTP does not redirect to HTTPS,
      HTTPS redirect not supported, weak TLS 1.2 cipher suites (5 assets), Server
      information header exposed (4 assets), and it also suppresses the version string
      the "EOL NGINX"/"NGINX x.y has vulnerabilities" checks read - though PATCHING
      nginx is the real fix for those and is in the remediation doc.)

Anchored on next.config.mjs; the nginx file is replaced wholesale (it is a template
that ships in docs/, not live config - the server's own copy under
/etc/nginx/sites-available is edited by hand, which the doc explains). Idempotent.
Frontend rebuild; no migration. Nginx changes require the owner to apply them on the
host and run `nginx -t` before reloading.
"""

from __future__ import annotations

import sys
from pathlib import Path

CONFIG = Path("frontend/next.config.mjs")
NGINX = Path("docs/nginx-prometheus.conf")

CONFIG_ANCHOR = '  output: "standalone",\n'
CONFIG_ADD = '''
  // Removes "X-Powered-By: Next.js" - a free version disclosure that the external
  // scan flags and that nothing needs.
  poweredByHeader: false,

  async headers() {
    // Enforced CSP: ONLY directives that cannot break a working dashboard. These
    // close clickjacking, plugin embedding, base-tag injection and form exfiltration
    // outright. script-src/connect-src are deliberately absent here - see the
    // report-only policy below.
    const enforcedCsp = [
      "frame-ancestors 'none'",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; ");

    // Report-only: the FULL policy. Browsers log violations without blocking, so the
    // real origin list can be confirmed against the running app (Firebase auth,
    // Google Fonts) before this is promoted to enforcing. Promote by moving this
    // value onto the Content-Security-Policy header - see docs/SECURITY-REMEDIATION.md.
    const reportOnlyCsp = [
      "default-src 'self'",
      // 'unsafe-inline' is required until a nonce is threaded through the Next.js
      // bootstrap scripts; that is the last step before enforcing.
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      "font-src 'self' data: https://fonts.gstatic.com",
      "img-src 'self' data: blob: https:",
      // Firebase Auth token exchange + the app's own API.
      "connect-src 'self' https://*.googleapis.com https://*.firebaseapp.com",
      "frame-ancestors 'none'",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "upgrade-insecure-requests",
    ].join("; ");

    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "geolocation=(), camera=(), microphone=(), interest-cohort=()",
          },
          { key: "Content-Security-Policy", value: enforcedCsp },
          { key: "Content-Security-Policy-Report-Only", value: reportOnlyCsp },
        ],
      },
    ];
  },
'''

NGINX_CONTENT = '''# nginx reverse proxy for Prometheus (single domain, both apps behind one host).
#
# Install:
#   sudo cp docs/nginx-prometheus.conf /etc/nginx/sites-available/prometheus
#   sudo ln -s /etc/nginx/sites-available/prometheus /etc/nginx/sites-enabled/
#   sudo rm -f /etc/nginx/sites-enabled/default
#   # edit server_name + certificate paths below, then:
#   sudo nginx -t && sudo systemctl reload nginx
#
# Hardened per the UpGuard external scan (Aug 18, 2026). See
# docs/SECURITY-REMEDIATION.md for the findings this file addresses and the ones that
# can only be fixed at the DNS registrar, the firewall, or by patching the host.

# WebSocket upgrade helper (valid here because sites-enabled/* is included inside the
# http{} block). If nginx reports "duplicate map", your base config already defines
# this - delete the next 4 lines.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# Do not advertise the nginx version. The external scan reads the version out of the
# Server header to flag "EOL NGINX" and version-specific CVEs; hiding it removes the
# free reconnaissance, but PATCHING nginx is the actual fix for those findings.
server_tokens off;

# ── HTTP: redirect everything to HTTPS ────────────────────────────────────────
# Scan findings: "HTTP does not redirect to HTTPS", "HTTPS redirect not supported".
# The ACME location stays on HTTP so certbot renewals keep working.
server {
    listen 80;
    listen [::]:80;
    server_name your-domain.example;   # <-- replace with your domain

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# ── HTTPS ─────────────────────────────────────────────────────────────────────
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name your-domain.example;   # <-- replace with your domain

    # certbot writes these paths when you run `sudo certbot --nginx`.
    ssl_certificate     /etc/letsencrypt/live/your-domain.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.example/privkey.pem;

    # TLS 1.2 + 1.3 only. The suite list drops everything the scan flags as weak in
    # 1.2 (NULL, RC4, DES/3DES, IDEA) and keeps forward-secret AEAD suites only.
    # TLS 1.3's own suites are fixed by the protocol and always safe.
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;   # let modern clients pick; the list is already safe
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;

    # HSTS. Scan finding: "HSTS not enforced" (7 assets) + "Domain was not found on
    # the HSTS preload list".
    # WARNING before adding `preload`: preloading is effectively PERMANENT (removal
    # takes months to reach browsers) and includeSubDomains means EVERY subdomain of
    # terafort.com must serve valid HTTPS - a subdomain still on plain HTTP becomes
    # unreachable. Verify every subdomain first, then submit at hstspreload.org.
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    # Allow report/export payloads (the API caps inputs separately).
    client_max_body_size 10m;

    # ── API -> FastAPI on loopback ────────────────────────────────────────────
    # No trailing slash on proxy_pass so the FULL /api/v1/... path is preserved
    # (the backend serves under /api/v1). The X-Forwarded-* headers let the app see
    # the real client IP/proto behind the proxy.
    #
    # The backend already stamps its own security headers on every response
    # (app/core/security_headers.py), so nothing is added here - a second copy would
    # only produce duplicate headers.
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_hide_header X-Powered-By;
    }

    # ── Everything else -> Next.js on loopback ────────────────────────────────
    # WebSocket upgrade headers support HMR and any future streaming responses.
    # Next.js sets its own security headers (see frontend/next.config.mjs); this
    # block only strips anything the upstream might still advertise about itself.
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        $connection_upgrade;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_hide_header X-Powered-By;
    }
}
'''


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    for path in (CONFIG, NGINX):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    config = CONFIG.read_text()

    wrote = False
    if "poweredByHeader" in config:
        print(f"{CONFIG}: already hardened")
    else:
        if config.count(CONFIG_ANCHOR) != 1:
            die(f"{CONFIG}: expected exactly one {CONFIG_ANCHOR.strip()!r}")
        CONFIG.write_text(config.replace(CONFIG_ANCHOR, CONFIG_ANCHOR + CONFIG_ADD, 1))
        print(f"patched {CONFIG}: no X-Powered-By, security headers, CSP")
        wrote = True

    if NGINX.read_text() == NGINX_CONTENT:
        print(f"{NGINX}: already hardened")
    else:
        NGINX.write_text(NGINX_CONTENT)
        print(f"rewrote {NGINX}: TLS block, HSTS, modern ciphers, server_tokens off")
        wrote = True

    if not wrote:
        print("already hardened - nothing to do")
        return

    print("\nFrontend rebuild applies the header changes.")
    print("The nginx file is a TEMPLATE - apply it on the host by hand, then:")
    print("  sudo nginx -t && sudo systemctl reload nginx")


if __name__ == "__main__":
    main()
