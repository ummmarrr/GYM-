import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUp, Bot, LifeBuoy, Lock, MessageCircle, Sparkles, X } from "lucide-react";

import { homeFor, useAuth } from "../context/AuthContext";
import { api, ApiError } from "../lib/api";
import type { ChatAction } from "../lib/api";
import { Alert, Button } from "./ui";

interface Bubble {
  id: number;
  from: "you" | "fitbot";
  text: string;
  sources?: string[];
  handoff?: boolean;
  action?: ChatAction;
}

const GREETING: Bubble = {
  id: 0,
  from: "fitbot",
  text:
    "Hi, I'm FitBot. Ask me about training, yoga, MMA, our packages or your own plan. " +
    "I never ask for your password here.",
};

const PROMPTS = [
  "What packages do you have?",
  "Give me a beginner push day",
  "How do I improve my flexibility?",
];

/** Signing in from inside the chat, without ever putting a password in the transcript. */
function SecureAuthCard({ mode, onDone }: { mode: "login" | "signup"; onDone: () => void }) {
  const { signIn, signUp } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") await signIn(email, password);
      else await signUp({ email, full_name: fullName, password });
      onDone();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not complete that. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="animate-pop rounded-2xl border border-volt-500/30 bg-ink-900 p-4"
    >
      <p className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-volt-400">
        <Lock className="h-3.5 w-3.5" aria-hidden />
        Secure {mode === "login" ? "sign in" : "sign up"}
      </p>

      <div className="space-y-2.5">
        {mode === "signup" && (
          <input
            className="input"
            placeholder="Full name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            required
            minLength={2}
            autoComplete="name"
          />
        )}
        <input
          className="input"
          type="email"
          placeholder="Email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="email"
        />
        <input
          className="input"
          type="password"
          placeholder={mode === "signup" ? "Password (min 8 characters)" : "Password"}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          minLength={8}
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
        />
        {error && <Alert kind="error" message={error} />}
        <Button type="submit" busy={busy} className="w-full">
          {mode === "login" ? "Sign in" : "Create account"}
        </Button>
      </div>

      <p className="mt-2.5 text-[11px] leading-relaxed text-slate-500">
        This form posts straight to the Master GYM API. Your password is never part of the chat.
      </p>
    </form>
  );
}

