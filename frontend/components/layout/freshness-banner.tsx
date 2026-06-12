"use client";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useFreshness } from "@/lib/api-hooks";

export function FreshnessBanner() {
  const { data, isLoading, isError } = useFreshness();

  if (isLoading) {
    return (
      <div className="border-b bg-muted px-4 py-2">
        <Skeleton className="h-4 w-64" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="border-b bg-muted px-4 py-2 text-xs text-muted-foreground">
        Data freshness unavailable
      </div>
    );
  }

  const builtAt = data.bq_built_at
    ? new Date(data.bq_built_at).toLocaleString()
    : "unknown";
  const ok = data.last_status === "success";

  return (
    <div className="flex items-center gap-2 border-b bg-muted px-4 py-2 text-xs text-muted-foreground">
      <span>
        Data as of{" "}
        <span className="font-medium text-foreground">{builtAt}</span>
      </span>
      <Badge variant={ok ? "secondary" : "destructive"}>
        {data.last_status ?? "unknown"}
      </Badge>
    </div>
  );
}
