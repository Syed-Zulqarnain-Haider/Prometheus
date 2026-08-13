"use client";

import { useEffect, useRef, useState } from "react";

import { useTable } from "@/lib/api-hooks";
import { previousWindow } from "@/lib/compare";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";
import { useFilters } from "@/lib/use-filters";

/* The tape: a trading-desk index ribbon, but for OUR apps. Each item is one app -
 * symbol, revenue for the window, absolute change vs the previous window of equal
 * length, percent change, and a state chip. It scrolls right-to-left forever.
 *
 * ACCESS comes free: both reads go through the same /metrics/table endpoint the rest of
 * the dashboard uses, and the server injects the caller's row scopes into the WHERE
 * clause. An admin's tape carries every app; a pod owner's carries only their pod's -
 * no client-side filtering is involved, so nothing can leak by omission of a check.
 *
 * Motion is a CSS animation on a duplicated track (two identical halves, translated
 * -50% -> 0), which the compositor runs off the main thread - no rAF loop, no jank
 * while the charts below are rendering. */

const TAPE_SIZE = 14;
const PX_PER_SECOND = 42; // steady reading pace, independent of how many items there are

interface TapeItem {
  key: string;
  symbol: string;
  value: number;
  delta: number | null;
  pct: number | null;
}

/** A short, tape-style ticker from the app name: uppercase, no spaces, ~10 chars. */
function symbolOf(name: string): string {
  const cleaned = name.replace(/[^A-Za-z0-9 ]/g, "").trim().toUpperCase();
  if (!cleaned) return "APP";
  const words = cleaned.split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 10);
  // Multi-word: initials if that reads well, else the first word.
  const initials = words.map((word) => word[0]).join("");
  return (initials.length >= 3 ? initials : words[0]).slice(0, 10);
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function AppTape() {
  const { filters } = useFilters();
  const current = useTable(filters as Filters, "total_revenue_usd", TAPE_SIZE);

  // The same window, shifted back by its own length - the backend's own comparison rule.
  const prevRange = previousWindow(filters.dateFrom, filters.dateTo);
  const previous = useTable(
    { ...(filters as Filters), dateFrom: prevRange.from, dateTo: prevRange.to },
    "total_revenue_usd",
    TAPE_SIZE * 3, // wider net: an app in this window may rank lower in the last one
  );

  const [paused, setPaused] = useState(false);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [duration, setDuration] = useState(60);

  const prevByKey = new Map<string, number>();
  for (const row of previous.data?.rows ?? []) {
    const key = String(row.canonical_key ?? "");
    const value = num(row.total_revenue_usd);
    if (key && value !== null) prevByKey.set(key, value);
  }

  const items: TapeItem[] = (current.data?.rows ?? [])
    .map((row) => {
      const key = String(row.canonical_key ?? "");
      const value = num(row.total_revenue_usd);
      if (!key || value === null) return null;
      const before = prevByKey.get(key);
      const delta = before === undefined ? null : value - before;
      // A previous value of 0 makes a percentage meaningless, not infinite.
      const pct = before === undefined || before === 0 ? null : (value - before) / before;
      return {
        key,
        symbol: symbolOf(String(row.app_name ?? key)),
        value,
        delta,
        pct,
      };
    })
    .filter((item): item is TapeItem => item !== null);

  // Duration from the measured track width, so the speed is constant regardless of how
  // many apps are on the tape (a short tape must not sprint).
  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const half = el.scrollWidth / 2;
    if (half > 0) setDuration(Math.max(20, half / PX_PER_SECOND));
  }, [items.length]);

  // Keyboard shortcut, as on the reference tape.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLElement) {
        const tag = event.target.tagName;
        if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      }
      if (event.key === "t" || event.key === "T") setPaused((value) => !value);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (items.length === 0) return null;

  return (
    <div
      role="marquee"
      aria-label="app performance tape"
      className="mb-4 flex items-stretch overflow-hidden rounded-[var(--radius-inner)] border border-[color:var(--color-border)] bg-[#0b0b0d]"
    >
      <style>{`
        @keyframes app-tape-scroll {
          from { transform: translateX(0); }
          to   { transform: translateX(-50%); }
        }
        .app-tape-track {
          display: flex;
          width: max-content;
          animation: app-tape-scroll linear infinite;
        }
        .app-tape-viewport:hover .app-tape-track { animation-play-state: paused; }
        @media (prefers-reduced-motion: reduce) {
          .app-tape-track { animation: none; }
        }
      `}</style>

      {/* Control cell - fixed, the tape slides past it. */}
      <div className="flex shrink-0 items-center gap-2 border-r border-[color:var(--color-border)] bg-[#131317] px-3 py-1.5">
        <span className="font-mono text-[10px] font-bold tracking-[0.18em] text-[color:var(--color-amber)]">
          TAPE
        </span>
        <button
          type="button"
          aria-label={paused ? "Resume tape scroll" : "Pause tape scroll"}
          title="pause/resume [T]"
          onClick={() => setPaused((value) => !value)}
          className="text-[11px] leading-none text-muted-foreground transition-colors hover:text-foreground"
        >
          {paused ? "▶" : "⏸"}
        </button>
      </div>

      <div className="app-tape-viewport min-w-0 flex-1 overflow-hidden">
        <div
          ref={trackRef}
          className="app-tape-track"
          style={{
            animationDuration: `${duration}s`,
            animationPlayState: paused ? "paused" : "running",
          }}
        >
          {[0, 1].map((copy) => (
            <div key={copy} aria-hidden={copy === 1} className="flex">
              {items.map((item) => {
                const up = (item.delta ?? 0) > 0;
                const down = (item.delta ?? 0) < 0;
                const tone = up
                  ? "text-[color:var(--color-positive)]"
                  : down
                    ? "text-[color:var(--color-negative)]"
                    : "text-muted-foreground";
                return (
                  <div
                    key={`${copy}-${item.key}`}
                    className="flex shrink-0 items-center gap-2 whitespace-nowrap border-r border-[color:var(--color-border)] px-3 py-1.5 font-mono text-[11px] tabular-nums"
                  >
                    <span className="font-bold tracking-wide text-[color:var(--color-amber)]">
                      {item.symbol}
                    </span>
                    <span className="text-foreground">
                      {formatUSD(item.value, { compact: true })}
                    </span>
                    {item.delta !== null && (
                      <span className={tone}>
                        {up ? "▲" : down ? "▼" : "="} {up ? "+" : ""}
                        {formatUSD(item.delta, { compact: true })}
                      </span>
                    )}
                    {item.pct !== null && (
                      <span className={tone}>
                        {item.pct > 0 ? "+" : ""}
                        {(item.pct * 100).toFixed(2)}%
                      </span>
                    )}
                    <span className="text-[9px] uppercase tracking-wider text-muted-foreground opacity-70">
                      {item.delta === null ? "NEW" : up ? "UP" : down ? "DOWN" : "FLAT"}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
