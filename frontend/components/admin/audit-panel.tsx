"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAudit, useAuditActions } from "@/lib/api-hooks";
import { formatDateTime } from "@/lib/format";

const ALL_ACTIONS = "__all__";
const PAGE_SIZE = 50;

export function AuditPanel() {
  const { data: actions } = useAuditActions();
  const [action, setAction] = useState<string>(ALL_ACTIONS);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, isLoading } = useAudit({
    action: action === ALL_ACTIONS ? undefined : action,
    date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
    date_to: dateTo ? new Date(`${dateTo}T23:59:59`).toISOString() : undefined,
    limit: PAGE_SIZE,
    offset,
  });

  function resetAndSet(setter: (value: string) => void, value: string) {
    setter(value);
    setOffset(0);
  }

  const entries = data?.entries ?? [];

  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 py-3">
          <div className="space-y-1">
            <Label>Action</Label>
            <Select value={action} onValueChange={(value) => resetAndSet(setAction, value)}>
              <SelectTrigger className="h-8 w-52">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_ACTIONS}>All actions</SelectItem>
                {(actions ?? []).map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="audit-from">From</Label>
            <Input
              id="audit-from"
              type="date"
              className="h-8 w-40"
              value={dateFrom}
              onChange={(event) => resetAndSet(setDateFrom, event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="audit-to">To</Label>
            <Input
              id="audit-to"
              type="date"
              className="h-8 w-40"
              value={dateTo}
              onChange={(event) => resetAndSet(setDateTo, event.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      <div className="overflow-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">User</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Resource</th>
              <th className="px-3 py-2">IP</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            ) : entries.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-center text-muted-foreground">
                  No audit entries match.
                </td>
              </tr>
            ) : (
              entries.map((entry) => (
                <tr key={entry.id} className="border-t align-top">
                  <td className="whitespace-nowrap px-3 py-1.5">
                    {formatDateTime(entry.created_at)}
                  </td>
                  <td className="px-3 py-1.5">{entry.user_email ?? "—"}</td>
                  <td className="px-3 py-1.5 font-medium">{entry.action}</td>
                  <td className="max-w-xs truncate px-3 py-1.5">{entry.resource ?? "—"}</td>
                  <td className="px-3 py-1.5">{entry.ip_address ?? "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          size="sm"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={data?.next_offset == null}
          onClick={() => data?.next_offset != null && setOffset(data.next_offset)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
