"use client";

import { useRef, useState } from "react";

import { cn } from "@/lib/utils";

/* Elastic slider: the knob follows the pointer while dragging, and on release it lands
 * with a springy overshoot (Web Animations API - no animation library). */

export function ElasticSlider({
  value,
  onChange,
  label,
}: {
  value: number; // 0..1
  onChange: (value: number) => void;
  label: string;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const knobRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);

  function valueFrom(clientX: number): number {
    const track = trackRef.current;
    if (!track) return value;
    const rect = track.getBoundingClientRect();
    return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
  }

  function release(): void {
    setDragging(false);
    knobRef.current?.animate(
      [
        { transform: "translate(-50%, -50%) scale(1.25)" },
        { transform: "translate(-50%, -50%) scale(0.92)" },
        { transform: "translate(-50%, -50%) scale(1)" },
      ],
      { duration: 340, easing: "cubic-bezier(0.34, 1.56, 0.64, 1)" },
    );
  }

  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <span className="text-xs tabular-nums text-muted-foreground">
          {Math.round(value * 100)}%
        </span>
      </div>
      <div
        ref={trackRef}
        role="slider"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(value * 100)}
        tabIndex={0}
        className="relative h-6 cursor-pointer touch-none"
        onPointerDown={(event) => {
          setDragging(true);
          onChange(valueFrom(event.clientX));
          (event.target as HTMLElement).setPointerCapture?.(event.pointerId);
        }}
        onPointerMove={(event) => dragging && onChange(valueFrom(event.clientX))}
        onPointerUp={release}
        onPointerCancel={release}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight") onChange(Math.min(1, value + 0.05));
          if (event.key === "ArrowLeft") onChange(Math.max(0, value - 0.05));
        }}
      >
        <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-[color:var(--color-bg-elevated)]" />
        <div
          className="absolute left-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-[color:var(--color-accent)]"
          style={{ width: `${value * 100}%` }}
        />
        <div
          ref={knobRef}
          className={cn(
            "absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[color:var(--color-accent)] shadow-md",
            dragging && "scale-125",
          )}
          style={{ left: `${value * 100}%` }}
        />
      </div>
    </div>
  );
}
