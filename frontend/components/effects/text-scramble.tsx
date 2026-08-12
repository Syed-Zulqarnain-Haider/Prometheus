"use client";

import { useEffect, useRef, useState } from "react";

/* Scramble-in text (the scrambled/split-flap treatment): when the value CHANGES, letters
 * cycle briefly before settling. Used on TITLES only, never on figures - animated
 * uncertainty on a number teaches people to distrust it. Reduced motion snaps. */

const POOL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

export function TextScramble({ text, className }: { text: string; className?: string }) {
  const [shown, setShown] = useState(text);
  const previous = useRef(text);
  const frame = useRef(0);

  useEffect(() => {
    if (previous.current === text) return;
    previous.current = text;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(text);
      return;
    }
    const start = performance.now();
    const duration = Math.min(600, 120 + text.length * 24);
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const settled = Math.floor(text.length * t);
      let output = text.slice(0, settled);
      for (let i = settled; i < text.length; i += 1) {
        output += text[i] === " " ? " " : POOL[Math.floor(Math.random() * POOL.length)];
      }
      setShown(output);
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [text]);

  return <span className={className}>{shown}</span>;
}
