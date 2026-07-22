"use client";

import { LogOut } from "lucide-react";

import { MobileNav } from "@/components/layout/mobile-nav";
import { NotificationBell } from "@/components/layout/notification-bell";
import { ThemeSelector } from "@/components/layout/theme-selector";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

export function Header() {
  const { user, signOut } = useAuth();

  return (
    <header className="flex h-14 items-center gap-2 border-b bg-card px-3 sm:px-4">
      {/* Mobile-only: hamburger + brand (the desktop Sidebar carries the brand at md+). */}
      <div className="flex items-center gap-2 md:hidden">
        <MobileNav />
        <span className="text-base font-semibold">Prometheus</span>
      </div>

      <div className="ml-auto flex items-center gap-1 sm:gap-2">
        {user?.email && (
          <span className="hidden max-w-[40vw] truncate text-sm text-muted-foreground sm:inline">
            {user.email}
          </span>
        )}
        <NotificationBell />
        <ThemeSelector />
        <Button
          variant="ghost"
          size="icon"
          aria-label="Sign out"
          onClick={() => {
            void signOut();
          }}
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
