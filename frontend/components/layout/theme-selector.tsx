"use client";

import { Check, Palette } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

// Each theme + a few swatch colors (bg, accent, positive) for a live preview chip.
const THEMES: { key: string; label: string; note?: string; swatches: [string, string, string] }[] = [
  { key: "light", label: "Paper", note: "Light", swatches: ["#fbfaf4", "#8a2f2f", "#2f6b4f"] },
  { key: "dark", label: "Night Ledger", note: "Dark", swatches: ["#1c1810", "#cb5d50", "#6faa7e"] },
  { key: "ocean", label: "Ocean", note: "Blue dark", swatches: ["#14202f", "#4a9ed8", "#4ec9a3"] },
  { key: "forest", label: "Forest", note: "Green dark", swatches: ["#1a2114", "#7aa34e", "#6faa7e"] },
  { key: "slate", label: "Slate", note: "Gray dark", swatches: ["#1b1f26", "#6d9dc5", "#63b389"] },
  { key: "rose", label: "Rose", note: "Light", swatches: ["#fffcfc", "#c14d6b", "#3d8a63"] },
  { key: "amber", label: "Amber", note: "Gold dark", swatches: ["#221b0d", "#e0a93c", "#6faa7e"] },
  { key: "grape", label: "Grape", note: "Purple dark", swatches: ["#1e1829", "#a06ce0", "#5fc0a0"] },
  {
    key: "contrast",
    label: "High Contrast",
    note: "Accessibility",
    swatches: ["#000000", "#ffd400", "#37e07a"],
  },
  {
    key: "colorblind",
    label: "Colorblind-safe",
    note: "Okabe–Ito",
    swatches: ["#ffffff", "#0072b2", "#009e73"],
  },
];

export function ThemeSelector() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => setMounted(true), []);

  const active = mounted ? theme : undefined;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Choose theme">
          <Palette className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-60 p-1">
        <p className="px-2 py-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Theme
        </p>
        {THEMES.map((t) => (
          <button
            key={t.key}
            type="button"
            className="flex w-full items-center gap-3 rounded px-2 py-2 text-left text-sm hover:bg-accent"
            onClick={() => {
              setTheme(t.key);
              setOpen(false);
            }}
          >
            <span className="flex shrink-0 overflow-hidden rounded-full border">
              {t.swatches.map((c, i) => (
                <span key={i} className="h-4 w-4" style={{ backgroundColor: c }} />
              ))}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{t.label}</span>
              {t.note && <span className="block text-xs text-muted-foreground">{t.note}</span>}
            </span>
            {active === t.key && <Check className="h-4 w-4 shrink-0 text-positive" />}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
}
