"use client";

import { Megaphone, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { apiFetch } from "@/lib/api-client";
import { useMe } from "@/lib/api-hooks";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

/* The platform-wide broadcast bar. Rendered through a PORTAL onto <body>, so it sits
 * above every page regardless of which layout file mounts it - and it works on mobile
 * even though its host (the sidebar) is display:none there. */

interface Announcement {
  id: string;
  body: string;
  level: "info" | "success" | "warning" | "critical";
  audience_roles: string[];
  cta_label: string | null;
  cta_url: string | null;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
}

/** Second line of defence behind the server's allow-list: only an in-app path or an
 *  https:// URL is ever turned into an href, so a javascript:/data: URL that somehow
 *  reached the database still cannot be clicked into execution. */
function safeHref(url: string | null): string | null {
  if (!url) return null;
  if (url.startsWith("/") && !url.startsWith("//")) return url;
  if (url.startsWith("https://")) return url;
  return null;
}

/** One message in the scrolling track: the text, an optional pill button, and the
 *  small square separator that divides it from the next. */
function TickerItem({ announcement }: { announcement: Announcement }) {
  const href = safeHref(announcement.cta_url);
  const external = href?.startsWith("https://") ?? false;
  return (
    <span className="flex shrink-0 items-center gap-3 pr-4">
      <span className="whitespace-nowrap font-medium">{announcement.body}</span>
      {href && (
        <a
          href={href}
          {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
          className="shrink-0 whitespace-nowrap rounded-full border border-current/40 bg-[color:var(--color-bg-card)] px-3 py-0.5 text-xs font-semibold transition-transform hover:scale-105"
        >
          {announcement.cta_label ?? "Learn more"}
        </a>
      )}
      <span aria-hidden className="ml-1 h-1.5 w-1.5 shrink-0 rounded-[1px] bg-current opacity-40" />
    </span>
  );
}

const ROLES = ["admin", "executive", "pod_owner", "marketing", "finance", "viewer"] as const;
const DISMISS_KEY = "announcements-dismissed";

const LEVEL_STYLES: Record<Announcement["level"], string> = {
  info: "bg-[color:var(--color-accent-soft)] text-[color:var(--color-text-primary)] border-[color:var(--color-accent)]",
  success:
    "bg-[color:var(--color-positive-soft)] text-[color:var(--color-text-primary)] border-[color:var(--color-positive)]",
  warning:
    "bg-[color:var(--color-amber-soft)] text-[color:var(--color-text-primary)] border-[color:var(--color-amber)]",
  critical:
    "bg-[color:var(--color-negative-soft)] text-[color:var(--color-text-primary)] border-[color:var(--color-negative)]",
};

function useActiveAnnouncements() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["announcements", "active"],
    queryFn: () => apiFetch<Announcement[]>("/api/v1/announcements/active"),
    enabled: Boolean(user),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}

/** Admin composer inside a popover: message, colour, and WHO sees it. */
function Composer() {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [level, setLevel] = useState<Announcement["level"]>("info");
  const [roles, setRoles] = useState<string[]>([]);
  const [ctaLabel, setCtaLabel] = useState("");
  const [ctaUrl, setCtaUrl] = useState("");

  const publish = useMutation({
    mutationFn: () =>
      apiFetch<Announcement>("/api/v1/announcements", {
        method: "POST",
        body: JSON.stringify({
          body: body.trim(),
          level,
          audience_roles: roles,
          cta_label: ctaLabel.trim() || null,
          cta_url: ctaUrl.trim() || null,
        }),
      }),
    onSuccess: () => {
      setBody("");
      setRoles([]);
      setLevel("info");
      setCtaLabel("");
      setCtaUrl("");
      queryClient.invalidateQueries({ queryKey: ["announcements"] });
    },
  });

  return (
    <div className="space-y-2 p-3">
      <p className="text-sm font-semibold">Publish an announcement</p>
      <textarea
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder="What should the team know?"
        rows={3}
        maxLength={500}
        className="w-full resize-none rounded-[var(--radius-inner)] border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring"
      />
      <div className="flex flex-wrap gap-1">
        {(["info", "success", "warning", "critical"] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setLevel(option)}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-[11px] capitalize transition-colors",
              level === option
                ? "border-[color:var(--color-accent)] bg-[color:var(--color-accent-soft)] font-semibold"
                : "text-muted-foreground hover:bg-accent",
            )}
          >
            {option}
          </button>
        ))}
      </div>
      <div>
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Who sees it (none selected = everyone)
        </p>
        <div className="flex flex-wrap gap-1">
          {ROLES.map((role) => (
            <button
              key={role}
              type="button"
              onClick={() =>
                setRoles((current) =>
                  current.includes(role)
                    ? current.filter((entry) => entry !== role)
                    : [...current, role],
                )
              }
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-[11px] transition-colors",
                roles.includes(role)
                  ? "border-[color:var(--color-accent)] bg-[color:var(--color-accent-soft)] font-semibold"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              {role.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>
      <div>
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Button (optional)
        </p>
        <div className="flex gap-1">
          <input
            value={ctaLabel}
            onChange={(event) => setCtaLabel(event.target.value)}
            placeholder="Learn how"
            maxLength={40}
            className="w-28 shrink-0 rounded-[var(--radius-inner)] border border-input bg-background px-2 py-1 text-xs outline-none focus:ring-1 focus:ring-ring"
          />
          <input
            value={ctaUrl}
            onChange={(event) => setCtaUrl(event.target.value)}
            placeholder="/reports or https://…"
            maxLength={500}
            className="min-w-0 flex-1 rounded-[var(--radius-inner)] border border-input bg-background px-2 py-1 text-xs outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      </div>
      <Button
        size="sm"
        className="w-full"
        disabled={!body.trim() || publish.isPending}
        onClick={() => publish.mutate()}
      >
        {publish.isPending ? "Publishing..." : roles.length ? `Publish to ${roles.length} role(s)` : "Publish to everyone"}
      </Button>
      {publish.isError && (
        <p className="text-xs text-destructive">{(publish.error as Error).message}</p>
      )}
    </div>
  );
}

export function AnnouncementBar() {
  const { data: me } = useMe();
  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;
  const { data } = useActiveAnnouncements();
  const queryClient = useQueryClient();

  // Dismissals are stored PER USER (keyed by id, like the nav order): on a shared
  // workstation an unscoped key let one person's dismissal hide a role-targeted -
  // possibly critical - announcement from the colleague it was actually aimed at.
  const dismissKey = me ? `${DISMISS_KEY}:${me.user_id}` : null;
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!dismissKey) return;
    try {
      const parsed: unknown = JSON.parse(localStorage.getItem(dismissKey) ?? "[]");
      // A stored non-array parses fine, then blanks the app on .includes() during
      // render - shape-check rather than trusting the cast.
      setDismissed(Array.isArray(parsed) ? (parsed as string[]) : []);
    } catch {
      setDismissed([]);
    }
    setReady(true);
  }, [dismissKey]);

  const retire = useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/v1/announcements/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["announcements"] }),
  });

  function dismissAll(ids: string[]): void {
    const next = [...dismissed, ...ids].slice(-50); // cap so the key cannot grow forever
    setDismissed(next);
    if (!dismissKey) return;
    try {
      localStorage.setItem(dismissKey, JSON.stringify(next));
    } catch {
      /* storage blocked - dismissal lasts the session */
    }
  }

  const visible = ready ? (data ?? []).filter((entry) => !dismissed.includes(entry.id)) : [];
  // Scroll duration scales with how much text is on the track, so a long tape does not
  // whip past and a short one does not crawl.
  const trackLength = visible.reduce((total, entry) => total + entry.body.length + 12, 0);
  // EVERY active announcement rides one continuous ticker (the owner's reference), so a
  // second message never has to wait for the first to be dismissed. The newest one sets
  // the bar's colour.
  const bar = visible[0];

  // The banner is fixed to the viewport top, which is where the app header lives. While
  // one is showing, pad <body> by the banner's real rendered height so the whole app
  // shifts down under it - covering the header's buttons is not an option.
  const barRef = useRef<HTMLDivElement | null>(null);
  const barId = bar?.id;
  useEffect(() => {
    if (!barId) return;
    const el = barRef.current;
    if (!el) return;
    const sync = () => {
      document.body.style.paddingTop = `${el.offsetHeight}px`;
      // Body padding moves everything in normal flow, but NOT position: fixed elements -
      // they are laid out against the viewport and would sit under the banner. The mobile
      // nav button is one of those, so publish the height for anything fixed to offset by.
      document.documentElement.style.setProperty("--announce-height", `${el.offsetHeight}px`);
    };
    sync();
    const observer = new ResizeObserver(sync); // tracks the flap-board swap and text wrap
    observer.observe(el);
    return () => {
      observer.disconnect();
      document.body.style.paddingTop = "";
      document.documentElement.style.removeProperty("--announce-height");
    };
  }, [barId]);

  // Portals need the DOM; on the server (and before hydration) render nothing.
  if (!ready || typeof document === "undefined") return null;

  return createPortal(
    <>
      <style>{`
        @keyframes announce-in {
          from { transform: translateY(-100%); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
        @keyframes announce-marquee {
          from { transform: translateX(-50%); }
          to { transform: translateX(0); }
        }
        .announce-marquee { animation: announce-marquee linear infinite; }
        /* Hovering pauses the scroll so a CTA can actually be clicked. */
        .announce-track:hover .announce-marquee { animation-play-state: paused; }
        @media (prefers-reduced-motion: reduce) {
          .announce-marquee { animation: none; }
        }
      `}</style>
      {bar && (
        <div
          ref={barRef}
          role="status"
          className={cn(
            "fixed inset-x-0 top-0 z-[60] flex h-9 items-center gap-3 overflow-hidden border-b px-4 text-sm shadow-lg backdrop-blur",
            LEVEL_STYLES[bar.level],
          )}
          style={{ animation: "announce-in var(--dur, 200ms) var(--ease, ease-out)" }}
        >
          <Megaphone className="h-4 w-4 shrink-0" />
          <div className="announce-track min-w-0 flex-1 overflow-hidden">
            {(
              // Two identical copies make the -50% -> 0 slide seamless: as the first
              // finishes leaving, the second is exactly where it started.
              <div
                className="announce-marquee flex w-max items-center"
                style={{ animationDuration: `${Math.max(20, trackLength * 0.42)}s` }}
              >
                {[0, 1].map((copy) => (
                  <div key={copy} aria-hidden={copy === 1} className="flex items-center">
                    {visible.map((entry) => (
                      <TickerItem key={`${copy}-${entry.id}`} announcement={entry} />
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
          {isAdmin && (
            <button
              type="button"
              title="Retire the newest announcement for everyone"
              className="shrink-0 text-xs underline opacity-80 hover:opacity-100"
              disabled={retire.isPending}
              onClick={() => retire.mutate(bar.id)}
            >
              retire
            </button>
          )}
          <button
            type="button"
            aria-label="Dismiss announcements"
            className="shrink-0 rounded p-1 opacity-70 transition-opacity hover:opacity-100"
            onClick={() => dismissAll(visible.map((entry) => entry.id))}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {isAdmin && (
        <div
          // Clear of the iPhone home indicator, which otherwise sits over the button.
          style={{ bottom: "calc(1rem + env(safe-area-inset-bottom, 0px))" }}
          className="fixed right-4 z-[60] opacity-40 transition-opacity hover:opacity-100 focus-within:opacity-100"
        >
          <Popover>
            <PopoverTrigger asChild>
              <span className="relative inline-flex">
                <span
                  aria-hidden
                  className="absolute inset-0 animate-ping rounded-full bg-[color:var(--color-accent)] opacity-20"
                  style={{ animationDuration: "2.5s" }}
                />
                <Button
                  size="icon"
                  aria-label="Publish announcement"
                  title="Publish announcement"
                  className="relative h-11 w-11 rounded-full shadow-lg transition-transform hover:scale-105 active:scale-95"
                >
                  <Megaphone className="h-5 w-5" />
                </Button>
              </span>
            </PopoverTrigger>
            <PopoverContent align="end" side="top" className="w-80 p-0">
              <Composer />
            </PopoverContent>
          </Popover>
        </div>
      )}
    </>,
    document.body,
  );
}
