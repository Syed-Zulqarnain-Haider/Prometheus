"use client";

import { useEffect, useRef, useState } from "react";

/* Animated counter (the reactbits "counter" idea, dashboard-grade): the value rolls up
 * with an ease-out tween instead of snapping. Numbers only animate when they CHANGE - a
 * figure that quietly settles reads as alive; one that scrambles reads as untrustworthy,
 * which is why the glitch/scramble text treatments were deliberately not used on data. */

export function RollingNumber({
  value,
  format,
  durationMs = 600,
}: {
  value: number | null | undefined;
  format: (value: number) => string;
  durationMs?: number;
}) {
  const [shown, setShown] = useState<number | null>(value ?? null);
  const fromRef = useRef<number | null>(value ?? null);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (value == null) {
      setShown(null);
      fromRef.current = null;
      return;
    }
    const from = fromRef.current ?? value;
    fromRef.current = value;
    if (from === value || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(value);
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(from + (value - from) * eased);
      if (t < 1) frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameRef.current);
  }, [value, durationMs]);

  return <span className="tabular-nums">{shown == null ? "-" : format(shown)}</span>;
}
