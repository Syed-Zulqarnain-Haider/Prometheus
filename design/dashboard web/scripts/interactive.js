/* ============================================================================
   INTERACTIVE — table sorting + clickable chart legends.
   ----------------------------------------------------------------------------
   Progressive enhancement layered onto already-rendered markup. Runs on the
   static Overview at load and re-runs for any page the router swaps into
   #page-dynamic. Safe to call twice (guards with a data-flag).
   ============================================================================ */
(function () {
  /* ---- parse a display value into a sortable number ------------------- */
  function parseNum(text) {
    let t = (text || "").trim();
    if (t === "" || t === "–" || t === "-" || t === "—") return null;
    const neg = /▼/.test(t) || /^-/.test(t);
    const m = t.replace(/,/g, "").match(/[\d.]+/);
    if (!m) return null;
    let n = parseFloat(m[0]);
    if (!isFinite(n)) return null;
    if (/B/i.test(t)) n *= 1e9;
    else if (/M/i.test(t)) n *= 1e6;
    else if (/K/i.test(t)) n *= 1e3;
    return neg ? -n : n;
  }

  /* ---- make a .ptable sortable --------------------------------------- */
  function enhanceTable(table) {
    if (table.dataset.sortable) return;
    table.dataset.sortable = "1";
    const ths = Array.from(table.querySelectorAll("thead th"));
    const tbody = table.querySelector("tbody");
    if (!tbody || !ths.length) return;

    ths.forEach((th, col) => {
      th.classList.add("sortable");
      const caret = document.createElement("span");
      caret.className = "sort-caret";
      caret.textContent = "↕";
      th.appendChild(caret);

      th.addEventListener("click", () => {
        const rows = Array.from(tbody.querySelectorAll("tr"));
        // decide column type by sampling
        let numeric = 0;
        rows.forEach((r) => { if (parseNum(r.children[col] && r.children[col].textContent) !== null) numeric++; });
        const isNum = numeric >= rows.length / 2;

        const prev = table.dataset.sortCol == String(col);
        const dir = prev ? (table.dataset.sortDir === "asc" ? "desc" : "asc")
                         : (isNum ? "desc" : "asc");
        table.dataset.sortCol = col;
        table.dataset.sortDir = dir;

        rows.sort((a, b) => {
          const av = a.children[col] ? a.children[col].textContent : "";
          const bv = b.children[col] ? b.children[col].textContent : "";
          let cmp;
          if (isNum) {
            const an = parseNum(av), bn = parseNum(bv);
            const aa = an === null ? -Infinity : an, bb = bn === null ? -Infinity : bn;
            cmp = aa - bb;
          } else {
            cmp = av.trim().localeCompare(bv.trim());
          }
          return dir === "asc" ? cmp : -cmp;
        });
        rows.forEach((r) => tbody.appendChild(r));

        ths.forEach((h, i) => {
          h.classList.toggle("sort-active", i === col);
          const cr = h.querySelector(".sort-caret");
          if (cr) cr.textContent = i === col ? (dir === "asc" ? "↑" : "↓") : "↕";
        });
      });
    });
  }

  /* ---- make a chart legend toggle its series ------------------------- */
  function enhanceLegends(root) {
    root.querySelectorAll(".card").forEach((card) => {
      const legend = card.querySelector(".chart-legend");
      const svg = card.querySelector(".chart svg");
      if (!legend || !svg || legend.dataset.wired) return;
      const items = Array.from(legend.querySelectorAll(".legend-item"));
      let wiredAny = false;
      items.forEach((item, idx) => {
        if (!svg.querySelector(`[data-si="${idx}"]`)) return;
        wiredAny = true;
        item.classList.add("legend-toggle");
        item.title = "Click to show / hide";
        item.addEventListener("click", () => {
          const off = item.classList.toggle("is-off");
          // re-query: the chart SVG may have been re-rendered (theme/tweaks) since wiring
          const grp = card.querySelector(`.chart svg [data-si="${idx}"]`);
          if (grp) grp.style.display = off ? "none" : "";
        });
      });
      if (wiredAny) legend.dataset.wired = "1";
    });
  }

  /* ---- wrap a table so it scrolls inside its card (never overflows) --- */
  function wrapTable(table) {
    const parent = table.parentElement;
    if (!parent || parent.classList.contains("table-scroll")) return;
    const w = document.createElement("div");
    w.className = "table-scroll";
    parent.insertBefore(w, table);
    w.appendChild(table);
  }

  function enhance(root) {
    if (!root) return;
    root.querySelectorAll(".ptable").forEach((t) => { wrapTable(t); enhanceTable(t); });
    enhanceLegends(root);
  }

  function init() {
    enhance(document.getElementById("page-overview"));
    const dyn = document.getElementById("page-dynamic");
    if (dyn) {
      new MutationObserver((muts) => {
        for (const mu of muts) {
          if (mu.addedNodes.length) { enhance(dyn); break; }
        }
      }).observe(dyn, { childList: true });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
