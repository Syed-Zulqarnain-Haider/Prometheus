"use client";

import { useEffect } from "react";

/* Registers the service worker, which is what makes the app installable to a home
 * screen and what keeps it from showing the browser's offline error.
 *
 * Registration is deferred to the load event: a service worker registering during the
 * initial page load competes with the app's own requests for bandwidth on exactly the
 * connection where that hurts most. Renders nothing. */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    // Service workers require a secure context; over plain HTTP (a LAN IP during
    // development) the API exists but registration always rejects, so skip it rather
    // than log a failure every load. localhost counts as secure by definition.
    if (!window.isSecureContext) return;

    const register = () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        /* Installability is an enhancement - the dashboard works fully without it. */
      });
    };

    if (document.readyState === "complete") {
      register();
      return;
    }
    window.addEventListener("load", register);
    return () => window.removeEventListener("load", register);
  }, []);

  return null;
}
