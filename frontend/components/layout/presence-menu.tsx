"use client";

import { format, parseISO } from "date-fns";
import { Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PersonAvatar } from "@/components/people/person-avatar";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useMe } from "@/lib/api-hooks";
import { usePeople, type Person } from "@/lib/people-hooks";
import { cn } from "@/lib/utils";

function seenLabel(person: Person): string {
  if (person.status === "online") return "Active now";
  if (!person.last_seen_at) return "Offline";
  return `Last seen ${format(parseISO(person.last_seen_at), "d MMM HH:mm")}`;
}

/** Header presence: "who is on the platform right now". The trigger shows the live online
 *  count; the dropdown lists everyone, online first, with their status and last-seen (and
 *  last-login for admins). Data refreshes every 30s via usePeople. */
export function PresenceMenu() {
  const [open, setOpen] = useState(false);
  const { data: me } = useMe();
  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;
  const { data } = usePeople();

  const online = data?.online ?? 0;
  const ordered = [...(data?.people ?? [])].sort((a, b) => {
    const rank = { online: 0, away: 1, offline: 2 } as const;
    return rank[a.status] - rank[b.status];
  });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-1.5" aria-label="Who is online">
          <span className="relative flex h-2 w-2">
            {online > 0 && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#34a853] opacity-60" />
            )}
            <span
              className={cn(
                "relative inline-flex h-2 w-2 rounded-full",
                online > 0 ? "bg-[#34a853]" : "bg-muted-foreground",
              )}
            />
          </span>
          <span className="text-xs tabular-nums">{online} online</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="flex items-center gap-1.5 text-sm font-semibold">
            <Users className="h-3.5 w-3.5" /> Team
          </span>
          <Link
            href="/profile"
            className="text-xs text-muted-foreground hover:underline"
            onClick={() => setOpen(false)}
          >
            My profile
          </Link>
        </div>
        <div className="max-h-96 overflow-y-auto p-1.5">
          {ordered.map((person) => (
            <div
              key={person.user_id}
              className="flex items-center gap-2.5 rounded-md px-2 py-1.5"
            >
              <PersonAvatar
                userId={person.user_id}
                displayName={person.display_name}
                email={person.email}
                hasAvatar={person.has_avatar}
                status={person.status}
                size={30}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">
                  {person.display_name ?? person.email}
                  {person.user_id === me?.user_id && (
                    <span className="text-muted-foreground"> (you)</span>
                  )}
                </span>
                <span className="block truncate text-[11px] text-muted-foreground">
                  {seenLabel(person)}
                  {isAdmin &&
                    person.last_login_at &&
                    ` · logged in ${format(parseISO(person.last_login_at), "d MMM HH:mm")}`}
                </span>
              </span>
            </div>
          ))}
          {ordered.length === 0 && (
            <p className="px-3 py-4 text-center text-xs text-muted-foreground">
              Nobody to show yet.
            </p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