export default function FitBotWidget() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [bubbles, setBubbles] = useState<Bubble[]>([GREETING]);
  const [draft, setDraft] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [thinking, setThinking] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "signup" | null>(null);

  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const nextId = useRef(1);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [bubbles, open, thinking, authMode]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const push = (bubble: Omit<Bubble, "id">) =>
    setBubbles((current) => [...current, { ...bubble, id: nextId.current++ }]);

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || thinking) return;

    push({ from: "you", text: message });
    setDraft("");
    setThinking(true);
    setAuthMode(null);

    try {
      const reply = await api.chat(message, conversationId);
      setConversationId(reply.conversation_id);
      push({
        from: "fitbot",
        text: reply.answer,
        sources: reply.sources.map((source) =>
          source.page ? `${source.source} p.${source.page}` : source.source,
        ),
        handoff: reply.needs_human_handoff,
        action: reply.action,
      });
      if (reply.action === "login" || reply.action === "signup") setAuthMode(reply.action);
    } catch (caught) {
      push({
        from: "fitbot",
        text:
          caught instanceof ApiError
            ? caught.message
            : "I could not reach the gym just now. Please try again in a moment.",
      });
    } finally {
      setThinking(false);
    }
  };

  const onAuthDone = async () => {
    setAuthMode(null);
    await refresh();
    push({
      from: "fitbot",
      text: "You're signed in. Ask me again and I'll pull up your details.",
    });
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label="Chat with FitBot"
        className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 rounded-full bg-volt-400 px-5 py-3.5
                   font-semibold text-ink-950 shadow-2xl shadow-volt-500/20 transition hover:bg-volt-500
                   focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-volt-400"
      >
        <MessageCircle className="h-5 w-5" aria-hidden />
        Ask FitBot
      </button>
    );
  }

  return (
    <div
      role="dialog"
      aria-label="FitBot chat"
      className="animate-pop fixed bottom-6 right-6 z-50 flex h-[min(38rem,calc(100vh-3rem))] w-[min(24rem,calc(100vw-3rem))]
                 flex-col overflow-hidden rounded-2xl border border-ink-700 bg-ink-900 shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-ink-800 bg-ink-850 px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-volt-400 text-ink-950">
            <Bot className="h-5 w-5" aria-hidden />
          </span>
          <div className="leading-tight">
            <p className="text-sm font-bold text-white">FitBot</p>
            <p className="text-[11px] text-slate-400">
              {user ? `Coaching ${user.full_name.split(" ")[0]}` : "Reception · Gym · Yoga · MMA"}
            </p>
          </div>
        </div>
        <button
          onClick={() => setOpen(false)}
          aria-label="Close chat"
          className="rounded-lg p-1.5 text-slate-400 transition hover:bg-ink-800 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {bubbles.map((bubble) => (
          <div
            key={bubble.id}
            className={`flex ${bubble.from === "you" ? "justify-end" : "justify-start"}`}
          >
            <div
              data-testid="fitbot-message"
              className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                bubble.from === "you"
                  ? "bg-volt-400 text-ink-950"
                  : "border border-ink-700 bg-ink-850 text-slate-200"
              }`}
            >
              {bubble.text}

              {bubble.handoff && (
                <p className="mt-2 flex items-center gap-1.5 text-xs text-amber-300">
                  <LifeBuoy className="h-3.5 w-3.5" aria-hidden />
                  Flagged for a human trainer
                </p>
              )}

              {bubble.sources && bubble.sources.length > 0 && (
                <p className="mt-2 border-t border-ink-700 pt-2 text-[11px] text-slate-500">
                  From: {Array.from(new Set(bubble.sources)).join(" · ")}
                </p>
              )}

              {bubble.action === "upgrade" && (
                <Button
                  className="mt-2.5 w-full"
                  onClick={() => {
                    setOpen(false);
                    navigate("/packages");
                  }}
                >
                  <Sparkles className="h-4 w-4" aria-hidden />
                  See upgrade options
                </Button>
              )}
            </div>
          </div>
        ))}

        {authMode && <SecureAuthCard mode={authMode} onDone={onAuthDone} />}

        {thinking && (
          <div className="flex gap-1.5 px-1" aria-label="FitBot is typing">
            {[0, 150, 300].map((delay) => (
              <span
                key={delay}
                className="h-2 w-2 animate-bounce rounded-full bg-slate-600"
                style={{ animationDelay: `${delay}ms` }}
              />
            ))}
          </div>
        )}

        {bubbles.length === 1 && !thinking && (
          <div className="flex flex-wrap gap-2 pt-1">
            {PROMPTS.map((prompt) => (
              <button
                key={prompt}
                onClick={() => void send(prompt)}
                className="rounded-full border border-ink-700 px-3 py-1.5 text-xs text-slate-300
                           transition hover:border-volt-500/50 hover:text-white"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}

        <div ref={endRef} />
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send(draft);
        }}
        className="flex items-center gap-2 border-t border-ink-800 bg-ink-850 px-3 py-3"
      >
        <input
          ref={inputRef}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask FitBot anything…"
          maxLength={4000}
          className="input flex-1"
          aria-label="Message FitBot"
        />
        <Button type="submit" disabled={!draft.trim() || thinking} aria-label="Send" className="px-3">
          <ArrowUp className="h-4 w-4" aria-hidden />
        </Button>
      </form>

      {user && (
        <button
          onClick={() => {
            setOpen(false);
            navigate(homeFor(user.role));
          }}
          className="border-t border-ink-800 py-2 text-[11px] text-slate-500 transition hover:text-slate-300"
        >
          Open my dashboard
        </button>
      )}
    </div>
  );
}
