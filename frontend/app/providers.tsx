"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState } from "react";

import { ApiError } from "@/lib/api-client";
import { AuthProvider } from "@/lib/auth-context";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            // Retry transient failures (429 rate-limit, 5xx) with backoff;
            // never retry deterministic 4xx (e.g. a 400 forbidden-metric).
            retry: (failureCount, error) => {
              if (error instanceof ApiError) {
                if (error.status === 429 || error.status >= 500) return failureCount < 3;
                return false;
              }
              return failureCount < 2;
            },
            retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
          },
        },
      }),
  );

  return (
    <ThemeProvider attribute="data-theme" defaultTheme="dark" enableSystem>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
