/* ============================================================================
   TERAFORT — CEO COMMAND CENTER · DATA
   ----------------------------------------------------------------------------
   ALL placeholder values live here so they're swappable in one place.
   Replace these arrays/objects with live data; the UI + charts re-read on
   render(). Nothing in the markup hard-codes a chart value.
   ============================================================================ */
window.DASH = {
  kpis: [
    { id: "gross-rev",  label: "Gross Revenue (MTD)", value: "$4,127,930",  delta: "+18.7%", dir: "up", note: "vs previous period", spark: "rev",   color: "var(--chart-spark)" },
    { id: "ua-spend",   label: "UA Spend (MTD)",      value: "$1,236,850",  delta: "+12.4%", dir: "up", note: "vs previous period", spark: "spend", color: "var(--chart-spark)" },
    { id: "net-rev",    label: "Net Revenue (MTD)",   value: "$2,891,080",  delta: "+21.3%", dir: "up", note: "vs previous period", spark: "net",   color: "var(--chart-spark)" },
    { id: "gp",         label: "Gross Profit (MTD)",  value: "$2,036,420",  delta: "+23.8%", dir: "up", note: "vs previous period", spark: "gp",    color: "var(--chart-spark)" },
    { id: "gp-pct",     label: "Gross Profit %",      value: "70.4%",       delta: "+1.6pp", dir: "up", note: "vs previous period", spark: "gppct", color: "var(--chart-spark)" },
    { id: "cash",       label: "Cash in Bank",        value: "$12,450,000", sub: "Runway: 18.6 Months", spark: "cash", color: "var(--chart-spark-cash)" },
  ],

  // sparkline series (0..1 normalized-ish; renderer auto-scales)
  sparks: {
    rev:   [12,14,13,16,18,17,20,19,22,24,23,27,29,31,30,34],
    spend: [20,19,22,21,24,23,25,24,27,26,29,28,31,30,33,35],
    net:   [10,12,11,14,13,16,15,18,17,20,22,21,24,26,25,29],
    gp:    [8,10,9,12,14,13,16,18,17,20,19,23,25,24,27,30],
    gppct: [60,61,62,61,63,64,63,65,66,65,67,68,67,69,70,70.4],
    cash:  [40,42,41,44,46,45,48,47,50,52,51,49,53,55,57,60],
  },

  revenueTarget: {
    pct: 35.6,
    ytd: "$35,610,500",
    remaining: "$64,389,500",
    targetDate: "Dec 31, 2025",
  },

  monthlyTrend: {
    // 12 months actual revenue ($M); null = future (dimmed)
    revenue: [3.1, 3.6, 4.2, 5.0, 5.8, 6.6, 7.4, 8.1, 8.9, 9.7, 10.5, 11.3],
    target:  [3.0, 3.9, 4.6, 5.4, 6.1, 6.9, 7.6, 8.4, 9.1, 9.9, 10.6, 11.4],
    actualThrough: 5, // index of last actual (Jun bars dim after)
    months: ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
    yMax: 12,
  },

  keyRatios: [
    { label: "LTV / CPI",     value: "2.45", delta: "+0.32", dir: "up" },
    { label: "ROAS (D30)",    value: "184%", delta: "+14%",  dir: "up" },
    { label: "ROAS (D90)",    value: "265%", delta: "+18%",  dir: "up" },
    { label: "AVG CPI",       value: "$1.32", delta: "-0.08", dir: "down" },
    { label: "AVG LTV",       value: "$3.24", delta: "+0.21", dir: "up" },
    { label: "PAYBACK (DAYS)",value: "48",    delta: "-6",    dir: "down" },
  ],

  products: [
    { name: "Merge Meta Narrative", initial: "M", icon: "#7c5cff", cat: "GAME",      catClass: "game",     rev: "$1,246,870", growth: "+28.4%", gdir: "up",   gp: "76%", status: "SCALE",     dau: "152K", mau: "1.02M" },
    { name: "Word Voyage",          initial: "W", icon: "#2b8c6a", cat: "GAME",      catClass: "game",     rev: "$678,230",   growth: "+15.2%", gdir: "up",   gp: "72%", status: "SCALE",     dau: "98K",  mau: "620K" },
    { name: "FitFlow",              initial: "F", icon: "#e8643c", cat: "HEALTH",    catClass: "health",   rev: "$445,120",   growth: "+8.1%",  gdir: "up",   gp: "68%", status: "IMPROVE",   dau: "76K",  mau: "410K" },
    { name: "Pocket Budget",        initial: "P", icon: "#2f7ff0", cat: "FINANCE",   catClass: "finance",  rev: "$312,440",   growth: "+5.4%",  gdir: "up",   gp: "65%", status: "IMPROVE",   dau: "64K",  mau: "365K" },
    { name: "Sleep Well",           initial: "S", icon: "#5b6bd6", cat: "LIFESTYLE", catClass: "lifestyle",rev: "$120,410",   growth: "-6.3%",  gdir: "down", gp: "40%", status: "REVIEW",    dau: "22K",  mau: "150K" },
    { name: "Battle Quest",         initial: "B", icon: "#c0476a", cat: "GAME",      catClass: "game",     rev: "$0",         growth: "–",      gdir: "flat", gp: "–",   status: "PROTOTYPE", dau: "–",    mau: "–" },
  ],

  uaPerformance: {
    metrics: [
      { label: "UA Spend",  value: "$1,236,850", delta: "+12.4%", dir: "up" },
      { label: "Installs",  value: "935,210",    delta: "+15.7%", dir: "up" },
      { label: "Avg CPI",   value: "$1.32",      delta: "-0.08",  dir: "down" },
      { label: "LTV / CPI", value: "2.45",       delta: "+0.32",  dir: "up" },
    ],
    // 28 days
    spend:    [62,70,58,80,74,66,90,72,85,95,78,120,88,76,92,84,70,98,82,74,88,80,72,90,84,68,78,86],
    installs: [48,55,44,62,58,50,70,56,66,74,60,92,68,58,72,66,54,76,64,58,68,62,56,70,66,52,60,68],
    cpi:      [1.30,1.28,1.34,1.29,1.31,1.33,1.27,1.32,1.30,1.26,1.34,1.22,1.31,1.33,1.29,1.32,1.35,1.28,1.31,1.34,1.30,1.32,1.33,1.29,1.31,1.36,1.33,1.32],
    xticks: { "Apr 28": 0, "May 5": 7, "May 12": 14, "May 19": 21, "May 25": 27 },
  },

  productHealth: [
    { label: "DAU",          value: "412K",   delta: "+11.3%", dir: "up" },
    { label: "MAU",          value: "2.45M",  delta: "+13.6%", dir: "up" },
    { label: "DAU / MAU",    value: "16.8%",  delta: "+0.8pp", dir: "up" },
    { label: "D1 Retention", value: "28.4%",  delta: "+1.9pp", dir: "up" },
    { label: "D7 Retention", value: "12.6%",  delta: "+1.2pp", dir: "up" },
    { label: "D30 Retention",value: "5.3%",   delta: "+0.6pp", dir: "up" },
    { label: "Avg Rating",   value: "4.45",   delta: "+0.08",  dir: "up" },
    { label: "Reviews (MTD)",value: "18,642", delta: "+15.2%", dir: "up" },
  ],

  factory: {
    steps: [
      { label: "Ideas",      value: "250", icon: "bulb" },
      { label: "Prototypes", value: "40",  icon: "box" },
      { label: "Testing",    value: "20",  icon: "flask" },
      { label: "Shipped",    value: "5",   icon: "ship" },
      { label: "Killed",     value: "15",  icon: "kill", killed: true },
    ],
    successRate: 0.32,
    benchmark: "Benchmark: 20%+",
  },

  alerts: [
    { dot: "positive", text: "Merge Meta Narrative hit key milestone: $1M+ revenue in May" },
    { dot: "info",     text: "LTV/CPI improved by 0.32 this month" },
    { dot: "warn",     text: "Sleep Well retention dropping – needs immediate attention" },
    { dot: "info",     text: "2 new prototypes ready for market testing" },
    { dot: "positive", text: "Cash runway increased to 18.6 months" },
  ],

  nav: [
    { label: "CEO Dashboard", icon: "grid", header: true },
    { label: "Overview", icon: "home", active: true },
    { label: "Finance", icon: "bank" },
    { label: "UA Marketing", icon: "target" },
    { label: "Products", icon: "stack" },
    { label: "Product Factory", icon: "factory" },
    { label: "User Analytics", icon: "users" },
    { label: "AI & Operations", icon: "spark" },
    { label: "Executive", icon: "person" },
    { label: "Reports", icon: "doc" },
    { label: "Alerts", icon: "bell" },
  ],
};
