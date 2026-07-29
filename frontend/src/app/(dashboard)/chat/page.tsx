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
  MessageSquare,
  Send,
  Loader2,
  Terminal,
  Download,
  Plus,
  Trash2,
  Sparkles,
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
          className="my-3 overflow-x-auto rounded-xl bg-black/40 border border-white/10 p-4 text-xs text-violet-300 font-mono"
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
            <li key={j} className="text-sm text-slate-200 leading-relaxed">
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
      <p key={i} className="text-sm leading-relaxed text-slate-100">
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
          className="rounded-md bg-black/50 border border-white/10 px-1.5 py-0.5 font-mono text-xs text-violet-300"
        >
          {part.slice(1, -1)}
        </code>
      );
    return part;
  });
}

// ---------------------------------------------------------------------------
// Date / time helpers
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
  return d.toLocaleDateString([], {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
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
    <div className="absolute bottom-full left-0 right-0 z-20 mb-2 rounded-xl border border-slate-700/80 bg-slate-900 shadow-2xl shadow-black/50 overflow-hidden">
      {matches.map((cmd, idx) => (
        <button
          key={cmd.trigger}
          type="button"
          onClick={() => onSelect(cmd)}
          className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors ${
            idx === selectedIdx
              ? "bg-violet-600 text-white"
              : "text-slate-300 hover:bg-slate-800"
          }`}
        >
          <Terminal className="h-3.5 w-3.5 shrink-0 opacity-50" />
          <span className="font-mono font-medium">{cmd.trigger}</span>
          {cmd.args && (
            <span className="font-mono text-xs opacity-50">{cmd.args}</span>
          )}
          <span className="ml-auto text-xs opacity-50">{cmd.description}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export helper
// ---------------------------------------------------------------------------

function exportChatAsMarkdown(messages: ChatMessage[]): void {
  const lines: string[] = [
    "# NeuralCleave Chat Export",
    `> Exported ${new Date().toLocaleString()}`,
    "",
  ];
  for (const m of messages) {
    const time = new Date(m.timestamp * 1000).toLocaleTimeString();
    lines.push(
      m.role === "user"
        ? `**You** *(${time})*`
        : m.role === "agent"
          ? `**NeuralCleave** *(${time})*`
          : `**Error** *(${time})*`
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
    <aside className="hidden md:flex w-56 shrink-0 flex-col border-r border-slate-800/50 bg-slate-950">
      <div className="p-2.5 border-b border-slate-800/40">
        <button
          onClick={onNew}
          className="w-full flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-slate-400 hover:bg-white/5 hover:text-white transition-colors"
        >
          <Plus className="h-4 w-4 shrink-0" />
          New chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {sessions.length === 0 ? (
          <p className="px-3 py-6 text-xs text-slate-600 text-center">
            No conversations yet
          </p>
        ) : (
          sessions.map((session) => (
            <div key={session.id} className="group relative">
              <button
                onClick={() => onSwitch(session.id)}
                className={`w-full flex flex-col items-start gap-0.5 rounded-xl px-3 py-2 text-left transition-colors pr-7 ${
                  session.id === activeSessionId
                    ? "bg-violet-600/15 text-violet-200"
                    : "text-slate-500 hover:bg-white/5 hover:text-slate-300"
                }`}
              >
                <span className="line-clamp-2 text-xs font-medium leading-snug w-full">
                  {session.title}
                </span>
                <span className="text-[10px] opacity-50 mt-0.5">
                  {formatRelativeDate(session.updatedAt)}
                </span>
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(session.id);
                }}
                className="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center justify-center rounded-md p-1 text-slate-600 hover:bg-slate-800 hover:text-rose-400 transition-colors"
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
        <div className="max-w-[80%]">
          <div className="rounded-2xl rounded-tr-md bg-violet-600 px-4 py-2.5 text-sm text-white leading-relaxed shadow-md shadow-violet-900/30">
            {m.text}
          </div>
          <p className="mt-1 text-right text-[10px] text-slate-600">
            {formatTime(m.timestamp)}
          </p>
        </div>
      </div>
    );
  }

  if (m.role === "error") {
    return (
      <div className="flex gap-3">
        <div className="shrink-0 mt-0.5 h-6 w-6 rounded-full bg-rose-950 border border-rose-800/50 flex items-center justify-center text-[9px] font-bold text-rose-400">
          !
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-rose-400 leading-relaxed">{m.text}</p>
          <p className="mt-1 text-[10px] text-slate-600">{formatTime(m.timestamp)}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <div className="shrink-0 mt-0.5 h-6 w-6 rounded-full bg-violet-950 border border-violet-800/40 flex items-center justify-center text-[9px] font-black text-violet-400">
        NC
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm text-slate-100 leading-relaxed">
          {renderMarkdown(m.text)}
        </div>
        <p className="mt-1 text-[10px] text-slate-600">{formatTime(m.timestamp)}</p>
      </div>
    </div>
  );
}

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

  const messages =
    sessions.find((s) => s.id === activeSessionId)?.messages ?? [];

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
        finalizeMessage(
          `${msg.message_id}-reply`,
          msg.text ?? "",
          msg.timestamp ?? Date.now() / 1000,
        );
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

  async function doSubmit() {
    if (cmdMatches.length > 0) { applyCommand(cmdMatches[cmdIdx]); return; }
    const text = input.trim();
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

  const replyHasStarted =
    pendingId !== null && messages.some((m) => m.id === `${pendingId}-reply`);

  return (
    <div className="flex h-full -m-4 sm:-m-6 overflow-hidden">
      <SessionsSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onNew={newSession}
        onSwitch={switchSession}
        onDelete={deleteSession}
      />

      <div className="flex flex-1 flex-col overflow-hidden bg-[#0b0b12]">
        {/* Top micro-bar */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800/40 shrink-0">
          <div className="flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5 text-violet-500 shrink-0" />
            <span className="text-xs font-medium text-slate-400 truncate max-w-[200px]">
              {sessions.find((s) => s.id === activeSessionId)?.title ?? "NeuralCleave"}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={newSession}
              className="flex md:hidden items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-slate-500 hover:bg-slate-800 hover:text-white transition-colors"
            >
              <Plus className="h-3.5 w-3.5" /> New
            </button>
            {messages.length > 0 && (
              <button
                onClick={() => exportChatAsMarkdown(messages)}
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-slate-500 hover:bg-slate-800 hover:text-white transition-colors"
                title="Export as Markdown"
              >
                <Download className="h-3.5 w-3.5" />
                Export
              </button>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
              <div className="h-14 w-14 rounded-2xl bg-violet-950 border border-violet-800/30 flex items-center justify-center">
                <MessageSquare className="h-6 w-6 text-violet-400" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-200">How can I help you today?</p>
                <p className="mt-1.5 text-xs text-slate-600 max-w-xs">
                  Type anything to start, or press{" "}
                  <span className="font-mono text-violet-500">/help</span> for commands.
                  <br />
                  Shift+Enter for a new line.
                </p>
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-5">
              {messages.map((m, idx) => {
                const showSeparator =
                  idx === 0 || !isSameDay(messages[idx - 1].timestamp, m.timestamp);
                return (
                  <div key={m.id}>
                    {showSeparator && (
                      <div className="flex items-center gap-3 my-2">
                        <div className="flex-1 h-px bg-slate-800/50" />
                        <span className="text-[10px] text-slate-600 font-medium uppercase tracking-wider">
                          {formatDaySeparator(m.timestamp)}
                        </span>
                        <div className="flex-1 h-px bg-slate-800/50" />
                      </div>
                    )}
                    <MessageBubble m={m} />
                  </div>
                );
              })}

              {pendingId && !replyHasStarted && (
                <div className="flex gap-3">
                  <div className="shrink-0 mt-0.5 h-6 w-6 rounded-full bg-violet-950 border border-violet-800/40 flex items-center justify-center text-[9px] font-black text-violet-400">
                    NC
                  </div>
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-500" />
                    Thinking…
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-slate-800/40 px-4 sm:px-6 py-4 shrink-0">
          <div className="max-w-3xl mx-auto">
            <div className="relative">
              <CommandPalette
                matches={cmdMatches}
                selectedIdx={cmdIdx}
                onSelect={applyCommand}
              />
              <form onSubmit={handleSubmit}>
                <div className="flex items-end gap-2 rounded-2xl border border-slate-700/50 bg-slate-900/70 px-4 pt-3 pb-2.5 focus-within:border-violet-500/40 focus-within:ring-1 focus-within:ring-violet-500/10 transition-all">
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => { setInput(e.target.value); autoResize(); }}
                    onKeyDown={handleKeyDown}
                    placeholder="Message NeuralCleave… (Shift+Enter for new line)"
                    disabled={!!pendingId}
                    rows={1}
                    className="flex-1 resize-none bg-transparent text-sm text-white placeholder:text-slate-600 outline-none disabled:opacity-40 leading-relaxed py-0.5"
                    style={{ maxHeight: "160px", overflowY: "auto" }}
                  />
                  <button
                    type="submit"
                    disabled={!input.trim() || !!pendingId}
                    className="mb-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-violet-600 text-white transition-colors hover:bg-violet-500 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    {pendingId && !replyHasStarted ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Send className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              </form>
              <p className="mt-1.5 text-center text-[10px] text-slate-700">
                NeuralCleave can make mistakes. Verify important information.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
