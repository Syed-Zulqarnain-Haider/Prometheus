import {
  DEFAULT_ADJUSTMENTS,
  DEFAULT_CHART_TYPE,
  applyAdjustments,
  detectCapabilities,
  isAdjusted,
} from "@/lib/chart-adjust";
import type { EChartsOption } from "@/lib/echarts";

/** Loose read-back of a series' type, since EChartsOption's series union is enormous. */
function types(option: EChartsOption): string[] {
  const series = option.series;
  const list = Array.isArray(series) ? series : series == null ? [] : [series];
  return (list as { type?: string }[]).map((s) => s.type ?? "");
}

const lineChart: EChartsOption = {
  yAxis: { type: "value" },
  series: [
    { type: "line", name: "Revenue", data: [1, 2, 3] },
    { type: "line", name: "Spend", data: [4, 5, 6] },
  ],
};

const mixedChart: EChartsOption = {
  yAxis: { type: "value" },
  series: [
    { type: "bar", name: "Spend", data: [1, 2, 3] },
    { type: "scatter", name: "CPI", data: [[1, 2]] },
  ],
};

const pieChart: EChartsOption = {
  series: [{ type: "pie", name: "Mix", data: [{ value: 1, name: "a" }] }],
};

describe("bar is the house default", () => {
  it("defaults the chart type to bar", () => {
    expect(DEFAULT_CHART_TYPE).toBe("bar");
    expect(DEFAULT_ADJUSTMENTS.type).toBe("bar");
  });

  it("does not mark an untouched chart as modified", () => {
    // Otherwise every chart would wear the "adjusted" dot straight out of the box.
    expect(isAdjusted(DEFAULT_ADJUSTMENTS)).toBe(false);
  });

  it("reports a chart as modified once the viewer changes something", () => {
    expect(isAdjusted({ ...DEFAULT_ADJUSTMENTS, type: "line" })).toBe(true);
    expect(isAdjusted({ ...DEFAULT_ADJUSTMENTS, labels: true })).toBe(true);
  });

  it("renders an all-line chart as bars", () => {
    expect(types(applyAdjustments(lineChart, DEFAULT_ADJUSTMENTS))).toEqual(["bar", "bar"]);
  });

  it("drops the area fill when a line becomes a bar", () => {
    const area: EChartsOption = {
      series: [
        { type: "line", name: "A", areaStyle: {}, data: [1, 2] },
        { type: "line", name: "B", areaStyle: {}, data: [3, 4] },
      ],
    };
    const out = applyAdjustments(area, DEFAULT_ADJUSTMENTS);
    const list = out.series as { areaStyle?: unknown }[];
    expect(list.every((s) => s.areaStyle === undefined)).toBe(true);
  });

  it("lets the viewer switch back to the author's shape with Auto", () => {
    expect(types(applyAdjustments(lineChart, { ...DEFAULT_ADJUSTMENTS, type: "auto" }))).toEqual([
      "line",
      "line",
    ]);
  });

  it("leaves a deliberately mixed chart alone", () => {
    // canSwitchType is false here, so the type control is not offered either - converting it
    // would produce a chart the viewer could not switch back.
    expect(detectCapabilities(mixedChart).canSwitchType).toBe(false);
    expect(types(applyAdjustments(mixedChart, DEFAULT_ADJUSTMENTS))).toEqual(["bar", "scatter"]);
  });

  it("never converts a pie", () => {
    expect(types(applyAdjustments(pieChart, DEFAULT_ADJUSTMENTS))).toEqual(["pie"]);
  });

  it("does not mutate the option it was given", () => {
    const before = JSON.stringify(lineChart);
    applyAdjustments(lineChart, DEFAULT_ADJUSTMENTS);
    expect(JSON.stringify(lineChart)).toBe(before);
  });
});
