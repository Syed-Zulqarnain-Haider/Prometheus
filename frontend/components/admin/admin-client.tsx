"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { AccessRequestsPanel } from "@/components/admin/access-requests-panel";
import { AuditPanel } from "@/components/admin/audit-panel";
import { IntegrationPanel } from "@/components/admin/integration-panel";
import { RolesPanel } from "@/components/admin/roles-panel";
import { SystemPanel } from "@/components/admin/system-panel";
import { TargetsPanel } from "@/components/admin/targets-panel";
import { UsersPanel } from "@/components/admin/users-panel";
import { useMe } from "@/lib/api-hooks";

type Tab = "users" | "access" | "roles" | "targets" | "audit" | "integration" | "system";

const TABS: { value: Tab; label: string }[] = [
  { value: "users", label: "Users" },
  { value: "access", label: "Access requests" },
  { value: "roles", label: "Roles & permissions" },
  { value: "targets", label: "Revenue targets" },
  { value: "audit", label: "Audit log" },
  { value: "integration", label: "Integration" },
  { value: "system", label: "System" },
];

const TAB_VALUES = new Set<string>(TABS.map((t) => t.value));

export function AdminClient() {
  const { data: me, isLoading } = useMe();
  // Honor a ?tab= deep-link (e.g. a notification linking straight to Integration) — falls
  // back to Users for an unknown/absent value.
  const searchParams = useSearchParams();
  const requested = searchParams.get("tab");
  const [tab, setTab] = useState<Tab>(
    requested && TAB_VALUES.has(requested) ? (requested as Tab) : "users",
  );

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
      {tab === "access" && <AccessRequestsPanel />}
      {tab === "roles" && <RolesPanel />}
      {tab === "targets" && <TargetsPanel />}
      {tab === "audit" && <AuditPanel />}
      {tab === "integration" && <IntegrationPanel />}
      {tab === "system" && <SystemPanel />}
    </div>
  );
}
