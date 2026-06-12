"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";

/** Revenue-progress donut. Real data (actual ÷ admin-set target) lands with Step 7;
 *  until a target exists this shows an honest "target not set" state, never a fake %. */
export function RevenueProgress() {
  const targetSet = false; // wired to GET /api/v1/meta/targets in Step 7

  const option: EChartsOption = {
    series: [
      {
        type: "pie",
        radius: ["64%", "82%"],
        center: ["50%", "50%"],
        silent: true,
        label: { show: false },
        data: [{ value: 1, itemStyle: { color: token("--color-bg-elevated") } }],
      },
    ],
  };

  return (
    <ChartCard title="Revenue Progress to Target">
      <div className="relative">
        <Chart option={option} height={240} />
        {!targetSet && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className="font-display text-[length:var(--fs-stat)] text-muted-foreground">
              Target not set
            </span>
            <span className="mt-1 max-w-[12rem] text-xs text-muted-foreground">
              Set yearly &amp; monthly revenue targets in Admin (Step 7) to track real
              progress.
            </span>
          </div>
        )}
      </div>
    </ChartCard>
  );
}
