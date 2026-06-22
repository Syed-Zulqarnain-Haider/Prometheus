"use client";

import { useState } from "react";

import { AuditPanel } from "@/components/admin/audit-panel";
import { RolesPanel } from "@/components/admin/roles-panel";
import { SystemPanel } from "@/components/admin/system-panel";
import { TargetsPanel } from "@/components/admin/targets-panel";
import { UsersPanel } from "@/components/admin/users-panel";
import { useMe } from "@/lib/api-hooks";

type Tab = "users" | "roles" | "targets" | "audit" | "system";

const TABS: { value: Tab; label: string }[] = [
  { value: "users", label: "Users" },
  { value: "roles", label: "Roles & permissions" },
  { value: "targets", label: "Revenue targets" },
  { value: "audit", label: "Audit log" },
  { value: "system", label: "System" },
];

export function AdminClient() {
  const { data: me, isLoading } = useMe();
  const [tab, setTab] = useState<Tab>("users");

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (!me?.capabilities.includes("admin_panel")) {
    return (
      <p className="text-sm text-muted-foreground">
        You don&apos;t have access to the admin panel.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 border-b">
        {TABS.map((entry) => (
          <button
            key={entry.value}
            type="button"
            onClick={() => setTab(entry.value)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              tab === entry.value
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {tab === "users" && <UsersPanel />}
      {tab === "roles" && <RolesPanel />}
      {tab === "targets" && <TargetsPanel />}
      {tab === "audit" && <AuditPanel />}
      {tab === "system" && <SystemPanel />}
    </div>
  );
}
