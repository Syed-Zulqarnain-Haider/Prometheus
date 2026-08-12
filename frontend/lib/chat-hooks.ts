"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { apiFetch, buildQuery } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { PresenceStatus } from "@/lib/people-hooks";

/* Hooks for person-to-person messaging. Polling, not WebSockets: the nginx /api/ proxy
 * does not pass Upgrade headers, so the open thread polls fast (3s) and the list polls
 * slowly (15s), each with an `after` cursor so a quiet thread costs an empty response. */

export interface ConversationPerson {
  user_id: string;
  display_name: string | null;
  email: string;
  job_title: string | null;
  has_avatar: boolean;
  status: PresenceStatus;
  last_seen_at: string | null;
}

export interface Conversation {
  id: string;
  kind: string;
  title: string | null;
  participants: ConversationPerson[];
  last_message_at: string | null;
  last_message_preview: string | null;
  last_message_mine: boolean;
  unread: number;
}

export interface ConversationList {
  conversations: Conversation[];
  unread_total: number;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  sender_id: string | null;
  sender_name: string | null;
  body: string;
  created_at: string;
  edited_at: string | null;
  deleted: boolean;
  mine: boolean;
  /** Delivery state for YOUR messages: sent -> delivered (they have been active since)
   *  -> read (their read marker passed it). null on other people's messages. */
  receipt: "sent" | "delivered" | "read" | null;
}

export interface MessagePage {
  messages: ChatMessage[];
  latest_at: string | null;
}

export function useConversations() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["chat", "conversations"],
    queryFn: () => apiFetch<ConversationList>("/api/v1/chat/conversations"),
    enabled: Boolean(user),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    // A focus/remount inside this window rides the cache instead of firing a duplicate
    // request on top of the 15s poll.
    staleTime: 10_000,
  });
}

const FULL_REFRESH_EVERY = 5; // every 5th poll is a full page so receipt ticks stay live
const MAX_KEPT_MESSAGES = 400; // bound what one open thread holds in memory

/** The open thread. Polls every 3 seconds, but INCREMENTALLY: after the first full page,
 *  each poll sends the server's `after` cursor and gets back only messages newer than
 *  what is already on screen - a quiet thread costs one empty response instead of
 *  re-downloading up to 200 messages. Every 5th poll re-fetches the full page so the
 *  delivery/read ticks on older messages keep advancing and remote deletions reconcile. */
export function useMessages(conversationId: string | null) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const pollsSinceFull = useRef(0);
  useEffect(() => {
    pollsSinceFull.current = 0; // a newly opened thread always starts with a full page
  }, [conversationId]);

  return useQuery({
    queryKey: ["chat", "messages", conversationId],
    queryFn: async (): Promise<MessagePage> => {
      const base = `/api/v1/chat/conversations/${conversationId}/messages`;
      const cached = queryClient.getQueryData<MessagePage>(["chat", "messages", conversationId]);
      if (!cached?.latest_at || pollsSinceFull.current >= FULL_REFRESH_EVERY - 1) {
        pollsSinceFull.current = 0;
        return apiFetch<MessagePage>(`${base}${buildQuery({ limit: 200 })}`);
      }
      pollsSinceFull.current += 1;
      const delta = await apiFetch<MessagePage>(
        `${base}${buildQuery({ after: cached.latest_at, limit: 200 })}`,
      );
      const latest = delta.latest_at ?? cached.latest_at;
      // Reuse the cached array identity when nothing changed - downstream memoized rows
      // and the scroll-pinning effect then have nothing to re-do.
      if (delta.messages.length === 0) return { ...cached, latest_at: latest };
      const known = new Set(cached.messages.map((message) => message.id));
      const fresh = delta.messages.filter((message) => !known.has(message.id));
      if (fresh.length === 0) return { ...cached, latest_at: latest };
      return {
        messages: [...cached.messages, ...fresh].slice(-MAX_KEPT_MESSAGES),
        latest_at: latest,
      };
    },
    enabled: Boolean(user) && Boolean(conversationId),
    refetchInterval: 3_000,
    // Scoped to THIS conversation: unscoped placeholderData carries over across query
    // keys, so switching threads briefly rendered the previous thread's messages in the
    // new pane - the wrong person's conversation on screen is a privacy bug, not a flicker.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[2] === conversationId ? previous : undefined,
  });
}

