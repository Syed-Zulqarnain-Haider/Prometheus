/* ============================================================================
   RENDER + INTERACTIVITY
   ----------------------------------------------------------------------------
   The MARKUP holds all text (values, labels, table, alerts) so every element
   is directly inspectable/editable. This script only:
     1. mounts real SVG charts into labelled placeholder slots
     2. wires interactivity (nav active state, date-range toggle, link feedback)
   Chart series come from scripts/data.js (window.DASH).
   ============================================================================ */
(function () {
  const D = window.DASH, C = window.CHARTS;

  function mount(slot, node) { if (slot) { slot.innerHTML = ""; slot.appendChild(node); } }

  /* mount all charts — re-callable so Tweaks can recolor SVGs from new tokens */
  function renderCharts() {
    document.querySelectorAll("[data-spark]").forEach((slot) => {
      const key = slot.getAttribute("data-spark");
      const series = D.sparks[key];
      if (!series) return;
      const color = slot.getAttribute("data-spark-color") || getComputedStyle(document.documentElement).getPropertyValue("--chart-spark").trim();
      // labels: most-recent N days, so hover reads like a real timeline
      const n = series.length;
      const labels = series.map((_, i) => (n - 1 - i === 0 ? "Today" : (n - 1 - i) + "d ago"));
      mount(slot, C.sparkline(series, color, { labels }));
    });
    document.querySelectorAll("[data-donut]").forEach((donutSlot) => {
      const attr = donutSlot.getAttribute("data-donut");
      const pct = attr ? parseFloat(attr) : D.revenueTarget.pct;
      mount(donutSlot, C.donut(pct));
    });
    const trendSlot = document.querySelector("[data-chart='monthly-trend']");
    if (trendSlot) mount(trendSlot, C.barTarget(D.monthlyTrend));
    const uaSlot = document.querySelector("[data-chart='ua']");
    if (uaSlot) mount(uaSlot, C.combo(D.uaPerformance));
  }
  renderCharts();
  window.__rerenderCharts = renderCharts;

  /* ---- factory success-rate bar -------------------------------------- */
  const sr = document.querySelector("[data-success-fill]");
  if (sr) {
    sr.style.width = "0%";
    setTimeout(() => { sr.style.width = (D.factory.successRate * 100).toFixed(0) + "%"; }, 60);
  }

  /* =====================================================================
     INTERACTIVITY
     ===================================================================== */
  // nav active state
  document.querySelectorAll(".nav__item:not(.is-header)").forEach((item) => {
    item.addEventListener("click", () => {
      document.querySelectorAll(".nav__item").forEach((n) => n.classList.remove("is-active"));
      item.classList.add("is-active");
    });
  });

  // date-range toggle — cycles a few preset ranges
  const ranges = [
    { main: "May 1 – May 25, 2025", cmp: "vs Apr 1 – Apr 25, 2025" },
    { main: "Apr 1 – Apr 30, 2025", cmp: "vs Mar 1 – Mar 31, 2025" },
    { main: "Q2 2025 (QTD)",        cmp: "vs Q1 2025" },
    { main: "YTD 2025",             cmp: "vs YTD 2024" },
  ];
  let ri = 0;
  const dateBtn = document.querySelector("[data-date-range]");
  const cmpBtn = document.querySelector("[data-date-compare]");
  if (dateBtn) {
    dateBtn.addEventListener("click", () => {
      ri = (ri + 1) % ranges.length;
      dateBtn.querySelector("[data-date-label]").textContent = ranges[ri].main;
      if (cmpBtn) cmpBtn.querySelector("[data-compare-label]").textContent = ranges[ri].cmp;
    });
  }

  // "View all →" links — gentle nudge feedback (non-destructive placeholder)
  document.querySelectorAll(".card-link").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      a.animate(
        [{ transform: "translateX(0)" }, { transform: "translateX(4px)" }, { transform: "translateX(0)" }],
        { duration: 260, easing: "ease-out" }
      );
    });
  });

  // hide tooltip when scrolling so it never floats stale
  window.addEventListener("scroll", () => C.hideTip(), true);
})();
