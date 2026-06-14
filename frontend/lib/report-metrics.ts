/** Client-side catalog of the additive measures a report can aggregate.
 *
 * Mirrors the backend's additive-measure registry (query_builder.ADDITIVE_MEASURES).
 * The picker is filtered to the metric groups the caller is permitted to see; the
 * server re-validates every column on save, so this is a UX convenience, not the
 * authorization boundary.
 */

export type MetricGroup =
  | "store_installs"
  | "ua_spend"
  | "ad_revenue"
  | "iap_revenue"
  | "attribution"
  | "profitability";

export interface ReportMetric {
  name: string;
  label: string;
  group: MetricGroup;
}

export const METRIC_GROUP_LABELS: Record<MetricGroup, string> = {
  store_installs: "Store installs",
  ua_spend: "UA spend",
  ad_revenue: "Ad revenue",
  iap_revenue: "IAP revenue",
  attribution: "Attribution",
  profitability: "Profitability",
};

export const REPORT_METRICS: ReportMetric[] = [
  // store_installs
  { name: "store_total_installs", label: "Total installs", group: "store_installs" },
  { name: "store_first_time_installs", label: "First-time installs", group: "store_installs" },
  { name: "store_organic_installs", label: "Organic installs", group: "store_installs" },
  { name: "store_redownloads", label: "Redownloads", group: "store_installs" },
  { name: "apple_restores", label: "Apple restores", group: "store_installs" },
  { name: "gp_uninstalls", label: "Play uninstalls", group: "store_installs" },
  // ua_spend
  { name: "total_ua_spend_usd", label: "Total UA spend", group: "ua_spend" },
  { name: "total_paid_installs", label: "Paid installs", group: "ua_spend" },
  { name: "fb_spend_usd", label: "Facebook spend", group: "ua_spend" },
  { name: "fb_paid_installs", label: "Facebook paid installs", group: "ua_spend" },
  { name: "fb_impressions", label: "Facebook impressions", group: "ua_spend" },
  { name: "fb_clicks", label: "Facebook clicks", group: "ua_spend" },
  { name: "fb_purchases", label: "Facebook purchases", group: "ua_spend" },
  { name: "fb_purchase_value", label: "Facebook purchase value", group: "ua_spend" },
  { name: "gads_spend_usd", label: "Google Ads spend", group: "ua_spend" },
  { name: "gads_paid_installs", label: "Google Ads paid installs", group: "ua_spend" },
  { name: "gads_impressions", label: "Google Ads impressions", group: "ua_spend" },
  { name: "gads_clicks", label: "Google Ads clicks", group: "ua_spend" },
  { name: "gads_conversions", label: "Google Ads conversions", group: "ua_spend" },
  { name: "gads_conversions_value", label: "Google Ads conversion value", group: "ua_spend" },
  { name: "mint_adv_spend_usd", label: "Mintegral spend", group: "ua_spend" },
  { name: "mint_adv_paid_installs", label: "Mintegral paid installs", group: "ua_spend" },
  { name: "mint_adv_impressions", label: "Mintegral impressions", group: "ua_spend" },
  { name: "mint_adv_clicks", label: "Mintegral clicks", group: "ua_spend" },
  // ad_revenue
  { name: "total_ad_revenue_usd", label: "Total ad revenue", group: "ad_revenue" },
  { name: "admob_revenue_usd", label: "AdMob revenue", group: "ad_revenue" },
  { name: "admob_impressions", label: "AdMob impressions", group: "ad_revenue" },
  { name: "applovin_revenue_usd", label: "AppLovin revenue", group: "ad_revenue" },
  { name: "applovin_impressions", label: "AppLovin impressions", group: "ad_revenue" },
  // iap_revenue
  { name: "total_iap_net_usd", label: "IAP net", group: "iap_revenue" },
  { name: "total_iap_gross_usd", label: "IAP gross", group: "iap_revenue" },
  { name: "apple_iap_net_usd", label: "Apple IAP net", group: "iap_revenue" },
  { name: "apple_iap_gross_usd", label: "Apple IAP gross", group: "iap_revenue" },
  { name: "apple_iap_purchases", label: "Apple IAP purchases", group: "iap_revenue" },
  { name: "apple_iap_refunds_usd", label: "Apple IAP refunds", group: "iap_revenue" },
  { name: "apple_fee_usd", label: "Apple fee", group: "iap_revenue" },
  { name: "gp_iap_net_usd", label: "Play IAP net", group: "iap_revenue" },
  { name: "gp_iap_gross_usd", label: "Play IAP gross", group: "iap_revenue" },
  { name: "gp_iap_refunds_usd", label: "Play IAP refunds", group: "iap_revenue" },
  { name: "gp_google_fee_usd", label: "Play fee", group: "iap_revenue" },
  // attribution
  { name: "adjust_installs", label: "Adjust installs", group: "attribution" },
  { name: "adjust_paid_installs", label: "Adjust paid installs", group: "attribution" },
  { name: "adjust_organic_installs", label: "Adjust organic installs", group: "attribution" },
  { name: "adjust_conversions", label: "Adjust conversions", group: "attribution" },
  { name: "adjust_reattributions", label: "Adjust reattributions", group: "attribution" },
  { name: "adjust_attribution", label: "Adjust attribution", group: "attribution" },
  // profitability
  { name: "total_revenue_usd", label: "Total revenue", group: "profitability" },
  { name: "profit_usd", label: "Profit", group: "profitability" },
];

const LABEL_BY_NAME = new Map(REPORT_METRICS.map((m) => [m.name, m.label]));

export function metricLabel(name: string): string {
  return LABEL_BY_NAME.get(name) ?? name;
}

/** The measures a caller may pick, grouped, given their permitted metric groups. */
export function permittedMetricsByGroup(
  metricGroups: string[],
): { group: MetricGroup; label: string; metrics: ReportMetric[] }[] {
  const allowed = new Set(metricGroups);
  const groups: MetricGroup[] = [
    "store_installs",
    "ua_spend",
    "ad_revenue",
    "iap_revenue",
    "attribution",
    "profitability",
  ];
  return groups
    .filter((g) => allowed.has(g))
    .map((g) => ({
      group: g,
      label: METRIC_GROUP_LABELS[g],
      metrics: REPORT_METRICS.filter((m) => m.group === g),
    }))
    .filter((entry) => entry.metrics.length > 0);
}
