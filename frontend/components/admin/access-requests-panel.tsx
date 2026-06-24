"use client";

import { useState } from "react";

import { ScopeEditor } from "@/components/admin/scope-editor";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  type AccessRequest,
  useAccessRequests,
  useAdminRoles,
  useApproveAccessRequest,
  useRejectAccessRequest,
} from "@/lib/api-hooks";
import { formatDateTime } from "@/lib/format";
import type { Scope } from "@/lib/types";

function RequestRow({ req, roleNames }: { req: AccessRequest; roleNames: string[] }) {
  const approve = useApproveAccessRequest();
  const reject = useRejectAccessRequest();
  const [roles, setRoles] = useState<string[]>([]);
  const [scopes, setScopes] = useState<Scope[]>([{ scope_type: "all", scope_value: null }]);
  const [expiryDays, setExpiryDays] = useState("");

  function toggleRole(role: string) {
    setRoles((c) => (c.includes(role) ? c.filter((r) => r !== role) : [...c, role]));
  }

  function onApprove() {
    const days = Number(expiryDays);
    approve.mutate({
      id: req.id,
      body: {
        roles,
        scopes,
        ...(expiryDays.trim() && Number.isInteger(days) && days >= 1
          ? { access_duration_days: days }
          : {}),
      },
    });
  }

  const busy = approve.isPending || reject.isPending;

  return (
    <Card>
      <CardContent className="space-y-3 py-3">
        <div>
          <p className="font-medium">{req.display_name ?? req.email}</p>
          <p className="text-xs text-muted-foreground">
            {req.email} · requested {formatDateTime(req.created_at)}
          </p>
        </div>
        <div className="space-y-1">
          <Label>Roles</Label>
          <div className="flex flex-wrap gap-3">
            {roleNames.map((role) => (
              <label key={role} className="flex cursor-pointer items-center gap-2 text-sm">
                <Checkbox checked={roles.includes(role)} onCheckedChange={() => toggleRole(role)} />
                {role}
              </label>
            ))}
          </div>
        </div>
        <div className="space-y-1">
          <Label>Row scopes</Label>
          <ScopeEditor scopes={scopes} onChange={setScopes} />
        </div>
        <div className="space-y-1">
          <Label htmlFor={`exp-${req.id}`}>Access expires in (days, optional)</Label>
          <Input
            id={`exp-${req.id}`}
            type="number"
            min={1}
            max={3650}
            className="w-40"
            placeholder="permanent"
            value={expiryDays}
            onChange={(e) => setExpiryDays(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={busy || roles.length === 0} onClick={onApprove}>
            {approve.isPending ? "Approving…" : "Approve"}
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={busy}
            onClick={() => reject.mutate(req.id)}
          >
            {reject.isPending ? "Rejecting…" : "Reject"}
          </Button>
          {roles.length === 0 && (
            <span className="text-xs text-muted-foreground">Pick at least one role to approve.</span>
          )}
          {(approve.isError || reject.isError) && (
            <span className="text-xs text-destructive">Action failed. Try again.</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function AccessRequestsPanel() {
  const { data: requests, isLoading } = useAccessRequests();
  const { data: roles } = useAdminRoles();
  const roleNames = (roles ?? []).map((r) => r.name);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (!requests?.length) {
    return <p className="text-sm text-muted-foreground">No pending access requests.</p>;
  }

  return (
    <div className="space-y-2">
      {requests.map((req) => (
        <RequestRow key={req.id} req={req} roleNames={roleNames} />
      ))}
    </div>
  );
}
