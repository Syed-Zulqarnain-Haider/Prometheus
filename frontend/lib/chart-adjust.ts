/** Generic, chart-agnostic adjustment logic shared by every chart.
 *
 * The dashboard's ~18 charts each hand-build an ECharts ``option``. Rather than rewrite
 * them, we let the shared ``Chart`` component derive what's adjustable from the option
 * itself and apply the viewer's tweaks as a pure transform. Defaults are all "auto"/off, so
 * an untouched chart renders EXACTLY as its author designed it - adjustments only ever layer
 * on top of an explicit user choice. Nothing here mutates the input option; a new object is
 * returned so React re-renders cleanly.
 */
import type { EChartsOption } from "@/lib/echarts";

export type TypeOverride = "auto" | "line" | "bar" | "area";
export type ScaleOverride = "auto" | "linear" | "log";
/** none = each series plotted independently; stacked = summed; percent = 100% stacked. */
export type StackMode = "none" | "stacked" | "percent";
/** A per-series data transform. Cumulative and average are mutually exclusive by design -
 *  a running total of a moving average answers no useful question. */
export type TransformMode = "none" | "cumulative" | "average";

/** Loose views of the ECharts option we manipulate. ECharts' own series/axis unions are
 *  enormous; we only touch a handful of well-known keys, so a narrow structural type keeps
 *  this honest without `any`. */
type SeriesRec = { type?: string; name?: string; areaStyle?: unknown; [k: string]: unknown };
type AxisRec = { type?: string; [k: string]: unknown };
/** One datum inside a series' ``data`` array: a bare number, an [x, y] pair, an
 *  ``{ value }`` object, or null for a gap. */
type Datum = unknown;

/** Series types that live on a cartesian grid and can be freely swapped between line/bar. */
const CARTESIAN = new Set(["line", "bar"]);

/** Longest moving-average window; shortened automatically for short series so a 7-day
 *  average over 4 points doesn't collapse into a flat line. */
const MAX_AVG_WINDOW = 7;

function asArray<T>(value: unknown): T[] {
  if (value == null) return [];
  return (Array.isArray(value) ? value : [value]) as T[];
}

function seriesOf(option: EChartsOption): SeriesRec[] {
  return asArray<SeriesRec>(option.series);
}

function isCartesian(s: SeriesRec): boolean {
  return typeof s.type === "string" && CARTESIAN.has(s.type);
}

// ── datum read/write ─────────────────────────────────────────────────────────
// Charts here use several datum shapes. Reading and writing through these helpers keeps
// every transform shape-preserving, so an [x, y] pair stays a pair and a category label
// on an { value } object survives.

function readValue(d: Datum): number | null {
  if (typeof d === "number") return Number.isFinite(d) ? d : null;
  if (d == null) return null;
  if (Array.isArray(d)) {
    const last: unknown = d[d.length - 1];
    return typeof last === "number" && Number.isFinite(last) ? last : null;
  }
  if (typeof d === "object" && "value" in (d as Record<string, unknown>)) {
    return readValue((d as { value: unknown }).value);
  }
  return null;
}

function writeValue(d: Datum, v: number | null): Datum {
  if (d == null || typeof d === "number") return v;
  if (Array.isArray(d)) {
    const copy: unknown[] = [...d];
    copy[copy.length - 1] = v;
    return copy;
  }
  if (typeof d === "object" && "value" in (d as Record<string, unknown>)) {
    const rec = d as Record<string, unknown>;
    return { ...rec, value: writeValue(rec.value, v) };
  }
  return d;
}

function round(n: number, dp: number): number {
  const f = 10 ** dp;
  return Math.round(n * f) / f;
}

// ── capabilities ─────────────────────────────────────────────────────────────

export interface ChartCapabilities {
  /** Line/Bar/Area switching - offered only when EVERY series is cartesian (line|bar). */
  canSwitchType: boolean;
  /** Linear/Log y-axis - offered only when a value axis exists on a cartesian chart. */
  canScale: boolean;
  /** Names of series the viewer can show/hide (only when ≥2 are named). */
  seriesNames: string[];
  /** Stacking needs at least two cartesian series - stacking one is a no-op. */
  canStack: boolean;
  /** Value labels make sense on any cartesian series. */
  canLabel: boolean;
  /** Cumulative / moving average need cartesian series with readable numeric data. */
  canTransform: boolean;
  /** Every series is a plain line (no area fill). Used to grey out stacking, which is
   *  misleading on lines - the viewer should pick Bar or Area first. */
  baseAllLine: boolean;
}

