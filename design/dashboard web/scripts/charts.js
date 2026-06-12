/* ============================================================================
   CHARTS — hand-rolled SVG renderers. No chart library.
   ----------------------------------------------------------------------------
   Strategy for "fit any size": every chart uses a fixed viewBox +
   preserveAspectRatio="none" so it stretches to its container width at a fixed
   CSS height, and every stroke uses vector-effect:non-scaling-stroke so lines
   stay crisp under non-uniform scale. A single shared tooltip element handles
   hover. Colors pull from CSS custom properties (see tokens.css).
   ============================================================================ */
(function () {
  const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs) => {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  };

  /* ---- shared tooltip ------------------------------------------------- */
  let tip;
  function ensureTip() {
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "chart-tip";
      document.body.appendChild(tip);
    }
    return tip;
  }
  function showTip(html, x, y) {
    const t = ensureTip();
    t.innerHTML = html;
    t.style.left = x + "px";
    t.style.top = y + "px";
    t.classList.add("is-on");
  }
  function hideTip() { if (tip) tip.classList.remove("is-on"); }
  function centerTop(node) {
    const r = node.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top };
  }

  /* =====================================================================
     SPARKLINE — area + line, fluid width
     ===================================================================== */
  function sparkline(series, color, opts) {
    opts = opts || {};
    const W = 240, H = 46, pad = 3;
    const min = Math.min(...series), max = Math.max(...series);
    const span = max - min || 1;
    const stepX = (W - pad * 2) / (series.length - 1);
    const pts = series.map((v, i) => [
      pad + i * stepX,
      H - pad - ((v - min) / span) * (H - pad * 2),
    ]);
    const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
    const area = line + ` L${(W - pad).toFixed(1)} ${H} L${pad} ${H} Z`;
    const uid = "sg" + Math.random().toString(36).slice(2, 7);

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });
    svg.innerHTML = `
      <defs><linearGradient id="${uid}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${color}" stop-opacity="0.34"/>
        <stop offset="1" stop-color="${color}" stop-opacity="0"/>
      </linearGradient></defs>
      <path d="${area}" fill="url(#${uid})"/>
      <path d="${line}" fill="none" stroke="${color}" stroke-width="2"
            vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>`;

    // ---- interactive hover: guide line + tracking dot + tooltip --------
    const guide = el("line", { y1: 0, y2: H, stroke: color, "stroke-width": "1", "vector-effect": "non-scaling-stroke", opacity: "0" });
    const dot = el("circle", { r: 3.2, fill: color, stroke: cssVar("--color-bg-card"), "stroke-width": "1.5", opacity: "0" });
    svg.appendChild(guide); svg.appendChild(dot);
    const overlay = el("rect", { x: 0, y: 0, width: W, height: H, fill: "transparent", style: "cursor:crosshair" });
    svg.appendChild(overlay);
    const fmt = opts.fmt;
    const labels = opts.labels;
    overlay.addEventListener("mousemove", (e) => {
      const r = svg.getBoundingClientRect();
      if (!r.width) return;
      const vx = ((e.clientX - r.left) / r.width) * W;
      let i = Math.round((vx - pad) / stepX);
      if (!isFinite(i)) return;
      i = Math.max(0, Math.min(series.length - 1, i));
      const px = pts[i][0], py = pts[i][1];
      guide.setAttribute("x1", px); guide.setAttribute("x2", px); guide.setAttribute("opacity", "0.35");
      dot.setAttribute("cx", px); dot.setAttribute("cy", py); dot.setAttribute("opacity", "1");
      const sx = r.left + (px / W) * r.width;
      const sy = r.top + (py / H) * r.height;
      if (fmt) {
        const lab = labels ? `<span class="chart-tip__k">${labels[i]}</span> ` : "";
        showTip(`${lab}<span class="chart-tip__v">${fmt(series[i], i)}${opts.unit || ""}</span>`, sx, sy);
      } else {
        showTip(`<span class="chart-tip__v">${labels ? labels[i] : Math.round(series[i])}</span>`, sx, sy);
      }
    });
    overlay.addEventListener("mouseleave", () => {
      guide.setAttribute("opacity", "0"); dot.setAttribute("opacity", "0"); hideTip();
    });
    return svg;
  }

  /* =====================================================================
     DONUT — single-value progress ring
     ===================================================================== */
  function donut(pct) {
    const r = 42, c = 2 * Math.PI * r;
    const filled = (pct / 100) * c;
    const accent = cssVar("--color-accent");
    const track = cssVar("--color-bg-elevated");
    const svg = el("svg", { viewBox: "0 0 100 100" });
    svg.innerHTML = `
      <circle cx="50" cy="50" r="${r}" fill="none" stroke="${track}" stroke-width="11"/>
      <circle cx="50" cy="50" r="${r}" fill="none" stroke="${accent}" stroke-width="11"
        stroke-linecap="round" stroke-dasharray="0 ${c}"
        style="transition:stroke-dasharray 1100ms cubic-bezier(0.22,1,0.36,1), stroke-width 160ms ease;cursor:pointer"/>`;
    // animate the ring filling from 0 → value after paint
    const ring = svg.querySelectorAll("circle")[1];
    const fill = () => ring.setAttribute("stroke-dasharray", `${filled} ${c}`);
    requestAnimationFrame(() => requestAnimationFrame(fill));
    setTimeout(fill, 700); // safety if rAF is throttled (hidden tab)
    // hover feedback
    ring.addEventListener("mouseenter", () => {
      ring.setAttribute("stroke-width", "13");
      const r2 = svg.getBoundingClientRect();
      showTip(`<span class="chart-tip__v">${pct}%</span> <span class="chart-tip__k">to $100M target</span>`, r2.left + r2.width / 2, r2.top + r2.height * 0.5);
    });
    ring.addEventListener("mouseleave", () => { ring.setAttribute("stroke-width", "11"); hideTip(); });
    return svg;
  }

  /* =====================================================================
     BAR + TARGET LINE — monthly revenue
     ===================================================================== */
  function barTarget(d) {
    const W = 600, H = 230, padL = 34, padR = 8, padT = 10, padB = 22;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const yMax = d.yMax;
    const n = d.revenue.length;
    const slot = plotW / n;
    const bw = slot * 0.5;
    const y = (v) => padT + plotH - (v / yMax) * plotH;
    const barColor = cssVar("--chart-bar");
    const barDim = cssVar("--chart-bar-2");
    const grid = cssVar("--chart-grid");
    const target = cssVar("--chart-target");
    const axisTxt = cssVar("--color-text-muted");

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });

    // gridlines + y labels (0,2,4,6,8,10,12)
    let g = "";
    for (let v = 0; v <= yMax; v += 2) {
      const yy = y(v);
      g += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="${grid}" stroke-width="1" vector-effect="non-scaling-stroke"/>`;
      g += `<text x="${padL - 6}" y="${yy + 3}" text-anchor="end" font-size="9" fill="${axisTxt}">${v === 0 ? "0" : v + "M"}</text>`;
    }
    svg.innerHTML = g;

    // bars (series 0 = Revenue)
    const barGroup = el("g", { "data-si": "0", "data-series": "Revenue" });
    svg.appendChild(barGroup);
    d.revenue.forEach((v, i) => {
      const x = padL + i * slot + (slot - bw) / 2;
      const hh = (v / yMax) * plotH;
      const dim = i > d.actualThrough;
      const rect = el("rect", {
        x: x.toFixed(1), y: y(v).toFixed(1), width: bw.toFixed(1), height: hh.toFixed(1),
        rx: 2, fill: dim ? barDim : barColor, style: "cursor:pointer",
      });
      rect.addEventListener("mouseenter", () => {
        rect.style.filter = "brightness(1.35)";
        const p = centerTop(rect);
        showTip(`<span class="chart-tip__k">${d.months[i]}</span> &nbsp;<span class="chart-tip__v">$${v.toFixed(1)}M</span>`, p.x, p.y);
      });
      rect.addEventListener("mouseleave", () => { rect.style.filter = ""; hideTip(); });
      barGroup.appendChild(rect);
      // x label
      svg.appendChild(el("text", {
        x: (padL + i * slot + slot / 2).toFixed(1), y: H - 6,
        "text-anchor": "middle", "font-size": "9", fill: axisTxt,
      })).textContent = d.months[i];
    });

    // dashed target line (series 1 = Target)
    const tline = d.target.map((v, i) => (i ? "L" : "M") + (padL + i * slot + slot / 2).toFixed(1) + " " + y(v).toFixed(1)).join(" ");
    svg.appendChild(el("path", {
      d: tline, fill: "none", stroke: target, "stroke-width": "1.6",
      "stroke-dasharray": "5 4", "vector-effect": "non-scaling-stroke", "stroke-linecap": "round",
      "data-si": "1", "data-series": "Target",
    }));
    return svg;
  }

  /* =====================================================================
     COMBO — UA spend/installs stacked-ish bars + CPI line (dual axis)
     ===================================================================== */
  function combo(d) {
    const W = 640, H = 250, padL = 34, padR = 34, padT = 14, padB = 24;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const n = d.spend.length;
    const slot = plotW / n;
    const bw = slot * 0.56;
    const spendMax = Math.max(...d.spend) * 1.1;
    const cpiMin = 0, cpiMax = 2.5;
    const ySpend = (v) => padT + plotH - (v / spendMax) * plotH;
    const yCpi = (v) => padT + plotH - ((v - cpiMin) / (cpiMax - cpiMin)) * plotH;
    const grid = cssVar("--chart-grid");
    const axisTxt = cssVar("--color-text-muted");
    const cpiCol = cssVar("--chart-line-cpi");
    const gFrom = cssVar("--chart-grad-from"), gTo = cssVar("--chart-grad-to");
    const uid = "cb" + Math.random().toString(36).slice(2, 7);

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });
    svg.innerHTML = `<defs><linearGradient id="${uid}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${gFrom}"/><stop offset="1" stop-color="${gTo}"/>
      </linearGradient></defs>`;

    // left gridlines (spend) every 30K -> use 0..150K style labels
    const leftTicks = [0, 30, 60, 90, 120, 150];
    leftTicks.forEach((v) => {
      const yy = padT + plotH - (v / 150) * plotH;
      svg.appendChild(el("line", { x1: padL, y1: yy, x2: W - padR, y2: yy, stroke: grid, "stroke-width": "1", "vector-effect": "non-scaling-stroke" }));
      svg.appendChild(el("text", { x: padL - 6, y: yy + 3, "text-anchor": "end", "font-size": "8.5", fill: axisTxt })).textContent = v === 0 ? "0" : v + "K";
    });
    // right axis CPI labels
    [0, 0.5, 1.0, 1.5, 2.0, 2.5].forEach((v) => {
      const yy = yCpi(v);
      svg.appendChild(el("text", { x: W - padR + 6, y: yy + 3, "text-anchor": "start", "font-size": "8.5", fill: axisTxt })).textContent = v.toFixed(1);
    });

    // bars (installs back, spend front gradient) — grouped for legend toggling
    const instGroup = el("g", { "data-si": "1", "data-series": "Installs" });
    const spendGroup = el("g", { "data-si": "0", "data-series": "UA Spend" });
    svg.appendChild(instGroup);
    svg.appendChild(spendGroup);
    d.spend.forEach((v, i) => {
      const x = padL + i * slot + (slot - bw) / 2;
      const inst = d.installs[i];
      // installs bar (purple-ish, behind, slightly wider/taller mapping)
      const ih = (inst / 150) * plotH;
      instGroup.appendChild(el("rect", { x: x.toFixed(1), y: (padT + plotH - ih).toFixed(1), width: bw.toFixed(1), height: ih.toFixed(1), rx: 1.5, fill: gTo, opacity: "0.55" }));
      // spend bar (gradient, front, thinner)
      const sh = (v / 150) * plotH;
      const sx = x + bw * 0.18;
      const rect = el("rect", { x: sx.toFixed(1), y: (padT + plotH - sh).toFixed(1), width: (bw * 0.64).toFixed(1), height: sh.toFixed(1), rx: 1.5, fill: `url(#${uid})`, style: "cursor:pointer" });
      rect.addEventListener("mouseenter", () => {
        rect.style.filter = "brightness(1.3)";
        const p = centerTop(rect);
        showTip(`<span class="chart-tip__v">$${v}K</span> spend<br><span class="chart-tip__k">${inst}K installs · $${d.cpi[i].toFixed(2)} CPI</span>`, p.x, p.y);
      });
      rect.addEventListener("mouseleave", () => { rect.style.filter = ""; hideTip(); });
      spendGroup.appendChild(rect);
    });

    // CPI line (series 2)
    const cline = d.cpi.map((v, i) => (i ? "L" : "M") + (padL + i * slot + slot / 2).toFixed(1) + " " + yCpi(v).toFixed(1)).join(" ");
    svg.appendChild(el("path", { d: cline, fill: "none", stroke: cpiCol, "stroke-width": "2", "vector-effect": "non-scaling-stroke", "stroke-linejoin": "round", "data-si": "2", "data-series": "CPI" }));

    // x ticks
    for (const lbl in d.xticks) {
      const i = d.xticks[lbl];
      svg.appendChild(el("text", { x: (padL + i * slot + slot / 2).toFixed(1), y: H - 7, "text-anchor": "middle", "font-size": "9", fill: axisTxt })).textContent = lbl;
    }
    return svg;
  }

  window.CHARTS = { sparkline, donut, barTarget, combo, hideTip, __showTip: showTip };
})();
