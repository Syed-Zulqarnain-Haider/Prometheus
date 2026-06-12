/* ============================================================================
   DIRECTION EXPLORATIONS — shared chart helpers (return SVG strings).
   Pure presentation; each direction passes its own palette so the same data
   reads in four distinct aesthetics. Static (no interactivity) — these are
   look-and-feel studies.
   ============================================================================ */
(function () {
  const REV = [3.1, 3.6, 4.2, 5.0, 5.8, 6.6, 7.4, 8.1, 8.9, 9.7, 10.5, 11.3];
  const TGT = [3.0, 3.9, 4.6, 5.4, 6.1, 6.9, 7.6, 8.4, 9.1, 9.9, 10.6, 11.4];
  const MON = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
  const SPARK = [12, 14, 13, 16, 18, 17, 20, 19, 22, 24, 23, 27, 29, 31, 30, 34];

  // Monthly revenue bar chart + dashed target line.
  // o: { bar, bar2, target, grid, axis, radius(optional), gradId(optional, [from,to]) }
  function bars(o) {
    const W = 560, H = 220, padL = 30, padR = 8, padT = 10, padB = 22;
    const plotW = W - padL - padR, plotH = H - padT - padB, yMax = 12;
    const n = REV.length, slot = plotW / n, bw = slot * (o.barW || 0.5);
    const y = (v) => padT + plotH - (v / yMax) * plotH;
    const rad = o.radius != null ? o.radius : 2;
    let g = "";
    for (let v = 0; v <= yMax; v += 3) {
      const yy = y(v);
      g += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="${o.grid}" stroke-width="1"/>`;
      g += `<text x="${padL - 5}" y="${yy + 3}" text-anchor="end" font-size="9" fill="${o.axis}">${v}M</text>`;
    }
    let defs = "";
    let fill = o.bar;
    if (o.gradId) {
      defs = `<linearGradient id="${o.gradId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${o.gradFrom}"/><stop offset="1" stop-color="${o.gradTo}"/></linearGradient>`;
      fill = `url(#${o.gradId})`;
    }
    let rects = "";
    REV.forEach((v, i) => {
      const x = padL + i * slot + (slot - bw) / 2, hh = (v / yMax) * plotH;
      const future = i > 5;
      rects += `<rect x="${x.toFixed(1)}" y="${y(v).toFixed(1)}" width="${bw.toFixed(1)}" height="${hh.toFixed(1)}" rx="${rad}" fill="${future ? o.bar2 : fill}"/>`;
      rects += `<text x="${(padL + i * slot + slot / 2).toFixed(1)}" y="${H - 7}" text-anchor="middle" font-size="8.5" fill="${o.axis}">${MON[i]}</text>`;
    });
    const tline = TGT.map((v, i) => (i ? "L" : "M") + (padL + i * slot + slot / 2).toFixed(1) + " " + y(v).toFixed(1)).join(" ");
    const tgt = `<path d="${tline}" fill="none" stroke="${o.target}" stroke-width="1.6" stroke-dasharray="5 4" stroke-linecap="round"/>`;
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:100%;display:block">${defs ? `<defs>${defs}</defs>` : ""}${g}${rects}${tgt}</svg>`;
  }

  // Small sparkline (area + line). o: { stroke, fill(optional rgba), width }
  function spark(o) {
    const W = 180, H = 44, pad = 3;
    const min = Math.min(...SPARK), max = Math.max(...SPARK), span = max - min || 1;
    const sx = (W - pad * 2) / (SPARK.length - 1);
    const pts = SPARK.map((v, i) => [pad + i * sx, H - pad - ((v - min) / span) * (H - pad * 2)]);
    const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
    const area = line + ` L${W - pad} ${H} L${pad} ${H} Z`;
    const uid = "s" + Math.random().toString(36).slice(2, 6);
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:100%;display:block">
      ${o.fill ? `<defs><linearGradient id="${uid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${o.stroke}" stop-opacity="0.28"/><stop offset="1" stop-color="${o.stroke}" stop-opacity="0"/></linearGradient></defs><path d="${area}" fill="url(#${uid})"/>` : ""}
      <path d="${line}" fill="none" stroke="${o.stroke}" stroke-width="${o.width || 2}" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
  }

  // Progress donut. o: { color, track, pct }
  function donut(o) {
    const r = 42, c = 2 * Math.PI * r, filled = (o.pct / 100) * c;
    return `<svg viewBox="0 0 100 100" style="width:100%;height:100%;transform:rotate(-90deg)">
      <circle cx="50" cy="50" r="${r}" fill="none" stroke="${o.track}" stroke-width="${o.weight || 10}"/>
      <circle cx="50" cy="50" r="${r}" fill="none" stroke="${o.color}" stroke-width="${o.weight || 10}" stroke-linecap="${o.cap || "round"}" stroke-dasharray="${filled} ${c}"/></svg>`;
  }

  window.DIRCHARTS = { bars, spark, donut };
})();