export function useOpenDirect() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) =>
      apiFetch<Conversation>("/api/v1/chat/conversations/direct", {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat", "conversations"] });
    },
  });
}

export function useSendMessage(conversationId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ body, mentions }: { body: string; mentions?: string[] }) =>
      apiFetch<ChatMessage>(`/api/v1/chat/conversations/${conversationId}/messages`, {
        method: "POST",
        body: JSON.stringify({ body, mentions: mentions ?? [] }),
      }),
    onSuccess: () => {
      // Refetch the thread immediately rather than waiting out the poll interval.
      queryClient.invalidateQueries({ queryKey: ["chat", "messages", conversationId] });
      queryClient.invalidateQueries({ queryKey: ["chat", "conversations"] });
    },
  });
}

export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) =>
      apiFetch<void>(`/api/v1/chat/conversations/${conversationId}/read`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat", "conversations"] });
    },
  });
}

export function useDeleteMessage(conversationId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) =>
      apiFetch<void>(`/api/v1/chat/messages/${messageId}`, { method: "DELETE" }),
    onSuccess: (_result, messageId) => {
      // Tombstone locally: the incremental poll only ever sees NEW messages, so a
      // deletion must not wait for the next full refresh to disappear from screen.
      queryClient.setQueryData<MessagePage>(["chat", "messages", conversationId], (page) =>
        page
          ? {
              ...page,
              messages: page.messages.map((message) =>
                message.id === messageId ? { ...message, deleted: true, body: "" } : message,
              ),
            }
          : page,
      );
      queryClient.invalidateQueries({ queryKey: ["chat", "conversations"] });
    },
  });
}

/* ── Admin oversight (read-only) ──────────────────────────────────────────────── */

export interface AdminConversation extends Conversation {
  /** Oversight listing shows EVERY participant, the caller included. */
  message_count: number;
}

export function useAdminConversations(enabled: boolean) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["chat", "admin", "conversations"],
    queryFn: () =>
      apiFetch<{ conversations: AdminConversation[] }>("/api/v1/chat/admin/conversations"),
    enabled: Boolean(user) && enabled,
  });
}

export function useAdminMessages(conversationId: string | null) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["chat", "admin", "messages", conversationId],
    queryFn: () =>
      apiFetch<MessagePage>(
        `/api/v1/chat/admin/conversations/${conversationId}/messages${buildQuery({ limit: 200 })}`,
      ),
    enabled: Boolean(user) && Boolean(conversationId),
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[3] === conversationId ? previous : undefined,
  });
}


export function useCreateGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ title, memberIds }: { title: string; memberIds: string[] }) =>
      apiFetch<Conversation>("/api/v1/chat/groups", {
        method: "POST",
        body: JSON.stringify({ title, member_ids: memberIds }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["chat", "conversations"] }),
  });
}

export interface InviteCode {
  code: string;
  expires_in_seconds: number;
}

export function useCreateInvite() {
  return useMutation({
    mutationFn: (conversationId: string) =>
      apiFetch<InviteCode>(`/api/v1/chat/conversations/${conversationId}/invite`, {
        method: "POST",
      }),
  });
}

export function useJoinByCode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (code: string) =>
      apiFetch<Conversation>("/api/v1/chat/join", {
        method: "POST",
        body: JSON.stringify({ code }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["chat", "conversations"] }),
  });
}

export function useAdminDeleteMessage(conversationId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) =>
      apiFetch<void>(`/api/v1/chat/admin/messages/${messageId}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat", "admin", "messages", conversationId] });
    },
  });
}

export function useAdminDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) =>
      apiFetch<void>(`/api/v1/chat/admin/conversations/${conversationId}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat", "admin", "conversations"] });
      queryClient.invalidateQueries({ queryKey: ["chat", "conversations"] });
    },
  });
}
