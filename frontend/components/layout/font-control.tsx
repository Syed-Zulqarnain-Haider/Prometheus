"use client";

import { Type } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

const SIZES = [
  { key: "sm", label: "S" },
  { key: "md", label: "M" },
  { key: "lg", label: "L" },
  { key: "xl", label: "XL" },
];

const FONTS = [
  { key: "default", label: "Archivo (default)" },
  { key: "system", label: "System" },
  { key: "serif", label: "Serif" },
  { key: "mono", label: "Monospace" },
  { key: "rounded", label: "Rounded" },
];

/** Apply the prefs to <html> via data-attributes the CSS keys off (md/default = no attr). */
function apply(size: string, font: string) {
  const el = document.documentElement;
  if (size === "md") el.removeAttribute("data-font-size");
  else el.setAttribute("data-font-size", size);
  if (font === "default") el.removeAttribute("data-font");
  else el.setAttribute("data-font", font);
}

export function FontControl() {
  const [size, setSize] = useState("md");
  const [font, setFont] = useState("default");

  useEffect(() => {
    const s = localStorage.getItem("font-size") ?? "md";
    const f = localStorage.getItem("font-family") ?? "default";
    setSize(s);
    setFont(f);
    apply(s, f);
  }, []);

  function updateSize(s: string) {
    setSize(s);
    localStorage.setItem("font-size", s);
    apply(s, font);
  }
  function updateFont(f: string) {
    setFont(f);
    localStorage.setItem("font-family", f);
    apply(size, f);
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Text size & font">
          <Type className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-56 space-y-3 p-2">
        <div>
          <p className="mb-1 px-1 text-xs uppercase tracking-wider text-muted-foreground">
            Text size
          </p>
          <div className="grid grid-cols-4 gap-1">
            {SIZES.map((s) => (
              <Button
                key={s.key}
                variant={size === s.key ? "default" : "outline"}
                size="sm"
                onClick={() => updateSize(s.key)}
              >
                {s.label}
              </Button>
            ))}
          </div>
        </div>
        <div>
          <p className="mb-1 px-1 text-xs uppercase tracking-wider text-muted-foreground">Font</p>
          <div className="space-y-0.5">
            {FONTS.map((f) => (
              <button
                key={f.key}
                type="button"
                className={`block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-accent ${
                  font === f.key ? "bg-accent font-medium" : ""
                }`}
                onClick={() => updateFont(f.key)}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
