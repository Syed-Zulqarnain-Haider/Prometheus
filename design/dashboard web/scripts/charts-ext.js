/* ============================================================================
   CHARTS — EXTENSIONS
   ----------------------------------------------------------------------------
   Additional SVG renderers used by the secondary nav pages. Same scaling
   strategy as charts.js (fixed viewBox + non-scaling-stroke). Appends to
   window.CHARTS. Colors read from CSS tokens at render time.
   ============================================================================ */
(function () {
  const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs) => {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  };
  const C = window.CHARTS;

  /* =====================================================================
     LINE — one or more series, optional area fill, gridlines, x labels
     cfg: { series:[{name,data,color,area?}], labels:[], yMax?, yTicks?, unit? }
     ===================================================================== */
  function line(cfg) {
    const W = 620, H = 240, padL = 38, padR = 12, padT = 12, padB = 24;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const all = cfg.series.flatMap((s) => s.data);
    const yMax = cfg.yMax != null ? cfg.yMax : Math.max(...all) * 1.15;
    const yMin = cfg.yMin != null ? cfg.yMin : 0;
    const n = cfg.labels.length;
    const stepX = plotW / (n - 1);
    const x = (i) => padL + i * stepX;
    const y = (v) => padT + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
    const grid = cssVar("--chart-grid");
    const axisTxt = cssVar("--color-text-muted");
    const ticks = cfg.yTicks || 4;

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });
    let defs = "";

    // gridlines + y labels
    for (let t = 0; t <= ticks; t++) {
      const v = yMin + ((yMax - yMin) / ticks) * t;
      const yy = y(v);
      svg.appendChild(el("line", { x1: padL, y1: yy, x2: W - padR, y2: yy, stroke: grid, "stroke-width": "1", "vector-effect": "non-scaling-stroke" }));
      svg.appendChild(el("text", { x: padL - 6, y: yy + 3, "text-anchor": "end", "font-size": "9", fill: axisTxt }))
        .textContent = (cfg.fmt ? cfg.fmt(v) : Math.round(v)) + (cfg.unit || "");
    }
    // x labels (skip to avoid crowding)
    const skip = Math.ceil(n / 8);
    cfg.labels.forEach((lbl, i) => {
      if (i % skip !== 0 && i !== n - 1) return;
      svg.appendChild(el("text", { x: x(i), y: H - 7, "text-anchor": "middle", "font-size": "9", fill: axisTxt })).textContent = lbl;
    });

    // each series (grouped + tagged for legend toggling)
    const seriesMeta = [];
    cfg.series.forEach((s, si) => {
      const color = s.color || cssVar("--color-accent");
      const g = el("g", { "data-si": String(si), "data-series": s.name });
      const path = s.data.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1)).join(" ");
      if (s.area) {
        const uid = "ln" + si + Math.random().toString(36).slice(2, 6);
        defs += `<linearGradient id="${uid}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="${color}" stop-opacity="0.28"/>
          <stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient>`;
        const area = path + ` L${x(n - 1).toFixed(1)} ${padT + plotH} L${x(0).toFixed(1)} ${padT + plotH} Z`;
        g.appendChild(el("path", { d: area, fill: `url(#${uid})` }));
      }
      g.appendChild(el("path", { d: path, fill: "none", stroke: color, "stroke-width": s.width || "2.2", "vector-effect": "non-scaling-stroke", "stroke-linejoin": "round", "stroke-linecap": "round", "stroke-dasharray": s.dash || "none" }));
      // small permanent point markers
      s.data.forEach((v, i) => g.appendChild(el("circle", { cx: x(i).toFixed(1), cy: y(v).toFixed(1), r: 2, fill: color, opacity: "0.55" })));
      svg.appendChild(g);
      seriesMeta.push({ name: s.name, color, data: s.data });
    });

    // ---- interactive crosshair + nearest-point readout --------------
    const cross = el("line", { y1: padT, y2: padT + plotH, stroke: cssVar("--color-border-strong"), "stroke-width": "1", "vector-effect": "non-scaling-stroke", opacity: "0" });
    svg.appendChild(cross);
    const hi = seriesMeta.map((m) => {
      const c = el("circle", { r: 4, fill: m.color, stroke: cssVar("--color-bg-card"), "stroke-width": "2", opacity: "0" });
      svg.appendChild(c); return c;
    });
    const overlay = el("rect", { x: padL, y: padT, width: plotW, height: plotH, fill: "transparent", style: "cursor:crosshair" });
    svg.appendChild(overlay);
    function moveTo(clientX) {
      const r = svg.getBoundingClientRect();
      if (!r.width) return;
      const vx = ((clientX - r.left) / r.width) * W;
      let i = Math.round((vx - padL) / stepX);
      if (!isFinite(i)) return;
      i = Math.max(0, Math.min(n - 1, i));
      const px = x(i);
      cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.setAttribute("opacity", "1");
      let top = Infinity, rows = "";
      seriesMeta.forEach((m, k) => {
        const v = m.data[i];
        hi[k].setAttribute("cx", px); hi[k].setAttribute("cy", y(v)); hi[k].setAttribute("opacity", "1");
        if (y(v) < top) top = y(v);
        rows += `<div style="display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:2px;background:${m.color}"></span><span class="chart-tip__k">${m.name}</span> <span class="chart-tip__v">${(cfg.fmt ? cfg.fmt(v) : v)}${cfg.unit || ""}</span></div>`;
      });
      const sx = r.left + (px / W) * r.width;
      const sy = r.top + (top / H) * r.height;
      C.__showTip(`<div class="chart-tip__k" style="margin-bottom:4px">${cfg.labels[i]}</div>${rows}`, sx, sy);
    }
    overlay.addEventListener("mousemove", (e) => moveTo(e.clientX));
    overlay.addEventListener("mouseleave", () => {
      cross.setAttribute("opacity", "0");
      hi.forEach((c) => c.setAttribute("opacity", "0"));
      C.hideTip();
    });

    if (defs) {
      const d = el("defs", {}); d.innerHTML = defs; svg.insertBefore(d, svg.firstChild);
    }
    return svg;
  }

  /* =====================================================================
     BARS — simple vertical bars, single series, value tooltip
     cfg: { data:[], labels:[], color?, unit?, yMax?, fmt? }
     ===================================================================== */
  function bars(cfg) {
    const W = 620, H = 230, padL = 38, padR = 10, padT = 12, padB = 24;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const yMax = cfg.yMax != null ? cfg.yMax : Math.max(...cfg.data) * 1.15;
    const n = cfg.data.length;
    const slot = plotW / n, bw = slot * 0.56;
    const y = (v) => padT + plotH - (v / yMax) * plotH;
    const grid = cssVar("--chart-grid"), axisTxt = cssVar("--color-text-muted");
    const color = cfg.color || cssVar("--chart-bar");
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });

    for (let t = 0; t <= 4; t++) {
      const v = (yMax / 4) * t, yy = y(v);
      svg.appendChild(el("line", { x1: padL, y1: yy, x2: W - padR, y2: yy, stroke: grid, "stroke-width": "1", "vector-effect": "non-scaling-stroke" }));
      svg.appendChild(el("text", { x: padL - 6, y: yy + 3, "text-anchor": "end", "font-size": "9", fill: axisTxt })).textContent = (cfg.fmt ? cfg.fmt(v) : Math.round(v)) + (cfg.unit || "");
    }
    cfg.data.forEach((v, i) => {
      const bx = padL + i * slot + (slot - bw) / 2, hh = (v / yMax) * plotH;
      const rect = el("rect", { x: bx.toFixed(1), y: y(v).toFixed(1), width: bw.toFixed(1), height: hh.toFixed(1), rx: 2, fill: color, style: "cursor:pointer" });
      rect.addEventListener("mouseenter", () => {
        rect.style.filter = "brightness(1.35)";
        const r = rect.getBoundingClientRect();
        C.__showTip(`<span class="chart-tip__k">${cfg.labels[i]}</span> <span class="chart-tip__v">${(cfg.fmt ? cfg.fmt(v) : v)}${cfg.unit || ""}</span>`, r.left + r.width / 2, r.top);
      });
      rect.addEventListener("mouseleave", () => { rect.style.filter = ""; C.hideTip(); });
      svg.appendChild(rect);
      svg.appendChild(el("text", { x: (padL + i * slot + slot / 2).toFixed(1), y: H - 7, "text-anchor": "middle", "font-size": "9", fill: axisTxt })).textContent = cfg.labels[i];
    });
    return svg;
  }

  /* =====================================================================
     HBARS — horizontal labelled bars (rankings / breakdowns)
     items: [{ label, value, display, color? }]  (value = relative 0..max)
     ===================================================================== */
  function hbars(items, opts) {
    opts = opts || {};
    const max = Math.max(...items.map((i) => i.value));
    const wrap = document.createElement("div");
    wrap.className = "hbars";
    items.forEach((it) => {
      const row = document.createElement("div");
      row.className = "hbar";
      const pct = (it.value / max) * 100;
      row.innerHTML = `
        <span class="hbar__label">${it.label}</span>
        <span class="hbar__track"><span class="hbar__fill" style="width:0%;background:${it.color || "var(--color-accent)"}"></span></span>
        <span class="hbar__value num">${it.display != null ? it.display : it.value}</span>`;
      wrap.appendChild(row);
      requestAnimationFrame(() => { row.querySelector(".hbar__fill").style.width = pct.toFixed(1) + "%"; });
    });
    return wrap;
  }

  /* =====================================================================
     DONUT-LEGEND — multi-segment donut with legend list
     segs: [{ label, value, color }]
     ===================================================================== */
  function donutSegments(segs, centerLabel, centerSub) {
    const total = segs.reduce((a, s) => a + s.value, 0);
    const r = 42, c = 2 * Math.PI * r;
    const svg = el("svg", { viewBox: "0 0 100 100" });
    svg.appendChild(el("circle", { cx: 50, cy: 50, r, fill: "none", stroke: cssVar("--color-bg-elevated"), "stroke-width": 12 }));
    const arcs = [];
    let offset = 0;
    segs.forEach((s) => {
      const len = (s.value / total) * c;
      const arc = el("circle", { cx: 50, cy: 50, r, fill: "none", stroke: s.color, "stroke-width": 12, "stroke-dasharray": `${len} ${c - len}`, "stroke-dashoffset": -offset, transform: "rotate(-90 50 50)", style: "cursor:pointer;transition:stroke-width 160ms ease, opacity 160ms ease" });
      svg.appendChild(arc);
      arcs.push(arc);
      offset += len;
    });
    const wrap = document.createElement("div");
    wrap.className = "donut-legend";
    const ring = document.createElement("div");
    ring.className = "donut donut--lg";
    ring.appendChild(svg);
    const ctr = document.createElement("div");
    ctr.className = "donut__center";
    if (centerLabel) ctr.innerHTML = `<span class="donut__pct num">${centerLabel}</span><span class="donut__cap">${centerSub || ""}</span>`;
    ring.appendChild(ctr);

    const list = document.createElement("div");
    list.className = "legend-list";
    const rows = [];
    segs.forEach((s, i) => {
      const item = document.createElement("div");
      item.className = "legend-row";
      item.style.cursor = "pointer";
      item.innerHTML = `<span class="legend-swatch" style="background:${s.color}"></span>
        <span class="legend-row__label">${s.label}</span>
        <span class="legend-row__value num">${s.display != null ? s.display : s.value}</span>`;
      list.appendChild(item);
      rows.push(item);

      // hover links legend row ↔ arc; center shows the focused segment
      const focus = () => {
        arcs.forEach((a, k) => {
          a.setAttribute("stroke-width", k === i ? "14" : "12");
          a.style.opacity = k === i ? "1" : "0.28";
        });
        rows.forEach((rw, k) => { rw.style.opacity = k === i ? "1" : "0.45"; });
        const pctShown = Math.round((s.value / total) * 100);
        ctr.innerHTML = `<span class="donut__pct num">${s.display != null ? s.display : pctShown + "%"}</span><span class="donut__cap">${s.label}</span>`;
      };
      const reset = () => {
        arcs.forEach((a) => { a.setAttribute("stroke-width", "12"); a.style.opacity = "1"; });
        rows.forEach((rw) => { rw.style.opacity = "1"; });
        if (centerLabel) ctr.innerHTML = `<span class="donut__pct num">${centerLabel}</span><span class="donut__cap">${centerSub || ""}</span>`;
      };
      item.addEventListener("mouseenter", focus);
      item.addEventListener("mouseleave", reset);
      arcs[i].addEventListener("mouseenter", focus);
      arcs[i].addEventListener("mouseleave", reset);
    });
    wrap.appendChild(ring);
    wrap.appendChild(list);
    return wrap;
  }

  Object.assign(window.CHARTS, { line, bars, hbars, donutSegments });
})();
