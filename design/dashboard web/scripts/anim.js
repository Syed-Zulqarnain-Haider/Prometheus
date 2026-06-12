/* ============================================================================
   ANIMATIONS — entrance stagger + number count-up.
   ----------------------------------------------------------------------------
   Progressive enhancement: if this fails or reduced-motion is set, the page is
   fully visible with final values (nothing depends on it).
   ============================================================================ */
(function () {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- staggered reveal for a page's top-level blocks ----------------- */
  function stagger(root) {
    if (reduce || !root) return;
    let i = 0;
    Array.from(root.children).forEach((child) => {
      if (child.classList.contains("kpi-row")) {
        // finer stagger across the KPI cards themselves
        Array.from(child.children).forEach((card) => {
          card.classList.add("reveal");
          card.style.setProperty("--ri", i++);
        });
      } else {
        child.classList.add("reveal");
        child.style.setProperty("--ri", i++);
      }
    });
  }

  /* ---- number count-up ------------------------------------------------ */
  function countUp(el) {
    if (reduce) return;
    const raw = el.textContent.trim();
    const m = raw.match(/^([^\d-]*)(-?[\d,]*\.?\d+)(.*)$/);
    if (!m) return;
    const prefix = m[1], numStr = m[2], suffix = m[3];
    const decimals = (numStr.split(".")[1] || "").length;
    const hasComma = numStr.includes(",");
    const target = parseFloat(numStr.replace(/,/g, ""));
    if (!isFinite(target)) return;

    const fmt = (v) => {
      let s = v.toFixed(decimals);
      if (hasComma) {
        const parts = s.split(".");
        parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        s = parts.join(".");
      }
      return prefix + s + suffix;
    };

    const dur = 950, start = performance.now();
    let done = false;
    el.textContent = fmt(0);
    function tick(now) {
      const t = Math.min(1, (now - start) / dur);
      const e = 1 - Math.pow(1 - t, 3);
      el.textContent = fmt(target * e);
      if (t < 1) requestAnimationFrame(tick); else { el.textContent = fmt(target); done = true; }
    }
    requestAnimationFrame(tick);
    // safety: if rAF is throttled (hidden tab), force the final value
    setTimeout(() => { if (!done) el.textContent = fmt(target); }, dur + 600);
  }

  function countAll(root) {
    if (!root) return;
    root.querySelectorAll(".kpi__value, .donut__pct, .bigstat__value").forEach(countUp);
  }

  /* ---- run on the static overview at load ----------------------------- */
  function init() {
    // reduced-motion: drop the intro gate immediately, leave final values
    if (reduce) { document.body.classList.remove("intro"); return; }

    const ov = document.getElementById("page-overview");
    stagger(ov);
    countAll(ov);

    // re-animate dynamic pages whenever the router swaps content in
    const dyn = document.getElementById("page-dynamic");
    if (dyn) {
      new MutationObserver((muts) => {
        for (const mu of muts) {
          if (mu.addedNodes.length) {
            const page = dyn.firstElementChild;
            if (page) { stagger(page); countAll(page); }
            break;
          }
        }
      }).observe(dyn, { childList: true });
    }

    // remove the intro gate once the entrance window has passed, so the
    // resting state is always visible even if the timeline was paused
    setTimeout(() => document.body.classList.remove("intro"), 2600);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
