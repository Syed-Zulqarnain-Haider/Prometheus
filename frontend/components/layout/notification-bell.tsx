"use client";

import { Bell } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  type NotificationItem,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/lib/api-hooks";

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

/** Left-border accent colour by severity (theme tokens). */
function severityColor(severity: NotificationItem["severity"]): string {
  if (severity === "critical") return "var(--color-negative)";
  if (severity === "warning") return "var(--color-warning, #d97706)";
  return "var(--color-accent)";
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const { data } = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();

  const items = data?.items ?? [];
  const unread = data?.unread ?? 0;

  function activate(n: NotificationItem) {
    if (!n.read) markRead.mutate(n.id);
    if (n.link) {
      setOpen(false);
      router.push(n.link); // deep-link straight to where the change happened
    }
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
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="text-sm font-semibold">Notifications</span>
          {unread > 0 && (
            <button
              type="button"
              className="text-xs text-muted-foreground hover:underline"
              onClick={() => markAll.mutate()}
            >
              Mark all read
            </button>
          )}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {items.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">You&apos;re all caught up.</p>
          )}
          {items.map((n: NotificationItem) => (
            <button
              key={n.id}
              type="button"
              className={`block w-full border-b border-l-2 border-border-faint px-3 py-2 text-left hover:bg-accent ${
                n.read ? "opacity-60" : ""
              } ${n.link ? "cursor-pointer" : ""}`}
              style={{ borderLeftColor: severityColor(n.severity) }}
              onClick={() => activate(n)}
              title={n.link ? "Open" : undefined}
            >
              <div className="flex items-start gap-2">
                {!n.read && (
                  <span
                    className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
                    style={{ background: severityColor(n.severity) }}
                  />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {n.severity === "critical" && "🔴 "}
                    {n.title}
                  </p>
                  {n.body && <p className="text-xs text-muted-foreground">{n.body}</p>}
                  <p className="mt-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                    {relativeTime(n.created_at)}
                    {n.link && " · click to open"}
                  </p>
                </div>
              </div>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
