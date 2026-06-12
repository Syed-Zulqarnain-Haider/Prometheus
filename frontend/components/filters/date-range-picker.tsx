"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type DatePreset, presetRange } from "@/lib/filters";

interface DateRangeValue {
  preset: DatePreset;
  dateFrom: string;
  dateTo: string;
}

const PRESETS: { key: Exclude<DatePreset, "custom">; label: string }[] = [
  { key: "7D", label: "7D" },
  { key: "30D", label: "30D" },
  { key: "90D", label: "90D" },
];

export function DateRangePicker({
  preset,
  dateFrom,
  dateTo,
  onChange,
}: DateRangeValue & { onChange: (value: DateRangeValue) => void }) {
  return (
    <div className="flex items-center gap-1">
      {PRESETS.map((p) => (
        <Button
          key={p.key}
          variant={preset === p.key ? "default" : "outline"}
          size="sm"
          onClick={() => {
            const range = presetRange(p.key);
            onChange({ preset: p.key, dateFrom: range.from, dateTo: range.to });
          }}
        >
          {p.label}
        </Button>
      ))}
      <Input
        type="date"
        aria-label="From date"
        value={dateFrom}
        className="h-8 w-[8.5rem]"
        onChange={(e) =>
          onChange({ preset: "custom", dateFrom: e.target.value, dateTo })
        }
      />
      <span className="text-muted-foreground">–</span>
      <Input
        type="date"
        aria-label="To date"
        value={dateTo}
        className="h-8 w-[8.5rem]"
        onChange={(e) =>
          onChange({ preset: "custom", dateFrom, dateTo: e.target.value })
        }
      />
    </div>
  );
}
