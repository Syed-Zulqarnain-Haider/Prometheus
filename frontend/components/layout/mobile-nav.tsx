"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { useConversations } from "@/lib/chat-hooks";
import { useMe } from "@/lib/api-hooks";
import { NAV_ITEMS } from "@/lib/nav";
import { cn } from "@/lib/utils";

/* Navigation for phones and narrow windows: a hamburger that opens a slide-in drawer.
 *
 * The button renders IN FLOW - the header mounts it first in its flex row, so it takes
 * real space beside the brand instead of floating over it, and it rides down with an
 * announcement banner for free (body padding moves the whole header). Only the drawer
 * overlay is fixed.
 *
 * Items come from NAV_ITEMS filtered by the same admin_panel capability the desktop
 * sidebar uses, so a page added or restricted there appears or disappears here with no
 * second edit. Filtering is cosmetic either way - the API enforces access server-side. */

export function MobileNav() {
  const pathname = usePathname();
  const { data: me } = useMe();
  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

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
    const panel = panelRef.current;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
      // Minimal focus trap: an aria-modal dialog must not let Tab walk the page
      // behind the overlay. Cycle within the panel's focusable elements.
      if (event.key === "Tab" && panel) {
        const focusable = panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement;
        if (event.shiftKey && (active === first || !panel.contains(active))) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && active === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    // Freeze the page behind the drawer - on iOS a scrollable body under a fixed overlay
    // scrolls instead of the overlay, which feels broken.
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    // Move focus into the dialog so keyboard and screen-reader users land inside it.
    panel?.querySelector<HTMLElement>("button")?.focus();
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
        className="relative flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <Menu className="h-5 w-5" />
        {unread > 0 && (
          <span
            aria-hidden
            className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[color:var(--color-accent)]"
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
            ref={panelRef}
            className="relative flex h-full w-72 max-w-[85vw] flex-col border-r bg-card shadow-xl"
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
