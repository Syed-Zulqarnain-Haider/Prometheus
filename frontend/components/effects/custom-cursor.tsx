"use client";

import { useEffect, useRef, useState } from "react";

/* User-selectable cursor treatments, chosen on the Profile page next to the background
 * effects. Two styles, both implemented dependency-free to match the 21st.dev sources
 * the owner picked:
 *  - "smooth": a spring-physics arrow that rotates to face its direction of travel and
 *    squashes slightly while moving (SmoothCursor).
 *  - "magnetic": an exclusion-blend circle that lags the pointer, stretches with speed,
 *    and morphs to wrap whatever interactive element is under it (MagneticCursor).
 * Both hide on touch devices and honour prefers-reduced-motion by collapsing the spring
 * to a direct follow. The native cursor is suppressed while a style is active, except
 * over text inputs where the caret cursor stays for usability. */

export const CURSOR_KEY = "cursor-style";
export const CURSOR_CHANGE_EVENT = "prometheus:cursor-change";

export type CursorStyle = "default" | "smooth" | "magnetic";

export const CURSOR_STYLES: Array<{ id: CursorStyle; label: string }> = [
  { id: "default", label: "System default" },
  { id: "smooth", label: "Smooth arrow" },
  { id: "magnetic", label: "Magnetic dot" },
];

export function readCursorPreference(): CursorStyle {
  try {
    const raw = localStorage.getItem(CURSOR_KEY);
    if (raw === "smooth" || raw === "magnetic") return raw;
  } catch {
    /* storage blocked - default */
  }
  return "default";
}

const INTERACTIVE = "button, a, [role='button'], [data-magnetic], input[type='checkbox'], select";

/** Semi-implicit Euler spring - the same feel as the pasted useSpring configs. */
class Spring {
  value: number;
  velocity = 0;
  constructor(
    value: number,
    private stiffness: number,
    private damping: number,
  ) {
    this.value = value;
  }
  step(target: number, dt: number): number {
    this.velocity += (target - this.value) * this.stiffness * dt;
    this.velocity *= Math.exp(-this.damping * dt);
    this.value += this.velocity * dt;
    return this.value;
  }
  jump(target: number): void {
    this.value = target;
    this.velocity = 0;
  }
}

function SmoothArrow() {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const x = new Spring(-100, 400, 45);
    const y = new Spring(-100, 400, 45);
    const rot = new Spring(0, 300, 60);
    const scale = new Spring(1, 500, 35);

    const target = { x: -100, y: -100 };
    const last = { x: -100, y: -100, t: performance.now() };
    let previousAngle = 0;
    let accumulated = 0;
    let movingUntil = 0;
    let frame = 0;
    let lastFrame = performance.now();

    const onMove = (event: PointerEvent) => {
      const now = performance.now();
      const dt = now - last.t;
      if (dt > 0) {
        const vx = (event.clientX - last.x) / dt;
        const vy = (event.clientY - last.y) / dt;
        const speed = Math.hypot(vx, vy);
        if (speed > 0.1) {
          const angle = Math.atan2(vy, vx) * (180 / Math.PI) + 90;
          let diff = angle - previousAngle;
          if (diff > 180) diff -= 360;
          if (diff < -180) diff += 360;
          accumulated += diff;
          previousAngle = angle;
          movingUntil = now + 150;
        }
      }
      last.x = event.clientX;
      last.y = event.clientY;
      last.t = now;
      target.x = event.clientX;
      target.y = event.clientY;
    };

    const render = (now: number) => {
      const dt = Math.min((now - lastFrame) / 1000, 0.032);
      lastFrame = now;
      if (reduced) {
        x.jump(target.x);
        y.jump(target.y);
        rot.jump(0);
        scale.jump(1);
      } else {
        x.step(target.x, dt);
        y.step(target.y, dt);
        rot.step(accumulated, dt);
        scale.step(now < movingUntil ? 0.95 : 1, dt);
      }
      el.style.transform = `translate3d(${x.value}px, ${y.value}px, 0) translate(-50%, -50%) rotate(${rot.value}deg) scale(${scale.value})`;
      frame = requestAnimationFrame(render);
    };

    window.addEventListener("pointermove", onMove);
    frame = requestAnimationFrame(render);
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div ref={ref} aria-hidden className="fixed left-0 top-0 z-[100] pointer-events-none will-change-transform">
      <svg width={25} height={27} viewBox="0 0 50 54" fill="none">
        <path
          d="M42.6817 41.1495L27.5103 6.79925C26.7269 5.02557 24.2082 5.02558 23.3927 6.79925L7.59814 41.1495C6.75833 42.9759 8.52712 44.8902 10.4125 44.1954L24.3757 39.0496C24.8829 38.8627 25.4385 38.8627 25.9422 39.0496L39.8121 44.1954C41.6849 44.8902 43.4884 42.9759 42.6817 41.1495Z"
          fill="black"
        />
        <path
          d="M43.7146 40.6933L28.5431 6.34306C27.3556 3.65428 23.5772 3.69516 22.3668 6.32755L6.57226 40.6778C5.3134 43.4156 7.97238 46.298 10.803 45.2549L24.7662 40.109C25.0221 40.0147 25.2999 40.0156 25.5494 40.1082L39.4193 45.254C42.2261 46.2953 44.9254 43.4347 43.7146 40.6933Z"
          stroke="white"
          strokeWidth={2.25825}
        />
      </svg>
    </div>
  );
}

