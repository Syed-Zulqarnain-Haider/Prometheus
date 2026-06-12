"use client";

import { LogOut } from "lucide-react";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

export function Header() {
  const { user, signOut } = useAuth();

  return (
    <header className="flex h-14 items-center justify-end gap-2 border-b bg-card px-4">
      {user?.email && (
        <span className="hidden text-sm text-muted-foreground sm:inline">
          {user.email}
        </span>
      )}
      <ThemeToggle />
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
    </header>
  );
}
