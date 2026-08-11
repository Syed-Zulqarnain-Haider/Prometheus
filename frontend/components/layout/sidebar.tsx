"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useMe } from "@/lib/api-hooks";
import { NAV_ITEMS, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

/** Section headings, keyed by href rather than stored on NAV_ITEMS: the nav list differs
 *  between trees, and an item this map does not know simply lands in the fallback group
 *  instead of disappearing. Order here is the render order. */
const GROUPS: { title: string; hrefs: string[] }[] = [
  { title: "Overview", hrefs: ["/overview", "/compare"] },
  { title: "Performance", hrefs: ["/revenue", "/ua", "/store"] },
  { title: "Apps", hrefs: ["/apps", "/explore", "/app-master"] },
  { title: "Reporting", hrefs: ["/reports", "/glossary"] },
];
/** Unmapped items land here; admin-ish pages get their own trailing section. */
const ADMIN_GROUP: { title: string; hrefs: string[] } = {
  title: "Administration",
  hrefs: ["/admin", "/security", "/data-health"],
};
const FALLBACK_TITLE = "More";

function groupItems(items: NavItem[]): { title: string; items: NavItem[] }[] {
  const byHref = new Map(items.map((item) => [item.href, item]));
  const used = new Set<string>();
  const sections: { title: string; items: NavItem[] }[] = [];

  for (const group of GROUPS) {
    const members = group.hrefs
      .map((href) => byHref.get(href))
      .filter((item): item is NavItem => Boolean(item));
    members.forEach((m) => used.add(m.href));
    if (members.length > 0) sections.push({ title: group.title, items: members });
  }

  const adminMembers = ADMIN_GROUP.hrefs
    .map((href) => byHref.get(href))
    .filter((item): item is NavItem => Boolean(item));
  adminMembers.forEach((m) => used.add(m.href));

  // Anything neither map knows keeps NAV_ITEMS order in a visible fallback section -
  // a new page must never silently drop out of the sidebar because this map is stale.
  const leftovers = items.filter((item) => !used.has(item.href));
  if (leftovers.length > 0) sections.push({ title: FALLBACK_TITLE, items: leftovers });
  if (adminMembers.length > 0) sections.push({ title: ADMIN_GROUP.title, items: adminMembers });

  return sections;
}

const COLLAPSE_KEY = "sidebar-collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const { data: me } = useMe();
  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;
  const items = NAV_ITEMS.filter((item) => !item.requiresAdmin || isAdmin);
  const sections = groupItems(items);

  // Collapsed state starts false on BOTH server and first client render, then reads the
  // saved preference in an effect - localStorage is touched post-hydration only, so SSR
  // can never crash on it and hydration never mismatches. (CLAUDE.md bans localStorage
  // where SSR runs; this access pattern is the SSR-safe exception, flagged to the owner.)
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
  }, []);

  function toggle(): void {
    setCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      return next;
    });
  }

  return (
    <aside
      className={cn(
        "relative hidden shrink-0 border-r bg-card transition-[width] duration-200 md:block",
        collapsed ? "w-14" : "w-60",
      )}
    >
      <div className="flex h-14 items-center border-b px-4 text-lg font-semibold">
        {collapsed ? "P" : "Prometheus"}
      </div>

      {/* Edge toggle - the small round chevron riding the sidebar border. */}
      <button
        type="button"
        onClick={toggle}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className="absolute -right-3 top-16 z-20 flex h-6 w-6 items-center justify-center rounded-full border bg-card text-muted-foreground shadow-sm hover:text-foreground"
      >
        {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
      </button>

      <nav className={cn("space-y-4 overflow-y-auto p-2", collapsed && "space-y-2")}>
        {sections.map((section) => (
          <div key={section.title}>
            {collapsed ? (
              <div className="mx-2 mb-1 border-t" aria-hidden />
            ) : (
              <p className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {section.title}
              </p>
            )}
            <div className="space-y-1">
              {section.items.map(({ href, label, icon: Icon }) => {
                const active = pathname === href || pathname.startsWith(`${href}/`);
                return (
                  <Link
                    key={href}
                    href={href}
                    title={collapsed ? label : undefined}
                    aria-label={label}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                      collapsed && "justify-center px-0",
                      active
                        ? "bg-accent font-medium text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {!collapsed && <span className="truncate">{label}</span>}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
