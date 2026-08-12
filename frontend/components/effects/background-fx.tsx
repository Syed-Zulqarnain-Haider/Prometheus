"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/* Ambient background effects, USER-SELECTABLE (owner request: ship them all, let each
 * person choose). One fixed canvas, one rAF loop, a registry of renderers. The canvas is
 * pointer-events:none and alpha-capped, pauses whenever the tab is hidden, and honors
 * prefers-reduced-motion by rendering a single static frame. Default is "none" - motion
 * is a choice someone makes, never an ambush. Choice + intensity persist per browser. */

export const BG_EFFECT_KEY = "bg-effect";
export const BG_INTENSITY_KEY = "bg-intensity";
export const BG_CHANGE_EVENT = "prometheus-bg-change";

type Draw = (ctx: CanvasRenderingContext2D, w: number, h: number, t: number) => void;

function accent(): string {
  return (
    getComputedStyle(document.documentElement).getPropertyValue("--color-accent").trim() ||
    "#8fbcaf"
  );
}

/* Deterministic pseudo-random per index, so particles don't teleport between frames. */
function rand(i: number, salt = 0): number {
  const x = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453;
  return x - Math.floor(x);
}

const aurora: Draw = (ctx, w, h, t) => {
  for (let band = 0; band < 3; band += 1) {
    const gradient = ctx.createLinearGradient(0, 0, w, h);
    const hue = (140 + band * 40 + t * 8) % 360;
    gradient.addColorStop(0, `hsla(${hue}, 70%, 60%, 0)`);
    gradient.addColorStop(0.5, `hsla(${hue}, 70%, 60%, 0.5)`);
    gradient.addColorStop(1, `hsla(${(hue + 60) % 360}, 70%, 60%, 0)`);
    ctx.fillStyle = gradient;
    ctx.beginPath();
    for (let x = 0; x <= w; x += 16) {
      const y =
        h * (0.25 + band * 0.18) +
        Math.sin(x / 180 + t * (0.4 + band * 0.15) + band * 2) * h * 0.08;
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fill();
  }
};

const softAurora: Draw = (ctx, w, h, t) => {
  const spots = 4;
  for (let i = 0; i < spots; i += 1) {
    const x = w * (0.2 + 0.6 * rand(i)) + Math.sin(t * 0.15 + i * 2) * w * 0.08;
    const y = h * (0.2 + 0.6 * rand(i, 1)) + Math.cos(t * 0.12 + i * 3) * h * 0.08;
    const radius = Math.min(w, h) * (0.35 + 0.15 * rand(i, 2));
    const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
    gradient.addColorStop(0, `${accent()}55`);
    gradient.addColorStop(1, "transparent");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);
  }
};

