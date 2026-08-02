"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import { TOUR_STEPS } from "@/lib/tour-steps";

const SEEN_KEY = "product-tour-seen-v1";
const START_EVENT = "prometheus:start-tour";
const PAD = 8; // spotlight padding around the target

/** (Re)start the product tour from anywhere (e.g. the header help button). */
export function startProductTour(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(START_EVENT));
}

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

function measure(selector?: string): Box | null {
  if (!selector) return null; // centered step
  const el = document.querySelector(selector);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return null;
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

/** Index of the next step (from `from`) whose target is either absent (centered) or present
 * in the DOM. Returns -1 when there are no more showable steps. */
function nextShowable(from: number): number {
  for (let i = from; i < TOUR_STEPS.length; i++) {
    const s = TOUR_STEPS[i];
    if (!s.selector || document.querySelector(s.selector)) return i;
  }
  return -1;
}

export function ProductTour() {
  const [active, setActive] = useState(false);
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const finish = useCallback(() => {
    setActive(false);
    try {
      localStorage.setItem(SEEN_KEY, "1");
    } catch {
      /* ignore */
    }
  }, []);

  const show = useCallback((i: number) => {
    const j = nextShowable(i);
    if (j < 0) {
      setActive(false);
      try {
        localStorage.setItem(SEEN_KEY, "1");
      } catch {
        /* ignore */
      }
      return;
    }
    setIndex(j);
    setBox(measure(TOUR_STEPS[j].selector));
  }, []);

  const start = useCallback(() => {
    setActive(true);
    show(0);
  }, [show]);

  // Launch on the custom event (help button) — always replays.
  useEffect(() => {
    window.addEventListener(START_EVENT, start);
    return () => window.removeEventListener(START_EVENT, start);
  }, [start]);

  // Auto-start once per browser for a first-time user (after mount, SSR-safe).
  useEffect(() => {
    if (!mounted) return;
    let seen = false;
    try {
      seen = localStorage.getItem(SEEN_KEY) === "1";
    } catch {
      seen = false;
    }
    if (!seen) {
      // Defer so the target elements have laid out.
      const t = window.setTimeout(start, 700);
      return () => window.clearTimeout(t);
    }
  }, [mounted, start]);

  // Keep the spotlight aligned as the page scrolls/resizes.
  useEffect(() => {
    if (!active) return;
    const reflow = () => setBox(measure(TOUR_STEPS[index].selector));
    window.addEventListener("resize", reflow);
    window.addEventListener("scroll", reflow, true);
    return () => {
      window.removeEventListener("resize", reflow);
      window.removeEventListener("scroll", reflow, true);
    };
  }, [active, index]);

  // Esc closes.
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, finish]);

  if (!active || !mounted) return null;

  const step = TOUR_STEPS[index];
  const isLast = nextShowable(index + 1) < 0;
  const stepNo = index + 1;

  // Tooltip position: near the target on the chosen side, else centered.
  const tip = (() => {
    const w = 320;
    if (!box) {
      return { top: "50%", left: "50%", transform: "translate(-50%, -50%)" as const };
    }
    const place = step.placement ?? "bottom";
    const vh = window.innerHeight;
    const vw = window.innerWidth;
    if (place === "right") {
      return { top: Math.min(box.top, vh - 220), left: Math.min(box.left + box.width + PAD + 8, vw - w - 12) };
    }
    if (place === "left") {
      return { top: Math.min(box.top, vh - 220), left: Math.max(12, box.left - w - PAD - 8) };
    }
    if (place === "top") {
      return { top: Math.max(12, box.top - 190), left: Math.min(Math.max(12, box.left), vw - w - 12) };
    }
    return { top: Math.min(box.top + box.height + PAD + 8, vh - 200), left: Math.min(Math.max(12, box.left), vw - w - 12) };
  })();

  return createPortal(
    <div className="fixed inset-0 z-[100]" role="dialog" aria-modal="true" aria-label="Product tour">
      {/* Dimmed backdrop with a spotlight cutout over the target (giant box-shadow). Clicking
          the backdrop advances; clicking the highlighted element does nothing special. */}
      {box ? (
        <div
          onClick={() => show(index + 1)}
          className="pointer-events-auto absolute rounded-lg transition-all duration-200"
          style={{
            top: box.top - PAD,
            left: box.left - PAD,
            width: box.width + PAD * 2,
            height: box.height + PAD * 2,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.6)",
          }}
        />
      ) : (
        <div onClick={() => show(index + 1)} className="absolute inset-0 bg-black/60" />
      )}

      {/* Tooltip card */}
      <div
        className="pointer-events-auto absolute w-[320px] rounded-lg border bg-card p-4 shadow-xl"
        style={tip}
      >
        <div className="mb-1 text-xs font-medium text-muted-foreground">
          Step {stepNo} of {TOUR_STEPS.length}
        </div>
        <h3 className="mb-1 text-sm font-semibold">{step.title}</h3>
        <p className="mb-3 text-sm text-muted-foreground">{step.body}</p>
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={finish}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Skip tour
          </button>
          <div className="flex items-center gap-2">
            {index > 0 && (
              <Button variant="outline" size="sm" onClick={() => show(Math.max(0, index - 1))}>
                Back
              </Button>
            )}
            <Button size="sm" onClick={() => (isLast ? finish() : show(index + 1))}>
              {isLast ? "Done" : "Next"}
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
