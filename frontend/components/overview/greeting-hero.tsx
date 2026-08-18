"use client";

import { useEffect, useState } from "react";

import { useMe } from "@/lib/api-hooks";

/* The welcome hero - the dashboard greets the person by name, like a colleague would.
 *
 * Borrowed from the owner's inspiration boards: the friendly "Welcome back" banner with
 * soft drifting colour behind it. Everything is theme tokens at low alpha, so the same
 * hero reads correctly on every theme, light or dark, and the drift animation is two
 * blurred blobs on a slow alternate loop - alive without demanding attention. Reduced
 * motion disables the drift (globals.css handles it with the other animations).
 *
 * The greeting resolves CLIENT-side after mount: the server cannot know the viewer's
 * local hour, and a wrong "Good morning" at 6pm is worse than a plain one appearing a
 * frame later. */

function greetingFor(hour: number): string {
  if (hour < 5) return "Working late";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export function GreetingHero() {
  const { data: me } = useMe();
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => setNow(new Date()), []);

  // First name only - "Good evening, Muhammad" is a greeting; the full corporate
  // display name is a form field.
  const name = (me?.display_name ?? me?.email ?? "").trim().split(/[@\s.]+/)[0];
  const pretty = name ? name.charAt(0).toUpperCase() + name.slice(1) : "";

  return (
    <div className="anim-rise relative min-w-[16rem] flex-1 overflow-hidden rounded-[var(--radius-card)] border bg-card px-5 py-4">
      {/* The drifting colour - decoration only, behind the text, invisible to readers. */}
      <div
        aria-hidden
        className="hero-blob absolute -right-10 -top-16 h-44 w-44 rounded-full blur-3xl"
        style={{ backgroundColor: "color-mix(in srgb, var(--color-accent) 26%, transparent)" }}
      />
      <div
        aria-hidden
        className="hero-blob absolute -bottom-20 right-24 h-36 w-36 rounded-full blur-3xl"
        style={{
          backgroundColor: "color-mix(in srgb, var(--color-positive) 18%, transparent)",
          animationDelay: "-7s",
        }}
      />

      <div className="relative">
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          Executive Overview
          {now &&
            ` · ${now.toLocaleDateString(undefined, {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}`}
        </p>
        <h1 className="mt-1 font-display text-2xl tracking-tight sm:text-3xl">
          {now ? greetingFor(now.getHours()) : "Welcome"}
          {pretty && <span className="text-[color:var(--color-accent)]">, {pretty}</span>}
        </h1>
      </div>
    </div>
  );
}