/** Inspect an option and report which generic controls make sense for it. A pie or heatmap
 *  returns all-false / empty, so those charts show only the resize control. */
export function detectCapabilities(option: EChartsOption): ChartCapabilities {
  const series = seriesOf(option);
  const convertible = series.filter(isCartesian);
  const canSwitchType = series.length > 0 && convertible.length === series.length;

  const yAxes = asArray<AxisRec>(option.yAxis);
  const canScale = canSwitchType && yAxes.some((a) => a.type === "value");

  const names = series
    .map((s) => s.name)
    .filter((n): n is string => typeof n === "string" && n.length > 0);

  const hasNumericData = convertible.some((s) =>
    asArray<Datum>(s.data).some((d) => readValue(d) !== null),
  );

  return {
    canSwitchType,
    canScale,
    seriesNames: names.length >= 2 ? names : [],
    canStack: canSwitchType && series.length >= 2 && hasNumericData,
    canLabel: convertible.length > 0 && hasNumericData,
    canTransform: canSwitchType && hasNumericData,
    baseAllLine: series.length > 0 && series.every((s) => s.type === "line" && s.areaStyle == null),
  };
}

// ── adjustments ──────────────────────────────────────────────────────────────

export interface Adjustments {
  type: TypeOverride;
  scale: ScaleOverride;
  hidden: string[];
  stack: StackMode;
  labels: boolean;
  transform: TransformMode;
}

/** House default for every convertible chart. Owner decision: the dashboard reads as bars,
 *  not lines. "auto" (the chart author's own shape) is still one click away in the panel,
 *  and charts that mix types deliberately are left alone - see ``applyAdjustments``. */
export const DEFAULT_CHART_TYPE: TypeOverride = "bar";

export const DEFAULT_ADJUSTMENTS: Adjustments = {
  type: DEFAULT_CHART_TYPE,
  scale: "auto",
  hidden: [],
  stack: "none",
  labels: false,
  transform: "none",
};

/** Is any adjustment active? (Drives the "modified" dot on the control button.)
 *  Compared against the defaults rather than hardcoded "auto", so the house bar default
 *  doesn't light up every chart as "modified". */
export function isAdjusted(a: Adjustments): boolean {
  return (
    a.type !== DEFAULT_ADJUSTMENTS.type ||
    a.scale !== DEFAULT_ADJUSTMENTS.scale ||
    a.hidden.length > 0 ||
    a.stack !== DEFAULT_ADJUSTMENTS.stack ||
    a.labels !== DEFAULT_ADJUSTMENTS.labels ||
    a.transform !== DEFAULT_ADJUSTMENTS.transform
  );
}

/** Would stacking actually render as stacked? Lines are excluded - see ``baseAllLine``. */
export function stackApplies(caps: ChartCapabilities, type: TypeOverride): boolean {
  if (!caps.canStack) return false;
  if (type === "line") return false;
  if (type === "bar" || type === "area") return true;
  return !caps.baseAllLine; // "auto": stack unless the chart is drawn as plain lines
}

// ── transforms ───────────────────────────────────────────────────────────────

function cumulative(data: Datum[]): Datum[] {
  let acc = 0;
  return data.map((d) => {
    const v = readValue(d);
    if (v === null) return writeValue(d, null);
    acc += v;
    return writeValue(d, round(acc, 4));
  });
}

/** Trailing moving average. Leading points average over however many points exist, so the
 *  line starts at the first datum rather than after a gap. */
function movingAverage(data: Datum[], window: number): Datum[] {
  const values = data.map(readValue);
  return data.map((d, i) => {
    const slice = values
      .slice(Math.max(0, i - window + 1), i + 1)
      .filter((v): v is number => v !== null);
    if (slice.length === 0) return writeValue(d, null);
    return writeValue(d, round(slice.reduce((a, b) => a + b, 0) / slice.length, 4));
  });
}

function avgWindow(length: number): number {
  if (length <= 3) return 2;
  return Math.min(MAX_AVG_WINDOW, Math.max(2, Math.floor(length / 2)));
}

/** Rewrite every series as its share (0–100) of that index's total. Totals use absolute
 *  values so a negative series (e.g. a loss-making Profit) still yields sane shares. */
