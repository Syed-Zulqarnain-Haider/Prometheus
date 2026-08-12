"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
  });
}

/** The open thread. Refetches every 3 seconds; TanStack keeps the previous data on screen
 *  while the next poll runs, so the thread never flickers. */
export function useMessages(conversationId: string | null) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["chat", "messages", conversationId],
    queryFn: () =>
      apiFetch<MessagePage>(
        `/api/v1/chat/conversations/${conversationId}/messages${buildQuery({ limit: 200 })}`,
      ),
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat", "messages", conversationId] });
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
