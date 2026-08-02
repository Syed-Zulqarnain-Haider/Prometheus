"use client";

import { ChevronDown, ChevronUp, GripVertical } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useMe } from "@/lib/api-hooks";
import { NAV_ITEMS } from "@/lib/nav";
import { cn } from "@/lib/utils";

const ORDER_KEY = "nav-order";

/** Apply a saved href order to the items; unknown/new items keep their default position. */
function applyOrder<T extends { href: string }>(items: T[], order: string[]): T[] {
  if (order.length === 0) return items;
  const rank = new Map(order.map((href, i) => [href, i]));
  return [...items].sort(
    (a, b) => (rank.get(a.href) ?? Infinity) - (rank.get(b.href) ?? Infinity),
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { data: me } = useMe();
  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;

  const visible = useMemo(
    () => NAV_ITEMS.filter((item) => !item.requiresAdmin || isAdmin),
    [isAdmin],
  );

  const [order, setOrder] = useState<string[]>([]);
  const [reordering, setReordering] = useState(false);

  // Persist PER USER (keyed by Firebase UID) so the nav order never leaks across account
  // switches on a shared workstation. Null until the profile resolves.
  const orderKey = me ? `${ORDER_KEY}:${me.user_id}` : null;

  // Read this user's saved order after mount / when the user changes (SSR-safe — never touch
  // localStorage during render).
  useEffect(() => {
    if (!orderKey) return;
    try {
      const raw = localStorage.getItem(orderKey);
      setOrder(raw ? (JSON.parse(raw) as string[]) : []);
    } catch {
      setOrder([]); // corrupt/absent — fall back to default order
    }
  }, [orderKey]);

  const items = useMemo(() => applyOrder(visible, order), [visible, order]);

  function move(index: number, dir: -1 | 1) {
    const next = [...items];
    const target = index + dir;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    const hrefs = next.map((i) => i.href);
    setOrder(hrefs);
    if (!orderKey) return;
    try {
      localStorage.setItem(orderKey, JSON.stringify(hrefs));
    } catch {
      /* storage full/blocked — order still applies for this session */
    }
  }

  return (
    <aside className="hidden w-60 shrink-0 border-r bg-card md:block">
      <div className="flex h-14 items-center justify-between border-b px-4">
        <span className="text-lg font-semibold">Prometheus</span>
        <button
          type="button"
          onClick={() => setReordering((v) => !v)}
          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          title={reordering ? "Done reordering" : "Reorder pages"}
          aria-label="Reorder pages"
        >
          <GripVertical className="h-4 w-4" />
        </button>
      </div>
      <nav className="space-y-1 p-2" data-tour="nav">
        {items.map(({ href, label, icon: Icon }, index) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          if (reordering) {
            return (
              <div
                key={href}
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground"
              >
                <Icon className="h-4 w-4" />
                <span className="flex-1 truncate">{label}</span>
                <button
                  type="button"
                  onClick={() => move(index, -1)}
                  disabled={index === 0}
                  className="rounded p-0.5 hover:bg-accent disabled:opacity-30"
                  aria-label={`Move ${label} up`}
                >
                  <ChevronUp className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => move(index, 1)}
                  disabled={index === items.length - 1}
                  className="rounded p-0.5 hover:bg-accent disabled:opacity-30"
                  aria-label={`Move ${label} down`}
                >
                  <ChevronDown className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          }
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-accent font-medium text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
