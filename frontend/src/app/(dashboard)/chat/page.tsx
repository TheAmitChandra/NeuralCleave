"use client";

import {
  useEffect,
  useRef,
  useState,
  FormEvent,
  KeyboardEvent,
  useCallback,
} from "react";
import {
  Send,
  Loader2,
  Terminal,
  Download,
  Plus,
  Trash2,
  PenSquare,
} from "lucide-react";
import type { ChatMessage, ChatSession } from "@/store/chat";
import { gatewayWS, type WSMessage } from "@/lib/websocket";
import { useChatStore } from "@/store/chat";
import api from "@/lib/api";
import {
  matchCommands,
  findCommand,
  buildHelpText,
  type Command,
} from "@/lib/commands";

// ---------------------------------------------------------------------------
// Markdown renderer
// ---------------------------------------------------------------------------

function renderMarkdown(text: string): React.ReactNode {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trimStart().startsWith("```")) {
      const lang = line.replace(/^`+/, "").trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trimStart().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      elements.push(
        <pre
          key={i}
          className="my-3 overflow-x-auto rounded-xl bg-black/60 border border-white/[0.08] p-4 text-xs text-violet-300 font-mono"
          data-lang={lang || undefined}
        >
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      i++;
      continue;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const cls =
        level === 1
          ? "text-base font-bold mt-3 mb-1 text-white"
          : level === 2
            ? "text-sm font-semibold mt-2 mb-0.5 text-slate-100"
            : "text-sm font-medium mt-1 text-slate-200";
      elements.push(
        <p key={i} className={cls}>
          {inlineMarkdown(headingMatch[2])}
        </p>
      );
      i++;
      continue;
    }

    if (/^[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s/, ""));
        i++;
      }
      elements.push(
        <ul key={i} className="my-1.5 list-disc pl-5 space-y-0.5">
          {items.map((item, j) => (
            <li key={j} className="text-sm text-slate-300 leading-relaxed">
              {inlineMarkdown(item)}
            </li>
          ))}
        </ul>
      );
      continue;
    }

    if (line.trim() === "") {
      elements.push(<div key={i} className="h-1.5" />);
      i++;
      continue;
    }

    elements.push(
      <p key={i} className="text-sm leading-relaxed text-slate-200">
        {inlineMarkdown(line)}
      </p>
    );
    i++;
  }

  return <>{elements}</>;
}

function inlineMarkdown(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**"))
      return (
        <strong key={i} className="font-semibold text-white">
          {part.slice(2, -2)}
        </strong>
      );
    if (part.startsWith("*") && part.endsWith("*"))
      return <em key={i}>{part.slice(1, -1)}</em>;
    if (part.startsWith("`") && part.endsWith("`"))
      return (
        <code
          key={i}
          className="rounded-md bg-black/60 border border-white/[0.08] px-1.5 py-0.5 font-mono text-xs text-violet-300"
        >
          {part.slice(1, -1)}
        </code>
      );
    return part;
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatRelativeDate(ts: number): string {
  const d = new Date(ts * 1000);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const msgDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round(
    (today.getTime() - msgDay.getTime()) / (1000 * 60 * 60 * 24)
  );
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function formatDaySeparator(ts: number): string {
  const d = new Date(ts * 1000);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const msgDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round(
    (today.getTime() - msgDay.getTime()) / (1000 * 60 * 60 * 24)
  );
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
}

function isSameDay(a: number, b: number): boolean {
  const da = new Date(a * 1000);
  const db = new Date(b * 1000);
  return (
    da.getFullYear() === db.getFullYear() &&
    da.getMonth() === db.getMonth() &&
    da.getDate() === db.getDate()
  );
}

function exportChatAsMarkdown(messages: ChatMessage[]): void {
  const lines: string[] = ["# NeuralCleave Chat Export", `> Exported ${new Date().toLocaleString()}`, ""];
  for (const m of messages) {
    const time = new Date(m.timestamp * 1000).toLocaleTimeString();
    lines.push(
      m.role === "user" ? `**You** *(${time})*` :
      m.role === "agent" ? `**NeuralCleave** *(${time})*` :
      `**Error** *(${time})*`
    );
    lines.push("", m.text, "");
  }
  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `neuralcleave-chat-${new Date().toISOString().slice(0, 10)}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Command palette
// ---------------------------------------------------------------------------

function CommandPalette({
  matches,
  selectedIdx,
  onSelect,
}: {
  matches: Command[];
  selectedIdx: number;
  onSelect: (cmd: Command) => void;
}) {
  if (matches.length === 0) return null;
  return (
    <div className="absolute bottom-full left-0 right-0 z-20 mb-2 rounded-2xl border border-white/[0.08] bg-[#0f0f18]/95 backdrop-blur-2xl shadow-2xl shadow-black/60 overflow-hidden">
      {matches.map((cmd, idx) => (
        <button
          key={cmd.trigger}
          type="button"
          onClick={() => onSelect(cmd)}
          className={`flex w-full items-center gap-3 px-4 py-3 text-left text-sm transition-colors ${
            idx === selectedIdx
              ? "bg-violet-600/20 text-white"
              : "text-slate-400 hover:bg-white/[0.04]"
          }`}
        >
          <Terminal className="h-3.5 w-3.5 shrink-0 opacity-40" />
          <span className="font-mono font-medium">{cmd.trigger}</span>
          {cmd.args && <span className="font-mono text-xs opacity-40">{cmd.args}</span>}
          <span className="ml-auto text-xs opacity-40">{cmd.description}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sessions sidebar
// ---------------------------------------------------------------------------

function SessionsSidebar({
  sessions,
  activeSessionId,
  onNew,
  onSwitch,
  onDelete,
}: {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onNew: () => void;
  onSwitch: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <aside className="hidden md:flex w-[220px] shrink-0 flex-col bg-[#080810] border-r border-white/[0.05]">
      <div className="p-3 pt-4">
        <button
          onClick={onNew}
          className="w-full flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-500 hover:bg-white/[0.05] hover:text-slate-200 transition-all duration-150"
        >
          <PenSquare className="h-3.5 w-3.5 shrink-0" />
          New chat
        </button>
      </div>

      <div className="px-2 mb-1.5">
        <p className="px-3 text-[10px] font-semibold uppercase tracking-widest text-white/[0.15]">
          Recents
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-0.5">
        {sessions.length === 0 ? (
          <p className="px-3 py-6 text-[11px] text-white/20 text-center leading-relaxed">
            No conversations yet
          </p>
        ) : (
          sessions.map((session) => (
            <div key={session.id} className="group relative">
              <button
                onClick={() => onSwitch(session.id)}
                className={`w-full flex flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left transition-all duration-150 pr-7 ${
                  session.id === activeSessionId
                    ? "bg-white/[0.08] text-white"
                    : "text-white/30 hover:bg-white/[0.04] hover:text-white/70"
                }`}
              >
                <span className="line-clamp-1 text-[12px] font-medium leading-snug w-full">
                  {session.title}
                </span>
                <span className="text-[10px] opacity-40 mt-0.5">
                  {formatRelativeDate(session.updatedAt)}
                </span>
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(session.id); }}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center justify-center rounded-md p-1 text-white/20 hover:text-rose-400 transition-colors"
                title="Delete"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------

function MessageBubble({ m }: { m: ChatMessage }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[78%]">
          <div className="rounded-2xl rounded-br-sm bg-violet-600 px-4 py-3 text-sm text-white leading-relaxed shadow-lg shadow-violet-950/40">
            {m.text}
          </div>
          <p className="mt-1 text-right text-[10px] text-white/[0.18]">
            {formatTime(m.timestamp)}
          </p>
        </div>
      </div>
    );
  }

  if (m.role === "error") {
    return (
      <div className="flex gap-3">
        <div className="shrink-0 mt-0.5 h-7 w-7 rounded-lg bg-rose-950/40 border border-rose-800/30 flex items-center justify-center text-[9px] font-bold text-rose-400">!</div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-rose-400 leading-relaxed">{m.text}</p>
          <p className="mt-1 text-[10px] text-white/[0.15]">{formatTime(m.timestamp)}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.png" alt="" className="shrink-0 mt-0.5 h-7 w-7 rounded-lg object-cover opacity-90" />
      <div className="flex-1 min-w-0">
        <div className="text-sm text-slate-200 leading-relaxed">
          {renderMarkdown(m.text)}
        </div>
        <p className="mt-1 text-[10px] text-white/[0.18]">{formatTime(m.timestamp)}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Suggestion chips
// ---------------------------------------------------------------------------

const SUGGESTIONS = [
  { label: "Your capabilities", text: "What can you do? Give me a quick overview." },
  { label: "Set up Telegram", text: "How do I set up a Telegram channel integration?" },
  { label: "How Memory works", text: "Explain how the Memory system works." },
  { label: "Available commands", text: "/help" },
];

// ---------------------------------------------------------------------------
// Main chat page
// ---------------------------------------------------------------------------

export default function ChatPage() {
  const {
    sessions,
    activeSessionId,
    pendingId,
    newSession,
    switchSession,
    deleteSession,
    addMessage,
    upsertAgentChunk,
    finalizeMessage,
    addErrorMessage,
    setPendingId,
    clearMessages,
  } = useChatStore();

  const messages = sessions.find((s) => s.id === activeSessionId)?.messages ?? [];

  const [input, setInput] = useState("");
  const [cmdMatches, setCmdMatches] = useState<Command[]>([]);
  const [cmdIdx, setCmdIdx] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, []);

  useEffect(() => {
    gatewayWS.connect();
    return () => { gatewayWS.disconnect(); };
  }, []);

  useEffect(() => {
    const unsubscribe = gatewayWS.subscribe((msg: WSMessage) => {
      if (msg.type === "message_chunk" && msg.message_id && msg.delta) {
        upsertAgentChunk(`${msg.message_id}-reply`, msg.delta, Date.now() / 1000);
      } else if (msg.type === "message_done" && msg.message_id) {
        setPendingId(pendingId === msg.message_id ? null : pendingId);
        finalizeMessage(`${msg.message_id}-reply`, msg.text ?? "", msg.timestamp ?? Date.now() / 1000);
      } else if (msg.type === "error" && msg.message_id) {
        setPendingId(pendingId === msg.message_id ? null : pendingId);
        addErrorMessage(`${msg.message_id}-error`, msg.message ?? "Something went wrong.");
      }
    });
    return unsubscribe;
  }, [pendingId, upsertAgentChunk, finalizeMessage, addErrorMessage, setPendingId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (input.startsWith("/")) {
      setCmdMatches(matchCommands(input.split(" ")[0]));
      setCmdIdx(0);
    } else {
      setCmdMatches([]);
    }
  }, [input]);

  function applyCommand(cmd: Command) {
    setInput(cmd.args ? `${cmd.trigger} ` : cmd.trigger);
    setCmdMatches([]);
    textareaRef.current?.focus();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (cmdMatches.length > 0) {
      if (e.key === "ArrowDown") { e.preventDefault(); setCmdIdx((p) => (p + 1) % cmdMatches.length); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setCmdIdx((p) => (p - 1 + cmdMatches.length) % cmdMatches.length); return; }
      if (e.key === "Tab" || e.key === "Enter") { e.preventDefault(); applyCommand(cmdMatches[cmdIdx]); return; }
      if (e.key === "Escape") { setCmdMatches([]); return; }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void doSubmit();
    }
  }

  async function doSubmit(override?: string) {
    if (!override && cmdMatches.length > 0) { applyCommand(cmdMatches[cmdIdx]); return; }
    const text = (override ?? input).trim();
    if (!text || pendingId) return;

    const cmd = findCommand(text);
    if (cmd?.scope === "local") {
      setInput("");
      setCmdMatches([]);
      if (cmd.name === "reset") {
        clearMessages();
        addMessage({ id: crypto.randomUUID(), role: "agent", text: "Conversation cleared.", timestamp: Date.now() / 1000 });
      } else if (cmd.name === "help") {
        addMessage({ id: crypto.randomUUID(), role: "agent", text: buildHelpText(), timestamp: Date.now() / 1000 });
      } else if (cmd.name === "info") {
        void api
          .get<{ version: string; uptime_seconds: number; active_sessions: number; runtime_available: boolean; init_phase?: string }>("/status")
          .then(({ data: s }) => {
            const mins = Math.floor(s.uptime_seconds / 60);
            const secs = Math.floor(s.uptime_seconds % 60);
            addMessage({
              id: crypto.randomUUID(), role: "agent",
              text: [`**NeuralCleave v${s.version}**`, `Uptime: ${mins}m ${secs}s`, `Runtime: ${s.runtime_available ? "ready" : (s.init_phase ?? "initializing")}`, `Sessions: ${s.active_sessions}`].join("\n"),
              timestamp: Date.now() / 1000,
            });
          })
          .catch(() => addMessage({ id: crypto.randomUUID(), role: "error", text: "Cannot reach gateway — check that the backend is running.", timestamp: Date.now() / 1000 }));
      } else if (cmd.name === "privacy") {
        const arg = text.split(" ")[1]?.toLowerCase();
        if (arg !== "on" && arg !== "off") {
          addMessage({ id: crypto.randomUUID(), role: "agent", text: "Usage: `/privacy on` or `/privacy off`\nPrivacy mode routes all LLM requests to your local Ollama instance.", timestamp: Date.now() / 1000 });
        } else {
          const enable = arg === "on";
          void api.post("/settings/model", { privacy_mode: enable })
            .then(() => addMessage({ id: crypto.randomUUID(), role: "agent", text: enable ? "Privacy mode **enabled** — all requests routed to local Ollama." : "Privacy mode **disabled** — automatic cloud/local routing restored.", timestamp: Date.now() / 1000 }))
            .catch(() => addMessage({ id: crypto.randomUUID(), role: "error", text: "Failed to update privacy mode — gateway unreachable.", timestamp: Date.now() / 1000 }));
        }
      }
      return;
    }

    const id = crypto.randomUUID();
    addMessage({ id, role: "user", text, timestamp: Date.now() / 1000 });
    setInput("");
    setCmdMatches([]);
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const sent = gatewayWS.send({ type: "message", id, text });
    if (!sent) {
      addErrorMessage(`${id}-error`, "Not connected to the gateway. Check the WebSocket URL in Settings.");
      return;
    }
    setPendingId(id);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    void doSubmit();
  }

  function sendSuggestion(text: string) {
    void doSubmit(text);
  }

  const replyHasStarted =
    pendingId !== null && messages.some((m) => m.id === `${pendingId}-reply`);

  return (
    <div className="flex h-full -m-4 sm:-m-6 overflow-hidden bg-[#030308]">
      <SessionsSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onNew={newSession}
        onSwitch={switchSession}
        onDelete={deleteSession}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            /* ── Premium empty state ── */
            <div className="flex h-full flex-col items-center justify-center gap-7 px-6 text-center">
              {/* Logo with glow */}
              <div className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src="/logo.png"
                  alt="NeuralCleave"
                  className="h-16 w-16 rounded-2xl relative z-10"
                  style={{ filter: "drop-shadow(0 0 32px rgba(124,58,237,0.55))" }}
                />
                <div className="absolute inset-0 rounded-2xl bg-violet-600/20 blur-2xl scale-150" />
              </div>

              <div>
                <h2 className="text-[22px] font-semibold tracking-tight text-white">
                  What can I help with?
                </h2>
                <p className="mt-1.5 text-[13px] text-white/30">
                  Type a message below, or start from a suggestion
                </p>
              </div>

              {/* Suggestion chips */}
              <div className="flex flex-wrap gap-2 justify-center max-w-md">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.label}
                    onClick={() => sendSuggestion(s.text)}
                    className="rounded-xl border border-white/[0.07] bg-white/[0.03] px-4 py-2.5 text-[13px] text-white/50 hover:bg-white/[0.07] hover:text-white/90 hover:border-white/[0.12] transition-all duration-150"
                  >
                    {s.label}
                  </button>
                ))}
              </div>

              {/* Mobile new chat */}
              <button
                onClick={newSession}
                className="flex md:hidden items-center gap-2 rounded-xl border border-white/[0.07] bg-white/[0.03] px-4 py-2 text-sm text-white/40 hover:text-white/70 hover:bg-white/[0.06] transition-colors"
              >
                <Plus className="h-4 w-4" /> New chat
              </button>
            </div>
          ) : (
            /* ── Messages list ── */
            <div className="max-w-[680px] mx-auto w-full px-4 sm:px-6 py-8 space-y-6">
              {messages.map((m, idx) => {
                const showSeparator = idx === 0 || !isSameDay(messages[idx - 1].timestamp, m.timestamp);
                return (
                  <div key={m.id}>
                    {showSeparator && (
                      <div className="flex items-center gap-3 mb-4">
                        <div className="flex-1 h-px bg-white/[0.05]" />
                        <span className="text-[10px] text-white/[0.2] uppercase tracking-widest">
                          {formatDaySeparator(m.timestamp)}
                        </span>
                        <div className="flex-1 h-px bg-white/[0.05]" />
                      </div>
                    )}
                    <MessageBubble m={m} />
                  </div>
                );
              })}

              {/* Typing / thinking indicator */}
              {pendingId && !replyHasStarted && (
                <div className="flex gap-3">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/logo.png" alt="" className="shrink-0 mt-0.5 h-7 w-7 rounded-lg object-cover opacity-60" />
                  <div className="flex items-center gap-1 pt-1.5">
                    {[0, 150, 300].map((delay) => (
                      <span
                        key={delay}
                        className="h-1.5 w-1.5 rounded-full bg-violet-500/70 animate-bounce"
                        style={{ animationDelay: `${delay}ms`, animationDuration: "1s" }}
                      />
                    ))}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* ── Glass input bar ── */}
        <div className="shrink-0 px-4 sm:px-6 pb-5 pt-2">
          <div className="max-w-[680px] mx-auto w-full">
            <div className="relative">
              <CommandPalette matches={cmdMatches} selectedIdx={cmdIdx} onSelect={applyCommand} />
              <form onSubmit={handleSubmit}>
                <div className="rounded-2xl border border-white/[0.07] bg-white/[0.04] backdrop-blur-2xl px-4 pt-4 pb-3 focus-within:border-violet-500/25 focus-within:bg-white/[0.055] transition-all duration-200 shadow-2xl shadow-black/60">
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => { setInput(e.target.value); autoResize(); }}
                    onKeyDown={handleKeyDown}
                    placeholder="Message NeuralCleave…"
                    disabled={!!pendingId}
                    rows={1}
                    className="w-full resize-none bg-transparent text-[14px] text-white placeholder:text-white/20 outline-none disabled:opacity-40 leading-relaxed"
                    style={{ maxHeight: "160px", overflowY: "auto" }}
                  />
                  <div className="mt-3 flex items-center justify-between">
                    <div className="flex items-center gap-0.5">
                      {messages.length > 0 && (
                        <button
                          type="button"
                          onClick={() => exportChatAsMarkdown(messages)}
                          title="Export as Markdown"
                          className="flex items-center gap-1.5 rounded-lg p-2 text-white/20 hover:bg-white/[0.05] hover:text-white/50 transition-colors"
                        >
                          <Download className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                    <div className="flex items-center gap-2.5">
                      <span className="text-[11px] text-white/[0.12] select-none">
                        Shift+Enter for new line
                      </span>
                      <button
                        type="submit"
                        disabled={!input.trim() || !!pendingId}
                        className="flex h-8 w-8 items-center justify-center rounded-xl bg-violet-600 text-white transition-all hover:bg-violet-500 disabled:opacity-20 disabled:cursor-not-allowed shadow-lg shadow-violet-950/50"
                      >
                        {pendingId && !replyHasStarted ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Send className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              </form>
              <p className="mt-2 text-center text-[11px] text-white/[0.1]">
                NeuralCleave can make mistakes. Verify important information.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
