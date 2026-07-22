"use client";

import { CalendarDays } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { type DatePreset, PRESET_LABELS, presetRange } from "@/lib/filters";

interface DateRangeValue {
  preset: DatePreset;
  dateFrom: string;
  dateTo: string;
}

function label(value: DateRangeValue): string {
  const found = PRESET_LABELS.find((p) => p.key === value.preset);
  if (found) return found.label;
  return `${value.dateFrom} – ${value.dateTo}`;
}

/** AdMob/Looker-style range picker: a preset list on the left + a custom calendar range
 *  on the right, inside a popover. */
export function DateRangePicker({
  preset,
  dateFrom,
  dateTo,
  onChange,
}: DateRangeValue & { onChange: (value: DateRangeValue) => void }) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <CalendarDays className="h-4 w-4 opacity-70" />
          {label({ preset, dateFrom, dateTo })}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[26rem] p-0">
        <div className="flex">
          {/* Presets */}
          <div className="w-40 shrink-0 border-r p-2">
            {PRESET_LABELS.map((p) => (
              <button
                key={p.key}
                type="button"
                className={`block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-accent ${
                  preset === p.key ? "bg-accent font-medium" : ""
                }`}
                onClick={() => {
                  const range = presetRange(p.key);
                  onChange({ preset: p.key, dateFrom: range.from, dateTo: range.to });
                  setOpen(false);
                }}
              >
                {p.label}
              </button>
            ))}
            <div
              className={`mt-1 border-t px-2 pt-2 text-sm ${
                preset === "custom" ? "font-medium text-foreground" : "text-muted-foreground"
              }`}
            >
              Custom
            </div>
          </div>

          {/* Custom calendar range */}
          <div className="flex-1 space-y-3 p-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Start date</label>
              <Input
                type="date"
                aria-label="From date"
                value={dateFrom}
                max={dateTo || undefined}
                onChange={(e) => onChange({ preset: "custom", dateFrom: e.target.value, dateTo })}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">End date</label>
              <Input
                type="date"
                aria-label="To date"
                value={dateTo}
                min={dateFrom || undefined}
                onChange={(e) => onChange({ preset: "custom", dateFrom, dateTo: e.target.value })}
              />
            </div>
            <Button size="sm" className="w-full" onClick={() => setOpen(false)}>
              Apply
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
