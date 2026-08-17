"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useConversations } from "@/lib/chat-hooks";
import { useMe } from "@/lib/api-hooks";
import { NAV_ITEMS } from "@/lib/nav";
import { cn } from "@/lib/utils";

/* Navigation for phones and narrow windows.
 *
 * The sidebar is `hidden md:block`, which below 768px left the app with no navigation at
 * all - every page was reachable only by typing its URL. This is that missing half: a
 * button in the header row and a slide-in drawer, shown ONLY where the sidebar is not.
 *
 * The item list is read from NAV_ITEMS and filtered by the same admin_panel capability
 * the sidebar uses, so a page added or restricted there appears or disappears here with
 * no second edit. Filtering is cosmetic either way - the API enforces access server-side. */

const PANEL_WIDTH = "w-72 max-w-[85vw]";

export function MobileNav() {
  const pathname = usePathname();
  const { data: me } = useMe();
  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;
  const [open, setOpen] = useState(false);

  const items = useMemo(
    () => NAV_ITEMS.filter((item) => !item.requiresAdmin || isAdmin),
    [isAdmin],
  );

  // Same unread maths as the sidebar badge: a pending request carries no messages yet,
  // so without counting it a contact request is invisible until you open /chat.
  const { data: chatState } = useConversations();
  const pendingRequests = (chatState?.conversations ?? []).filter(
    (conversation) => conversation.status === "pending" && !conversation.requested_by_me,
  ).length;
  const unread = (chatState?.unread_total ?? 0) + pendingRequests;

  // A tap that navigates must also dismiss: the drawer covers the page it just opened.
  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    // Freeze the page behind the drawer - on iOS a scrollable body under a fixed overlay
    // scrolls instead of the overlay, which feels broken.
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="md:hidden">
      <button
        type="button"
        aria-label="Open navigation"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        // Pinned to the header row rather than placed inside <header>: the header is
        // shared with the desktop layout, and this keeps the two from having to know
        // about each other.
        //
        // The offset is not just the notch inset. An announcement banner shifts the app
        // down by padding <body>, which moves everything in normal flow but NOT a fixed
        // element like this one - so it publishes its height as --announce-height and
        // this rides down with it instead of hiding underneath.
        className="fixed left-0 z-40 flex h-14 w-14 items-center justify-center text-muted-foreground transition-colors hover:text-foreground"
        style={{
          top: "calc(env(safe-area-inset-top, 0px) + var(--announce-height, 0px))",
          paddingLeft: "env(safe-area-inset-left, 0px)",
        }}
      >
        <Menu className="h-5 w-5" />
        {unread > 0 && (
          <span
            aria-hidden
            className="absolute right-3 top-3 h-2 w-2 rounded-full bg-[color:var(--color-accent)]"
          />
        )}
      </button>

      {open && (
        <div className="fixed inset-0 z-[70]" role="dialog" aria-modal aria-label="Navigation">
          <button
            type="button"
            aria-label="Close navigation"
            tabIndex={-1}
            onClick={() => setOpen(false)}
            className="absolute inset-0 h-full w-full cursor-default bg-black/50"
          />
          <div
            className={cn(
              "relative flex h-full flex-col border-r bg-card shadow-xl",
              PANEL_WIDTH,
            )}
            style={{
              paddingTop: "env(safe-area-inset-top, 0px)",
              paddingBottom: "env(safe-area-inset-bottom, 0px)",
              paddingLeft: "env(safe-area-inset-left, 0px)",
            }}
          >
            <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
              <span className="text-lg font-semibold">Prometheus</span>
              <button
                type="button"
                aria-label="Close navigation"
                onClick={() => setOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <nav className="flex-1 space-y-1 overflow-y-auto p-2">
              {items.map(({ href, label, icon: Icon }) => {
                const active = pathname === href || pathname.startsWith(`${href}/`);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      // min-h-11: a 44px target is the smallest a finger reliably hits.
                      "flex min-h-11 items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                      active
                        ? "bg-[color:var(--color-accent)] text-[color:var(--color-accent-foreground)]"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground",
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="flex-1 truncate">{label}</span>
                    {href === "/chat" && unread > 0 && (
                      <span className="rounded-full bg-[color:var(--color-accent)] px-1.5 py-0.5 text-[10px] font-semibold text-[color:var(--color-accent-foreground)]">
                        {unread > 99 ? "99+" : unread}
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>

            {me?.email && (
              <p className="shrink-0 truncate border-t px-4 py-3 text-xs text-muted-foreground">
                {me.email}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
