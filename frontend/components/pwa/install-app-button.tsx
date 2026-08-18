"use client";

import { Download, Share, SquarePlus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/* The "Install app" button - makes getting Prometheus onto a phone a visible action
 * instead of a hidden browser menu.
 *
 * Three worlds, three behaviours:
 *   * Chromium (Android + desktop): the browser fires `beforeinstallprompt` when the
 *     app qualifies for install. The event is stashed and replayed on click, which
 *     opens the REAL install dialog. This is the only programmatic install that exists.
 *   * iOS Safari: Apple provides no install API at all - the only path is the user's
 *     own Share -> Add to Home Screen. The button opens a two-step instruction card,
 *     because a button that does nothing is worse than no button.
 *   * Already installed (standalone display mode), or a browser that offers neither:
 *     the button renders nothing. It never shows a dead control.
 */

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as { standalone?: boolean }).standalone === true
  );
}

function isIos(): boolean {
  const ua = navigator.userAgent;
  // iPadOS 13+ masquerades as a Mac; the touch-point count gives it away.
  return (
    /iPhone|iPad|iPod/.test(ua) || (ua.includes("Mac") && navigator.maxTouchPoints > 1)
  );
}

export function InstallAppButton() {
  const [mode, setMode] = useState<"hidden" | "chromium" | "ios">("hidden");
  const [showIosHelp, setShowIosHelp] = useState(false);
  const deferred = useRef<BeforeInstallPromptEvent | null>(null);

  useEffect(() => {
    if (isStandalone()) return; // already installed - nothing to offer

    const onPrompt = (event: Event) => {
      event.preventDefault(); // hold the mini-infobar; the button replays it on demand
      deferred.current = event as BeforeInstallPromptEvent;
      setMode("chromium");
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    // Some Chromium builds fire `appinstalled` without a reload following install.
    const onInstalled = () => setMode("hidden");
    window.addEventListener("appinstalled", onInstalled);

    if (isIos()) setMode("ios");

    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (mode === "hidden") return null;

  async function install(): Promise<void> {
    if (mode === "ios") {
      setShowIosHelp((value) => !value);
      return;
    }
    const event = deferred.current;
    if (!event) return;
    deferred.current = null; // a prompt event is single-use
    await event.prompt();
    const { outcome } = await event.userChoice;
    // Declined: the browser will fire beforeinstallprompt again on a later visit and
    // the button re-arms itself; until then it hides rather than sitting dead.
    if (outcome !== "accepted") setMode("hidden");
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => void install()}
        className="flex h-9 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <Download className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Install app</span>
      </button>

      {showIosHelp && (
        <div className="absolute right-0 top-full z-50 mt-2 w-64 rounded-[var(--radius-inner)] border bg-card p-3 text-left shadow-lg">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs font-semibold">Install on iPhone / iPad</p>
            <button
              type="button"
              aria-label="Close"
              onClick={() => setShowIosHelp(false)}
              className="rounded p-0.5 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          {/* Safari offers no install API, so the honest thing is to show the two taps. */}
          <ol className="mt-2 space-y-2 text-xs text-muted-foreground">
            <li className="flex items-center gap-2">
              <Share className="h-4 w-4 shrink-0 text-foreground" />
              <span>
                Tap the <span className="font-medium text-foreground">Share</span> button in
                Safari
              </span>
            </li>
            <li className="flex items-center gap-2">
              <SquarePlus className="h-4 w-4 shrink-0 text-foreground" />
              <span>
                Choose{" "}
                <span className="font-medium text-foreground">Add to Home Screen</span>
              </span>
            </li>
          </ol>
        </div>
      )}
    </div>
  );
}
