"use client";

import { Megaphone, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { SplitFlapText } from "@/components/effects/split-flap-text";
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
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
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

  const publish = useMutation({
    mutationFn: () =>
      apiFetch<Announcement>("/api/v1/announcements", {
        method: "POST",
        body: JSON.stringify({ body: body.trim(), level, audience_roles: roles }),
      }),
    onSuccess: () => {
      setBody("");
      setRoles([]);
      setLevel("info");
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

  // Per-user dismissal, localStorage, read post-hydration only (the SSR rule).
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    try {
      setDismissed(JSON.parse(localStorage.getItem(DISMISS_KEY) ?? "[]") as string[]);
    } catch {
      setDismissed([]);
    }
    setReady(true);
  }, []);

  const retire = useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/v1/announcements/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["announcements"] }),
  });

  function dismiss(id: string): void {
    const next = [...dismissed, id].slice(-50); // cap so the key cannot grow forever
    setDismissed(next);
    try {
      localStorage.setItem(DISMISS_KEY, JSON.stringify(next));
    } catch {
      /* storage blocked - dismissal lasts the session */
    }
  }

  const visible = ready ? (data ?? []).filter((entry) => !dismissed.includes(entry.id)) : [];
  const bar = visible[0]; // newest first from the API; one at a time keeps it a banner, not a feed

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
    };
    sync();
    const observer = new ResizeObserver(sync); // tracks the flap-board swap and text wrap
    observer.observe(el);
    return () => {
      observer.disconnect();
      document.body.style.paddingTop = "";
    };
  }, [barId]);

  // The owner's attention loop: the message scrolls left-to-right as a looping ticker,
  // and every few seconds it deals itself onto the split-flap board instead, forever
  // alternating between the two.
  const [phase, setPhase] = useState<"marquee" | "flap">("marquee");
  useEffect(() => {
    if (!barId) return;
    setPhase("marquee");
    const timer = window.setInterval(() => {
      setPhase((current) => (current === "marquee" ? "flap" : "marquee"));
    }, 8000);
    return () => window.clearInterval(timer);
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
        @media (prefers-reduced-motion: reduce) {
          .announce-marquee { animation: none; }
        }
      `}</style>
      {bar && (
        <div
          ref={barRef}
          role="status"
          className={cn(
            "fixed inset-x-0 top-0 z-[60] flex items-center gap-3 border-b px-4 py-2 text-sm shadow-lg backdrop-blur",
            LEVEL_STYLES[bar.level],
          )}
          style={{ animation: "announce-in var(--dur, 200ms) var(--ease, ease-out)" }}
        >
          <Megaphone className="h-4 w-4 shrink-0" />
          <div className="min-w-0 flex-1 overflow-hidden" title={bar.body}>
            {phase === "flap" ? (
              <SplitFlapText
                words={[bar.body.length > 42 ? `${bar.body.slice(0, 42)}…` : bar.body]}
                flipDuration={0.12}
                stagger={0.06}
                charset="alphanumeric"
                flipsPerChar={8}
                tileColor="#111827"
                textColor="#f8fafc"
                tileRadius={4}
                gap={3}
                fontSize={12}
              />
            ) : (
              // Two copies with a fixed gap make the -50% -> 0 slide a seamless
              // left-to-right loop; reduced-motion shows the text statically.
              <div
                className="announce-marquee flex w-max items-center font-medium"
                style={{ animationDuration: `${Math.max(14, bar.body.length * 0.45)}s` }}
              >
                <span className="whitespace-nowrap pr-16">{bar.body}</span>
                <span aria-hidden className="whitespace-nowrap pr-16">
                  {bar.body}
                </span>
              </div>
            )}
          </div>
          {visible.length > 1 && (
            <span className="shrink-0 text-xs opacity-70">+{visible.length - 1} more</span>
          )}
          {isAdmin && (
            <button
              type="button"
              className="shrink-0 text-xs underline opacity-80 hover:opacity-100"
              disabled={retire.isPending}
              onClick={() => retire.mutate(bar.id)}
            >
              retire
            </button>
          )}
          <button
            type="button"
            aria-label="Dismiss announcement"
            className="shrink-0 rounded p-1 opacity-70 transition-opacity hover:opacity-100"
            onClick={() => dismiss(bar.id)}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {isAdmin && (
        <div className="fixed bottom-4 right-4 z-[60]">
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
