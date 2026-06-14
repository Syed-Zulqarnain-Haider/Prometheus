"use client";

import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Scope, ScopeType } from "@/lib/types";

const SCOPE_TYPES: ScopeType[] = ["all", "hou", "pod", "publisher", "app"];

/** Edit a user's row-scope grants. Effective access is the UNION of these rows;
 *  an "all" grant needs no value, every other type requires one. */
export function ScopeEditor({
  scopes,
  onChange,
}: {
  scopes: Scope[];
  onChange: (next: Scope[]) => void;
}) {
  function update(index: number, patch: Partial<Scope>) {
    onChange(scopes.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  return (
    <div className="space-y-2">
      {scopes.length === 0 && (
        <p className="text-xs text-muted-foreground">
          No scopes — this user sees nothing until a scope is added.
        </p>
      )}
      {scopes.map((scope, index) => (
        <div key={index} className="flex items-center gap-2">
          <Select
            value={scope.scope_type}
            onValueChange={(value) =>
              update(index, {
                scope_type: value as ScopeType,
                scope_value: value === "all" ? null : (scope.scope_value ?? ""),
              })
            }
          >
            <SelectTrigger className="h-8 w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SCOPE_TYPES.map((type) => (
                <SelectItem key={type} value={type}>
                  {type}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            className="h-8 flex-1"
            placeholder={scope.scope_type === "all" ? "— (whole org)" : "value"}
            value={scope.scope_value ?? ""}
            disabled={scope.scope_type === "all"}
            onChange={(event) => update(index, { scope_value: event.target.value })}
          />
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={() => onChange(scopes.filter((_, i) => i !== index))}
            aria-label="Remove scope"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        className="gap-1"
        onClick={() => onChange([...scopes, { scope_type: "all", scope_value: null }])}
      >
        <Plus className="h-4 w-4" />
        Add scope
      </Button>
    </div>
  );
}
