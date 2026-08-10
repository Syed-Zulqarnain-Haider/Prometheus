/** @type {import('next').NextConfig} */

/** Baseline response headers for every page the Next server returns.
 *
 *  Set here rather than only in nginx so they travel with the app: a rebuilt host, a
 *  second environment or a misapplied nginx snippet can't quietly drop them. nginx should
 *  ALSO set them (see docs/nginx-prometheus.conf) so `/api/` responses are covered - this
 *  block only reaches what Next.js serves.
 *
 *  No `script-src` CSP here on purpose. Next.js emits inline bootstrap scripts, so a
 *  meaningful script policy needs per-request nonces and middleware; a half-written one
 *  would either break the app or read as protection that isn't there. `frame-ancestors`
 *  is safe to set on its own and is the part that actually stops clickjacking.
 */
const securityHeaders = [
  // Clickjacking: an authenticated admin must not be framable into clicking something
  // they can't see. frame-ancestors is the modern rule; X-Frame-Options covers old browsers.
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  { key: "X-Frame-Options", value: "DENY" },
  // Stop MIME sniffing - an export or upload must never be re-interpreted as script.
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Filter state lives in the query string (app names, pods, publishers). Send the origin
  // only when leaving the site, never the full URL.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // The dashboard needs none of these; deny them so injected content can't ask either.
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
  // Two years, subdomains included. No `preload` - that is a public, hard-to-reverse
  // commitment and belongs to whoever owns the domain, not to a config default.
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "X-DNS-Prefetch-Control", value: "off" },
];

const nextConfig = {
  // Emit a self-contained server bundle (.next/standalone) for the production
  // Docker image - see frontend/Dockerfile. No other behavior changes.
  output: "standalone",
  // Don't advertise the framework version to scanners.
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
