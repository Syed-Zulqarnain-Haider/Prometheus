"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

export interface Option {
  value: string;
  label: string;
}

interface MultiSelectProps {
  label: string;
  options: Option[];
  selected: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

export function MultiSelect({
  label,
  options,
  selected,
  onChange,
  disabled,
}: MultiSelectProps) {
  const [open, setOpen] = useState(false);

  function toggle(value: string) {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  }

  const summary =
    selected.length === 0 ? `All ${label.toLowerCase()}` : `${selected.length} selected`;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          className="min-w-[9rem] justify-between gap-2"
        >
          <span className="truncate">{summary}</span>
          <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="max-h-72 overflow-auto">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium">{label}</span>
          {selected.length > 0 && (
            <button
              type="button"
              className="text-xs text-muted-foreground hover:underline"
              onClick={() => onChange([])}
            >
              Clear
            </button>
          )}
        </div>
        <div className="space-y-1">
          {options.length === 0 && (
            <p className="text-xs text-muted-foreground">No options</p>
          )}
          {options.map((option) => (
            <div
              key={option.value}
              className="group flex items-center gap-2 rounded px-1 py-1 text-sm hover:bg-accent"
            >
              <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2">
                <Checkbox
                  checked={selected.includes(option.value)}
                  onCheckedChange={() => toggle(option.value)}
                />
                <span className="truncate">{option.label}</span>
              </label>
              {/* "only" quick-pick: select just this one (like Looker/Tableau). */}
              <button
                type="button"
                className="shrink-0 rounded px-1 text-xs text-muted-foreground opacity-0 hover:underline group-hover:opacity-100"
                onClick={() => onChange([option.value])}
              >
                only
              </button>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
