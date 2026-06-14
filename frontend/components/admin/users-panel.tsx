"use client";

import { useState } from "react";

import { ScopeEditor } from "@/components/admin/scope-editor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useAdminRoles,
  useAdminUsers,
  useCreateUser,
  useUpdateUser,
} from "@/lib/api-hooks";
import type { AdminUser, Scope } from "@/lib/types";

function RolePicker({
  available,
  selected,
  onToggle,
}: {
  available: string[];
  selected: string[];
  onToggle: (role: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-3">
      {available.map((role) => (
        <label key={role} className="flex cursor-pointer items-center gap-2 text-sm">
          <Checkbox checked={selected.includes(role)} onCheckedChange={() => onToggle(role)} />
          {role}
        </label>
      ))}
    </div>
  );
}

function UserEditor({ user, roleNames }: { user: AdminUser; roleNames: string[] }) {
  const update = useUpdateUser();
  const [roles, setRoles] = useState<string[]>(user.roles);
  const [scopes, setScopes] = useState<Scope[]>(user.scopes);

  function toggleRole(role: string) {
    setRoles((current) =>
      current.includes(role) ? current.filter((r) => r !== role) : [...current, role],
    );
  }

  return (
    <div className="space-y-4 border-t pt-4">
      <div className="space-y-1">
        <Label>Roles</Label>
        <RolePicker available={roleNames} selected={roles} onToggle={toggleRole} />
      </div>
      <div className="space-y-1">
        <Label>Row scopes</Label>
        <ScopeEditor scopes={scopes} onChange={setScopes} />
      </div>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          onClick={() => update.mutate({ id: user.id, body: { roles, scopes } })}
          disabled={update.isPending}
        >
          {update.isPending ? "Saving…" : "Save changes"}
        </Button>
        <Button
          size="sm"
          variant={user.is_active ? "destructive" : "secondary"}
          onClick={() =>
            update.mutate({ id: user.id, body: { is_active: !user.is_active } })
          }
          disabled={update.isPending}
        >
          {user.is_active ? "Deactivate" : "Reactivate"}
        </Button>
        {update.isError && (
          <span className="text-xs text-destructive">
            {update.error instanceof Error ? update.error.message : "Save failed."}
          </span>
        )}
      </div>
    </div>
  );
}

function CreateUserForm({ roleNames }: { roleNames: string[] }) {
  const create = useCreateUser();
  const [open, setOpen] = useState(false);
  const [firebaseUid, setFirebaseUid] = useState("");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [roles, setRoles] = useState<string[]>([]);
  const [scopes, setScopes] = useState<Scope[]>([{ scope_type: "all", scope_value: null }]);

  function reset() {
    setFirebaseUid("");
    setEmail("");
    setDisplayName("");
    setRoles([]);
    setScopes([{ scope_type: "all", scope_value: null }]);
  }

  function submit() {
    if (!firebaseUid.trim() || !email.trim()) return;
    create.mutate(
      {
        firebase_uid: firebaseUid.trim(),
        email: email.trim(),
        display_name: displayName.trim() || null,
        roles,
        scopes,
      },
      {
        onSuccess: () => {
          reset();
          setOpen(false);
        },
      },
    );
  }

  if (!open) {
    return (
      <Button onClick={() => setOpen(true)}>New user</Button>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New user</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1">
            <Label htmlFor="nu-uid">Firebase UID</Label>
            <Input id="nu-uid" value={firebaseUid} onChange={(e) => setFirebaseUid(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="nu-email">Email</Label>
            <Input id="nu-email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="nu-name">Display name</Label>
            <Input id="nu-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </div>
        </div>
        <div className="space-y-1">
          <Label>Roles</Label>
          <RolePicker
            available={roleNames}
            selected={roles}
            onToggle={(role) =>
              setRoles((c) => (c.includes(role) ? c.filter((r) => r !== role) : [...c, role]))
            }
          />
        </div>
        <div className="space-y-1">
          <Label>Row scopes</Label>
          <ScopeEditor scopes={scopes} onChange={setScopes} />
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={submit} disabled={!firebaseUid.trim() || !email.trim() || create.isPending}>
            {create.isPending ? "Creating…" : "Create user"}
          </Button>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          {create.isError && (
            <span className="text-xs text-destructive">
              {create.error instanceof Error ? create.error.message : "Create failed."}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function scopeLabel(scope: Scope): string {
  return scope.scope_type === "all" ? "all" : `${scope.scope_type}:${scope.scope_value}`;
}

export function UsersPanel() {
  const { data: users } = useAdminUsers();
  const { data: roles } = useAdminRoles();
  const roleNames = (roles ?? []).map((r) => r.name);
  const [editing, setEditing] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <CreateUserForm roleNames={roleNames} />
      <div className="space-y-2">
        {(users ?? []).map((user) => (
          <Card key={user.id}>
            <CardContent className="space-y-2 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">
                      {user.display_name ?? user.email}
                    </span>
                    {!user.is_active && <Badge variant="destructive">inactive</Badge>}
                  </div>
                  <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {user.roles.map((role) => (
                      <Badge key={role} variant="secondary">
                        {role}
                      </Badge>
                    ))}
                    {user.scopes.map((scope, i) => (
                      <Badge key={i} variant="outline">
                        {scopeLabel(scope)}
                      </Badge>
                    ))}
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setEditing(editing === user.id ? null : user.id)}
                >
                  {editing === user.id ? "Close" : "Edit"}
                </Button>
              </div>
              {editing === user.id && <UserEditor user={user} roleNames={roleNames} />}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
