"use client";

import { useState } from "react";

// Deterministic, theme-neutral palette for the initials fallback (colour-blind-safe hues).
const PALETTE = [
  "#2563eb", "#0891b2", "#059669", "#65a30d", "#ca8a04",
  "#ea580c", "#dc2626", "#db2777", "#7c3aed", "#4f46e5",
];

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

function colorFor(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

/** App avatar: shows the store icon when ``iconUrl`` is available, otherwise a coloured
 *  initials badge (deterministic per app name) so every row always has a recognisable mark.
 *  Falls back to the badge if the image fails to load. */
export function AppIcon({
  name,
  iconUrl,
  size = 20,
}: {
  name: string;
  iconUrl?: string | null;
  size?: number;
}) {
  const [failed, setFailed] = useState(false);
  const safeName = name || "?";

  if (iconUrl && !failed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- external, variable store CDNs
      <img
        src={iconUrl}
        alt=""
        width={size}
        height={size}
        loading="lazy"
        onError={() => setFailed(true)}
        className="shrink-0 rounded-[5px] object-cover ring-1 ring-black/5"
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center justify-center rounded-[5px] font-semibold text-white"
      style={{
        width: size,
        height: size,
        background: colorFor(safeName),
        fontSize: Math.round(size * 0.42),
      }}
    >
      {initials(safeName)}
    </span>
  );
}
