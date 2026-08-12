"use client";

import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, GripVertical } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { useMe } from "@/lib/api-hooks";
import { BackgroundFx } from "@/components/effects/background-fx";
import { ClickSpark } from "@/components/effects/click-spark";
import { CursorFx } from "@/components/effects/custom-cursor";
import { PrivacyShield } from "@/components/effects/privacy-shield";
import { AnnouncementBar } from "@/components/layout/announcement-bar";
import { useConversations } from "@/lib/chat-hooks";
import { NAV_ITEMS, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

const ORDER_KEY = "nav-order";
const COLLAPSE_KEY = "sidebar-collapsed";

/** Section headings, keyed by href rather than stored on NAV_ITEMS: the nav list grows over
 *  time, and an item this map does not know lands in the fallback group instead of
 *  disappearing. Order here is the render order; the user's saved reorder applies WITHIN
 *  each group, so grouping and per-user ordering coexist. */
const GROUPS: { title: string; hrefs: string[] }[] = [
  { title: "Overview", hrefs: ["/overview", "/compare"] },
  { title: "Performance", hrefs: ["/revenue", "/ua", "/store"] },
  { title: "Apps", hrefs: ["/apps", "/explore", "/app-master", "/spotlight"] },
  { title: "Reporting", hrefs: ["/reports", "/glossary"] },
  { title: "People", hrefs: ["/chat", "/profile"] },
];
const ADMIN_GROUP: { title: string; hrefs: string[] } = {
  title: "Administration",
  hrefs: ["/admin", "/security", "/data-health"],
};
const FALLBACK_TITLE = "More";

/** Apply a saved href order to the items; unknown/new items keep their default position. */
function applyOrder<T extends { href: string }>(items: T[], order: string[]): T[] {
  if (order.length === 0) return items;
  const rank = new Map(order.map((href, i) => [href, i]));
  return [...items].sort(
    (a, b) => (rank.get(a.href) ?? Infinity) - (rank.get(b.href) ?? Infinity),
  );
}

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

  // Anything neither map knows keeps its order in a visible fallback section - a new page
  // must never silently drop out of the sidebar because this map is stale.
  const leftovers = items.filter((item) => !used.has(item.href));
  if (leftovers.length > 0) sections.push({ title: FALLBACK_TITLE, items: leftovers });
  if (adminMembers.length > 0) sections.push({ title: ADMIN_GROUP.title, items: adminMembers });

  return sections;
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

  // Chat unread state powers three things wherever the user is in the app: the badge on
  // the Chat entry, the "(N)" tab-title prefix, and a browser popup when a NEW message
  // arrives while this tab is unfocused. Permission is only requested after the user has
  // engaged with chat once (clicked the entry), never on first page load.
  const { data: chatState } = useConversations();
  // Pending chat requests you RECEIVED count toward the badge: a request carries no
  // messages yet, so without this it would be invisible until you stumbled onto /chat.
  const pendingRequests = (chatState?.conversations ?? []).filter(
    (conversation) => conversation.status === "pending" && !conversation.requested_by_me,
  ).length;
  const unreadTotal = (chatState?.unread_total ?? 0) + pendingRequests;
  // null until the FIRST real payload arrives: pre-existing unread found on page load is
  // a baseline, not a new arrival, so it must never fire the popup.
  const previousUnread = useRef<number | null>(null);
  useEffect(() => {
    const base = document.title.replace(/^\(\d+\+?\)\s/, "");
    document.title = unreadTotal > 0 ? `(${unreadTotal > 99 ? "99+" : unreadTotal}) ${base}` : base;
  }, [unreadTotal]);
  useEffect(() => {
    if (!chatState) return; // nothing fetched yet - don't seed from the placeholder zero
    const prior = previousUnread.current;
    previousUnread.current = unreadTotal;
    if (prior === null) return; // first data arrival seeds the baseline only
    if (unreadTotal <= prior || document.hasFocus()) return;
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    const notification = new Notification("New message", {
      body: "A new chat message or request is waiting in Prometheus.",
      tag: "prometheus-chat", // replaces rather than stacks
    });
    notification.onclick = () => {
      window.focus();
      window.location.assign("/chat");
    };
  }, [chatState, unreadTotal]);

  // Collapsed starts false on BOTH server and first client render, then reads the saved
  // preference in an effect - localStorage is touched post-hydration only, so SSR can
  // never crash on it and hydration never mismatches.
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
  }, []);

  // Persist the nav order PER USER (keyed by Firebase UID) so it never leaks across
  // account switches on a shared workstation. Null until the profile resolves.
  const orderKey = me ? `${ORDER_KEY}:${me.user_id}` : null;

  useEffect(() => {
    if (!orderKey) return;
    try {
      const raw = localStorage.getItem(orderKey);
      setOrder(raw ? (JSON.parse(raw) as string[]) : []);
    } catch {
      setOrder([]); // corrupt/absent - fall back to default order
    }
  }, [orderKey]);

  const items = useMemo(() => applyOrder(visible, order), [visible, order]);
  // The saved reorder is applied BEFORE grouping, so it decides order within each group.
  const sections = useMemo(() => groupItems(items), [items]);

  function toggleCollapsed(): void {
    // The next value is computed OUTSIDE the updater. A state updater must be pure - React
    // may call it twice (StrictMode does) and writing to localStorage inside it made the
    // toggle do synchronous storage I/O during the render phase, which is what made the
    // collapse feel like it stuttered.
    const next = !collapsed;
    setCollapsed(next);
    try {
      window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
    } catch {
      /* storage blocked - the sidebar still collapses for this session */
    }
  }

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
      /* storage full/blocked - order still applies for this session */
    }
  }

  function navLink({ href, label, icon: Icon }: NavItem) {
    const active = pathname === href || pathname.startsWith(`${href}/`);
    return (
      <Link
        key={href}
        href={href}
        title={collapsed ? label : undefined}
        aria-label={label}
        onClick={() => {
          // First engagement with chat is the moment to ask for popup permission - asking
          // on page load is the pattern browsers (rightly) punish.
          if (
            href === "/chat" &&
            typeof Notification !== "undefined" &&
            Notification.permission === "default"
          ) {
            void Notification.requestPermission();
          }
        }}
        className={cn(
          "relative flex items-center gap-3 text-sm",
          "transition-all duration-[var(--dur)] ease-[var(--ease)]",
          collapsed
            ? cn(
                // Bubble mode: each item is a floating circular button (the reference
                // medical-sidebar look) - active fills solid, others sit on a soft disc
                // that lifts and scales on hover.
                "mx-auto h-10 w-10 justify-center rounded-full",
                active
                  ? "scale-105 bg-[color:var(--color-accent)] text-[color:var(--color-accent-foreground)] shadow-md"
                  : "bg-[color:var(--color-bg-elevated)] text-muted-foreground hover:scale-110 hover:text-foreground hover:shadow-md",
              )
            : cn(
                "rounded-md px-3 py-2 hover:translate-x-0.5",
                active
                  ? "bg-accent font-medium text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              ),
        )}
      >
        <Icon className="h-4 w-4 shrink-0" />
        {href === "/chat" && unreadTotal > 0 && (
          <span
            className={cn(
              "absolute flex h-4 min-w-4 items-center justify-center rounded-full bg-[color:var(--color-accent)] px-1 text-[9px] font-semibold text-[color:var(--color-accent-foreground)]",
              collapsed ? "right-0.5 top-0.5" : "right-2 top-1/2 -translate-y-1/2",
            )}
          >
            {unreadTotal > 99 ? "99+" : unreadTotal}
          </span>
        )}
        {/* The label stays mounted and fades, rather than unmounting on collapse: removing
            it mid-animation forces a reflow of every row at once. */}
        <span
          className={cn(
            "truncate transition-opacity duration-[var(--dur-fast)]",
            collapsed && "pointer-events-none w-0 opacity-0",
          )}
          aria-hidden={collapsed}
        >
          {label}
        </span>
      </Link>
    );
  }

  return (
    <>
    <AnnouncementBar />
    <ClickSpark />
    <BackgroundFx />
    <PrivacyShield />
    <CursorFx />
    <aside
      className={cn(
        // Only width animates; the easing and duration come from the theme tokens, so the
        // sidebar moves like everything else in the app. Overflow stays VISIBLE here - the
        // edge chevron rides outside the border - and the nav blocks clip horizontally
        // instead, so labels cannot wrap mid-transition (a reflowing label reads as "lag").
        "relative hidden shrink-0 border-r bg-card md:block",
        "transition-[width] duration-[var(--dur)] ease-[var(--ease)] will-change-[width]",
        collapsed ? "w-14" : "w-60",
      )}
    >
      <div className="flex h-14 items-center justify-between border-b px-4">
        <span className="text-lg font-semibold">{collapsed ? "P" : "Prometheus"}</span>
        {!collapsed && (
          <button
            type="button"
            onClick={() => setReordering((v) => !v)}
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            title={reordering ? "Done reordering" : "Reorder pages"}
            aria-label="Reorder pages"
          >
            <GripVertical className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Edge toggle - the small round chevron riding the sidebar border. Reordering needs
          labels, so entering reorder mode while collapsed expands first. */}
      <button
        type="button"
        onClick={toggleCollapsed}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className="absolute -right-3 top-16 z-20 flex h-6 w-6 items-center justify-center rounded-full border bg-card text-muted-foreground shadow-sm hover:text-foreground"
      >
        {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
      </button>

      {reordering && !collapsed ? (
        /* Reorder mode keeps the original flat list + arrows: moving across group
           boundaries changes order within the destination group. */
        <nav className="space-y-1 overflow-x-hidden p-2" data-tour="nav">
          {items.map(({ href, label, icon: Icon }, index) => (
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
          ))}
        </nav>
      ) : (
        <nav className={cn("space-y-4 overflow-y-auto overflow-x-hidden p-2", collapsed && "space-y-3 py-3")} data-tour="nav">
          {sections.map((section) => (
            <div key={section.title}>
              {collapsed ? (
                <div className="mx-2 mb-1 border-t" aria-hidden />
              ) : (
                <p className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  {section.title}
                </p>
              )}
              <div className="space-y-1">{section.items.map(navLink)}</div>
            </div>
          ))}
        </nav>
      )}
    </aside>
    </>
  );
}