function MagneticDot() {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const SIZE = 26;
    const PADDING = 12 * 1.2;

    const pos = { x: -100, y: -100 };
    const target = { x: -100, y: -100 };
    const previous = { x: -100, y: -100 };
    let hovered: HTMLElement | null = null;
    let frame = 0;

    const onMove = (event: PointerEvent) => {
      target.x = event.clientX;
      target.y = event.clientY;
      const at = event.target instanceof Element ? event.target.closest<HTMLElement>(INTERACTIVE) : null;
      if (at !== hovered) {
        hovered = at;
        if (at) {
          const bounds = at.getBoundingClientRect();
          el.style.width = `${bounds.width + PADDING * 2}px`;
          el.style.height = `${bounds.height + PADDING * 2}px`;
          el.style.borderRadius = window.getComputedStyle(at).borderRadius || "9999px";
        } else {
          el.style.width = `${SIZE}px`;
          el.style.height = `${SIZE}px`;
          el.style.borderRadius = "50%";
        }
      }
    };

    const render = () => {
      if (hovered) {
        // Snap the circle onto the hovered control's centre - the "magnetic" grab.
        const bounds = hovered.getBoundingClientRect();
        const cx = bounds.left + bounds.width / 2;
        const cy = bounds.top + bounds.height / 2;
        pos.x += (cx - pos.x) * (reduced ? 1 : 0.22);
        pos.y += (cy - pos.y) * (reduced ? 1 : 0.22);
        el.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0) translate(-50%, -50%)`;
      } else {
        pos.x += (target.x - pos.x) * (reduced ? 1 : 0.12);
        pos.y += (target.y - pos.y) * (reduced ? 1 : 0.12);
        const dx = pos.x - previous.x;
        const dy = pos.y - previous.y;
        const speed = Math.hypot(dx, dy) * 0.02;
        const rotate = reduced ? 0 : Math.atan2(dy, dx) * (180 / Math.PI);
        const sx = 1 + Math.min(speed, 1);
        const sy = 1 - Math.min(speed, 0.3);
        el.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0) translate(-50%, -50%) rotate(${rotate}deg) scale(${reduced ? 1 : sx}, ${reduced ? 1 : sy})`;
      }
      previous.x = pos.x;
      previous.y = pos.y;
      frame = requestAnimationFrame(render);
    };

    window.addEventListener("pointermove", onMove);
    frame = requestAnimationFrame(render);
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div
      ref={ref}
      aria-hidden
      className="fixed left-0 top-0 z-[100] pointer-events-none will-change-transform"
      style={{
        width: 26,
        height: 26,
        borderRadius: "50%",
        backgroundColor: "white",
        mixBlendMode: "exclusion",
        backdropFilter: "contrast(1.5)",
        WebkitBackdropFilter: "contrast(1.5)",
        transition: "width 0.3s ease, height 0.3s ease, border-radius 0.3s ease",
      }}
    />
  );
}

export function CursorFx() {
  const [style, setStyle] = useState<CursorStyle>("default");
  const [touch, setTouch] = useState(true); // assume touch until proven otherwise - no flash

  useEffect(() => {
    setTouch("ontouchstart" in window || navigator.maxTouchPoints > 0);
    setStyle(readCursorPreference());
    const onChange = () => setStyle(readCursorPreference());
    window.addEventListener(CURSOR_CHANGE_EVENT, onChange);
    return () => window.removeEventListener(CURSOR_CHANGE_EVENT, onChange);
  }, []);

  if (touch || style === "default") return null;

  return (
    <>
      {/* Native cursor off while a custom one is active; text fields keep the caret. */}
      <style>{`
        body, body * { cursor: none !important; }
        body :is(input:not([type="checkbox"]):not([type="radio"]), textarea, [contenteditable="true"]) { cursor: text !important; }
      `}</style>
      {style === "smooth" ? <SmoothArrow /> : <MagneticDot />}
    </>
  );
}
