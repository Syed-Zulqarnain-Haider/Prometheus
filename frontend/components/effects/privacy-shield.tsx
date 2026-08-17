"use client";

import { Eye, EyeOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/* Privacy shield: with the toggle ON, the whole screen is blurred behind a frosted
 * overlay and only a soft circle around the pointer stays readable - so the owner can
 * leave a dashboard open in a room without everyone reading the numbers, and reveal
 * just the area they point at. OFF (the default) shows everything as normal.
 *
 * Mechanics: one fixed overlay carrying backdrop-filter blur, masked by a radial
 * gradient that cuts a transparent hole which lerps after the pointer. The overlay is
 * pointer-events: none, so the page stays fully interactive - this is a visual shield
 * against shoulder-surfing, not an access control (RBAC already handles that server-side). */

const PRIVACY_KEY = "privacy-shield";
const REVEAL_RADIUS = 130; // px fully clear around the pointer
const FEATHER = 80; // px soft edge beyond the clear radius

export function PrivacyShield() {
  const [on, setOn] = useState(false);
  const [ready, setReady] = useState(false);
  const overlayRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    try {
      setOn(localStorage.getItem(PRIVACY_KEY) === "1");
    } catch {
      /* storage blocked - starts off */
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!on) return;
    const el = overlayRef.current;
    if (!el) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Start fully shielded (hole parked offscreen) until the pointer says otherwise.
    const pos = { x: -9999, y: -9999 };
    const target = { x: -9999, y: -9999 };
    let frame = 0;

    const paint = () => {
      const mask = `radial-gradient(circle at ${pos.x}px ${pos.y}px, transparent ${REVEAL_RADIUS}px, black ${REVEAL_RADIUS + FEATHER}px)`;
      el.style.webkitMaskImage = mask;
      el.style.maskImage = mask;
    };

    const onMove = (event: PointerEvent) => {
      target.x = event.clientX;
      target.y = event.clientY;
      if (reduced) {
        pos.x = target.x;
        pos.y = target.y;
        paint();
      }
    };
    const onLeave = () => {
      target.x = -9999;
      target.y = -9999;
    };

    const render = () => {
      pos.x += (target.x - pos.x) * 0.2;
      pos.y += (target.y - pos.y) * 0.2;
      paint();
      frame = requestAnimationFrame(render);
    };

    window.addEventListener("pointermove", onMove);
    document.documentElement.addEventListener("mouseleave", onLeave);
    if (!reduced) frame = requestAnimationFrame(render);
    else paint();
    return () => {
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("mouseleave", onLeave);
      cancelAnimationFrame(frame);
    };
  }, [on]);

  function toggle(): void {
    const next = !on;
    setOn(next);
    try {
      localStorage.setItem(PRIVACY_KEY, next ? "1" : "0");
    } catch {
      /* storage blocked - lasts the session */
    }
  }

  if (!ready) return null;

  return (
    <>
      {on && (
        <div
          ref={overlayRef}
          aria-hidden
          className="fixed inset-0 z-[55] pointer-events-none"
          style={{
            backdropFilter: "blur(18px) saturate(0.65)",
            WebkitBackdropFilter: "blur(18px) saturate(0.65)",
            backgroundColor: "color-mix(in srgb, var(--color-bg-app, #000) 35%, transparent)",
          }}
        />
      )}
      <button
        type="button"
        aria-pressed={on}
        aria-label={on ? "Turn privacy shield off" : "Turn privacy shield on"}
        title={on ? "Privacy shield ON - hover to reveal. Click to show everything." : "Privacy shield: blur the screen, reveal only around your pointer"}
        onClick={toggle}
        className={cn(
          "fixed bottom-20 right-4 z-[60] flex h-11 w-11 items-center justify-center rounded-full shadow-lg",
          // Dimmed at rest: these float over page content (table pagination sits
          // right underneath) and a solid button there hides data. Full opacity
          // returns on hover/focus, and while the shield is ON it stays visible so
          // its state is never in doubt.
          "opacity-40 transition-all duration-[var(--dur-fast)] hover:scale-105 hover:opacity-100 focus-visible:opacity-100 active:scale-95",
          on
            ? "opacity-100 bg-[color:var(--color-accent)] text-[color:var(--color-accent-foreground)]"
            : "bg-[color:var(--color-bg-elevated)] text-muted-foreground hover:text-foreground",
        )}
      >
        {on ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
      </button>
    </>
  );
}
