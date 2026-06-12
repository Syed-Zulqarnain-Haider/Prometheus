"use client";

import { Delta } from "@/components/overview/delta";
import { Chart } from "@/components/charts/chart";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { EChartsOption } from "@/lib/echarts";
import { token } from "@/lib/chart-helpers";

function sparklineOption(values: number[]): EChartsOption {
  return {
    grid: { top: 4, bottom: 4, left: 0, right: 0 },
    xAxis: { type: "category", show: false, data: values.map((_, i) => i) },
    yAxis: { type: "value", show: false, scale: true },
    tooltip: { show: false },
    series: [
      {
        type: "line",
        data: values,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.5, color: token("--chart-spark") },
        areaStyle: { color: token("--color-positive-soft"), opacity: 1 },
      },
    ],
  };
}

export function KpiCard({
  label,
  value,
  current,
  previous,
  spark,
  loading,
}: {
  label: string;
  value: string;
  current?: number | null;
  previous?: number | null;
  spark?: number[];
  loading?: boolean;
}) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          {label}
        </div>
        {loading ? (
          <Skeleton className="mt-2 h-8 w-28" />
        ) : (
          <div className="mt-1 font-display text-[length:var(--fs-kpi)] leading-tight">
            {value}
          </div>
        )}
        <div className="mt-1 flex items-center justify-between">
          {loading ? (
            <Skeleton className="h-4 w-16" />
          ) : (
            <Delta current={current} previous={previous} />
          )}
          {spark && spark.length > 1 && (
            <div className="w-24">
              <Chart option={sparklineOption(spark)} height={32} />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
