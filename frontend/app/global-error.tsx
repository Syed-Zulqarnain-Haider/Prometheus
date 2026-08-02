"use client";

import { useEffect } from "react";

/** Last-resort boundary for errors thrown in the root layout itself. It replaces the whole
 * document, so it renders its own <html>/<body> and uses inline styles (the app CSS may not
 * be present here). Logs the error (Sentry-ready) and offers a reload. */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Fatal UI error", error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "system-ui, sans-serif",
          background: "#0b0b0c",
          color: "#e5e5e5",
        }}
      >
        <div style={{ maxWidth: 420, padding: 32, textAlign: "center" }}>
          <h1 style={{ fontSize: 20, fontWeight: 600 }}>Something went wrong</h1>
          <p style={{ marginTop: 8, fontSize: 14, color: "#a1a1aa" }}>
            The application hit an unexpected error. Please reload the page.
          </p>
          {error.digest && (
            <p style={{ marginTop: 8, fontSize: 12, color: "#71717a" }}>
              Reference: {error.digest}
            </p>
          )}
          <button
            onClick={reset}
            style={{
              marginTop: 24,
              borderRadius: 6,
              border: "none",
              padding: "8px 16px",
              fontSize: 14,
              background: "#6366f1",
              color: "white",
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
