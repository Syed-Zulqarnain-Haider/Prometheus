"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useMe } from "@/lib/api-hooks";
import { NAV_ITEMS } from "@/lib/nav";
import { cn } from "@/lib/utils";

/** Mobile navigation: a hamburger button (shown < md) that opens a slide-in drawer with the
 *  SAME nav items + admin gating as the desktop Sidebar. Closes on navigation, backdrop tap,
 *  or Escape; locks body scroll while open. The desktop Sidebar stays untouched at md+. */
export function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const { data: me } = useMe();
  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;
  const items = NAV_ITEMS.filter((item) => !item.requiresAdmin || isAdmin);

  // Close whenever the route changes (e.g. after tapping a link).
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Escape to close + lock background scroll while the drawer is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        aria-label="Open menu"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true">
          <button
            aria-label="Close menu"
            tabIndex={-1}
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-black/50 duration-200 animate-in fade-in"
          />
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[82%] flex-col border-r bg-card shadow-xl duration-200 animate-in slide-in-from-left">
            <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
              <span className="text-lg font-semibold">Prometheus</span>
              <button
                type="button"
                aria-label="Close menu"
                onClick={() => setOpen(false)}
                className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <nav className="space-y-1 overflow-y-auto p-2">
              {items.map(({ href, label, icon: Icon }) => {
                const active = pathname === href || pathname.startsWith(`${href}/`);
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors",
                      active
                        ? "bg-accent font-medium text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>
      )}
    </>
  );
}
