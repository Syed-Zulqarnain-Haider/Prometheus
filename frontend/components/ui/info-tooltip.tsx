"use client";

import { Info } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/* An ⓘ with a themed tooltip that escapes its container.
 *
 * The KPI cards clip their contents (`overflow-hidden`, so the sparkline respects the
 * rounded corners), which meant an absolutely-positioned tooltip was cut off at the card
 * edge. Rendering into <body> with `position: fixed` escapes every ancestor's clipping
 * and stacking context - the same trick the announcement bar uses.
 *
 * Because it is fixed to the viewport, the position must be measured at open time and
 * abandoned on scroll: a tooltip anchored to coordinates that no longer describe its
 * trigger is worse than no tooltip, so scrolling closes it rather than chasing it. */

const WIDTH = 240; // px - matches the bubble's max-width below
const GAP = 8; // px between the icon and the bubble
const EDGE = 8; // px minimum breathing room from the viewport edge

export function InfoTooltip({ text }: { text: string }) {
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const [box, setBox] = useState<{ top: number; left: number } | null>(null);

  const open = useCallback(() => {
    const el = anchorRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    // Centre on the icon, then clamp so the bubble never leaves the viewport - the
    // leftmost and rightmost KPI cards would otherwise push it off-screen.
    const centred = rect.left + rect.width / 2 - WIDTH / 2;
    const left = Math.min(Math.max(centred, EDGE), window.innerWidth - WIDTH - EDGE);
    setBox({ top: rect.top - GAP, left });
  }, []);

  const close = useCallback(() => setBox(null), []);

  // Scroll or resize invalidates the measured position; close rather than re-measure so
  // a stale bubble can never sit detached from its icon.
  useEffect(() => {
    if (!box) return;
    window.addEventListener("scroll", close, true); // capture: catches scrolling ancestors
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [box, close]);

  return (
    <>
      <span
        ref={anchorRef}
        tabIndex={0}
        role="button"
        aria-label={text}
        onMouseEnter={open}
        onMouseLeave={close}
        onFocus={open}
        onBlur={close}
        onKeyDown={(event) => {
          if (event.key === "Escape") close();
        }}
        className="mt-0.5 inline-flex shrink-0 cursor-help text-muted-foreground/70 outline-none transition-colors hover:text-muted-foreground focus-visible:text-muted-foreground"
      >
        <Info className="h-3.5 w-3.5" />
      </span>
      {box &&
        typeof document !== "undefined" &&
        createPortal(
          <span
            role="tooltip"
            style={{
              position: "fixed",
              top: box.top,
              left: box.left,
              width: WIDTH,
              transform: "translateY(-100%)",
            }}
            className="pointer-events-none z-[80] rounded-[var(--radius-inner)] border border-[color:var(--color-border)] bg-card px-3 py-2 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-foreground shadow-lg"
          >
            {text}
          </span>,
          document.body,
        )}
    </>
  );
}
