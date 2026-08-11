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
  type StackMode,
  type TransformMode,
  type TypeOverride,
  isAdjusted,
  stackApplies,
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

const STACK_OPTIONS: { value: StackMode; label: string }[] = [
  { value: "none", label: "Off" },
  { value: "stacked", label: "Stacked" },
  { value: "percent", label: "100%" },
];

const TRANSFORM_OPTIONS: { value: TransformMode; label: string }[] = [
  { value: "none", label: "Actual" },
  { value: "cumulative", label: "Cumulative" },
  { value: "average", label: "Avg" },
];

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled = false,
  hint,
  isOptionDisabled,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  disabled?: boolean;
  hint?: string;
  isOptionDisabled?: (v: T) => boolean;
}) {
  return (
    <div className={cn("space-y-1.5", disabled && "opacity-50")}>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="flex rounded-md border p-0.5">
        {options.map((opt) => {
          const optDisabled = disabled || isOptionDisabled?.(opt.value) === true;
          return (
            <button
              key={opt.value}
              type="button"
              disabled={optDisabled}
              onClick={() => onChange(opt.value)}
              className={cn(
                "flex-1 rounded-sm px-2 py-1 text-xs transition-colors",
                value === opt.value
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                optDisabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
              )}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      {hint && <p className="text-[10px] leading-tight text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** The per-chart adjustment panel: chart type, y-axis scale, stacking, value labels, a
 *  cumulative/moving-average transform, and series visibility. Which sections appear is
 *  driven by the chart's detected capabilities, so a pie/heatmap shows nothing
 *  type/scale-related. Rendered inside a small popover triggered from the chart's
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
  const { canSwitchType, canScale, canStack, canLabel, canTransform, seriesNames } = capabilities;
  const hasControls =
    canSwitchType || canScale || canStack || canLabel || canTransform || seriesNames.length > 0;
  if (!hasControls) return null;

  // Stacking is meaningless on plain lines - grey it out until the viewer picks Bar/Area.
  const stackable = stackApplies(capabilities, adjustments.type);
  const isPercent = adjustments.stack === "percent" && stackable;

  const toggleSeries = (name: string) => {
    const hidden = adjustments.hidden.includes(name)
      ? adjustments.hidden.filter((n) => n !== name)
      : [...adjustments.hidden, name];
    // Never let the viewer hide the last visible series (nothing to chart).
    if (hidden.length >= seriesNames.length) return;
    onChange({ ...adjustments, hidden });
  };

  // Picking 100% while on a log axis would plot log-of-a-share; drop back to auto instead.
  const setStack = (stack: StackMode) =>
    onChange({
      ...adjustments,
      stack,
      scale: stack === "percent" && adjustments.scale === "log" ? "auto" : adjustments.scale,
    });

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
      <PopoverContent align="end" className="max-h-[70vh] w-60 space-y-3 overflow-auto">
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
            value={isPercent ? "linear" : adjustments.scale}
            options={SCALE_OPTIONS}
            onChange={(scale) => onChange({ ...adjustments, scale })}
            disabled={isPercent}
            hint={isPercent ? "Fixed to 0–100% while 100% stacking is on." : undefined}
            isOptionDisabled={(v) => v === "log" && adjustments.stack === "percent"}
          />
        )}

        {canStack && (
          <Segmented
            label="Stacking"
            value={adjustments.stack}
            options={STACK_OPTIONS}
            onChange={setStack}
            disabled={!stackable}
            hint={!stackable ? "Choose Bar or Area to stack series." : undefined}
          />
        )}

        {canTransform && (
          <Segmented
            label="Values"
            value={adjustments.transform}
            options={TRANSFORM_OPTIONS}
            onChange={(transform) => onChange({ ...adjustments, transform })}
            hint={
              adjustments.transform === "cumulative"
                ? "Running total across the selected range."
                : adjustments.transform === "average"
                  ? "Trailing moving average (up to 7 points)."
                  : undefined
            }
          />
        )}

        {canLabel && (
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox
              checked={adjustments.labels}
              onCheckedChange={() => onChange({ ...adjustments, labels: !adjustments.labels })}
            />
            <span>Show data labels</span>
          </label>
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
