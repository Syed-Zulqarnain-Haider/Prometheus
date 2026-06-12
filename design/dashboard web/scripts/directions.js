/* ============================================================================
   DIRECTION EXPLORATIONS — four distinct aesthetics of the same dashboard
   slice. Each returns a self-contained HTML string (scoped class prefix +
   embedded <style>). All use sharp / precise corners per the brief.
   window.DIRECTIONS = { A, B, C, D }
   ============================================================================ */
(function () {
  const CH = window.DIRCHARTS;

  /* ========================================================================
     A · SWISS LEDGER — light, editorial, hairline rules, serif headlines,
     monochrome + oxblood accent. Calm, intelligent, broadsheet-financial.
     ======================================================================== */
  function A() {
    const spark = CH.spark({ stroke: "#2f6b4f", width: 1.6 });
    const chart = CH.bars({ bar: "#26241f", bar2: "#d8d2c2", target: "#8a2f2f", grid: "#e6e1d4", axis: "#9c968a", barW: 0.46, radius: 1 });
    const donut = CH.donut({ color: "#8a2f2f", track: "#e6e1d4", pct: 35.6, cap: "butt", weight: 9 });
    return `<div class="da">
<style>
.da{--ink:#1c1b17;--mut:#6f6a5e;--line:#e2ddcf;--paper:#f7f5ee;--ox:#8a2f2f;--grn:#2f6b4f;
  background:var(--paper);color:var(--ink);font-family:"Archivo",sans-serif;padding:34px 38px;height:100%;box-sizing:border-box}
.da *{box-sizing:border-box}
.da-top{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid var(--ink);padding-bottom:16px}
.da-brand{font-family:"Spectral",serif;font-weight:600;font-size:13px;letter-spacing:.34em;text-transform:uppercase}
.da-h{font-family:"Spectral",serif;font-weight:500;font-size:34px;letter-spacing:-.01em;margin:6px 0 0}
.da-sub{font-size:12px;color:var(--mut);margin-top:4px;letter-spacing:.02em}
.da-date{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--mut);border:1px solid var(--line);padding:7px 12px}
.da-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:26px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.da-kpi{padding:18px 22px 18px 0;border-right:1px solid var(--line)}
.da-kpi:last-child{border-right:none}
.da-lab{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut)}
.da-val{font-family:"Spectral",serif;font-weight:600;font-size:30px;letter-spacing:-.01em;margin:8px 0 6px;font-variant-numeric:tabular-nums}
.da-d{font-size:12px;color:var(--grn);font-weight:600;letter-spacing:.02em}
.da-spk{height:34px;margin-top:10px}
.da-main{display:grid;grid-template-columns:1.55fr 1fr;gap:30px;margin-top:30px}
.da-ct{font-family:"Spectral",serif;font-weight:600;font-size:16px;margin:0 0 14px;display:flex;justify-content:space-between;align-items:baseline}
.da-ct small{font-family:"Archivo";font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--mut);font-weight:500}
.da-chart{height:212px}
.da-prog{display:flex;align-items:center;gap:22px}
.da-donut{width:118px;height:118px;flex:none;position:relative}
.da-donut-c{position:absolute;inset:0;display:grid;place-content:center;text-align:center}
.da-donut-p{font-family:"Spectral",serif;font-weight:600;font-size:22px}
.da-donut-l{font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}
.da-stats div{padding:9px 0;border-bottom:1px solid var(--line)}
.da-stats div:last-child{border-bottom:none}
.da-stats .k{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}
.da-stats .v{font-family:"Spectral",serif;font-weight:600;font-size:16px;font-variant-numeric:tabular-nums}
</style>
<header class="da-top"><div><div class="da-brand">Terafort</div><h1 class="da-h">CEO Command Center</h1><div class="da-sub">Real-time overview of enterprise performance</div></div><div class="da-date">May 1 — 25, 2025</div></header>
<div class="da-kpis">
  <div class="da-kpi"><div class="da-lab">Gross Revenue</div><div class="da-val">$4.13M</div><div class="da-d">▲ 18.7%</div><div class="da-spk">${spark}</div></div>
  <div class="da-kpi"><div class="da-lab">Net Revenue</div><div class="da-val">$2.89M</div><div class="da-d">▲ 21.3%</div><div class="da-spk">${spark}</div></div>
  <div class="da-kpi"><div class="da-lab">Gross Profit</div><div class="da-val">$2.04M</div><div class="da-d">▲ 23.8%</div><div class="da-spk">${spark}</div></div>
</div>
<div class="da-main">
  <div><div class="da-ct">Monthly Revenue Trend <small>Actual vs Target</small></div><div class="da-chart">${chart}</div></div>
  <div><div class="da-ct">Revenue to $100M</div><div class="da-prog"><div class="da-donut">${donut}<div class="da-donut-c"><div class="da-donut-p">35.6%</div><div class="da-donut-l">Achieved</div></div></div><div class="da-stats" style="flex:1"><div><div class="k">YTD Revenue</div><div class="v">$35.61M</div></div><div><div class="k">Remaining</div><div class="v">$64.39M</div></div></div></div></div>
</div>
</div>`;
  }

  /* ========================================================================
     B · ELECTRIC — light, vivid indigo, big bold sans, gradient charts,
     confident & energetic modern-SaaS. Precise 4px corners.
     ======================================================================== */
  function B() {
    const spark = CH.spark({ stroke: "#5a3df5", fill: true, width: 2.4 });
    const chart = CH.bars({ bar: "#5a3df5", bar2: "#d3ccf9", target: "#9aa0ae", grid: "#eef0f5", axis: "#9aa0ae", barW: 0.56, radius: 3, gradId: "bg", gradFrom: "#6d4dff", gradTo: "#a06bff" });
    const donut = CH.donut({ color: "#5a3df5", track: "#e9ebf2", pct: 35.6, weight: 11 });
    return `<div class="db">
<style>
.db{--ind:#5a3df5;--ink:#10131c;--mut:#6b7280;--line:#e7eaf1;--bg:#eef1f7;--card:#fff;--grn:#0fae74;
  background:var(--bg);color:var(--ink);font-family:"Plus Jakarta Sans",sans-serif;padding:30px 34px;height:100%;box-sizing:border-box}
.db *{box-sizing:border-box}
.db-top{display:flex;justify-content:space-between;align-items:center}
.db-brand{display:flex;align-items:center;gap:10px}
.db-logo{width:30px;height:30px;border-radius:7px;background:linear-gradient(135deg,#6d4dff,#a06bff);display:grid;place-items:center;color:#fff;font-weight:800;font-size:15px}
.db-bn{font-weight:800;font-size:15px;letter-spacing:-.01em}
.db-h{font-weight:800;font-size:30px;letter-spacing:-.025em;margin:14px 0 0}
.db-sub{color:var(--mut);font-size:13px;margin-top:3px;font-weight:500}
.db-date{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:9px 14px;font-size:12.5px;font-weight:700;color:var(--ind)}
.db-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:22px}
.db-kpi{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:16px 17px;box-shadow:0 2px 10px rgba(30,40,80,.04)}
.db-lab{font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--mut)}
.db-val{font-weight:800;font-size:28px;letter-spacing:-.03em;margin:8px 0 8px;font-variant-numeric:tabular-nums}
.db-d{display:inline-flex;align-items:center;gap:4px;background:rgba(15,174,116,.12);color:var(--grn);font-weight:800;font-size:12px;padding:3px 9px;border-radius:5px}
.db-spk{height:38px;margin-top:12px}
.db-main{display:grid;grid-template-columns:1.5fr 1fr;gap:14px;margin-top:14px}
.db-card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:18px;box-shadow:0 2px 10px rgba(30,40,80,.04)}
.db-ct{font-weight:800;font-size:14px;letter-spacing:-.01em;margin:0 0 14px;display:flex;justify-content:space-between}
.db-ct .pill{background:rgba(90,61,245,.1);color:var(--ind);font-size:10.5px;font-weight:800;padding:3px 9px;border-radius:5px;text-transform:uppercase;letter-spacing:.04em}
.db-chart{height:208px}
.db-prog{display:flex;align-items:center;gap:18px}
.db-donut{width:120px;height:120px;flex:none;position:relative}
.db-donut-c{position:absolute;inset:0;display:grid;place-content:center;text-align:center}
.db-donut-p{font-weight:800;font-size:23px;letter-spacing:-.02em}
.db-donut-l{font-size:10px;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
.db-stats .row{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid var(--line)}
.db-stats .row:last-child{border-bottom:none}
.db-stats .k{font-size:12px;color:var(--mut);font-weight:600}
.db-stats .v{font-weight:800;font-size:15px;font-variant-numeric:tabular-nums}
</style>
<header class="db-top"><div class="db-brand"><div class="db-logo">T</div><div class="db-bn">TERAFORT</div></div><div class="db-date">May 1 – 25, 2025</div></header>
<h1 class="db-h">CEO Command Center</h1><div class="db-sub">Real-time overview of Terafort performance</div>
<div class="db-kpis">
  <div class="db-kpi"><div class="db-lab">Gross Revenue</div><div class="db-val">$4.13M</div><span class="db-d">↑ 18.7%</span><div class="db-spk">${spark}</div></div>
  <div class="db-kpi"><div class="db-lab">Net Revenue</div><div class="db-val">$2.89M</div><span class="db-d">↑ 21.3%</span><div class="db-spk">${spark}</div></div>
  <div class="db-kpi"><div class="db-lab">Gross Profit</div><div class="db-val">$2.04M</div><span class="db-d">↑ 23.8%</span><div class="db-spk">${spark}</div></div>
</div>
<div class="db-main">
  <div class="db-card"><div class="db-ct">Monthly Revenue Trend <span class="pill">Target</span></div><div class="db-chart">${chart}</div></div>
  <div class="db-card"><div class="db-ct">Revenue to $100M</div><div class="db-prog"><div class="db-donut">${donut}<div class="db-donut-c"><div class="db-donut-p">35.6%</div><div class="db-donut-l">Achieved</div></div></div></div><div class="db-stats" style="margin-top:16px"><div class="row"><span class="k">YTD Revenue</span><span class="v">$35.61M</span></div><div class="row"><span class="k">Remaining</span><span class="v">$64.39M</span></div></div></div>
</div>
</div>`;
  }

  /* ========================================================================
     C · WARM LUXE — dark warm charcoal, gold + sage, elegant serif display.
     Private-bank / luxury-brand restraint. Sharp 2px corners, gold hairlines.
     ======================================================================== */
  function C() {
    const spark = CH.spark({ stroke: "#d8b15a", width: 1.8 });
    const chart = CH.bars({ bar: "#d8b15a", bar2: "#4a4230", target: "#93a585", grid: "#2a251c", axis: "#8a7f68", barW: 0.46, radius: 1 });
    const donut = CH.donut({ color: "#d8b15a", track: "#2a251c", pct: 35.6, cap: "butt", weight: 9 });
    return `<div class="dc">
<style>
.dc{--gold:#d8b15a;--sage:#93a585;--ink:#f1e9d6;--mut:#9b9079;--line:#2c2719;--bg:#141009;--card:#1c1710;
  background:radial-gradient(900px 480px at 85% -10%,rgba(216,177,90,.08),transparent 60%),var(--bg);color:var(--ink);font-family:"Jost",sans-serif;padding:34px 38px;height:100%;box-sizing:border-box}
.dc *{box-sizing:border-box}
.dc-top{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:1px solid var(--line);padding-bottom:18px}
.dc-brand{font-size:12px;letter-spacing:.42em;text-transform:uppercase;color:var(--gold);font-weight:500}
.dc-h{font-family:"Cormorant Garamond",serif;font-weight:600;font-size:42px;letter-spacing:.005em;margin:8px 0 0;line-height:1}
.dc-sub{font-size:12.5px;color:var(--mut);margin-top:7px;letter-spacing:.04em}
.dc-date{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut);border:1px solid var(--line);padding:8px 13px}
.dc-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin-top:26px;background:var(--line);border:1px solid var(--line)}
.dc-kpi{background:var(--card);padding:18px 20px}
.dc-lab{font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--mut)}
.dc-val{font-family:"Cormorant Garamond",serif;font-weight:600;font-size:36px;margin:6px 0 4px;line-height:1;font-variant-numeric:tabular-nums}
.dc-d{font-size:12px;color:var(--sage);letter-spacing:.04em}
.dc-spk{height:34px;margin-top:12px;color:var(--gold)}
.dc-main{display:grid;grid-template-columns:1.55fr 1fr;gap:28px;margin-top:28px}
.dc-ct{font-family:"Cormorant Garamond",serif;font-size:22px;font-weight:600;margin:0 0 14px;display:flex;justify-content:space-between;align-items:baseline}
.dc-ct small{font-family:"Jost";font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut)}
.dc-chart{height:208px}
.dc-prog{display:flex;align-items:center;gap:22px}
.dc-donut{width:120px;height:120px;flex:none;position:relative}
.dc-donut-c{position:absolute;inset:0;display:grid;place-content:center;text-align:center}
.dc-donut-p{font-family:"Cormorant Garamond",serif;font-weight:600;font-size:26px}
.dc-donut-l{font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut)}
.dc-stats div{padding:10px 0;border-bottom:1px solid var(--line)}
.dc-stats div:last-child{border-bottom:none}
.dc-stats .k{font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut)}
.dc-stats .v{font-family:"Cormorant Garamond",serif;font-weight:600;font-size:20px;font-variant-numeric:tabular-nums}
</style>
<header class="dc-top"><div><div class="dc-brand">Terafort</div><h1 class="dc-h">CEO Command Center</h1><div class="dc-sub">Real-time overview of enterprise performance</div></div><div class="dc-date">May 1 — 25, 2025</div></header>
<div class="dc-kpis">
  <div class="dc-kpi"><div class="dc-lab">Gross Revenue</div><div class="dc-val">$4.13M</div><div class="dc-d">▲ 18.7%</div><div class="dc-spk">${spark}</div></div>
  <div class="dc-kpi"><div class="dc-lab">Net Revenue</div><div class="dc-val">$2.89M</div><div class="dc-d">▲ 21.3%</div><div class="dc-spk">${spark}</div></div>
  <div class="dc-kpi"><div class="dc-lab">Gross Profit</div><div class="dc-val">$2.04M</div><div class="dc-d">▲ 23.8%</div><div class="dc-spk">${spark}</div></div>
</div>
<div class="dc-main">
  <div><div class="dc-ct">Monthly Revenue Trend <small>Actual vs Target</small></div><div class="dc-chart">${chart}</div></div>
  <div><div class="dc-ct">Revenue to $100M</div><div class="dc-prog"><div class="dc-donut">${donut}<div class="dc-donut-c"><div class="dc-donut-p">35.6%</div><div class="dc-donut-l">Achieved</div></div></div><div class="dc-stats" style="flex:1"><div><div class="k">YTD Revenue</div><div class="v">$35.61M</div></div><div><div class="k">Remaining</div><div class="v">$64.39M</div></div></div></div></div>
</div>
</div>`;
  }

  /* ========================================================================
     D · TERMINAL — near-black, monospace everything, amber + cyan, visible
     grid & bracket motifs. Bold technical command-center. Zero radius.
     ======================================================================== */
  function D() {
    const spark = CH.spark({ stroke: "#ffb454", width: 1.6 });
    const chart = CH.bars({ bar: "#ffb454", bar2: "#3a3320", target: "#4fd2e0", grid: "#1c1c20", axis: "#6c6c74", barW: 0.5, radius: 0 });
    const donut = CH.donut({ color: "#ffb454", track: "#1c1c20", pct: 35.6, cap: "butt", weight: 10 });
    return `<div class="dd">
<style>
.dd{--amb:#ffb454;--cyan:#4fd2e0;--ink:#e9e9ec;--mut:#74747c;--line:#26262c;--bg:#0a0a0b;--card:#101013;--grn:#5ef08a;
  background:var(--bg);color:var(--ink);font-family:"JetBrains Mono",monospace;padding:30px 34px;height:100%;box-sizing:border-box}
.dd *{box-sizing:border-box}
.dd-top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:16px}
.dd-brand{font-size:12px;letter-spacing:.3em;color:var(--amb);font-weight:700}
.dd-brand::before{content:"▍ "}
.dd-h{font-size:23px;font-weight:700;letter-spacing:.02em;margin:14px 0 0}
.dd-h::before{content:"> ";color:var(--amb)}
.dd-sub{font-size:11.5px;color:var(--mut);margin-top:4px}
.dd-date{font-size:11px;color:var(--cyan);border:1px solid var(--line);padding:8px 12px;letter-spacing:.04em}
.dd-date::before{content:"[ ";color:var(--mut)}.dd-date::after{content:" ]";color:var(--mut)}
.dd-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:22px}
.dd-kpi{background:var(--card);border:1px solid var(--line);padding:15px 16px;position:relative}
.dd-kpi::before{content:"";position:absolute;top:0;left:0;width:8px;height:8px;border-top:2px solid var(--amb);border-left:2px solid var(--amb)}
.dd-lab{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut)}
.dd-val{font-size:26px;font-weight:700;letter-spacing:-.02em;margin:9px 0 7px}
.dd-d{font-size:11.5px;color:var(--grn);font-weight:700}
.dd-d::before{content:"▲ "}
.dd-spk{height:36px;margin-top:11px}
.dd-main{display:grid;grid-template-columns:1.5fr 1fr;gap:12px;margin-top:12px}
.dd-card{background:var(--card);border:1px solid var(--line);padding:17px}
.dd-ct{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;margin:0 0 14px;display:flex;justify-content:space-between;color:var(--ink)}
.dd-ct span{color:var(--cyan)}
.dd-chart{height:206px}
.dd-prog{display:flex;align-items:center;gap:18px}
.dd-donut{width:118px;height:118px;flex:none;position:relative}
.dd-donut-c{position:absolute;inset:0;display:grid;place-content:center;text-align:center}
.dd-donut-p{font-size:22px;font-weight:700}
.dd-donut-l{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut)}
.dd-stats .row{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px dashed var(--line)}
.dd-stats .row:last-child{border-bottom:none}
.dd-stats .k{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
.dd-stats .v{font-size:14px;font-weight:700}
</style>
<header class="dd-top"><div class="dd-brand">TERAFORT</div><div class="dd-date">MAY 01—25 2025</div></header>
<h1 class="dd-h">CEO_COMMAND_CENTER</h1><div class="dd-sub">// real-time overview of terafort performance</div>
<div class="dd-kpis">
  <div class="dd-kpi"><div class="dd-lab">GROSS_REVENUE</div><div class="dd-val">$4.13M</div><div class="dd-d">18.7%</div><div class="dd-spk">${spark}</div></div>
  <div class="dd-kpi"><div class="dd-lab">NET_REVENUE</div><div class="dd-val">$2.89M</div><div class="dd-d">21.3%</div><div class="dd-spk">${spark}</div></div>
  <div class="dd-kpi"><div class="dd-lab">GROSS_PROFIT</div><div class="dd-val">$2.04M</div><div class="dd-d">23.8%</div><div class="dd-spk">${spark}</div></div>
</div>
<div class="dd-main">
  <div class="dd-card"><div class="dd-ct">MONTHLY_REVENUE_TREND <span>// target</span></div><div class="dd-chart">${chart}</div></div>
  <div class="dd-card"><div class="dd-ct">REVENUE → $100M</div><div class="dd-prog"><div class="dd-donut">${donut}<div class="dd-donut-c"><div class="dd-donut-p">35.6%</div><div class="dd-donut-l">ACHIEVED</div></div></div></div><div class="dd-stats" style="margin-top:14px"><div class="row"><span class="k">YTD_REV</span><span class="v">$35.61M</span></div><div class="row"><span class="k">REMAINING</span><span class="v">$64.39M</span></div></div></div>
</div>
</div>`;
  }

  window.DIRECTIONS = { A, B, C, D };
})();
