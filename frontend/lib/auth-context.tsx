"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  GoogleAuthProvider,
  type User,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut as firebaseSignOut,
} from "firebase/auth";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

import { getFirebaseAuth } from "@/lib/firebase";

interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const queryClient = useQueryClient();
  // Track the previously-seen identity so we can wipe the cache whenever it changes.
  const prevUid = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    const auth = getFirebaseAuth();
    const unsubscribe = onAuthStateChanged(auth, (nextUser) => {
      const nextUid = nextUser?.uid ?? null;
      // SECURITY: on ANY identity change (sign-out, or a different account signing in on a
      // shared machine) drop every cached query. Without this, TanStack Query's global keys
      // would serve the previous user's cached data to the next user until it went stale.
      if (prevUid.current !== undefined && prevUid.current !== nextUid) {
        queryClient.clear();
      }
      prevUid.current = nextUid;
      setUser(nextUser);
      setLoading(false);
    });
    return unsubscribe;
  }, [queryClient]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      // Both sign-in methods only AUTHENTICATE via Firebase. Authorization is
      // unchanged: every backend route still requires a provisioned user (matched
      // by Firebase UID) — an unprovisioned account gets no data and no role.
      signIn: async (email, password) => {
        await signInWithEmailAndPassword(getFirebaseAuth(), email, password);
      },
      signInWithGoogle: async () => {
        await signInWithPopup(getFirebaseAuth(), new GoogleAuthProvider());
      },
      signOut: async () => {
        await firebaseSignOut(getFirebaseAuth());
      },
    }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
