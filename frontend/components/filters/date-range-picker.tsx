"use client";

import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isAfter,
  isBefore,
  isSameDay,
  isSameMonth,
  isValid,
  parseISO,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import { CalendarDays, ChevronLeft, ChevronRight, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ALL_TIME_START, type DatePreset, PRESET_LABELS, presetRange } from "@/lib/filters";
import { cn } from "@/lib/utils";

export interface DateRangeValue {
  preset: DatePreset;
  dateFrom: string; // yyyy-MM-dd
  dateTo: string; // yyyy-MM-dd
  compare: boolean;
}

/** Which endpoint the next calendar click sets. A range is picked start-then-end, and the
 *  cursor flips back to "start" afterwards so a second pair of clicks starts a new range. */
type Phase = "start" | "end";

const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];

function iso(date: Date): string {
  return format(date, "yyyy-MM-dd");
}

/** Parse a yyyy-MM-dd string, returning null for anything malformed. The date inputs are
 *  free-typed, so a half-entered value like "2026-0" must not blow up the calendar. */
function fromIso(value: string): Date | null {
  if (!value) return null;
  const parsed = parseISO(value);
  return isValid(parsed) ? parsed : null;
}

function prettyDate(value: string): string {
  const d = fromIso(value);
  return d ? format(d, "d MMM yyyy") : value;
}

function triggerLabel(value: DateRangeValue): string {
  const found = PRESET_LABELS.find((p) => p.key === value.preset);
  if (found) return found.label;
  if (value.dateFrom === value.dateTo) return prettyDate(value.dateFrom);
  return `${prettyDate(value.dateFrom)} – ${prettyDate(value.dateTo)}`;
}

/** Every month between the earliest selectable date and this month, newest first - the
 *  jump-to-month dropdown above the calendar. */
function monthOptions(earliest: Date, latest: Date): Date[] {
  const out: Date[] = [];
  let cursor = startOfMonth(latest);
  const floor = startOfMonth(earliest);
  while (!isBefore(cursor, floor)) {
    out.push(cursor);
    cursor = addMonths(cursor, -1);
  }
  return out;
}

/** Looker-style range picker: preset list on the left, a month calendar on the right.
 *
 *  Nothing is committed until **Apply**. The previous version fired ``onChange`` on every
 *  keystroke and every preset click, so each interaction rewrote the URL and refetched every
 *  chart on the page - which is what made picking a range feel jumpy. Here the popover owns
 *  a private draft and the page sees exactly one update.
 */
