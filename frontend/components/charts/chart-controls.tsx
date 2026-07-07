"use client";

import { RotateCcw, SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  type Adjustments,
  type ChartCapabilities,
  DEFAULT_ADJUSTMENTS,
  type ScaleOverride,
  type TypeOverride,
  isAdjusted,
} from "@/lib/chart-adjust";
import { cn } from "@/lib/utils";

const TYPE_OPTIONS: { value: TypeOverride; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "line", label: "Line" },
  { value: "bar", label: "Bar" },
  { value: "area", label: "Area" },
];

const SCALE_OPTIONS: { value: ScaleOverride; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "linear", label: "Linear" },
  { value: "log", label: "Log" },
];

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="flex rounded-md border p-0.5">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={cn(
              "flex-1 rounded-sm px-2 py-1 text-xs transition-colors",
              value === opt.value
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** The per-chart adjustment panel: chart type, y-axis scale, series visibility. Which
 *  sections appear is driven by the chart's detected capabilities, so a pie/heatmap shows
 *  nothing type/scale-related. Rendered inside a small popover triggered from the chart's
 *  top-right corner. */
export function ChartControls({
  capabilities,
  adjustments,
  onChange,
}: {
  capabilities: ChartCapabilities;
  adjustments: Adjustments;
  onChange: (next: Adjustments) => void;
}) {
  const { canSwitchType, canScale, seriesNames } = capabilities;
  const hasControls = canSwitchType || canScale || seriesNames.length > 0;
  if (!hasControls) return null;

  const toggleSeries = (name: string) => {
    const hidden = adjustments.hidden.includes(name)
      ? adjustments.hidden.filter((n) => n !== name)
      : [...adjustments.hidden, name];
    // Never let the viewer hide the last visible series (nothing to chart).
    if (hidden.length >= seriesNames.length) return;
    onChange({ ...adjustments, hidden });
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label="Adjust chart"
          className="relative h-7 w-7 bg-background/80 backdrop-blur"
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
          {isAdjusted(adjustments) && (
            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-primary" />
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-60 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Adjust chart</p>
          {isAdjusted(adjustments) && (
            <button
              type="button"
              onClick={() => onChange({ ...DEFAULT_ADJUSTMENTS })}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <RotateCcw className="h-3 w-3" /> Reset
            </button>
          )}
        </div>

        {canSwitchType && (
          <Segmented
            label="Chart type"
            value={adjustments.type}
            options={TYPE_OPTIONS}
            onChange={(type) => onChange({ ...adjustments, type })}
          />
        )}

        {canScale && (
          <Segmented
            label="Y-axis scale"
            value={adjustments.scale}
            options={SCALE_OPTIONS}
            onChange={(scale) => onChange({ ...adjustments, scale })}
          />
        )}

        {seriesNames.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">Series</p>
            <div className="space-y-1.5">
              {seriesNames.map((name) => (
                <label key={name} className="flex cursor-pointer items-center gap-2 text-sm">
                  <Checkbox
                    checked={!adjustments.hidden.includes(name)}
                    onCheckedChange={() => toggleSeries(name)}
                  />
                  <span className="truncate">{name}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