function toPercent(list: SeriesRec[]): SeriesRec[] {
  const datas = list.map((s) => asArray<Datum>(s.data));
  const length = datas.reduce((m, d) => Math.max(m, d.length), 0);
  const totals: number[] = [];
  for (let i = 0; i < length; i++) {
    let total = 0;
    for (const data of datas) {
      const v = readValue(data[i]);
      if (v !== null) total += Math.abs(v);
    }
    totals[i] = total;
  }
  return list.map((s, si) => ({
    ...s,
    data: datas[si].map((d, i) => {
      const v = readValue(d);
      const total = totals[i];
      if (v === null || !total) return writeValue(d, null);
      return writeValue(d, round((v / total) * 100, 1));
    }),
  }));
}

function retypeSeries(s: SeriesRec, target: Exclude<TypeOverride, "auto">): SeriesRec {
  if (!isCartesian(s)) return s; // leave pie/heatmap alone
  if (target === "area") return { ...s, type: "line", areaStyle: s.areaStyle ?? {} };
  const next: SeriesRec = { ...s, type: target };
  delete next.areaStyle; // line/bar: drop any area fill so the switch is clean
  return next;
}

function withLabels(s: SeriesRec, stacked: boolean, percent: boolean): SeriesRec {
  if (!isCartesian(s)) return s;
  return {
    ...s,
    label: {
      show: true,
      // Inside a stacked segment there is no room above the bar; elsewhere sit on top.
      position: stacked && s.type === "bar" ? "inside" : "top",
      fontSize: 10,
      ...(percent ? { formatter: "{c}%" } : {}),
    },
    // Dense daily series would otherwise print an unreadable wall of numbers.
    labelLayout: { hideOverlap: true },
  };
}

/** Apply the viewer's adjustments to a base option, returning a NEW option. */
export function applyAdjustments(option: EChartsOption, adj: Adjustments): EChartsOption {
  let series = seriesOf(option);

  if (adj.hidden.length > 0) {
    const hide = new Set(adj.hidden);
    series = series.filter((s) => !(typeof s.name === "string" && hide.has(s.name)));
  }

  // Transform values BEFORE stacking/percent so shares are computed on what's displayed.
  if (adj.transform !== "none") {
    series = series.map((s) => {
      if (!isCartesian(s)) return s;
      const data = asArray<Datum>(s.data);
      if (data.length === 0) return s;
      return {
        ...s,
        data:
          adj.transform === "cumulative"
            ? cumulative(data)
            : movingAverage(data, avgWindow(data.length)),
      };
    });
  }

  // Stacking only renders as stacked for bar/area - mirror the UI's rule here so a stale
  // adjustment can never silently produce a misleading stacked line chart.
  const caps = detectCapabilities(option);
  const stacking = adj.stack !== "none" && stackApplies(caps, adj.type);
  const percent = stacking && adj.stack === "percent";

  if (percent) series = toPercent(series);

  // Retype only when EVERY series is convertible. A chart that mixes types on purpose - bars
  // plus a trend or break-even line, or a scatter with an overlay - keeps the shape its
  // author gave it, and is exactly the chart whose type switcher we don't offer either
  // (``canSwitchType`` gates the control), so nothing becomes unswitchable.
  if (adj.type !== "auto" && caps.canSwitchType) {
    series = series.map((s) => retypeSeries(s, adj.type as Exclude<TypeOverride, "auto">));
  }

  if (stacking) {
    series = series.map((s) => (isCartesian(s) ? { ...s, stack: "total" } : s));
  }

  if (adj.labels) {
    series = series.map((s) => withLabels(s, stacking, percent));
  }

  let next: EChartsOption = { ...option, series: series as EChartsOption["series"] };

  // 100% stacked is a share, so the axis is pinned to 0–100% and log is meaningless.
  const scale: ScaleOverride = percent ? "linear" : adj.scale;

  if (scale !== "auto" || percent) {
    const targetType = scale === "log" ? "log" : "value";
    const mapAxis = (a: AxisRec): AxisRec => {
      if (a.type !== "value" && a.type !== "log") return a;
      if (!percent) return { ...a, type: targetType };
      const axisLabel =
        typeof a.axisLabel === "object" && a.axisLabel !== null
          ? (a.axisLabel as Record<string, unknown>)
          : {};
      return {
        ...a,
        type: "value",
        min: 0,
        max: 100,
        axisLabel: { ...axisLabel, formatter: "{value}%" },
      };
    };
    const yAxis = option.yAxis;
    if (Array.isArray(yAxis)) {
      next = { ...next, yAxis: (yAxis as AxisRec[]).map(mapAxis) as EChartsOption["yAxis"] };
    } else if (yAxis != null) {
      next = { ...next, yAxis: mapAxis(yAxis as AxisRec) as EChartsOption["yAxis"] };
    }
  }

  return next;
}
