"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { RollingNumber } from "@/components/effects/rolling-number";
import { useTable } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";
import { formatNumber, formatUSD } from "@/lib/format";
import { useFilters } from "@/lib/use-filters";
import { cn } from "@/lib/utils";

/* App Spotlight: the depth-carousel / Tinder treatment the owner asked for. One app at a
 * time as a large card with revenue, installs and UA cost, the next cards stacked behind
 * with depth; swipe (drag), arrows, or arrow keys to move. Data comes from the same
 * server-sorted table endpoint Apps Explorer uses, so RBAC and the global filters apply
 * untouched - a metric the viewer cannot see is simply absent and its slot shows a dash. */

const DECK_SIZE = 20;
const SWIPE_THRESHOLD = 80;

interface SpotlightApp {
  key: string;
  name: string;
  revenue: number | null;
  installs: number | null;
  uaCost: number | null;
}

function metric(row: Record<string, unknown>, field: string): number | null {
  const value = row[field];
  return typeof value === "number" ? value : null;
}

function Stat({
  label,
  value,
  format,
}: {
  label: string;
  value: number | null;
  format: (value: number) => string;
}) {
  return (
    <div className="rounded-[var(--radius-inner)] bg-[color:var(--color-bg-card-sunken)] px-4 py-3 text-center">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 font-display text-xl">
        <RollingNumber value={value} format={format} />
      </p>
    </div>
  );
}

export function SpotlightClient() {
  const { filters } = useFilters();
  const table = useTable(filters as Filters, "total_revenue_usd", DECK_SIZE);
  const apps: SpotlightApp[] = (table.data?.rows ?? []).map((row) => ({
    key: String(row.canonical_key ?? ""),
    name: String(row.app_name ?? row.canonical_key ?? "-"),
    revenue: metric(row, "total_revenue_usd"),
    installs: metric(row, "store_total_installs"),
    uaCost: metric(row, "total_ua_spend_usd"),
  }));

  const [index, setIndex] = useState(0);
  const clamped = apps.length ? Math.min(index, apps.length - 1) : 0;

  const go = useCallback(
    (dir: -1 | 1) => {
      setIndex((current) => {
        const next = current + dir;
        if (next < 0 || next >= apps.length) return current;
        return next;
      });
    },
    [apps.length],
  );

  // Arrow keys page the deck - the carousel is the page's one interaction, so global
  // keys are appropriate here (and only here).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight") go(1);
      if (event.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  // Tinder-style drag: track pointer delta on the top card, commit past the threshold.
  const [drag, setDrag] = useState(0);
  const dragStart = useRef<number | null>(null);
  function onPointerDown(event: React.PointerEvent) {
    dragStart.current = event.clientX;
    (event.target as HTMLElement).setPointerCapture?.(event.pointerId);
  }
  function onPointerMove(event: React.PointerEvent) {
    if (dragStart.current === null) return;
    setDrag(event.clientX - dragStart.current);
  }
  function onPointerUp() {
    if (dragStart.current === null) return;
    if (drag <= -SWIPE_THRESHOLD) go(1);
    if (drag >= SWIPE_THRESHOLD) go(-1);
    dragStart.current = null;
    setDrag(0);
  }

  if (table.isLoading) {
    return <p className="text-sm text-muted-foreground">Dealing the deck...</p>;
  }
  if (apps.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No apps match the current filters - nothing to spotlight.
      </p>
    );
  }

  const deck = apps.slice(clamped, clamped + 3);

  return (
    <div className="mx-auto max-w-xl select-none">
      <style>{`
        @keyframes spotlight-border-spin {
          to { transform: rotate(1turn); }
        }
      `}</style>

      <div className="relative h-[21rem]" role="group" aria-label="App spotlight deck">
        {deck.map((app, depth) => {
          const top = depth === 0;
          return (
            <div
              key={app.key}
              aria-hidden={!top}
              className={cn(
                "absolute inset-x-0 top-0 origin-top rounded-[var(--radius-card)]",
                "transition-transform duration-[var(--dur)] ease-[var(--ease)]",
                top && "cursor-grab active:cursor-grabbing",
              )}
              style={{
                zIndex: 3 - depth,
                transform: top
                  ? `translateX(${drag}px) rotate(${drag / 30}deg)`
                  : `translateY(${depth * 14}px) scale(${1 - depth * 0.05})`,
                opacity: top ? 1 : 0.55 - depth * 0.15,
              }}
              onPointerDown={top ? onPointerDown : undefined}
              onPointerMove={top ? onPointerMove : undefined}
              onPointerUp={top ? onPointerUp : undefined}
              onPointerCancel={top ? onPointerUp : undefined}
            >
              {/* Star-border treatment on the active card only: a slowly sweeping conic
                  highlight riding the card edge. Pure CSS, and only ONE animates. */}
              <div
                className={cn("relative overflow-hidden rounded-[var(--radius-card)] p-px", top && "shadow-lg")}
              >
                {top && (
                  <div
                    aria-hidden
                    className="absolute inset-[-100%]"
                    style={{
                      background:
                        "conic-gradient(from 0deg, transparent 0 340deg, var(--color-accent) 355deg, transparent 360deg)",
                      animation: "spotlight-border-spin 6s linear infinite",
                    }}
                  />
                )}
                <div className="relative rounded-[calc(var(--radius-card)-1px)] border border-transparent bg-card p-6">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                    #{clamped + depth + 1} by revenue
                  </p>
                  <h3 className="mt-1 truncate font-display text-2xl" title={app.name}>
                    {app.name}
                  </h3>
                  <div className="mt-5 grid grid-cols-3 gap-3">
                    <Stat
                      label="Revenue"
                      value={app.revenue}
                      format={(v) => formatUSD(v, { compact: true })}
                    />
                    <Stat label="Installs" value={app.installs} format={formatNumber} />
                    <Stat
                      label="UA Cost"
                      value={app.uaCost}
                      format={(v) => formatUSD(v, { compact: true })}
                    />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex items-center justify-between">
        <button
          type="button"
          aria-label="Previous app"
          disabled={clamped === 0}
          onClick={() => go(-1)}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-[color:var(--color-bg-elevated)] text-muted-foreground transition-all duration-[var(--dur-fast)] hover:scale-110 hover:text-foreground disabled:opacity-30 disabled:hover:scale-100"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <p className="text-xs tabular-nums text-muted-foreground">
          {clamped + 1} / {apps.length}
          <span className="ml-2 hidden sm:inline">swipe, arrows or arrow keys</span>
        </p>
        <button
          type="button"
          aria-label="Next app"
          disabled={clamped >= apps.length - 1}
          onClick={() => go(1)}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-[color:var(--color-accent)] text-[color:var(--color-accent-foreground)] transition-all duration-[var(--dur-fast)] hover:scale-110 disabled:opacity-30 disabled:hover:scale-100"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}
