"use client";

import { Bell, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  type NotificationItem,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/lib/api-hooks";
import { cn } from "@/lib/utils";

type SortMode = "date" | "type";

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

/** Severity accent colour (theme tokens, matching the previous bell). */
function severityColor(severity: NotificationItem["severity"]): string {
  if (severity === "critical") return "var(--color-negative)";
  if (severity === "warning") return "var(--color-warning, #d97706)";
  return "var(--color-accent)";
}

const SEVERITY_TITLE: Record<NotificationItem["severity"], string> = {
  critical: "Alerts",
  warning: "Warnings",
  info: "Updates",
};

/** AdMob-style notification card: severity-tinted background + left accent bar, a "New"
 *  badge while unread, and a dismiss X. There is no delete endpoint - dismiss marks the
 *  notification read (it stays in the list, dimmed), which matches the server model. */
function NotificationCard({
  item,
  onActivate,
  onDismiss,
}: {
  item: NotificationItem;
  onActivate: (n: NotificationItem) => void;
  onDismiss: (n: NotificationItem) => void;
}) {
  const accent = severityColor(item.severity);
  return (
    <div
      className={cn(
        "relative rounded-lg border border-border-faint",
        item.read && "opacity-60",
      )}
      style={{
        borderLeft: `4px solid ${accent}`,
        // Pale severity wash like AdMob's alert cards; falls back to the card bg where
        // color-mix is unavailable.
        background: item.read
          ? undefined
          : `color-mix(in srgb, ${accent} 8%, transparent)`,
      }}
    >
      <button
        type="button"
        className={cn("block w-full px-3 py-2.5 pr-8 text-left", item.link && "cursor-pointer")}
        onClick={() => onActivate(item)}
        title={item.link ? "Open" : undefined}
      >
        <div className="flex items-center gap-2">
          <p className="min-w-0 flex-1 truncate text-sm font-medium">{item.title}</p>
          {!item.read && (
            <span
              className="shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white"
              style={{ background: accent }}
            >
              New
            </span>
          )}
        </div>
        {item.body && <p className="mt-0.5 text-xs text-muted-foreground">{item.body}</p>}
        <p className="mt-1 text-[10px] uppercase tracking-wider text-muted-foreground">
          {relativeTime(item.created_at)}
          {item.link && " · click to open"}
        </p>
      </button>
      {!item.read && (
        <button
          type="button"
          aria-label="Dismiss notification"
          title="Dismiss"
          className="absolute right-1.5 top-1.5 rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          onClick={(e) => {
            e.stopPropagation();
            onDismiss(item);
          }}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [sort, setSort] = useState<SortMode>("date");
  const router = useRouter();
  const { data } = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();

  const unread = data?.unread ?? 0;
  const isEmpty = (data?.items.length ?? 0) === 0;

  // "Sort by date": newest first, flat. "Sort by type": severity sections (Alerts /
  // Warnings / Updates), newest first within each - grouping is what makes the type
  // sort scannable, a flat severity-ordered list reads as noise.
  const sorted = useMemo(() => {
    const byDate = [...(data?.items ?? [])].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
    if (sort === "date") return [{ title: null as string | null, items: byDate }];
    const groups: { title: string | null; items: NotificationItem[] }[] = [];
    for (const severity of ["critical", "warning", "info"] as const) {
      const members = byDate.filter((n) => n.severity === severity);
      if (members.length > 0) groups.push({ title: SEVERITY_TITLE[severity], items: members });
    }
    return groups;
  }, [data, sort]);

  function activate(n: NotificationItem) {
    if (!n.read) markRead.mutate(n.id);
    // Only an in-app path is ever navigated to. router.push() hands anything with a
    // foreign origin to location.assign(), and a "javascript:" URL has an opaque origin -
    // so an unchecked link would execute script in this authenticated session. The
    // leading-slash test (rejecting "//host", which is protocol-relative) closes both
    // that and the silent off-site redirect.
    if (n.link && n.link.startsWith("/") && !n.link.startsWith("//")) {
      setOpen(false);
      router.push(n.link); // deep-link straight to where the change happened
    }
  }

  // Dismiss marks read WITHOUT following the link - the X must never navigate.
  function dismiss(n: NotificationItem) {
    if (!n.read) markRead.mutate(n.id);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Notifications" className="relative">
          <Bell className="h-4 w-4" />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[color:var(--color-accent)] px-1 text-[10px] font-semibold text-[color:var(--color-accent-foreground)]">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0">
        <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
          <span className="text-sm font-semibold">Notifications</span>
          <div className="flex items-center gap-2">
            <Select value={sort} onValueChange={(v) => setSort(v as SortMode)}>
              <SelectTrigger className="h-7 w-32 text-xs" aria-label="Sort notifications">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="date">Sort by date</SelectItem>
                <SelectItem value="type">Sort by type</SelectItem>
              </SelectContent>
            </Select>
            {unread > 0 && (
              <button
                type="button"
                className="whitespace-nowrap text-xs text-muted-foreground hover:underline"
                onClick={() => markAll.mutate()}
              >
                Mark all read
              </button>
            )}
          </div>
        </div>
        <div className="max-h-96 space-y-2 overflow-y-auto p-2">
          {isEmpty && (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">
              You&apos;re all caught up.
            </p>
          )}
          {sorted.map((group) => (
            <div key={group.title ?? "all"} className="space-y-2">
              {group.title && (
                <p className="px-1 pt-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  {group.title}
                </p>
              )}
              {group.items.map((n) => (
                <NotificationCard key={n.id} item={n} onActivate={activate} onDismiss={dismiss} />
              ))}
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
