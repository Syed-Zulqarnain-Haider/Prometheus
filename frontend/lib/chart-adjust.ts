/** Generic, chart-agnostic adjustment logic shared by every chart.
 *
 * The dashboard's ~18 charts each hand-build an ECharts ``option``. Rather than rewrite
 * them, we let the shared ``Chart`` component derive what's adjustable from the option
 * itself and apply the viewer's tweaks as a pure transform. Defaults are all "auto", so an
 * untouched chart renders EXACTLY as its author designed it — adjustments only ever layer on
 * top of an explicit user choice. Nothing here mutates the input option; a new object is
 * returned so React re-renders cleanly.
 */
import type { EChartsOption } from "@/lib/echarts";

export type TypeOverride = "auto" | "line" | "bar" | "area";
export type ScaleOverride = "auto" | "linear" | "log";

/** Loose views of the ECharts option we manipulate. ECharts' own series/axis unions are
 *  enormous; we only touch a handful of well-known keys, so a narrow structural type keeps
 *  this honest without `any`. */
type SeriesRec = { type?: string; name?: string; areaStyle?: unknown; [k: string]: unknown };
type AxisRec = { type?: string; [k: string]: unknown };

/** Series types that live on a cartesian grid and can be freely swapped between line/bar. */
const CARTESIAN = new Set(["line", "bar"]);

function asArray<T>(value: unknown): T[] {
  if (value == null) return [];
  return (Array.isArray(value) ? value : [value]) as T[];
}

function seriesOf(option: EChartsOption): SeriesRec[] {
  return asArray<SeriesRec>(option.series);
}

export interface ChartCapabilities {
  /** Line/Bar/Area switching — offered only when EVERY series is cartesian (line|bar). */
  canSwitchType: boolean;
  /** Linear/Log y-axis — offered only when a value axis exists on a cartesian chart. */
  canScale: boolean;
  /** Names of series the viewer can show/hide (only when ≥2 are named). */
  seriesNames: string[];
}

/** Inspect an option and report which generic controls make sense for it. A pie or heatmap
 *  returns all-false / empty, so those charts show only the resize control. */
export function detectCapabilities(option: EChartsOption): ChartCapabilities {
  const series = seriesOf(option);
  const convertible = series.filter((s) => typeof s.type === "string" && CARTESIAN.has(s.type));
  const canSwitchType = series.length > 0 && convertible.length === series.length;

  const yAxes = asArray<AxisRec>(option.yAxis);
  const canScale = canSwitchType && yAxes.some((a) => a.type === "value");

  const names = series
    .map((s) => s.name)
    .filter((n): n is string => typeof n === "string" && n.length > 0);

  return { canSwitchType, canScale, seriesNames: names.length >= 2 ? names : [] };
}

export interface Adjustments {
  type: TypeOverride;
  scale: ScaleOverride;
  hidden: string[];
}

export const DEFAULT_ADJUSTMENTS: Adjustments = { type: "auto", scale: "auto", hidden: [] };

/** Is any adjustment active? (Drives the "modified" dot on the control button.) */
export function isAdjusted(a: Adjustments): boolean {
  return a.type !== "auto" || a.scale !== "auto" || a.hidden.length > 0;
}

function retypeSeries(s: SeriesRec, target: Exclude<TypeOverride, "auto">): SeriesRec {
  if (typeof s.type !== "string" || !CARTESIAN.has(s.type)) return s; // leave pie/heatmap alone
  if (target === "area") return { ...s, type: "line", areaStyle: s.areaStyle ?? {} };
  const next: SeriesRec = { ...s, type: target };
  delete next.areaStyle; // line/bar: drop any area fill so the switch is clean
  return next;
}

/** Apply the viewer's adjustments to a base option, returning a NEW option. */
export function applyAdjustments(option: EChartsOption, adj: Adjustments): EChartsOption {
  let series = seriesOf(option);

  if (adj.hidden.length > 0) {
    const hide = new Set(adj.hidden);
    series = series.filter((s) => !(typeof s.name === "string" && hide.has(s.name)));
  }
  if (adj.type !== "auto") {
    series = series.map((s) => retypeSeries(s, adj.type as Exclude<TypeOverride, "auto">));
  }

  let next: EChartsOption = { ...option, series: series as EChartsOption["series"] };

  if (adj.scale !== "auto") {
    const targetType = adj.scale === "log" ? "log" : "value";
    const mapAxis = (a: AxisRec): AxisRec => (a.type === "value" ? { ...a, type: targetType } : a);
    const yAxis = option.yAxis;
    if (Array.isArray(yAxis)) {
      next = { ...next, yAxis: (yAxis as AxisRec[]).map(mapAxis) as EChartsOption["yAxis"] };
    } else if (yAxis != null) {
      next = { ...next, yAxis: mapAxis(yAxis as AxisRec) as EChartsOption["yAxis"] };
    }
  }

  return next;
}
