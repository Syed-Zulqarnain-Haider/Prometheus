import { formatMultiplier, formatNumber, formatPercent, formatUSD } from "@/lib/format";

export type MetricKind = "usd" | "usd2" | "pct" | "mult" | "num";

export interface CompareMetric {
  field: string;
  label: string;
  kind: MetricKind;
  /** Whether an increase is an improvement - drives delta coloring (a CPI drop is green). */
  goodWhenUp: boolean;
}

/** The curated metric catalog shared by the A-vs-B table and the top-apps chart. RBAC
 *  filters columns server-side, so a metric the viewer cannot see is simply absent from the
 *  payload and its row/series is dropped - never zeroed. */
export const COMPARE_METRICS: CompareMetric[] = [
  { field: "total_revenue_usd", label: "Revenue", kind: "usd", goodWhenUp: true },
  { field: "total_ad_revenue_usd", label: "Ad revenue", kind: "usd", goodWhenUp: true },
  { field: "total_iap_net_usd", label: "IAP net revenue", kind: "usd", goodWhenUp: true },
  { field: "total_iap_gross_usd", label: "IAP gross revenue", kind: "usd", goodWhenUp: true },
  { field: "total_ua_spend_usd", label: "UA spend", kind: "usd", goodWhenUp: false },
  { field: "tech_cost_usd", label: "Tech cost", kind: "usd", goodWhenUp: false },
  { field: "net_revenue_usd", label: "Net revenue", kind: "usd", goodWhenUp: true },
  { field: "gross_profit_usd", label: "Gross profit", kind: "usd", goodWhenUp: true },
  { field: "profit_margin", label: "Profit %", kind: "pct", goodWhenUp: true },
  { field: "roas", label: "ROAS", kind: "mult", goodWhenUp: true },
  { field: "ad_roas", label: "Ad ROAS", kind: "mult", goodWhenUp: true },
  { field: "cpi", label: "CPI", kind: "usd2", goodWhenUp: false },
  { field: "store_total_installs", label: "Store installs", kind: "num", goodWhenUp: true },
  { field: "store_organic_installs", label: "Organic installs", kind: "num", goodWhenUp: true },
  { field: "total_paid_installs", label: "Paid installs", kind: "num", goodWhenUp: true },
  {
    field: "organic_install_share",
    label: "Organic share",
    kind: "pct",
    goodWhenUp: true,
  },
  // More uninstalls is worse, so the delta colours invert. The uninstall RATE is excluded
  // by owner decision; this is the raw count the store reports.
  { field: "gp_uninstalls", label: "Play uninstalls", kind: "num", goodWhenUp: false },
];

export function formatMetricValue(value: number | null | undefined, kind: MetricKind): string {
  if (value === null || value === undefined) return "-";
  switch (kind) {
    case "usd":
      return formatUSD(value, { compact: true });
    case "usd2":
      return formatUSD(value, { digits: 2 });
    case "pct":
      return formatPercent(value);
    case "mult":
      return formatMultiplier(value);
    case "num":
      return formatNumber(value);
  }
}
