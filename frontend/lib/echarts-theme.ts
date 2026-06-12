/** Builds an ECharts theme from the live Swiss Ledger CSS tokens, so charts match
 *  the active dark/light mode exactly. Tokens are read at render time. */

export interface ChartTokens {
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  border: string;
  grid: string;
  card: string;
  bar: string;
  bar2: string;
  spark: string;
  sparkCash: string;
  target: string;
  lineCpi: string;
  gradFrom: string;
  gradTo: string;
  accent: string;
  positive: string;
  negative: string;
  amber: string;
  purple: string;
  fontFamily: string;
}

/** Read the current token values from :root (client-side only). */
export function readChartTokens(): ChartTokens {
  const style = getComputedStyle(document.documentElement);
  const get = (name: string): string => style.getPropertyValue(name).trim();
  return {
    textPrimary: get("--color-text-primary"),
    textSecondary: get("--color-text-secondary"),
    textMuted: get("--color-text-muted"),
    border: get("--color-border"),
    grid: get("--chart-grid"),
    card: get("--color-bg-card"),
    bar: get("--chart-bar"),
    bar2: get("--chart-bar-2"),
    spark: get("--chart-spark"),
    sparkCash: get("--chart-spark-cash"),
    target: get("--chart-target"),
    lineCpi: get("--chart-line-cpi"),
    gradFrom: get("--chart-grad-from"),
    gradTo: get("--chart-grad-to"),
    accent: get("--color-accent"),
    positive: get("--color-positive"),
    negative: get("--color-negative"),
    amber: get("--color-amber"),
    purple: get("--color-purple"),
    fontFamily: get("--font-sans") || "sans-serif",
  };
}

/** Assemble an ECharts theme object from tokens. */
export function buildEChartsTheme(t: ChartTokens): Record<string, unknown> {
  const axisCommon = {
    axisLine: { lineStyle: { color: t.border } },
    axisTick: { show: false },
    axisLabel: { color: t.textMuted, fontFamily: t.fontFamily },
    splitLine: { lineStyle: { color: t.grid } },
  };

  return {
    color: [t.bar, t.spark, t.sparkCash, t.amber, t.purple, t.positive, t.negative],
    backgroundColor: "transparent",
    textStyle: { fontFamily: t.fontFamily, color: t.textSecondary },
    title: {
      textStyle: { color: t.textPrimary, fontFamily: t.fontFamily },
      subtextStyle: { color: t.textMuted },
    },
    legend: { textStyle: { color: t.textSecondary, fontFamily: t.fontFamily } },
    tooltip: {
      backgroundColor: t.card,
      borderColor: t.border,
      borderWidth: 1,
      textStyle: { color: t.textPrimary, fontFamily: t.fontFamily },
    },
    grid: { borderColor: t.border, containLabel: true },
    categoryAxis: axisCommon,
    valueAxis: axisCommon,
    logAxis: axisCommon,
    timeAxis: axisCommon,
    line: { symbol: "none", lineStyle: { width: 2 } },
    bar: { itemStyle: { borderRadius: [2, 2, 0, 0] } },
    visualMap: { textStyle: { color: t.textSecondary } },
    dataZoom: {
      borderColor: t.border,
      textStyle: { color: t.textMuted },
    },
  };
}

export const ECHARTS_THEME_NAME = "swiss-ledger";
