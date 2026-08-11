"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiFetch, buildQuery } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { getFirebaseAuth } from "@/lib/firebase";

/* Hooks for the profile page, the people directory and presence. Kept OUT of api-hooks.ts
 * on purpose: that file has drifted between this tree and the deployed one, so shared new
 * code lives in new files that can ship whole to both. */

export type PresenceStatus = "online" | "away" | "offline";

export interface Profile {
  user_id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  display_name: string | null;
  job_title: string | null;
  phone: string | null;
  timezone: string | null;
  has_avatar: boolean;
  roles: string[];
  last_login_at: string | null;
  last_seen_at: string | null;
  created_at: string;
}

export interface ProfileUpdate {
  first_name: string | null;
  last_name: string | null;
  job_title: string | null;
  phone: string | null;
  timezone: string | null;
}

export interface Person {
  user_id: string;
  email: string;
  display_name: string | null;
  first_name: string | null;
  last_name: string | null;
  job_title: string | null;
  roles: string[];
  has_avatar: boolean;
  status: PresenceStatus;
  last_seen_at: string | null;
  last_login_at: string | null;
}

export interface PeopleList {
  people: Person[];
  online: number;
}

export function useProfile() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["profile"],
    queryFn: () => apiFetch<Profile>("/api/v1/me/profile"),
    enabled: Boolean(user),
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProfileUpdate) =>
      apiFetch<Profile>("/api/v1/me/profile", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profile"] });
      queryClient.invalidateQueries({ queryKey: ["people"] });
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

export function useUploadAvatar() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      // Multipart upload - Content-Type must NOT be set by hand, the browser writes the
      // boundary itself, so this cannot go through apiFetch (which forces JSON).
      const auth = getFirebaseAuth().currentUser;
      const token = auth ? await auth.getIdToken() : "";
      const body = new FormData();
      body.append("file", file);
      const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
      const response = await fetch(`${base}/api/v1/me/profile/avatar`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body,
      });
      if (!response.ok) {
        let message = "Upload failed";
        try {
          const parsed = (await response.json()) as { error?: { message?: string } };
          message = parsed.error?.message ?? message;
        } catch {
          /* non-JSON error body */
        }
        throw new Error(message);
      }
      return (await response.json()) as { has_avatar: boolean };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profile"] });
      queryClient.invalidateQueries({ queryKey: ["people"] });
      queryClient.invalidateQueries({ queryKey: ["avatar"] });
    },
  });
}

export function useDeleteAvatar() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>("/api/v1/me/profile/avatar", { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profile"] });
      queryClient.invalidateQueries({ queryKey: ["people"] });
      queryClient.invalidateQueries({ queryKey: ["avatar"] });
    },
  });
}

/** The people directory with live presence. Polls every 30s and on focus, so the online
 *  dots stay honest without hammering the API. */
export function usePeople(query?: string) {
  const { user } = useAuth();
  const params = buildQuery({ q: query ?? "" });
  return useQuery({
    queryKey: ["people", query ?? ""],
    queryFn: () => apiFetch<PeopleList>(`/api/v1/me/people${params}`),
    enabled: Boolean(user),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });
}

/** An avatar image as a Blob. <img src> cannot carry the Authorization header, so the
 *  bytes are fetched with the token; the COMPONENT turns the blob into an object URL and
 *  revokes it on unmount - minting the URL here leaked one per avatar per refetch, since
 *  nothing ever called revokeObjectURL. */
export function useAvatarBlob(userId: string | null | undefined, hasAvatar: boolean) {
  return useQuery({
    queryKey: ["avatar", userId],
    enabled: Boolean(userId) && hasAvatar,
    staleTime: 5 * 60 * 1000,
    queryFn: async () => {
      const auth = getFirebaseAuth().currentUser;
      const token = auth ? await auth.getIdToken() : "";
      const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
      const response = await fetch(`${base}/api/v1/me/people/${userId}/avatar`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) return null;
      return await response.blob();
    },
  });
}

/** Debounce a fast-changing value (search inputs) so each keystroke does not become an
 *  API call and a permanent cache entry. */
export function useDebounced<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

/** Initials for the fallback avatar - "Zulqarnain Haider" -> "ZH". */
export function initialsOf(person: {
  display_name?: string | null;
  email?: string;
}): string {
  const name = person.display_name?.trim();
  if (name) {
    const parts = name.split(/\s+/);
    return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
  }
  return (person.email?.[0] ?? "?").toUpperCase();
}