const lineWaves: Draw = (ctx, w, h, t) => {
  ctx.strokeStyle = accent();
  ctx.lineWidth = 1;
  for (let line = 0; line < 7; line += 1) {
    ctx.globalAlpha = 0.5 - line * 0.055;
    ctx.beginPath();
    for (let x = 0; x <= w; x += 10) {
      const y =
        h * 0.5 +
        (line - 3) * 26 +
        Math.sin(x / 140 + t * 0.8 + line * 0.7) * 24 +
        Math.sin(x / 47 + t * 1.3) * 8;
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
};

const pixelSnow: Draw = (ctx, w, h, t) => {
  ctx.fillStyle = "#ffffff";
  for (let i = 0; i < 140; i += 1) {
    const speed = 20 + rand(i) * 40;
    const x = rand(i, 1) * w + Math.sin(t * 0.6 + i) * 14;
    const y = (rand(i, 2) * h + t * speed) % h;
    const size = 2 + Math.floor(rand(i, 3) * 3);
    ctx.globalAlpha = 0.35 + rand(i, 4) * 0.4;
    ctx.fillRect(Math.floor(x), Math.floor(y), size, size);
  }
  ctx.globalAlpha = 1;
};

const galaxy: Draw = (ctx, w, h, t) => {
  const cx = w / 2;
  const cy = h / 2;
  for (let i = 0; i < 240; i += 1) {
    const armAngle = rand(i) * Math.PI * 2 + t * 0.02;
    const distance = rand(i, 1) ** 0.6 * Math.min(w, h) * 0.75;
    const x = cx + Math.cos(armAngle + distance * 0.004) * distance;
    const y = cy + Math.sin(armAngle + distance * 0.004) * distance * 0.62;
    const twinkle = 0.3 + 0.7 * Math.abs(Math.sin(t * (0.5 + rand(i, 2)) + i));
    ctx.globalAlpha = twinkle * 0.7;
    ctx.fillStyle = rand(i, 3) > 0.85 ? accent() : "#cfd8dc";
    ctx.fillRect(x, y, rand(i, 4) > 0.9 ? 2 : 1, rand(i, 4) > 0.9 ? 2 : 1);
  }
  ctx.globalAlpha = 1;
};

const iridescence: Draw = (ctx, w, h, t) => {
  const gradient = ctx.createLinearGradient(0, 0, w, h);
  for (let stop = 0; stop <= 4; stop += 1) {
    gradient.addColorStop(stop / 4, `hsla(${(t * 18 + stop * 70) % 360}, 65%, 62%, 0.5)`);
  }
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, w, h);
};

const liquidChrome: Draw = (ctx, w, h, t) => {
  for (let i = 0; i < 5; i += 1) {
    const x = w * (0.5 + 0.4 * Math.sin(t * 0.25 + i * 1.7));
    const y = h * (0.5 + 0.4 * Math.cos(t * 0.2 + i * 2.3));
    const radius = Math.min(w, h) * 0.4;
    const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
    const shade = 200 + Math.floor(40 * Math.sin(t + i));
    gradient.addColorStop(0, `rgba(${shade},${shade},${shade + 15},0.5)`);
    gradient.addColorStop(1, "transparent");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);
  }
};

const moltenMetal: Draw = (ctx, w, h, t) => {
  for (let i = 0; i < 4; i += 1) {
    const x = w * (0.5 + 0.38 * Math.sin(t * 0.3 + i * 2.1));
    const y = h * (0.6 + 0.3 * Math.cos(t * 0.22 + i * 1.4));
    const radius = Math.min(w, h) * (0.25 + 0.1 * Math.sin(t + i));
    const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
    gradient.addColorStop(0, "rgba(255,140,50,0.55)");
    gradient.addColorStop(0.6, "rgba(200,60,30,0.3)");
    gradient.addColorStop(1, "transparent");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);
  }
};

/* Ferrofluid doubles as the meta-balls treatment: soft dark blobs that merge visually. */
const ferrofluid: Draw = (ctx, w, h, t) => {
  ctx.fillStyle = "rgba(10,10,12,0.9)";
  for (let i = 0; i < 6; i += 1) {
    const x = w * (0.5 + 0.35 * Math.sin(t * (0.3 + rand(i) * 0.2) + i * 1.9));
    const y = h * (0.5 + 0.35 * Math.cos(t * (0.25 + rand(i, 1) * 0.2) + i * 1.1));
    const radius = 40 + rand(i, 2) * 70 + Math.sin(t * 2 + i) * 12;
    ctx.save();
    ctx.shadowColor = "rgba(10,10,12,0.9)";
    ctx.shadowBlur = 40;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
};

const darkVeil: Draw = (ctx, w, h, t) => {
  const vignette = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.3, w / 2, h / 2, Math.max(w, h) * 0.8);
  vignette.addColorStop(0, "transparent");
  vignette.addColorStop(1, "rgba(0,0,0,0.85)");
  ctx.fillStyle = vignette;
  ctx.fillRect(0, 0, w, h);
  for (let i = 0; i < 3; i += 1) {
    const x = w * (0.5 + 0.45 * Math.sin(t * 0.1 + i * 2.2));
    const gradient = ctx.createRadialGradient(x, h * 0.85, 0, x, h * 0.85, h * 0.5);
    gradient.addColorStop(0, "rgba(0,0,0,0.5)");
    gradient.addColorStop(1, "transparent");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);
  }
};

