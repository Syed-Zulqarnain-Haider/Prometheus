import { PageHeader } from "@/components/layout/page-header";

interface Term {
  name: string;
  desc: string;
}
interface Group {
  title: string;
  note?: string;
  terms: Term[];
}

// Grounded in backend/app/core/metric_registry.py and the CLAUDE.md contract rules. This is a
// human reference, so it explains the WHY (reported vs modeled, exclusions) — not every column.
const GLOSSARY: Group[] = [
  {
    title: "Reading the numbers: Reported vs Modeled",
    note: "The two families of figures and when to trust which.",
    terms: [
      {
        name: "Reported (rpt_*)",
        desc: "Finance-authoritative totals computed upstream and passed straight through — e.g. rpt_gross_revenue_usd, rpt_net_profit_usd, rpt_total_cost_usd. These are the headline KPIs on the Overview. Use them for reporting.",
      },
      {
        name: "Modeled",
        desc: "Platform-computed figures from the raw signals (total_revenue_usd, total_ua_spend_usd, profit_usd). Useful for drill-downs and per-app analysis where a reported breakdown isn't available.",
      },
    ],
  },
  {
    title: "Revenue",
    note: "total_revenue_usd = total_iap_net_usd + total_ad_revenue_usd.",
    terms: [
      { name: "IAP revenue", desc: "In-app purchase revenue, net of refunds and store fees (gp_iap_net_usd + apple_iap_net_usd → total_iap_net_usd)." },
      { name: "Ad revenue", desc: "AdMob + AppLovin only. The Mintegral publisher is EXCLUDED by design — it double-counts inside AdMob mediation. This is intentional, not a bug." },
      { name: "Reported ladder", desc: "The full P&L: gross revenue → costs, taxes, fees, partner shares → net profit, and Terafort's retained net revenue (rpt_net_revenue_terafort_usd)." },
    ],
  },
  {
    title: "User acquisition (UA)",
    terms: [
      { name: "total_ua_spend_usd", desc: "Total paid marketing spend across Facebook, Google Ads, and Mintegral (advertiser)." },
      { name: "Paid installs", desc: "Installs attributed to paid campaigns (fb/gads/mint_adv). Organic installs are tracked separately." },
      { name: "CPI", desc: "Cost per install = spend ÷ paid installs. Per-network variants: fb_cpi, gads_cpi, mint_adv_cpi." },
      { name: "CTR", desc: "Click-through rate = clicks ÷ impressions, per network." },
    ],
  },
  {
    title: "Store & installs",
    terms: [
      { name: "store_total_installs", desc: "Total store installs (first-time + redownloads)." },
      { name: "organic_install_share", desc: "Organic installs ÷ total installs." },
      { name: "gp_uninstalls", desc: "Google Play uninstalls (raw count). The uninstall RATE is intentionally excluded in v1." },
    ],
  },
  {
    title: "Profitability & efficiency",
    terms: [
      { name: "profit_usd", desc: "total_revenue_usd − total_ua_spend_usd (modeled)." },
      { name: "ROAS", desc: "Return on ad spend = total_revenue_usd ÷ total_ua_spend_usd. ad_roas uses ad revenue only." },
      { name: "eCPM", desc: "Effective revenue per 1,000 ad impressions (admob_ecpm, applovin_ecpm)." },
    ],
  },
  {
    title: "How derived metrics are computed",
    note: "ROAS, profit, CPI, eCPM, CTR and organic-share are computed at the data source (BigQuery), never in the app — so every surface shows the same number. SAFE_DIVIDE returns blank on a zero denominator (never a fake zero).",
    terms: [],
  },
  {
    title: "Data freshness",
    note: "Apple data lags ~2–3 days; the current day is often Adjust-only or zero-filled. Always check the 'data as of' banner. Zeros on the latest day are usually source lag, not real zeros.",
    terms: [],
  },
];

export default function GlossaryPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Metric glossary" />
      <p className="max-w-2xl text-sm text-muted-foreground">
        A quick reference for the metrics and conventions used across the dashboard. When a number
        looks surprising, this is the first place to check.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        {GLOSSARY.map((group) => (
          <section key={group.title} className="rounded-lg border bg-card p-4">
            <h2 className="text-sm font-semibold">{group.title}</h2>
            {group.note && <p className="mt-1 text-xs text-muted-foreground">{group.note}</p>}
            {group.terms.length > 0 && (
              <dl className="mt-3 space-y-2">
                {group.terms.map((t) => (
                  <div key={t.name}>
                    <dt className="text-sm font-medium">{t.name}</dt>
                    <dd className="text-sm text-muted-foreground">{t.desc}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
