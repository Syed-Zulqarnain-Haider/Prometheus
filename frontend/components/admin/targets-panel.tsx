"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSetTarget, useTargets } from "@/lib/api-hooks";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = [CURRENT_YEAR - 1, CURRENT_YEAR, CURRENT_YEAR + 1];

function numberOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed.replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

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

  useEffect(() => {
    setAnnual(initial.annual);
    setMonths(initial.months);
  }, [initial]);

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
        <div className="max-w-xs space-y-1">
          <Label htmlFor="annual-target">Annual target (USD)</Label>
          <Input
            id="annual-target"
            inputMode="numeric"
            value={annual}
            onChange={(event) => setAnnual(event.target.value)}
            placeholder="e.g. 1200000"
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {MONTHS.map((label, index) => {
            const month = index + 1;
            return (
              <div key={month} className="space-y-1">
                <Label htmlFor={`m-${month}`}>{label}</Label>
                <Input
                  id={`m-${month}`}
                  inputMode="numeric"
                  value={months[month] ?? ""}
                  onChange={(event) =>
                    setMonths((current) => ({ ...current, [month]: event.target.value }))
                  }
                  placeholder="—"
                />
              </div>
            );
          })}
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
