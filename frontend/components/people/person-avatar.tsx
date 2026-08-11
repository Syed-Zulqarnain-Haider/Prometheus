"use client";

import { initialsOf, useAvatar, type PresenceStatus } from "@/lib/people-hooks";
import { cn } from "@/lib/utils";

/** Presence dot colours: green = online now (live heartbeat), amber = seen in the last
 *  15 minutes, grey = offline. Matching what chat clients have trained everyone to read. */
const DOT: Record<PresenceStatus, string> = {
  online: "bg-[#34a853]",
  away: "bg-[color:var(--color-amber)]",
  offline: "bg-[color:var(--color-text-muted)]",
};

export function PersonAvatar({
  userId,
  displayName,
  email,
  hasAvatar,
  status,
  size = 36,
}: {
  userId: string;
  displayName: string | null;
  email: string;
  hasAvatar: boolean;
  status?: PresenceStatus;
  size?: number;
}) {
  const avatar = useAvatar(userId, hasAvatar);
  const px = { width: size, height: size };

  return (
    <span className="relative inline-block shrink-0" style={px}>
      {avatar.data ? (
        // Blob object URL, fetched with the auth token - a plain <img src> to the API
        // cannot carry the Authorization header. eslint-disable: next/image cannot
        // optimise blob: URLs, and the optimizer is disabled anyway.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={avatar.data}
          alt={displayName ?? email}
          className="h-full w-full rounded-full object-cover"
        />
      ) : (
        <span
          className="flex h-full w-full items-center justify-center rounded-full bg-[color:var(--color-accent-soft)] font-medium text-[color:var(--color-accent)]"
          style={{ fontSize: Math.max(11, size * 0.38) }}
          aria-hidden
        >
          {initialsOf({ display_name: displayName, email })}
        </span>
      )}
      {status && (
        <span
          title={status}
          className={cn(
            "absolute -bottom-0.5 -right-0.5 rounded-full border-2 border-[color:var(--color-bg-card)]",
            DOT[status],
          )}
          style={{ width: Math.max(10, size * 0.3), height: Math.max(10, size * 0.3) }}
        />
      )}
    </span>
  );
}
