"use client";

import { format, isToday, isYesterday, parseISO } from "date-fns";
import {
  Check,
  CheckCheck,
  ChevronLeft,
  Eye,
  KeyRound,
  MessageSquarePlus,
  Search,
  Send,
  Trash2,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { PersonAvatar } from "@/components/people/person-avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useMe } from "@/lib/api-hooks";
import {
  type ChatMessage,
  type Conversation,
  useAdminConversations,
  useAdminDeleteConversation,
  useAdminDeleteMessage,
  useAdminMessages,
  useConversations,
  useCreateGroup,
  useCreateInvite,
  useJoinByCode,
  useDeleteMessage,
  useMarkRead,
  useMessages,
  useOpenDirect,
  useSendMessage,
} from "@/lib/chat-hooks";
import { useDebounced, usePeople, type Person } from "@/lib/people-hooks";
import { cn } from "@/lib/utils";

function timeOf(iso: string): string {
  const date = parseISO(iso);
  if (isToday(date)) return format(date, "HH:mm");
  if (isYesterday(date)) return `Yesterday ${format(date, "HH:mm")}`;
  return format(date, "d MMM HH:mm");
}

function lastSeenLabel(person: { status: string; last_seen_at: string | null }): string {
  if (person.status === "online") return "Active now";
  if (!person.last_seen_at) return "Offline";
  return `Last seen ${timeOf(person.last_seen_at)}`;
}

/** The person on the other side. Oversight rows include EVERY participant (the admin
 *  too), so filter self out rather than trusting position 0. */
function counterpart(conversation: Conversation, meId: string | undefined) {
  return (
    conversation.participants.find((participant) => participant.user_id !== meId) ??
    conversation.participants[0] ??
    null
  );
}

function ConversationRow({
  conversation,
  active,
  meId,
  onSelect,
}: {
  conversation: Conversation;
  active: boolean;
  meId: string | undefined;
  onSelect: () => void;
}) {
  const other = counterpart(conversation, meId);
  if (!other) return null;
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-3 rounded-[var(--radius-inner)] px-3 py-2.5 text-left transition-colors",
        active ? "bg-accent" : "hover:bg-accent/60",
      )}
    >
      <PersonAvatar
        userId={other.user_id}
        displayName={other.display_name}
        email={other.email}
        hasAvatar={other.has_avatar}
        status={other.status}
        size={40}
      />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="truncate text-sm font-medium">
            {other.display_name ?? other.email}
          </span>
          {conversation.last_message_at && (
            <span className="shrink-0 text-[10px] text-muted-foreground">
              {timeOf(conversation.last_message_at)}
            </span>
          )}
        </span>
        <span className="flex items-center justify-between gap-2">
          <span className="truncate text-xs text-muted-foreground">
            {conversation.last_message_mine && "You: "}
            {conversation.last_message_preview ?? "No messages yet"}
          </span>
          {conversation.unread > 0 && (
            <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-[color:var(--color-accent)] px-1.5 text-[10px] font-semibold text-[color:var(--color-accent-foreground)]">
              {conversation.unread > 99 ? "99+" : conversation.unread}
            </span>
          )}
        </span>
      </span>
    </button>
  );
}

/** WhatsApp-style delivery ticks on your own messages: one grey = sent, two grey = the
 *  recipient's account has been active since, two blue = their read marker passed it.
 *  In groups a state only shows once EVERY member reached it. */
function Ticks({ receipt }: { receipt: "sent" | "delivered" | "read" | null }) {
  if (!receipt) return null;
  if (receipt === "sent") return <Check className="h-3 w-3" aria-label="Sent" />;
  return (
    <CheckCheck
      className={cn("h-3 w-3", receipt === "read" && "text-[#53bdeb]")}
      aria-label={receipt === "read" ? "Read" : "Delivered"}
    />
  );
}

/** Highlight @mentions in a message body. Display-only - the authoritative mention list
 *  went to the server at send time. */
