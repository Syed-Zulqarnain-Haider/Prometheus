/* ============================================================================
   PAGES — part 2: User Analytics, AI & Operations, Executive, Reports, Alerts
   Uses the helpers exposed on window.PG by pages-core.js.
   ============================================================================ */
(function () {
  const { node, frag, delta, kpi, cardHead, C, ic } = window.PG;
  const PAGES = window.PAGES;

  /* =====================================================================
     USER ANALYTICS
     ===================================================================== */
  PAGES.analytics = function () {
    const root = frag(`
      <section class="kpi-row kpi-row--auto">
        ${kpi("DAU", "412K", { t: "11.3%", dir: "up" })}
        ${kpi("MAU", "2.45M", { t: "13.6%", dir: "up" })}
        ${kpi("DAU / MAU", "16.8%", { t: "0.8pp", dir: "up" })}
        ${kpi("Avg Session", "14.2 min", { t: "1.1 min", dir: "up" })}
        ${kpi("Sessions / User", "4.6", { t: "0.3", dir: "up" })}
        ${kpi("Avg Rating", "4.45", { t: "0.08", dir: "up" })}
      </section>

      <section class="grid-7-3">
        <article class="card">
          ${cardHead("Retention Curve", "(portfolio avg)")}
          <div class="chart-legend" style="margin-bottom:8px">
            <span class="legend-item"><span class="legend-swatch" style="background:var(--color-accent)"></span>This Cohort</span>
            <span class="legend-item"><span class="legend-swatch" style="background:var(--color-text-muted)"></span>Prev Cohort</span>
          </div>
          <div class="chart" data-slot="retention"></div>
        </article>
        <article class="card">
          ${cardHead("Active Users", "(DAU, 30d)")}
          <div class="chart" data-slot="dau"></div>
        </article>
      </section>

      <section class="grid-2-even">
        <article class="card">
          ${cardHead("Retention Benchmarks")}
          <div class="tile-grid">
            <div class="tile"><span class="tile__label">D1</span><span class="tile__value num">28.4%</span>${delta("1.9pp","up")}</div>
            <div class="tile"><span class="tile__label">D7</span><span class="tile__value num">12.6%</span>${delta("1.2pp","up")}</div>
            <div class="tile"><span class="tile__label">D14</span><span class="tile__value num">8.1%</span>${delta("0.7pp","up")}</div>
            <div class="tile"><span class="tile__label">D30</span><span class="tile__value num">5.3%</span>${delta("0.6pp","up")}</div>
          </div>
        </article>
        <article class="card">
          ${cardHead("Users by Platform")}
          <div data-slot="platform"></div>
        </article>
      </section>
    `);
    root.querySelector("[data-slot=retention]").appendChild(C.line({
      labels: ["D0","D1","D3","D7","D14","D21","D30"], yMax: 100, unit: "%", yTicks: 4,
      series: [
        { name: "This Cohort", data: [100, 28.4, 18.2, 12.6, 8.1, 6.4, 5.3], color: "var(--color-accent)", area: true },
        { name: "Prev Cohort", data: [100, 26.5, 16.4, 11.4, 7.4, 5.8, 4.7], color: "var(--color-text-muted)", dash: "5 4" },
      ],
    }));
    root.querySelector("[data-slot=dau]").appendChild(C.line({
      labels: Array.from({ length: 30 }, (_, i) => "D" + (i + 1)), yMax: 460, unit: "K", yTicks: 4,
      fmt: (v) => Math.round(v / 1),
      series: [{ name: "DAU", data: [320,332,328,345,351,360,372,365,380,392,386,401,395,388,402,396,410,405,412,408,418,412,420,415,422,418,430,425,438,412], color: "var(--color-positive)", area: true }],
    }));
    root.querySelector("[data-slot=platform]").appendChild(C.donutSegments([
      { label: "iOS", value: 58, display: "58%", color: "var(--color-accent)" },
      { label: "Android", value: 38, display: "38%", color: "var(--color-positive)" },
      { label: "Web", value: 4, display: "4%", color: "var(--color-purple)" },
    ], "2.45M", "MAU"));
    return { title: "USER ANALYTICS", subtitle: "Engagement, retention and cohort behavior", node: root };
  };

  /* =====================================================================
     AI & OPERATIONS
     ===================================================================== */
  PAGES.ai = function () {
    const root = frag(`
      <section class="kpi-row kpi-row--auto">
        ${kpi("AI Tasks Run (MTD)", "1.84M", { t: "32.5%", dir: "up" })}
        ${kpi("Automation Coverage", "68%", { t: "6pp", dir: "up" })}
        ${kpi("Cost Saved (MTD)", "$214K", { t: "18.2%", dir: "up" })}
        ${kpi("Avg Response Time", "1.9s", { t: "0.4s", dir: "down" })}
        ${kpi("System Uptime", "99.98%", { t: "0.02pp", dir: "up" })}
        ${kpi("Open Incidents", "2", { t: "1", dir: "down" })}
      </section>

      <section class="grid-7-3">
        <article class="card">
          ${cardHead("AI Workload", "(tasks/day, 30d)")}
          <div class="chart" data-slot="aiload"></div>
        </article>
        <article class="card">
          ${cardHead("Spend by Workload")}
          <div data-slot="aimix"></div>
        </article>
      </section>

      <section class="grid-2-even">
        <article class="card">
          ${cardHead("Operations Status")}
          <div class="drow"><span class="drow__label">API Gateway</span><span class="pill pill--ok">${ic("sun",0)}Operational</span></div>
          <div class="drow"><span class="drow__label">Data Pipeline</span><span class="pill pill--ok">Operational</span></div>
          <div class="drow"><span class="drow__label">Model Serving</span><span class="pill pill--ok">Operational</span></div>
          <div class="drow"><span class="drow__label">Analytics Warehouse</span><span class="pill pill--warn">Degraded</span></div>
          <div class="drow"><span class="drow__label">Build & CI</span><span class="pill pill--ok">Operational</span></div>
        </article>
        <article class="card">
          ${cardHead("Automation by Function")}
          <div data-slot="autofn"></div>
        </article>
      </section>
    `);
    root.querySelector("[data-slot=aiload]").appendChild(C.bars({
      labels: Array.from({ length: 30 }, (_, i) => "D" + (i + 1)),
      data: [42,46,44,52,55,58,61,57,63,68,64,71,66,62,69,65,72,70,75,71,78,74,80,76,82,78,85,81,88,84],
      unit: "K", color: "var(--color-purple)", fmt: (v) => Math.round(v),
    }));
    root.querySelector("[data-slot=aimix]").appendChild(C.donutSegments([
      { label: "Inference", value: 54, display: "54%", color: "var(--color-purple)" },
      { label: "Training", value: 26, display: "26%", color: "var(--color-accent)" },
      { label: "Data Ops", value: 14, display: "14%", color: "var(--color-positive)" },
      { label: "Other", value: 6, display: "6%", color: "var(--color-amber)" },
    ], "$92K", "MTD"));
    root.querySelector("[data-slot=autofn]").appendChild(C.hbars([
      { label: "Player Support", value: 92, display: "92%", color: "var(--color-positive)" },
      { label: "Creative QA", value: 74, display: "74%", color: "var(--color-accent)" },
      { label: "UA Bidding", value: 68, display: "68%", color: "var(--color-purple)" },
      { label: "Localization", value: 55, display: "55%", color: "var(--color-amber)" },
      { label: "Fraud Review", value: 40, display: "40%", color: "var(--color-orange)" },
    ]));
    return { title: "AI & OPERATIONS", subtitle: "Automation footprint and system health", node: root };
  };

  /* =====================================================================
     EXECUTIVE
     ===================================================================== */
  PAGES.executive = function () {
    function okr(name, owner, pct, color) {
      return `<div class="okr">
        <div class="okr__head"><span class="okr__name">${name}</span><span class="okr__pct" style="color:${color}">${pct}%</span></div>
        <div class="progress"><div class="progress__fill" data-okr style="width:0%;background:${color}" data-target="${pct}"></div></div>
        <span class="okr__owner">Owner · ${owner}</span>
      </div>`;
    }
    const root = frag(`
      <section class="kpi-row kpi-row--auto">
        ${kpi("Annual Revenue Target", "$100M", null)}
        ${kpi("Achieved YTD", "35.6%", { t: "On track", dir: "up" })}
        ${kpi("Cash in Bank", "$12.45M", null)}
        ${kpi("Runway", "18.6 mo", { t: "2.1 mo", dir: "up" })}
        ${kpi("Headcount", "148", { t: "12", dir: "up", note: "QTD" })}
      </section>

      <section class="grid-2-even">
        <article class="card">
          ${cardHead("Company OKRs", "(Q2 2025)")}
          ${okr("Reach $40M cumulative revenue", "Finance", 89, "var(--color-positive)")}
          ${okr("Ship 3 new titles to soft launch", "Product Factory", 67, "var(--color-accent)")}
          ${okr("Improve portfolio D30 to 6%", "Analytics", 53, "var(--color-amber)")}
          ${okr("Lift blended ROAS D90 to 280%", "UA Marketing", 72, "var(--color-purple)")}
        </article>
        <article class="card">
          ${cardHead("Revenue vs Target", "(cumulative)")}
          <div class="chart" data-slot="exectrend"></div>
        </article>
      </section>

      <section class="grid-3-even">
        <article class="card"><div class="bigstat"><span class="bigstat__label">Enterprise Value (est.)</span><span class="bigstat__value num">$280M</span>${delta("9.4% QoQ","up")}</div></article>
        <article class="card"><div class="bigstat"><span class="bigstat__label">Net Margin (MTD)</span><span class="bigstat__value num">44.4%</span>${delta("2.1pp","up")}</div></article>
        <article class="card"><div class="bigstat"><span class="bigstat__label">Rule of 40</span><span class="bigstat__value num">71</span>${delta("Healthy","flat")}</div></article>
      </section>
    `);
    root.querySelectorAll("[data-okr]").forEach((b) => setTimeout(() => { b.style.width = b.getAttribute("data-target") + "%"; }, 80));
    root.querySelector("[data-slot=exectrend]").appendChild(C.line({
      labels: ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
      yMax: 100, unit: "M", fmt: (v) => "$" + v.toFixed(0), yTicks: 5,
      series: [
        { name: "Actual", data: [3.1,6.7,10.9,15.9,21.7,28.3,null,null,null,null,null,null].filter((v)=>v!=null), color: "var(--color-positive)", area: true },
        { name: "Target", data: [8.3,16.6,25,33.3,41.6,50,58.3,66.6,75,83.3,91.6,100], color: "var(--color-text-muted)", dash: "5 4" },
      ],
    }));
    return { title: "EXECUTIVE", subtitle: "Strategic objectives and board-level metrics", node: root };
  };

  /* =====================================================================
     REPORTS
     ===================================================================== */
  PAGES.reports = function () {
    const rows = [
      ["Monthly Financial Summary", "Finance", "May 2025", "Ready"],
      ["UA Performance Deep-Dive", "Marketing", "May 2025", "Ready"],
      ["Product Portfolio Review", "Product", "Q2 2025", "Ready"],
      ["Cohort & Retention Analysis", "Analytics", "May 2025", "Ready"],
      ["Board Deck", "Executive", "Q2 2025", "Draft"],
      ["AI Cost & Usage Report", "Operations", "May 2025", "Ready"],
      ["Cash Flow Forecast", "Finance", "Jun 2025", "Scheduled"],
    ];
    const statusPill = (s) => s === "Ready" ? '<span class="pill pill--ok">Ready</span>'
      : s === "Draft" ? '<span class="pill pill--warn">Draft</span>'
      : '<span class="pill pill--run">Scheduled</span>';
    const tbody = rows.map((r) => `<tr>
      <td><div class="product-cell"><span class="product-icon" style="background:var(--color-bg-elevated);color:var(--color-text-secondary)">${ic("doc",14)}</span><span class="product-name">${r[0]}</span></div></td>
      <td><span class="muted">${r[1]}</span></td>
      <td>${r[2]}</td>
      <td>${statusPill(r[3])}</td>
      <td class="is-num"><a class="card-link" href="#">Open ${ic("arrowR",13)}</a></td>
    </tr>`).join("");

    const root = frag(`
      <section class="kpi-row kpi-row--auto">
        ${kpi("Reports Available", "24", null)}
        ${kpi("Generated This Month", "9", { t: "3", dir: "up" })}
        ${kpi("Scheduled", "5", null)}
        ${kpi("Pending Review", "1", null)}
      </section>
      <article class="card card--full">
        ${cardHead("Report Library")}
        <table class="ptable">
          <thead><tr><th>Report</th><th>Department</th><th>Period</th><th>Status</th><th class="is-num">Action</th></tr></thead>
          <tbody>${tbody}</tbody>
        </table>
      </article>
    `);
    return { title: "REPORTS", subtitle: "Generated, scheduled and draft reports", node: root };
  };

  /* =====================================================================
     ALERTS
     ===================================================================== */
  PAGES.alerts = function () {
    function group(title, items) {
      return `<article class="card">
        ${cardHead(title)}
        <div class="alerts">${items.map((a) => `
          <div class="alert"><span class="alert__dot alert__dot--${a.dot}"></span>
            <span><strong style="color:var(--color-text-primary)">${a.t}</strong><br><span class="muted">${a.meta}</span></span>
          </div>`).join("")}</div>
      </article>`;
    }
    const root = frag(`
      <section class="kpi-row kpi-row--auto">
        ${kpi("Active Alerts", "7", null)}
        ${kpi("Critical", "1", { t: "needs action", dir: "down" })}
        ${kpi("Positive Signals", "4", { t: "2", dir: "up" })}
        ${kpi("Resolved (7d)", "12", null)}
      </section>
      <section class="grid-3-even" data-slot="groups"></section>
    `);
    root.querySelector("[data-slot=groups]").innerHTML =
      group("Needs Attention", [
        { dot: "warn", t: "Sleep Well retention dropping", meta: "D7 −2.1pp · Sleep Well · 2h ago" },
        { dot: "warn", t: "Unity Ads ROAS below target", meta: "D30 ROAS 9% under plan · 5h ago" },
        { dot: "warn", t: "Analytics warehouse degraded", meta: "Query latency elevated · 1h ago" },
      ]) +
      group("Positive Signals", [
        { dot: "positive", t: "Merge Meta Narrative passed $1M", meta: "Monthly revenue milestone · 1d ago" },
        { dot: "positive", t: "Cash runway up to 18.6 months", meta: "Finance · 1d ago" },
        { dot: "positive", t: "LTV/CPI improved by 0.32", meta: "Blended portfolio · 2d ago" },
        { dot: "positive", t: "Blended D1 retention +1.9pp", meta: "Analytics · 3d ago" },
      ]) +
      group("Informational", [
        { dot: "info", t: "2 new prototypes ready for testing", meta: "Product Factory · 6h ago" },
        { dot: "info", t: "Cash flow forecast scheduled", meta: "Finance · 12h ago" },
        { dot: "info", t: "Quarterly board deck in draft", meta: "Executive · 1d ago" },
      ]);
    return { title: "ALERTS", subtitle: "Signals across finance, product and operations", node: root };
  };
})();
