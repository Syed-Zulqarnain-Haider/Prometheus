/** DEMO DATA — placeholder series for the Overview's demo-only widgets.
 *
 *  NONE of this is real. Every value here is fabricated for visual completeness
 *  and is gated by `SHOW_DEMO_WIDGETS` + a `<DemoBadge />`. See docs/DESIGN.md §3
 *  for each widget's would-be real source. Widgets MUST import their data from
 *  this module and from nowhere else.
 */

export interface DemoSeriesPoint {
  label: string;
  value: number;
}

export const demoData = {
  cashRunway: {
    cashUsd: 18_400_000,
    runwayMonths: 23,
    burnUsd: 800_000,
  },
  ltv: {
    ltvUsd: 42.18,
    cacUsd: 19.6,
    ltvCacRatio: 2.15,
  },
  cohortRoas: {
    d30: 0.62,
    d90: 1.18,
    curve: [
      { label: "D0", value: 0.18 },
      { label: "D7", value: 0.41 },
      { label: "D30", value: 0.62 },
      { label: "D60", value: 0.94 },
      { label: "D90", value: 1.18 },
    ] satisfies DemoSeriesPoint[],
  },
  payback: {
    days: 74,
  },
  dauMau: {
    dau: 312_400,
    mau: 1_240_000,
    stickiness: 0.252,
  },
  retention: {
    d1: 0.41,
    d7: 0.19,
    d30: 0.08,
    curve: [
      { label: "D1", value: 0.41 },
      { label: "D7", value: 0.19 },
      { label: "D14", value: 0.12 },
      { label: "D30", value: 0.08 },
    ] satisfies DemoSeriesPoint[],
  },
  ratings: {
    average: 4.6,
    reviews: 128_400,
  },
  productFactory: {
    pipeline: [
      { label: "Ideas", value: 24 },
      { label: "Prototype", value: 9 },
      { label: "Soft launch", value: 4 },
      { label: "Scale", value: 2 },
      { label: "Killed", value: 11 },
    ] satisfies DemoSeriesPoint[],
  },
  alerts: [
    { severity: "positive", text: "Portfolio ROAS up 8% week-over-week" },
    { severity: "warn", text: "App 'Nimbus' CPI exceeded target by 22%" },
    { severity: "info", text: "Apple revenue lag: 2 apps zero-filled today" },
  ] as { severity: "positive" | "warn" | "info"; text: string }[],
};
