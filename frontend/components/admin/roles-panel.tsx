"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { useAdminRoles, useUpdateRole } from "@/lib/api-hooks";
import { METRIC_GROUP_LABELS, type MetricGroup } from "@/lib/report-metrics";
import type { RoleConfig } from "@/lib/types";

const ALL_GROUPS = Object.keys(METRIC_GROUP_LABELS) as MetricGroup[];
const ALL_CAPABILITIES = ["export", "share_report", "admin_panel"] as const;
const CAPABILITY_LABELS: Record<string, string> = {
  export: "Export",
  share_report: "Share reports",
  admin_panel: "Admin panel",
};

function RoleRow({ role }: { role: RoleConfig }) {
  const update = useUpdateRole();
  const [groups, setGroups] = useState<string[]>(role.metric_groups);
  const [caps, setCaps] = useState<string[]>(role.capabilities);

  const dirty =
    groups.slice().sort().join() !== role.metric_groups.slice().sort().join() ||
    caps.slice().sort().join() !== role.capabilities.slice().sort().join();

  function toggle(list: string[], setList: (v: string[]) => void, value: string) {
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
          {role.name}
        </CardTitle>
        <Button
          size="sm"
          onClick={() => update.mutate({ id: role.id, metricGroups: groups, capabilities: caps })}
          disabled={!dirty || update.isPending}
        >
          {update.isPending ? "Saving…" : "Save"}
        </Button>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Metric groups
          </p>
          <div className="grid grid-cols-1 gap-1">
            {ALL_GROUPS.map((group) => (
              <label key={group} className="flex cursor-pointer items-center gap-2 text-sm">
                <Checkbox
                  checked={groups.includes(group)}
                  onCheckedChange={() => toggle(groups, setGroups, group)}
                />
                {METRIC_GROUP_LABELS[group]}
              </label>
            ))}
          </div>
        </div>
        <div className="space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Capabilities
          </p>
          <div className="grid grid-cols-1 gap-1">
            {ALL_CAPABILITIES.map((cap) => (
              <label key={cap} className="flex cursor-pointer items-center gap-2 text-sm">
                <Checkbox
                  checked={caps.includes(cap)}
                  onCheckedChange={() => toggle(caps, setCaps, cap)}
                />
                {CAPABILITY_LABELS[cap]}
              </label>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function RolesPanel() {
  const { data: roles } = useAdminRoles();
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Metric-group and capability grants are per role and take effect immediately
        (cached sessions are busted on save).
      </p>
      {(roles ?? []).map((role) => (
        <RoleRow key={role.id} role={role} />
      ))}
    </div>
  );
}