export function DateRangePicker({
  preset,
  dateFrom,
  dateTo,
  compare,
  onChange,
}: DateRangeValue & { onChange: (value: DateRangeValue) => void }) {
  const [open, setOpen] = useState(false);

  const [draftPreset, setDraftPreset] = useState<DatePreset>(preset);
  const [draftFrom, setDraftFrom] = useState(dateFrom);
  const [draftTo, setDraftTo] = useState(dateTo);
  const [draftCompare, setDraftCompare] = useState(compare);
  const [phase, setPhase] = useState<Phase>("start");
  const [viewMonth, setViewMonth] = useState<Date>(() => startOfMonth(new Date()));

  // Re-seed the draft every time the popover opens, so an abandoned edit is discarded and a
  // range applied elsewhere (a saved view, the back button) shows up correctly.
  useEffect(() => {
    if (!open) return;
    setDraftPreset(preset);
    setDraftFrom(dateFrom);
    setDraftTo(dateTo);
    setDraftCompare(compare);
    setPhase("start");
    setViewMonth(startOfMonth(fromIso(dateTo) ?? new Date()));
  }, [open, preset, dateFrom, dateTo, compare]);

  const today = useMemo(() => new Date(), []);
  const from = fromIso(draftFrom);
  const to = fromIso(draftTo);
  const rangeValid = from !== null && to !== null && !isAfter(from, to);

  const days = useMemo(
    () =>
      eachDayOfInterval({
        start: startOfWeek(startOfMonth(viewMonth)),
        end: endOfWeek(endOfMonth(viewMonth)),
      }),
    [viewMonth],
  );

  const months = useMemo(() => {
    const earliest = fromIso(ALL_TIME_START) ?? new Date(2020, 0, 1);
    const floor = from !== null && isBefore(from, earliest) ? from : earliest;
    return monthOptions(floor, today);
  }, [from, today]);

  const canGoBack = months.length > 0 && !isSameMonth(viewMonth, months[months.length - 1]);
  const canGoForward = !isSameMonth(viewMonth, today) && isBefore(viewMonth, today);

  function applyPreset(key: Exclude<DatePreset, "custom">): void {
    const range = presetRange(key);
    setDraftPreset(key);
    setDraftFrom(range.from);
    setDraftTo(range.to);
    setPhase("start");
    setViewMonth(startOfMonth(fromIso(range.to) ?? today));
  }

  function pickDay(day: Date): void {
    if (isAfter(day, today)) return; // no data ahead of today
    const value = iso(day);
    setDraftPreset("custom");
    if (phase === "start" || from === null || isBefore(day, from)) {
      setDraftFrom(value);
      setDraftTo(value);
      setPhase("end");
    } else {
      setDraftTo(value);
      setPhase("start");
    }
  }

  function commit(): void {
    if (!rangeValid) return;
    onChange({
      preset: draftPreset,
      dateFrom: draftFrom,
      dateTo: draftTo,
      compare: draftCompare,
    });
    setOpen(false);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <CalendarDays className="h-4 w-4 opacity-70" />
          {triggerLabel({ preset, dateFrom, dateTo, compare })}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[34rem] p-0" align="start">
        <div className="flex">
          {/* ── Presets ─────────────────────────────────────────── */}
          <div className="w-44 shrink-0 border-r p-2">
            {PRESET_LABELS.map((p) => (
              <button
                key={p.key}
                type="button"
                className={cn(
                  "block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-accent",
                  draftPreset === p.key && "bg-accent font-medium",
                )}
                onClick={() => applyPreset(p.key)}
              >
                {p.label}
              </button>
            ))}
            <div className="my-1 border-t" />
            <button
              type="button"
              className={cn(
                "block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-accent",
                draftPreset === "custom" ? "bg-accent font-medium" : "text-muted-foreground",
              )}
              onClick={() => {
                setDraftPreset("custom");
                setPhase("start");
              }}
            >
              Custom
            </button>
          </div>

          {/* ── Range + calendar ────────────────────────────────── */}
          <div className="flex-1 p-3">
            <div className="flex items-start gap-2">
              <div className="flex-1 space-y-1">
                <label htmlFor="range-start" className="text-xs text-muted-foreground">
                  Start date
                </label>
                <Input
                  id="range-start"
                  type="date"
                  aria-label="Start date"
                  className="h-8"
                  value={draftFrom}
                  max={draftTo || undefined}
                  onChange={(e) => {
                    setDraftPreset("custom");
                    setDraftFrom(e.target.value);
                    const parsed = fromIso(e.target.value);
                    if (parsed) setViewMonth(startOfMonth(parsed));
                  }}
                />
              </div>
              <span className="pt-6 text-muted-foreground">–</span>
              <div className="flex-1 space-y-1">
                <label htmlFor="range-end" className="text-xs text-muted-foreground">
                  End date
                </label>
                <Input
                  id="range-end"
                  type="date"
                  aria-label="End date"
                  className="h-8"
                  value={draftTo}
                  min={draftFrom || undefined}
                  max={iso(today)}
                  onChange={(e) => {
                    setDraftPreset("custom");
                    setDraftTo(e.target.value);
                    const parsed = fromIso(e.target.value);
                    if (parsed) setViewMonth(startOfMonth(parsed));
                  }}
                />
              </div>
              <button
                type="button"
                aria-label="Close date picker"
                className="mt-5 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                onClick={() => setOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Month navigation */}
            <div className="mt-3 flex items-center justify-between">
              <button
                type="button"
                aria-label="Previous month"
                disabled={!canGoBack}
                className="rounded p-1 hover:bg-accent disabled:opacity-30 disabled:hover:bg-transparent"
                onClick={() => setViewMonth(addMonths(viewMonth, -1))}
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <select
                aria-label="Jump to month"
                className="h-7 rounded border border-input bg-background px-2 text-sm"
                value={iso(viewMonth)}
                onChange={(e) => {
                  const parsed = fromIso(e.target.value);
                  if (parsed) setViewMonth(startOfMonth(parsed));
                }}
              >
                {months.map((m) => (
                  <option key={iso(m)} value={iso(m)}>
                    {format(m, "MMMM yyyy")}
                  </option>
                ))}
              </select>
              <button
                type="button"
                aria-label="Next month"
                disabled={!canGoForward}
                className="rounded p-1 hover:bg-accent disabled:opacity-30 disabled:hover:bg-transparent"
                onClick={() => setViewMonth(addMonths(viewMonth, 1))}
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>

            {/* Day grid */}
            <div className="mt-2 grid grid-cols-7 text-center text-xs text-muted-foreground">
              {WEEKDAYS.map((d, i) => (
                <div key={`${d}-${i}`} className="py-1">
                  {d}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7 text-center text-sm">
              {days.map((day) => {
                const outside = !isSameMonth(day, viewMonth);
                const future = isAfter(day, today);
                const isStart = from !== null && isSameDay(day, from);
                const isEnd = to !== null && isSameDay(day, to);
                const inRange =
                  rangeValid &&
                  from !== null &&
                  to !== null &&
                  !isBefore(day, from) &&
                  !isAfter(day, to);
                return (
                  <button
                    key={iso(day)}
                    type="button"
                    disabled={future}
                    aria-label={format(day, "d MMMM yyyy")}
                    aria-pressed={isStart || isEnd}
                    onClick={() => pickDay(day)}
                    className={cn(
                      "h-8 leading-8 transition-colors",
                      // The range band is drawn on the cell so consecutive days join up;
                      // the endpoints get the rounded pill.
                      inRange && !isStart && !isEnd && "bg-accent",
                      isStart && "rounded-l-md bg-primary text-primary-foreground",
                      isEnd && "rounded-r-md bg-primary text-primary-foreground",
                      isStart && isEnd && "rounded-md",
                      !inRange && !future && "hover:bg-accent hover:rounded-md",
                      outside && !inRange && "text-muted-foreground/50",
                      future && "cursor-not-allowed text-muted-foreground/30",
                    )}
                  >
                    {format(day, "d")}
                  </button>
                );
              })}
            </div>

            {/* Compare + actions */}
            <div className="mt-3 flex items-center gap-2 border-t pt-3">
              <Checkbox
                id="range-compare"
                checked={draftCompare}
                onCheckedChange={(checked) => setDraftCompare(checked === true)}
              />
              <label htmlFor="range-compare" className="cursor-pointer text-sm">
                Compare to previous period
              </label>
            </div>
            <div className="mt-3 flex items-center justify-end gap-2">
              {!rangeValid && (
                <span className="mr-auto text-xs text-destructive">
                  End date must be on or after the start date.
                </span>
              )}
              <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button size="sm" disabled={!rangeValid} onClick={commit}>
                Apply
              </Button>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
