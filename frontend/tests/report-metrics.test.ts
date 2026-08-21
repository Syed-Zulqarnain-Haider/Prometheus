import { describe, expect, it } from "vitest";

import {
  METRIC_GROUP_LABELS,
  REPORT_METRICS,
  metricLabel,
  permittedMetricsByGroup,
} from "@/lib/report-metrics";

// The report builder offers metrics based on the caller's permitted groups. Offering one
// they cannot see is a disclosure the server would refuse anyway - but the UI must not
// invite it, and the catalogue must not drift from the groups it claims to belong to.
describe("report metrics catalogue", () => {
  it("labels every metric, and falls back to the raw name for an unknown one", () => {
    for (const metric of REPORT_METRICS) {
      expect(metricLabel(metric.name)).not.toBe("");
    }
    expect(metricLabel("not_a_metric")).toBe("not_a_metric");
  });

  it("has no duplicate metric names", () => {
    const names = REPORT_METRICS.map((m) => m.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("only uses groups that have a label", () => {
    for (const metric of REPORT_METRICS) {
      expect(METRIC_GROUP_LABELS[metric.group]).toBeTruthy();
    }
  });
});

describe("permittedMetricsByGroup", () => {
  it("offers nothing to a caller with no groups", () => {
    expect(permittedMetricsByGroup([])).toEqual([]);
  });

  it("offers only the groups the caller holds", () => {
    const groups = permittedMetricsByGroup(["store_installs"]).map((g) => g.group);
    expect(groups).toEqual(["store_installs"]);
  });

  it("never returns a metric outside its own group", () => {
    for (const entry of permittedMetricsByGroup(["ua_spend", "profitability"])) {
      for (const metric of entry.metrics) {
        expect(metric.group).toBe(entry.group);
      }
    }
  });

  it("silently ignores a group name that does not exist", () => {
    expect(permittedMetricsByGroup(["made_up_group"])).toEqual([]);
  });

  it("drops a permitted group that has no metrics rather than showing an empty section", () => {
    for (const entry of permittedMetricsByGroup(Object.keys(METRIC_GROUP_LABELS))) {
      expect(entry.metrics.length).toBeGreaterThan(0);
    }
  });
});
