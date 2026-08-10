"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSetTarget, useTargets } from "@/lib/api-hooks";
import { formatUSD } from "@/lib/format";
import {
  MONTH_NUMBERS,
  numberOrNull,
  redistribute,
  sumCents,
  toCents,
} from "@/lib/target-split";
import { cn } from "@/lib/utils";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = [CURRENT_YEAR - 1, CURRENT_YEAR, CURRENT_YEAR + 1];

export function TargetsPanel() {
  const [year, setYear] = useState(CURRENT_YEAR);
  const { data } = useTargets(year);
  const setTarget = useSetTarget();

  const initial = useMemo(() => {
    const months: Record<number, string> = {};
    for (const m of data?.monthly ?? []) {
      if (m.period_month) months[m.period_month] = String(m.target_usd);
    }
    return { annual: data?.annual ? String(data.annual.target_usd) : "", months };
  }, [data]);

  const [annual, setAnnual] = useState("");
  const [months, setMonths] = useState<Record<number, string>>({});
  // Months the user has typed into. These are held fixed and the rest absorb the difference.
  const [manual, setManual] = useState<Set<number>>(new Set());

  useEffect(() => {
    setAnnual(initial.annual);
    setMonths(initial.months);
    // Every stored month counts as manual on load, so opening the page never silently
    // rewrites targets somebody already saved. Redistribution starts on the first edit.
    setManual(new Set(MONTH_NUMBERS.filter((m) => (initial.months[m] ?? "") !== "")));
  }, [initial]);

  /** Typing an annual target re-splits the whole year and drops every manual override -
   *  "distribute this across the months" is the intent of entering it. */
  function onAnnualChange(value: string): void {
    setAnnual(value);
    const cleared = new Set<number>();
    setManual(cleared);
    setMonths((current) => redistribute(value, current, cleared));
  }

  /** Typing a month fixes that month and lets the others absorb the difference. Clearing it
   *  hands it back to the automatic split.
   *
   *  `nextManual` is computed OUTSIDE the state updaters: an updater must be pure, and
   *  React StrictMode double-invokes them - a `setMonths` fired from inside the `setManual`
   *  updater would redistribute twice per keystroke. */
  function onMonthChange(month: number, value: string): void {
    const nextManual = new Set(manual);
    if (value.trim() === "") nextManual.delete(month);
    else nextManual.add(month);
    setManual(nextManual);
    setMonths((current) => redistribute(annual, { ...current, [month]: value }, nextManual));
  }

  function distributeEvenly(): void {
    const cleared = new Set<number>();
    setManual(cleared);
    setMonths((current) => redistribute(annual, current, cleared));
  }

  const annualCents = toCents(annual);
  const monthsCents = sumCents(months);
  const difference = annualCents === null ? null : monthsCents - annualCents;

  async function saveAll() {
    const annualValue = numberOrNull(annual);
    if (annualValue !== null && annual !== initial.annual) {
      await setTarget.mutateAsync({
        period_type: "year",
        period_year: year,
        target_usd: annualValue,
      });
    }
    for (let m = 1; m <= 12; m += 1) {
      const value = numberOrNull(months[m] ?? "");
      if (value !== null && (months[m] ?? "") !== (initial.months[m] ?? "")) {
        await setTarget.mutateAsync({
          period_type: "month",
          period_year: year,
          period_month: m,
          target_usd: value,
        });
      }
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
          Revenue targets
        </CardTitle>
        <div className="flex items-center gap-2">
          {YEAR_OPTIONS.map((option) => (
            <Button
              key={option}
              variant={option === year ? "default" : "outline"}
              size="sm"
              onClick={() => setYear(option)}
            >
              {option}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="max-w-xs flex-1 space-y-1">
            <Label htmlFor="annual-target">Annual target (USD)</Label>
            <Input
              id="annual-target"
              inputMode="numeric"
              value={annual}
              onChange={(event) => onAnnualChange(event.target.value)}
              placeholder="e.g. 1200000"
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={distributeEvenly}
            disabled={annualCents === null}
            title="Split the annual target evenly across all twelve months and clear every manual value"
          >
            Distribute evenly
          </Button>
        </div>

        <p className="text-xs text-muted-foreground">
          Entering an annual target splits it across the twelve months. Edit any month and the
          months you have not touched absorb the difference, so the twelve always add up to the
          annual figure. Clear a month to hand it back to the automatic split.
        </p>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {MONTHS.map((label, index) => {
            const month = index + 1;
            const isManual = manual.has(month);
            return (
              <div key={month} className="space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor={`m-${month}`}>{label}</Label>
                  {isManual && (
                    <button
                      type="button"
                      className="text-[10px] uppercase tracking-wider text-muted-foreground hover:text-foreground"
                      title="This month is fixed. Click to hand it back to the automatic split."
                      onClick={() => onMonthChange(month, "")}
                    >
                      manual
                    </button>
                  )}
                </div>
                <Input
                  id={`m-${month}`}
                  inputMode="numeric"
                  value={months[month] ?? ""}
                  onChange={(event) => onMonthChange(month, event.target.value)}
                  placeholder="-"
                  className={cn(isManual && "border-primary/60")}
                />
              </div>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-3 text-xs">
          <span className="text-muted-foreground">
            Months total <span className="font-medium text-foreground">{formatUSD(monthsCents / 100)}</span>
          </span>
          {annualCents !== null && (
            <>
              <span className="text-muted-foreground">
                Annual <span className="font-medium text-foreground">{formatUSD(annualCents / 100)}</span>
              </span>
              {difference === 0 ? (
                <span className="text-[color:var(--color-positive)]">matches</span>
              ) : (
                <span className="text-destructive">
                  {difference !== null && difference > 0 ? "over by " : "short by "}
                  {formatUSD(Math.abs(difference ?? 0) / 100)}
                </span>
              )}
            </>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button onClick={saveAll} disabled={setTarget.isPending}>
            {setTarget.isPending ? "Saving…" : "Save targets"}
          </Button>
          {setTarget.isError && (
            <span className="text-xs text-destructive">
              {setTarget.error instanceof Error ? setTarget.error.message : "Save failed."}
            </span>
          )}
          {setTarget.isSuccess && !setTarget.isPending && (
            <span className="text-xs text-muted-foreground">Saved.</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
