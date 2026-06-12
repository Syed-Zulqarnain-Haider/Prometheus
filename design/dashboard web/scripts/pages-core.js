/* ============================================================================
   PAGES — shared helpers + builders (part 1: Finance, UA, Products, Factory)
   ----------------------------------------------------------------------------
   Each builder returns { title, subtitle, node } where node is the page body
   (everything below the shared topbar). Charts are mounted directly into slots.
   All numbers are PLACEHOLDER data, kept inline per page for easy swapping.
   Reuses the same component classes as the Overview (cards, tables, badges…).
   ============================================================================ */
(function () {
  const C = window.CHARTS;
  const ic = window.icon;

  /* ---- tiny builders -------------------------------------------------- */
  function node(html) { const d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstElementChild; }
  function frag(html) { const d = document.createElement("div"); d.innerHTML = html; return d; }
  function delta(txt, dir) {
    const cls = dir === "down" ? "delta--down" : (dir === "flat" ? "" : "delta--up");
    const arrow = dir === "down" ? "▼" : (dir === "flat" ? "" : "▲");
    return `<span class="delta ${cls}">${arrow ? arrow + " " : ""}${txt}</span>`;
  }
  function kpi(label, value, d) {
    return `<article class="card kpi">
      <span class="kpi__label">${label}</span>
      <span class="kpi__value num">${value}</span>
      ${d ? delta(d.t, d.dir) + (d.note ? ` <span class="delta__note">${d.note}</span>` : "") : ""}
    </article>`;
  }
  function cardHead(title, sub) {
    return `<div class="card__head"><h2 class="card__title">${title}${sub ? ` <em>${sub}</em>` : ""}</h2></div>`;
  }
  // expose helpers for part 2
  window.PG = { node, frag, delta, kpi, cardHead, C, ic };

  const PAGES = (window.PAGES = window.PAGES || {});

  /* =====================================================================
     FINANCE
     ===================================================================== */
  PAGES.finance = function () {
    const root = frag(`
      <section class="kpi-row kpi-row--auto">
        ${kpi("Gross Revenue (MTD)", "$4,127,930", { t: "18.7%", dir: "up" })}
        ${kpi("Net Revenue (MTD)", "$2,891,080", { t: "21.3%", dir: "up" })}
        ${kpi("Gross Profit (MTD)", "$2,036,420", { t: "23.8%", dir: "up" })}
        ${kpi("EBITDA (MTD)", "$1,284,500", { t: "26.1%", dir: "up" })}
        ${kpi("Operating Expenses", "$751,920", { t: "4.2%", dir: "down" })}
        ${kpi("Net Margin", "44.4%", { t: "2.1pp", dir: "up" })}
      </section>

      <section class="grid-7-3">
        <article class="card">
          ${cardHead("Cash Flow", "(Net, last 12 months)")}
          <div class="chart" data-slot="cashflow"></div>
        </article>
        <article class="card">
          ${cardHead("Revenue Mix", "(by business line)")}
          <div data-slot="revmix"></div>
        </article>
      </section>

      <section class="grid-2-even">
        <article class="card">
          ${cardHead("Profit &amp; Loss", "(MTD)")}
          <div class="drow"><span class="drow__label">Gross Revenue</span><span class="drow__value num">$4,127,930</span></div>
          <div class="drow"><span class="drow__label">Platform &amp; Payment Fees</span><span class="drow__value num">−$1,236,850</span></div>
          <div class="drow"><span class="drow__label">Net Revenue</span><span class="drow__value num">$2,891,080</span></div>
          <div class="drow"><span class="drow__label">Cost of Revenue</span><span class="drow__value num">−$854,660</span></div>
          <div class="drow"><span class="drow__label">Gross Profit</span><span class="drow__value num">$2,036,420</span></div>
          <div class="drow"><span class="drow__label">Operating Expenses</span><span class="drow__value num">−$751,920</span></div>
          <div class="drow drow--total"><span class="drow__label">EBITDA</span><span class="drow__value num">$1,284,500</span></div>
        </article>
        <article class="card">
          ${cardHead("Operating Expense Breakdown")}
          <div data-slot="opex"></div>
        </article>
      </section>
    `);

    root.querySelector("[data-slot=cashflow]").appendChild(C.line({
      labels: ["Jun","Jul","Aug","Sep","Oct","Nov","Dec","Jan","Feb","Mar","Apr","May"],
      yMax: 3, unit: "M", fmt: (v) => "$" + v.toFixed(0),
      series: [{ name: "Net Cash Flow", data: [1.2,1.4,1.3,1.6,1.5,1.8,1.7,1.9,2.0,2.2,2.1,2.4], color: "var(--color-positive)", area: true }],
    }));
    root.querySelector("[data-slot=revmix]").appendChild(C.donutSegments([
      { label: "Games", value: 62, display: "62%", color: "var(--color-accent)" },
      { label: "Health & Fitness", value: 18, display: "18%", color: "var(--color-positive)" },
      { label: "Finance", value: 12, display: "12%", color: "var(--color-purple)" },
      { label: "Lifestyle", value: 8, display: "8%", color: "var(--color-amber)" },
    ], "$4.1M", "MTD"));
    root.querySelector("[data-slot=opex]").appendChild(C.hbars([
      { label: "User Acquisition", value: 1236, display: "$1.24M", color: "var(--color-accent)" },
      { label: "Salaries", value: 420, display: "$420K", color: "var(--color-purple)" },
      { label: "Infrastructure", value: 186, display: "$186K", color: "var(--color-positive)" },
      { label: "Tooling & SaaS", value: 92, display: "$92K", color: "var(--color-amber)" },
      { label: "Office & Admin", value: 54, display: "$54K", color: "var(--color-orange)" },
    ]));
    return { title: "FINANCE", subtitle: "P&L, cash flow and expense detail", node: root };
  };

  /* =====================================================================
     UA MARKETING
     ===================================================================== */
  PAGES.ua = function () {
    const D = window.DASH.uaPerformance;
    const root = frag(`
      <section class="kpi-row kpi-row--auto">
        ${kpi("UA Spend (MTD)", "$1,236,850", { t: "12.4%", dir: "up" })}
        ${kpi("Installs (MTD)", "935,210", { t: "15.7%", dir: "up" })}
        ${kpi("Avg CPI", "$1.32", { t: "0.08", dir: "down" })}
        ${kpi("Avg LTV", "$3.24", { t: "0.21", dir: "up" })}
        ${kpi("ROAS (D30)", "184%", { t: "14%", dir: "up" })}
        ${kpi("ROAS (D90)", "265%", { t: "18%", dir: "up" })}
      </section>

      <section class="grid-7-3">
        <article class="card">
          ${cardHead("Spend, Installs &amp; CPI", "(last 28 days)")}
          <div class="chart-legend" style="margin-bottom:8px">
            <span class="legend-item"><span class="legend-swatch" style="background:var(--chart-grad-from)"></span>UA Spend</span>
            <span class="legend-item"><span class="legend-swatch" style="background:var(--chart-grad-to)"></span>Installs</span>
            <span class="legend-item"><span class="legend-swatch legend-swatch--cpi"></span>CPI</span>
          </div>
          <div class="chart" data-slot="uacombo"></div>
        </article>
        <article class="card">
          ${cardHead("Spend by Channel")}
          <div data-slot="channelmix"></div>
        </article>
      </section>

      <article class="card card--full">
        ${cardHead("Channel Performance", "(MTD)")}
        <table class="ptable">
          <thead><tr>
            <th>Channel</th><th class="is-num">Spend</th><th class="is-num">Installs</th>
            <th class="is-num">CPI</th><th class="is-num">LTV/CPI</th><th class="is-num">ROAS D30</th><th>Trend</th>
          </tr></thead>
          <tbody>
            <tr><td><span class="product-name">Meta Ads</span></td><td class="is-num num">$486,200</td><td class="is-num num">372K</td><td class="is-num num">$1.31</td><td class="is-num num">2.58</td><td class="is-num">${delta("192%","up")}</td><td><span class="pill pill--ok">Scaling</span></td></tr>
            <tr><td><span class="product-name">Google Ads</span></td><td class="is-num num">$342,750</td><td class="is-num num">258K</td><td class="is-num num">$1.33</td><td class="is-num num">2.41</td><td class="is-num">${delta("181%","up")}</td><td><span class="pill pill--ok">Scaling</span></td></tr>
            <tr><td><span class="product-name">TikTok Ads</span></td><td class="is-num num">$248,400</td><td class="is-num num">196K</td><td class="is-num num">$1.27</td><td class="is-num num">2.62</td><td class="is-num">${delta("204%","up")}</td><td><span class="pill pill--ok">Scaling</span></td></tr>
            <tr><td><span class="product-name">Apple Search</span></td><td class="is-num num">$104,300</td><td class="is-num num">68K</td><td class="is-num num">$1.53</td><td class="is-num num">2.05</td><td class="is-num">${delta("158%","up")}</td><td><span class="pill pill--run">Steady</span></td></tr>
            <tr><td><span class="product-name">Unity Ads</span></td><td class="is-num num">$55,000</td><td class="is-num num">41K</td><td class="is-num num">$1.34</td><td class="is-num num">1.82</td><td class="is-num">${delta("9%","down")}</td><td><span class="pill pill--warn">Watch</span></td></tr>
          </tbody>
        </table>
      </article>
    `);
    root.querySelector("[data-slot=uacombo]").appendChild(C.combo(D));
    root.querySelector("[data-slot=channelmix]").appendChild(C.donutSegments([
      { label: "Meta Ads", value: 486, display: "39%", color: "var(--color-accent)" },
      { label: "Google Ads", value: 343, display: "28%", color: "var(--color-positive)" },
      { label: "TikTok Ads", value: 248, display: "20%", color: "var(--color-purple)" },
      { label: "Apple Search", value: 104, display: "8%", color: "var(--color-amber)" },
      { label: "Unity Ads", value: 55, display: "5%", color: "var(--color-orange)" },
    ], "$1.24M", "Total"));
    return { title: "UA MARKETING", subtitle: "Acquisition channels, spend and efficiency", node: root };
  };

  /* =====================================================================
     PRODUCTS
     ===================================================================== */
  PAGES.products = function () {
    const sparks = window.DASH.sparks;
    const prods = [
      { initial: "M", color: "#8c6df0", name: "Merge Meta Narrative", cat: "GAME", catClass: "game", rev: "$1.25M", dau: "152K", gp: "76%", badge: "scale", status: "Scale", spark: "rev" },
      { initial: "W", color: "#2bb079", name: "Word Voyage", cat: "GAME", catClass: "game", rev: "$678K", dau: "98K", gp: "72%", badge: "scale", status: "Scale", spark: "net" },
      { initial: "F", color: "#e8743f", name: "FitFlow", cat: "HEALTH", catClass: "health", rev: "$445K", dau: "76K", gp: "68%", badge: "improve", status: "Improve", spark: "gp" },
      { initial: "P", color: "#3f86f2", name: "Pocket Budget", cat: "FINANCE", catClass: "finance", rev: "$312K", dau: "64K", gp: "65%", badge: "improve", status: "Improve", spark: "spend" },
      { initial: "S", color: "#6470e6", name: "Sleep Well", cat: "LIFESTYLE", catClass: "lifestyle", rev: "$120K", dau: "22K", gp: "40%", badge: "review", status: "Review", spark: "gppct" },
      { initial: "B", color: "#d65a7e", name: "Battle Quest", cat: "GAME", catClass: "game", rev: "$0", dau: "–", gp: "–", badge: "prototype", status: "Prototype", spark: "cash" },
    ];
    const cards = prods.map((p) => `
      <article class="card pcard" data-spark-card="${p.spark}">
        <div class="pcard__top">
          <span class="product-icon" style="background:${p.color}">${p.initial}</span>
          <div><div class="product-name">${p.name}</div><div class="cat cat--${p.catClass}">${p.cat}</div></div>
          <span class="badge badge--${p.badge}" style="margin-left:auto">${p.status}</span>
        </div>
        <div class="pcard__meta">
          <div class="pcard__metric"><span class="k">Revenue</span><span class="v num">${p.rev}</span></div>
          <div class="pcard__metric"><span class="k">DAU</span><span class="v num">${p.dau}</span></div>
          <div class="pcard__metric"><span class="k">GP %</span><span class="v num">${p.gp}</span></div>
        </div>
        <div class="pcard__spark" data-slot="spark-${p.spark}"></div>
      </article>`).join("");

    const root = frag(`
      <section class="kpi-row kpi-row--auto">
        ${kpi("Live Products", "5", null)}
        ${kpi("In Prototype", "1", null)}
        ${kpi("Total Revenue (MTD)", "$2.80M", { t: "19.4%", dir: "up" })}
        ${kpi("Avg GP %", "64.2%", { t: "1.8pp", dir: "up" })}
        ${kpi("Portfolio DAU", "412K", { t: "11.3%", dir: "up" })}
      </section>
      <p class="section-label">Product Portfolio</p>
      <section class="grid-3-even" data-slot="pcards"></section>
    `);
    const grid = root.querySelector("[data-slot=pcards]");
    grid.innerHTML = cards;
    prods.forEach((p) => {
      const slot = grid.querySelector(`[data-slot="spark-${p.spark}"]`);
      if (slot) slot.appendChild(C.sparkline(sparks[p.spark], getComputedStyle(document.documentElement).getPropertyValue("--chart-spark").trim()));
    });
    return { title: "PRODUCTS", subtitle: "Per-product performance across the portfolio", node: root };
  };

  /* =====================================================================
     PRODUCT FACTORY
     ===================================================================== */
  PAGES.factory = function () {
    const F = window.DASH.factory;
    const steps = F.steps.map((s, i) => `
      ${i ? '<span class="pipe-arrow">' + ic("arrowR", 16) + "</span>" : ""}
      <div class="pipe-step ${s.killed ? "pipe-step--killed" : ""}">
        <span class="pipe-step__icon">${ic(s.icon, 21)}</span>
        <span class="pipe-step__label">${s.label}</span>
        <span class="pipe-step__value num">${s.value}</span>
      </div>`).join("");

    const root = frag(`
      <section class="kpi-row kpi-row--auto">
        ${kpi("Ideas Logged (YTD)", "250", null)}
        ${kpi("In Prototyping", "40", null)}
        ${kpi("In Testing", "20", null)}
        ${kpi("Shipped (YTD)", "5", { t: "2", dir: "up", note: "vs last year" })}
        ${kpi("Success Rate", "32%", { t: "Benchmark 20%", dir: "flat" })}
      </section>

      <article class="card card--full">
        ${cardHead("Pipeline Funnel")}
        <div class="pipeline">${steps}</div>
        <div class="success-rate">
          <div class="success-rate__head"><span class="success-rate__label">Idea → Ship Conversion</span><span class="success-rate__bench">Benchmark: 20%+</span></div>
          <div class="progress"><div class="progress__fill" data-slot="srfill" style="width:0%"></div></div>
        </div>
      </article>

      <section class="grid-2-even">
        <article class="card">
          ${cardHead("Recently Greenlit")}
          <div class="drow"><span class="drow__label">Merge Kingdoms <span class="cat cat--game">GAME</span></span><span class="pill pill--run">Testing</span></div>
          <div class="drow"><span class="drow__label">Calm Coach <span class="cat cat--health">HEALTH</span></span><span class="pill pill--run">Testing</span></div>
          <div class="drow"><span class="drow__label">Battle Quest <span class="cat cat--game">GAME</span></span><span class="pill pill--ok">Shipped</span></div>
          <div class="drow"><span class="drow__label">Splash Saga <span class="cat cat--game">GAME</span></span><span class="pill pill--run">Prototype</span></div>
        </article>
        <article class="card">
          ${cardHead("Recently Killed", "(last 90 days)")}
          <div class="drow"><span class="drow__label">Trivia Rush</span><span class="muted">Low D1 retention</span></div>
          <div class="drow"><span class="drow__label">Budget Buddy</span><span class="muted">CPI too high</span></div>
          <div class="drow"><span class="drow__label">Zen Garden</span><span class="muted">Weak monetization</span></div>
          <div class="drow"><span class="drow__label">Pixel Racer</span><span class="muted">Crowded market</span></div>
        </article>
      </section>
    `);
    const sr = root.querySelector("[data-slot=srfill]");
    setTimeout(() => { sr.style.width = (F.successRate * 100).toFixed(0) + "%"; }, 80);
    return { title: "PRODUCT FACTORY", subtitle: "Idea-to-ship pipeline and greenlight decisions", node: root };
  };
})();