function renderBody(body: string) {
  const parts = body.split(/(@[\w.][\w.\s]{0,40}?)(?=\s@|\s{2}|[,.!?;:]|$)/g);
  if (parts.length === 1) return body;
  return parts.map((part, index) =>
    part.startsWith("@") ? (
      <mark
        key={index}
        className="rounded bg-transparent px-0.5 font-semibold text-inherit underline decoration-dotted underline-offset-2"
      >
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

function MessageBubble({
  message,
  onDelete,
}: {
  message: ChatMessage;
  onDelete?: (id: string) => void;
}) {
  return (
    <div className={cn("group flex", message.mine ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "relative max-w-[75%] rounded-2xl px-3.5 py-2 text-sm",
          message.mine
            ? "rounded-br-md bg-[color:var(--color-accent)] text-[color:var(--color-accent-foreground)]"
            : "rounded-bl-md bg-[color:var(--color-bg-elevated)]",
        )}
      >
        {!message.mine && message.sender_name && (
          <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider opacity-70">
            {message.sender_name}
          </p>
        )}
        {message.deleted ? (
          <p className="italic opacity-60">Message deleted</p>
        ) : (
          <p className="whitespace-pre-wrap break-words">{renderBody(message.body)}</p>
        )}
        <p
          className={cn(
            "mt-0.5 flex items-center justify-end gap-1 text-[10px]",
            message.mine ? "opacity-70" : "text-muted-foreground",
          )}
        >
          {timeOf(message.created_at)}
          {message.mine && !message.deleted && <Ticks receipt={message.receipt} />}
        </p>
        {!message.deleted && onDelete && (
          <button
            type="button"
            aria-label="Delete message"
            onClick={() => onDelete(message.id)}
            className="absolute -left-7 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

/** Slack-style messaging: conversations on the left, the thread in the middle, contact
 *  details on the right. Admins get a read-only "All chats" oversight tab (audit-logged
 *  server-side). Presence and threads poll; the open thread refreshes every 3 seconds. */
export function ChatClient() {
  const { data: me } = useMe();
  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;

  const [tab, setTab] = useState<"mine" | "oversight">("mine");
  const [selected, setSelected] = useState<string | null>(null);
  const [personSearch, setPersonSearch] = useState("");
  const [draft, setDraft] = useState("");

  const conversations = useConversations();
  const debouncedSearch = useDebounced(personSearch);
  const people = usePeople(debouncedSearch || undefined);
  const openDirect = useOpenDirect();
  const markRead = useMarkRead();

  const oversight = useAdminConversations(isAdmin && tab === "oversight");
  const mineMessages = useMessages(tab === "mine" ? selected : null);
  const adminMessages = useAdminMessages(tab === "oversight" ? selected : null);
  const messages = tab === "mine" ? mineMessages.data : adminMessages.data;

  const send = useSendMessage(selected);
  const removeMessage = useDeleteMessage(selected);
  const createGroup = useCreateGroup();
  const createInvite = useCreateInvite();
  const joinByCode = useJoinByCode();
  const adminDeleteMessage = useAdminDeleteMessage(selected);
  const adminDeleteConversation = useAdminDeleteConversation();

  const [groupMode, setGroupMode] = useState(false);
  const [groupTitle, setGroupTitle] = useState("");
  const [groupMembers, setGroupMembers] = useState<string[]>([]);
  const [joinCode, setJoinCode] = useState("");
  const [inviteShown, setInviteShown] = useState<string | null>(null);
  const [mentionOpen, setMentionOpen] = useState(false);
  // user_ids attached to the next send, collected as autocomplete picks happen.
  const mentionIds = useRef<Set<string>>(new Set());

  const list: Conversation[] =
    tab === "mine"
      ? (conversations.data?.conversations ?? [])
      : (oversight.data?.conversations ?? []);
  const current = list.find((conversation) => conversation.id === selected) ?? null;
  const other = current ? counterpart(current, me?.user_id) : null;

  // Mark read when the open thread actually has something new from the OTHER side, at
  // most once per (thread, newest message). Driving this off the unread badge fired a
  // POST every badge tick and never retried a failure.
  const lastMarked = useRef<string | null>(null);
  const latestAt = messages?.latest_at ?? null;
  const hasTheirMessages = (messages?.messages ?? []).some((m) => !m.mine && !m.deleted);
  useEffect(() => {
    if (tab !== "mine" || !selected || !latestAt || !hasTheirMessages) return;
    const stamp = `${selected}|${latestAt}`;
    if (lastMarked.current === stamp) return;
    lastMarked.current = stamp;
    markRead.mutate(selected, {
      onError: () => {
        // Allow a retry on the next poll instead of leaving the badge stuck.
        if (lastMarked.current === stamp) lastMarked.current = null;
      },
    });
    // markRead is a stable mutation object; listing it would re-run this every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, latestAt, hasTheirMessages, tab]);

  // Pin to the newest message ONLY when the reader is already at the bottom (or has just
  // switched threads) - yanking someone down while they read history is hostile.
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollBoxRef = useRef<HTMLDivElement>(null);
  const messageCount = messages?.messages.length ?? 0;
  useEffect(() => {
    const box = scrollBoxRef.current;
    const nearBottom =
      !box || box.scrollHeight - box.scrollTop - box.clientHeight < 120;
    if (nearBottom) bottomRef.current?.scrollIntoView({ block: "nearest" });
  }, [messageCount, selected]);

  // People not yet in a conversation, for starting a new one.
  const startablePeople = useMemo(() => {
    const inThreads = new Set(
      (conversations.data?.conversations ?? []).flatMap((conversation) =>
        conversation.participants.map((participant) => participant.user_id),
      ),
    );
    return (people.data?.people ?? []).filter(
      (person) => person.user_id !== me?.user_id && (personSearch || !inThreads.has(person.user_id)),
    );
  }, [people.data, conversations.data, me?.user_id, personSearch]);

  function startChat(person: Person): void {
    openDirect.mutate(person.user_id, {
      onSuccess: (conversation) => {
        setTab("mine");
        setSelected(conversation.id);
        setPersonSearch("");
      },
    });
  }

  function submit(): void {
    const body = draft.trim();
    if (!body || !selected || send.isPending) return;
    // Clear only on SUCCESS - clearing up front destroys the typed message if the send
    // fails, with nothing to retry from. Mentions only count if their @text survived edits.
    const roster = current?.participants ?? [];
    const mentions = [...mentionIds.current].filter((id) => {
      const person = roster.find((entry) => entry.user_id === id);
      return person && body.includes(`@${person.display_name ?? person.email}`);
    });
    send.mutate(
      { body, mentions },
      {
        onSuccess: () => {
          setDraft("");
          mentionIds.current.clear();
        },
      },
    );
  }

  const mentionQuery = /@([\w.]*)$/.exec(draft.slice(0, undefined))?.[1] ?? null;
  const mentionCandidates =
    mentionOpen && current
      ? current.participants
          .filter((participant) =>
            (participant.display_name ?? participant.email)
              .toLowerCase()
              .includes((mentionQuery ?? "").toLowerCase()),
          )
          .slice(0, 5)
      : [];

  function pickMention(person: { user_id: string; display_name: string | null; email: string }) {
    const name = person.display_name ?? person.email;
    setDraft((value) => value.replace(/@[\w.]*$/, `@${name} `));
    mentionIds.current.add(person.user_id);
    setMentionOpen(false);
  }

  return (
    <div className="flex h-[calc(100dvh-10.5rem)] min-h-[24rem] overflow-hidden rounded-[var(--radius-card)] border bg-card">
      {/* ── Left: conversations + people. Below md the screen shows list OR thread,
          never both squeezed side by side. ─────────────────────── */}
      <div
        className={cn(
          "min-h-0 w-full flex-col border-r md:flex md:w-72 md:shrink-0",
          selected ? "hidden" : "flex",
        )}
      >
        <div className="space-y-2 border-b p-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={personSearch}
              onChange={(event) => setPersonSearch(event.target.value)}
              placeholder="Search people"
              className="h-8 pl-8"
            />
          </div>
          <div className="flex gap-1">
            <Button
              size="sm"
              variant={groupMode ? "default" : "outline"}
              className="h-7 flex-1 gap-1 text-xs"
              onClick={() => setGroupMode((value) => !value)}
            >
              <Users className="h-3 w-3" /> New group
            </Button>
          </div>
          {groupMode && (
            <div className="space-y-2 rounded-[var(--radius-inner)] border p-2">
              <Input
                value={groupTitle}
                onChange={(event) => setGroupTitle(event.target.value)}
                placeholder="Group name"
                className="h-8"
              />
              <div className="max-h-40 space-y-0.5 overflow-y-auto">
                {(people.data?.people ?? [])
                  .filter((person) => person.user_id !== me?.user_id)
                  .map((person) => (
                    <label
                      key={person.user_id}
                      className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-accent/60"
                    >
                      <input
                        type="checkbox"
                        checked={groupMembers.includes(person.user_id)}
                        onChange={(event) =>
                          setGroupMembers((current) =>
                            event.target.checked
                              ? [...current, person.user_id]
                              : current.filter((id) => id !== person.user_id),
                          )
                        }
                      />
                      <span className="truncate">{person.display_name ?? person.email}</span>
                    </label>
                  ))}
              </div>
              <Button
                size="sm"
                className="w-full"
                disabled={!groupTitle.trim() || groupMembers.length === 0 || createGroup.isPending}
                onClick={() =>
                  createGroup.mutate(
                    { title: groupTitle.trim(), memberIds: groupMembers },
                    {
                      onSuccess: (group) => {
                        setGroupMode(false);
                        setGroupTitle("");
                        setGroupMembers([]);
                        setTab("mine");
                        setSelected(group.id);
                      },
                    },
                  )
                }
              >
                Create group ({groupMembers.length})
              </Button>
            </div>
          )}
          <div className="flex items-center gap-1">
            <KeyRound className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <Input
              value={joinCode}
              onChange={(event) => setJoinCode(event.target.value.toUpperCase())}
              placeholder="Join with code"
              className="h-7 text-xs"
              maxLength={16}
            />
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              disabled={joinCode.trim().length < 4 || joinByCode.isPending}
              onClick={() =>
                joinByCode.mutate(joinCode.trim(), {
                  onSuccess: (group) => {
                    setJoinCode("");
                    setTab("mine");
                    setSelected(group.id);
                  },
                })
              }
            >
              Join
            </Button>
          </div>
          {joinByCode.isError && (
            <p className="text-xs text-destructive">That code is invalid or has expired.</p>
          )}
          {isAdmin && (
            <div className="flex gap-1">
              <Button
                size="sm"
                variant={tab === "mine" ? "default" : "outline"}
                className="h-7 flex-1 text-xs"
                onClick={() => {
                  setTab("mine");
                  setSelected(null);
                }}
              >
                My chats
              </Button>
              <Button
                size="sm"
                variant={tab === "oversight" ? "default" : "outline"}
                className="h-7 flex-1 gap-1 text-xs"
                onClick={() => {
                  setTab("oversight");
                  setSelected(null);
                }}
              >
                <Eye className="h-3 w-3" /> All chats
              </Button>
            </div>
          )}
        </div>

        <div className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {list.map((conversation) => (
            <ConversationRow
              key={conversation.id}
              conversation={conversation}
              active={conversation.id === selected}
              meId={me?.user_id}
              onSelect={() => setSelected(conversation.id)}
            />
          ))}
          {list.length === 0 && (
            <p className="px-3 py-4 text-center text-xs text-muted-foreground">
              {tab === "mine" ? "No conversations yet." : "No conversations on the platform."}
            </p>
          )}

          {tab === "mine" && startablePeople.length > 0 && (
            <>
              <p className="px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {personSearch ? "People" : "Start a conversation"}
              </p>
              {startablePeople.map((person) => (
                <button
                  key={person.user_id}
                  type="button"
                  onClick={() => startChat(person)}
                  className="flex w-full items-center gap-3 rounded-[var(--radius-inner)] px-3 py-2 text-left hover:bg-accent/60"
                >
                  <PersonAvatar
                    userId={person.user_id}
                    displayName={person.display_name}
                    email={person.email}
                    hasAvatar={person.has_avatar}
                    status={person.status}
                    size={32}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm">{person.display_name ?? person.email}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">
                      {person.job_title ?? person.roles.join(", ") ?? ""}
                    </span>
                  </span>
                  <MessageSquarePlus className="h-4 w-4 shrink-0 text-muted-foreground" />
                </button>
              ))}
            </>
          )}
        </div>
      </div>

      {/* ── Middle: the thread ───────────────────────────────────── */}
      <div className={cn("min-h-0 min-w-0 flex-1 flex-col md:flex", selected ? "flex" : "hidden")}>
        {current && other ? (
          <>
            <div className="flex items-center gap-3 border-b px-4 py-2.5">
              <button
                type="button"
                aria-label="Back to conversations"
                className="rounded p-1 text-muted-foreground hover:bg-accent md:hidden"
                onClick={() => setSelected(null)}
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <PersonAvatar
                userId={other.user_id}
                displayName={other.display_name}
                email={other.email}
                hasAvatar={other.has_avatar}
                status={other.status}
                size={36}
              />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">
                  {current.kind === "group"
                    ? (current.title ?? "Group")
                    : (other.display_name ?? other.email)}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {current.kind === "group"
                    ? `${current.participants.length + 1} members`
                    : lastSeenLabel(other)}
                </p>
              </div>
              {tab === "mine" && current.kind === "group" && (
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto h-7 gap-1 text-xs"
                  disabled={createInvite.isPending}
                  onClick={() =>
                    createInvite.mutate(current.id, {
                      onSuccess: (invite) => setInviteShown(invite.code),
                    })
                  }
                >
                  <KeyRound className="h-3 w-3" /> Invite code
                </Button>
              )}
              {tab === "oversight" && isAdmin && (
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto h-7 gap-1 text-xs text-destructive"
                  disabled={adminDeleteConversation.isPending}
                  onClick={() => {
                    if (window.confirm("Permanently delete this entire conversation? This reclaims its storage and cannot be undone.")) {
                      adminDeleteConversation.mutate(current.id, {
                        onSuccess: () => setSelected(null),
                      });
                    }
                  }}
                >
                  <Trash2 className="h-3 w-3" /> Delete thread
                </Button>
              )}
              {tab === "oversight" && (
                <span className="ml-auto rounded-full border border-[color:var(--color-amber)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-amber)]">
                  Read-only oversight
                </span>
              )}
            </div>

            {inviteShown && (
              <p className="border-b bg-[color:var(--color-accent-soft)] px-4 py-2 text-xs">
                Invite code: <span className="font-mono text-sm font-bold tracking-widest">{inviteShown}</span>
                {" "}- one use, expires in 15 minutes. Share it only with the person you mean to add.
                <button type="button" className="ml-2 underline" onClick={() => setInviteShown(null)}>
                  dismiss
                </button>
              </p>
            )}
            <div ref={scrollBoxRef} className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4">
              {(messages?.messages ?? []).map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  onDelete={
                    tab === "mine"
                      ? (id) => removeMessage.mutate(id)
                      : isAdmin
                        ? (id) => adminDeleteMessage.mutate(id)
                        : undefined
                  }
                />
              ))}
              {messages && messages.messages.length === 0 && (
                <p className="pt-8 text-center text-sm text-muted-foreground">
                  Say hello - this is the start of your conversation.
                </p>
              )}
              <div ref={bottomRef} />
            </div>

            {tab === "mine" && send.isError && (
              <p className="border-t px-3 pt-2 text-xs text-destructive">
                Message failed to send - it is still in the box below. Try again.
              </p>
            )}
            {tab === "mine" && (
              <div className="relative flex items-end gap-2 border-t p-3">
                {mentionOpen && mentionCandidates.length > 0 && (
                  <div className="absolute bottom-16 left-3 z-10 w-64 rounded-[var(--radius-inner)] border bg-card p-1 shadow-lg">
                    {mentionCandidates.map((person) => (
                      <button
                        key={person.user_id}
                        type="button"
                        className="block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
                        onClick={() => pickMention(person)}
                      >
                        @{person.display_name ?? person.email}
                      </button>
                    ))}
                  </div>
                )}
                <textarea
                  value={draft}
                  onChange={(event) => {
                    setDraft(event.target.value);
                    setMentionOpen(/@[\w.]*$/.test(event.target.value));
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      submit();
                    }
                  }}
                  placeholder="Write a message... (Enter to send, Shift+Enter for a new line)"
                  rows={draft.includes("\n") ? 3 : 1}
                  className="max-h-32 flex-1 resize-none rounded-[var(--radius-inner)] border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring"
                />
                <Button
                  size="icon"
                  aria-label="Send"
                  disabled={!draft.trim() || send.isPending}
                  onClick={submit}
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            )}
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center p-8 text-center text-sm text-muted-foreground">
            {tab === "oversight"
              ? "Select a conversation to review it. Every view is audit-logged."
              : "Pick a conversation, or search for a colleague to start one."}
          </div>
        )}
      </div>

      {/* ── Right: contact info (hidden on smaller screens) ──────── */}
      {current && other && (
        <div className="hidden w-64 shrink-0 flex-col items-center gap-2 border-l p-5 text-center xl:flex">
          <PersonAvatar
            userId={other.user_id}
            displayName={other.display_name}
            email={other.email}
            hasAvatar={other.has_avatar}
            status={other.status}
            size={72}
          />
          <p className="mt-1 text-sm font-semibold">{other.display_name ?? other.email}</p>
          {other.job_title && <p className="text-xs text-muted-foreground">{other.job_title}</p>}
          <p className="text-xs text-muted-foreground">{other.email}</p>
          <p
            className={cn(
              "mt-2 rounded-full px-2.5 py-0.5 text-[11px]",
              other.status === "online"
                ? "bg-[color:var(--color-positive-soft)] text-[color:var(--color-positive)]"
                : "bg-[color:var(--color-bg-elevated)] text-muted-foreground",
            )}
          >
            {lastSeenLabel(other)}
          </p>
        </div>
      )}
    </div>
  );
}
