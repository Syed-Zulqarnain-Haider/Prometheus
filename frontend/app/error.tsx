"use client";

import { useEffect } from "react";

/** Route-segment error boundary (App Router). Surfaces a friendly card instead of a blank
 * screen, logs the error (Sentry-ready), and lets the user retry. `digest` correlates with
 * the server log for this render. */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Central place to report UI errors. Wire a browser error tracker here when configured.
    console.error("Unhandled UI error", error);
  }, [error]);

  return (
    <main className="flex min-h-[60vh] items-center justify-center p-4">
      <div className="w-full max-w-md rounded-lg border bg-card p-8 text-center shadow-sm">
        <h1 className="text-xl font-semibold tracking-tight">Something went wrong</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          An unexpected error occurred while rendering this page. You can try again.
        </p>
        {error.digest && (
          <p className="mt-2 text-xs text-muted-foreground">Reference: {error.digest}</p>
        )}
        <div className="mt-6 flex justify-center gap-2">
          <button
            onClick={reset}
            className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90"
          >
            Try again
          </button>
        </div>
      </div>
    </main>
  );
}
