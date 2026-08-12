"use client";

import { useEffect } from "react";

/* Global click spark (owner request): a small radial burst at the pointer on every click.
 * Implemented with the Web Animations API on throwaway DOM nodes - no canvas loop, no
 * state, no re-renders, and nothing runs at all between clicks. Honors
 * prefers-reduced-motion, and sparks are pointer-events:none so they can never steal a
 * click from the thing being clicked. */

const SPARK_COUNT = 8;
const SPARK_LENGTH = 10;
const SPARK_TRAVEL = 22;
const DURATION_MS = 420;

function spawnSpark(x: number, y: number): void {
  const root = document.createElement("div");
  root.style.cssText = `position:fixed;left:${x}px;top:${y}px;width:0;height:0;z-index:9999;pointer-events:none;`;

  for (let i = 0; i < SPARK_COUNT; i += 1) {
    const angle = (Math.PI * 2 * i) / SPARK_COUNT;
    const line = document.createElement("span");
    line.style.cssText = [
      "position:absolute",
      `width:${SPARK_LENGTH}px`,
      "height:2px",
      "border-radius:2px",
      "background:var(--color-accent, #8fbcaf)",
      "transform-origin:0 50%",
      `transform:rotate(${(angle * 180) / Math.PI}deg) translateX(0)`,
    ].join(";");
    root.appendChild(line);
    line.animate(
      [
        { transform: `rotate(${(angle * 180) / Math.PI}deg) translateX(4px) scaleX(1)`, opacity: 1 },
        {
          transform: `rotate(${(angle * 180) / Math.PI}deg) translateX(${SPARK_TRAVEL}px) scaleX(0.3)`,
          opacity: 0,
        },
      ],
      { duration: DURATION_MS, easing: "cubic-bezier(0.25, 1, 0.5, 1)", fill: "forwards" },
    );
  }

  document.body.appendChild(root);
  window.setTimeout(() => root.remove(), DURATION_MS + 50);
}

export function ClickSpark() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const onClick = (event: MouseEvent) => {
      // Real pointer clicks only - synthetic clicks (keyboard activation reports 0,0)
      // must not paint a spark in the corner.
      if (event.clientX === 0 && event.clientY === 0) return;
      spawnSpark(event.clientX, event.clientY);
    };
    document.addEventListener("click", onClick, { passive: true });
    return () => document.removeEventListener("click", onClick);
  }, []);
  return null;
}
