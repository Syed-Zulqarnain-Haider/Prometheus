/* Service worker for the installed app.
 *
 * A service worker is what lets the browser offer "Install app" and what keeps the
 * installed shell from showing the browser's dinosaur when the phone drops signal. It is
 * DELIBERATELY conservative, because this app serves per-user, permission-filtered data
 * on a device that may be shared:
 *
 *   * /api/ is never touched. Every response there is scoped to the caller's RBAC and
 *     may be seconds-fresh; caching it risks showing one user another's numbers, or
 *     yesterday's numbers as today's. Those requests pass straight through.
 *   * Navigations are network-first and are NOT stored. Offline, they fall back to a
 *     static offline page rather than a cached copy of somebody's dashboard.
 *   * Only immutable static assets are cached: /_next/static/* is content-hashed, so a
 *     cached entry can never be stale, and the icons never change within a version.
 *
 * Nothing user-specific is ever written to the cache. Signing out therefore leaves no
 * data behind here to clear.
 */

const VERSION = "prometheus-v2";
const STATIC_CACHE = `static-${VERSION}`;
const OFFLINE_URL = "/offline.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll([OFFLINE_URL, "/icon-192.png"])),
    // NO skipWaiting: the new worker waits until every old tab closes. Taking over
    // immediately and deleting the old cache would strand still-open tabs - their next
    // lazy-loaded chunk is from a build the server no longer has (ChunkLoadError).
    // Waiting means the old cache is only cleaned once nothing can still want it.
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== STATIC_CACHE).map((key) => caches.delete(key))),
      ),
    // No clients.claim() either - pages keep their current worker until reload,
    // consistent with the no-skipWaiting stance above.
  );
});

/** ONLY content-hashed assets - a cached entry is stale-proof by construction.
 * Icons/fonts are deliberately NOT runtime-cached: their URLs never change, so a cached
 * copy would outlive every future redesign with no way to refresh it short of a new
 * worker version. The offline page's needs are covered at install time. */
function isImmutable(url) {
  return url.pathname.startsWith("/_next/static/");
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  // Another origin's response is not ours to cache or reason about.
  if (url.origin !== self.location.origin) return;
  // Authenticated, permission-scoped, and time-sensitive. Never intercept.
  if (url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () => {
        const cache = await caches.open(STATIC_CACHE);
        // No cached dashboards - just an honest "you are offline" page.
        return (await cache.match(OFFLINE_URL)) ?? Response.error();
      }),
    );
    return;
  }

  if (!isImmutable(url)) return;

  event.respondWith(
    caches.open(STATIC_CACHE).then(async (cache) => {
      const hit = await cache.match(request);
      if (hit) return hit;
      const response = await fetch(request);
      // Opaque and error responses are not worth keeping; a cached 404 would survive
      // the deploy that fixes it.
      if (response.ok && response.type === "basic") cache.put(request, response.clone());
      return response;
    }),
  );
});
