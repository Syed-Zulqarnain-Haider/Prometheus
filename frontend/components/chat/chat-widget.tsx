"use client";

import { Bot, Loader2, Send, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { type ChatMessage, useChatStatus, useSendChat } from "@/lib/api-hooks";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

// A local UI message may be flagged as a client-side error bubble; those are shown but never
// sent back to the model (they aren't real assistant turns).
type UiMessage = ChatMessage & { error?: boolean };

// Backend caps a transcript at 20 messages — keep the sent history comfortably under that.
const MAX_SENT_TURNS = 18;

const GREETING: UiMessage = {
  role: "assistant",
  content:
    "Hi! Ask me about your performance data — e.g. “What was total revenue last month?” " +
    "or “Top 5 apps by ROAS in June”. I only ever see the data you're allowed to see.",
};

const SUGGESTIONS = [
  "What was total revenue last 30 days?",
  "Top 5 apps by profit this month",
  "How did UA spend change vs the prior period?",
];

/** Floating "ask your data" assistant. Renders only when an admin has enabled it and the
 * backend is configured; otherwise it stays completely hidden. */
export function ChatWidget() {
  const status = useChatStatus();
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<UiMessage[]>([GREETING]);
  const [provider, setProvider] = useState<string>("");
  const send = useSendChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const providers = useMemo(() => status.data?.providers ?? [], [status.data?.providers]);

  useEffect(() => setMounted(true), []);

  // Default the picker to the first available provider once status resolves.
  useEffect(() => {
    if (!provider && providers.length > 0) setProvider(providers[0].id);
  }, [provider, providers]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, send.isPending]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  if (!mounted || !status.data?.available) return null;

  async function submit(question: string) {
    const q = question.trim();
    if (!q || send.isPending) return;
    const next: UiMessage[] = [...messages, { role: "user", content: q }];
    setMessages(next);
    setInput("");
    try {
      // Send only REAL turns: drop the local greeting and any prior error bubbles (they aren't
      // genuine assistant turns), strip the UI-only `error` flag, and cap the history length so
      // the request stays within the backend's transcript limit and payload/token cost is bounded.
      const transcript = next
        .filter((m) => m !== GREETING && !m.error)
        .slice(-MAX_SENT_TURNS)
        .map(({ role, content }) => ({ role, content }));
      const res = await send.mutateAsync({ messages: transcript, provider: provider || undefined });
      setMessages((prev) => [...prev, { role: "assistant", content: res.answer }]);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Something went wrong. Please try again in a moment.";
      setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ ${msg}`, error: true }]);
    }
  }

  const panel = (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-3 print:hidden">
      {open && (
        <div className="flex h-[min(32rem,80vh)] w-[min(24rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border bg-card shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b bg-muted/40 px-4 py-3">
            <div className="flex min-w-0 items-center gap-2">
              <Sparkles className="h-4 w-4 shrink-0 text-primary" />
              <div className="min-w-0">
                <p className="text-sm font-semibold leading-none">Ask your data</p>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Answers respect your access
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {providers.length > 0 && (
                <label className="sr-only" htmlFor="chat-provider">
                  Choose model
                </label>
              )}
              {providers.length > 1 && (
                <select
                  id="chat-provider"
                  aria-label="Choose which LLM answers"
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  className="max-w-[7.5rem] rounded-md border bg-background px-2 py-1 text-xs outline-none focus:ring-2 focus:ring-ring"
                >
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              )}
              {providers.length === 1 && (
                <span className="rounded-md border bg-background px-2 py-1 text-xs text-muted-foreground">
                  {providers[0].label}
                </span>
              )}
              <button
                type="button"
                aria-label="Close assistant"
                className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={() => setOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.map((m, i) => (
              <div
                key={i}
                className={cn("flex gap-2", m.role === "user" ? "justify-end" : "justify-start")}
              >
                {m.role === "assistant" && (
                  <Bot className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
                )}
                <div
                  className={cn(
                    "max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm leading-relaxed",
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-foreground",
                  )}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {send.isPending && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Bot className="h-4 w-4" />
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Looking at the numbers…</span>
              </div>
            )}
            {messages.length === 1 && !send.isPending && (
              <div className="space-y-1.5 pt-1">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void submit(s)}
                    className="block w-full rounded-md border border-dashed px-3 py-1.5 text-left text-xs text-muted-foreground hover:border-solid hover:bg-muted hover:text-foreground"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Composer */}
          <form
            className="flex items-center gap-2 border-t p-3"
            onSubmit={(e) => {
              e.preventDefault();
              void submit(input);
            }}
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={4000}
              placeholder="Ask about revenue, spend, ROAS…"
              className="min-w-0 flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
            <button
              type="submit"
              aria-label="Send"
              disabled={send.isPending || !input.trim()}
              className="rounded-md bg-primary p-2 text-primary-foreground disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      )}

      {/* Launcher */}
      <button
        type="button"
        aria-label={open ? "Close assistant" : "Open the ask-your-data assistant"}
        onClick={() => setOpen((v) => !v)}
        className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition hover:scale-105"
      >
        {open ? <X className="h-5 w-5" /> : <Sparkles className="h-5 w-5" />}
      </button>
    </div>
  );

  return createPortal(panel, document.body);
}