const GLYPHS = "01<>[]{}#$%&*+=?ABCDEF";
const letterGlitch: Draw = (ctx, w, h, t) => {
  const cell = 18;
  ctx.font = "12px monospace";
  const cols = Math.ceil(w / cell);
  const rows = Math.ceil(h / cell);
  for (let col = 0; col < cols; col += 1) {
    for (let row = 0; row < rows; row += 1) {
      const i = col * 997 + row;
      // Only a sparse, slowly-changing subset lights up - a full grid strobing is noise.
      const phase = Math.floor(t * (0.5 + rand(i) * 1.5) + rand(i, 1) * 10);
      if (rand(i + phase, 2) > 0.06) continue;
      const glyph = GLYPHS[Math.floor(rand(i + phase, 3) * GLYPHS.length)];
      ctx.globalAlpha = 0.25 + rand(i + phase, 4) * 0.5;
      ctx.fillStyle = rand(i, 5) > 0.9 ? accent() : "#6b7280";
      ctx.fillText(glyph, col * cell, row * cell + 12);
    }
  }
  ctx.globalAlpha = 1;
};

export const BG_EFFECTS: { id: string; label: string; draw: Draw | null }[] = [
  { id: "none", label: "None", draw: null },
  { id: "soft-aurora", label: "Soft Aurora", draw: softAurora },
  { id: "aurora", label: "Aurora", draw: aurora },
  { id: "line-waves", label: "Line Waves", draw: lineWaves },
  { id: "galaxy", label: "Galaxy", draw: galaxy },
  { id: "pixel-snow", label: "Pixel Snow", draw: pixelSnow },
  { id: "iridescence", label: "Iridescence", draw: iridescence },
  { id: "liquid-chrome", label: "Liquid Chrome", draw: liquidChrome },
  { id: "molten-metal", label: "Molten Metal", draw: moltenMetal },
  { id: "ferrofluid", label: "Ferrofluid", draw: ferrofluid },
  { id: "dark-veil", label: "Dark Veil", draw: darkVeil },
  { id: "letter-glitch", label: "Letter Glitch", draw: letterGlitch },
];

export function readBgPreference(): { effect: string; intensity: number } {
  try {
    return {
      effect: localStorage.getItem(BG_EFFECT_KEY) ?? "none",
      intensity: Math.min(1, Math.max(0, Number(localStorage.getItem(BG_INTENSITY_KEY) ?? "0.5"))),
    };
  } catch {
    return { effect: "none", intensity: 0.5 };
  }
}

export function BackgroundFx() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pref, setPref] = useState<{ effect: string; intensity: number } | null>(null);

  // Preference is read post-hydration only, and re-read when the picker broadcasts a
  // change (same tab) or another tab writes storage.
  useEffect(() => {
    setPref(readBgPreference());
    const refresh = () => setPref(readBgPreference());
    window.addEventListener(BG_CHANGE_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(BG_CHANGE_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  // Intensity lives in a ref so the slider can preview live WITHOUT tearing down and
  // rebuilding the whole canvas/loop on every pointermove (that reallocation dozens of
  // times a second is what a drag used to cost).
  const alphaRef = useRef(0.06);
  useEffect(() => {
    if (pref) alphaRef.current = 0.06 + pref.intensity * 0.22;
  }, [pref]);

  const effectId = pref?.effect ?? "none";
  useEffect(() => {
    const canvas = canvasRef.current;
    const effect = BG_EFFECTS.find((entry) => entry.id === effectId);
    if (!canvas || !effect?.draw) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const draw = effect.draw;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    let running = true;
    let scheduled = false;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    const render = (now: number) => {
      scheduled = false;
      if (!running) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.globalAlpha = alphaRef.current;
      draw(ctx, canvas.width, canvas.height, now / 1000);
      ctx.globalAlpha = 1;
      if (!reduced && !scheduled) {
        scheduled = true;
        frame = requestAnimationFrame(render);
      }
    };
    scheduled = true;
    frame = requestAnimationFrame(render);

    // A background may never cost battery in a hidden tab. cancel + the `scheduled`
    // guard together make resume idempotent - a start-while-hidden left one callback
    // pending, and resume used to stack a SECOND loop on top of it, forever.
    const onVisibility = () => {
      cancelAnimationFrame(frame);
      scheduled = false;
      if (document.hidden) {
        running = false;
      } else {
        running = true;
        scheduled = true;
        frame = requestAnimationFrame(render);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      running = false;
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [effectId]);

  if (!pref || pref.effect === "none" || typeof document === "undefined") return null;

  return createPortal(
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0"
    />,
    document.body,
  );
}
