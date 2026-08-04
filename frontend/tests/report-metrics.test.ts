import { describe, expect, it } from "vitest";

import { REPORT_METRICS, metricLabel, permittedMetricsByGroup } from "@/lib/report-metrics";

describe("metric catalog (incl. reported rpt_* ladder)", () => {
  it("includes the reported install + finance fields", () => {
    const names = new Set(REPORT_METRICS.map((m) => m.name));
    for (const required of [
      "rpt_total_installs",
      "rpt_organic_installs",
      "rpt_total_revenue_usd",
      "rpt_net_profit_usd",
      "rpt_ua_cost_usd",
      "rpt_ad_revenue_usd",
      "store_total_installs",
      "total_paid_installs",
    ]) {
      expect(names.has(required), `missing ${required}`).toBe(true);
    }
  });

  it("has no duplicate metric names", () => {
    const names = REPORT_METRICS.map((m) => m.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("labels resolve for rpt fields", () => {
    expect(metricLabel("rpt_total_installs")).toBe("Reported total installs");
    expect(metricLabel("unknown_thing")).toBe("unknown_thing"); // graceful fallback
  });

  it("permission gating: viewers (store_installs only) never see revenue metrics", () => {
    const groups = permittedMetricsByGroup(["store_installs"]);
    const offered = groups.flatMap((g) => g.metrics.map((m) => m.name));
    expect(offered).toContain("store_total_installs");
    expect(offered).toContain("rpt_total_installs"); // reported installs are store_installs too
    expect(offered).not.toContain("total_revenue_usd");
    expect(offered).not.toContain("rpt_net_profit_usd");
  });
});
