"use client";

import {
  useEffect,
  useRef,
  useState,
  FormEvent,
  KeyboardEvent,
  useCallback,
} from "react";
import { Send, Loader2, Terminal, Download, Plus, Trash2, PenLine } from "lucide-react";
import type { ChatMessage, ChatSession } from "@/store/chat";
import { gatewayWS, type WSMessage } from "@/lib/websocket";
import { useChatStore } from "@/store/chat";
import api from "@/lib/api";
import { matchCommands, findCommand, buildHelpText, type Command } from "@/lib/commands";

// ─── Markdown renderer ────────────────────────────────────────────────────────

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
        <pre key={i} className="my-3 overflow-x-auto rounded-xl bg-black/50 border border-white/[0.07] p-4 text-xs text-cyan-300 font-mono">
          {lang && <div className="mb-2 text-[10px] text-white/25 uppercase tracking-widest">{lang}</div>}
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      i++; continue;
    }
    const hm = line.match(/^(#{1,3})\s+(.+)$/);
    if (hm) {
      const cls = hm[1].length === 1 ? "text-base font-bold mt-3 mb-1 text-white" : hm[1].length === 2 ? "text-sm font-semibold mt-2 mb-0.5 text-white/90" : "text-sm font-medium mt-1 text-white/80";
      elements.push(<p key={i} className={cls}>{inlineMd(hm[2])}</p>);
      i++; continue;
    }
    if (/^[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i])) { items.push(lines[i].replace(/^[-*]\s/, "")); i++; }
      elements.push(<ul key={i} className="my-1.5 list-disc pl-5 space-y-0.5">{items.map((it, j) => <li key={j} className="text-sm text-white/75 leading-relaxed">{inlineMd(it)}</li>)}</ul>);
      continue;
    }
    if (line.trim() === "") { elements.push(<div key={i} className="h-1.5" />); i++; continue; }
    elements.push(<p key={i} className="text-sm leading-relaxed text-white/80">{inlineMd(line)}</p>);
    i++;
  }
  return <>{elements}</>;
}

function inlineMd(text: string): React.ReactNode {
  return text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g).map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={i} className="font-semibold text-white">{p.slice(2, -2)}</strong>;
    if (p.startsWith("*") && p.endsWith("*")) return <em key={i} className="text-white/70">{p.slice(1, -1)}</em>;
    if (p.startsWith("`") && p.endsWith("`")) return <code key={i} className="rounded bg-black/50 border border-white/[0.07] px-1.5 py-0.5 font-mono text-[11px] text-cyan-300">{p.slice(1, -1)}</code>;
    return p;
  });
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const fmt = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function relDate(ts: number): string {
  const d = new Date(ts * 1000), now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const msgDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round((today.getTime() - msgDay.getTime()) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function daySep(ts: number): string {
  const d = new Date(ts * 1000), now = new Date();
  const diff = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() - new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
}

function sameDay(a: number, b: number): boolean {
  const da = new Date(a * 1000), db = new Date(b * 1000);
  return da.getFullYear() === db.getFullYear() && da.getMonth() === db.getMonth() && da.getDate() === db.getDate();
}

function exportMd(messages: ChatMessage[]) {
  const lines = ["# NeuralCleave Chat Export", `> ${new Date().toLocaleString()}`, ""];
  for (const m of messages) {
    const t = new Date(m.timestamp * 1000).toLocaleTimeString();
    lines.push(m.role === "user" ? `**You** *(${t})*` : m.role === "agent" ? `**NeuralCleave** *(${t})*` : `**Error** *(${t})*`, "", m.text, "");
  }
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/markdown" })), download: `nc-chat-${new Date().toISOString().slice(0, 10)}.md` });
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}

// ─── Command palette ──────────────────────────────────────────────────────────

function CmdPalette({ matches, idx, onSelect }: { matches: Command[]; idx: number; onSelect: (c: Command) => void }) {
  if (!matches.length) return null;
  return (
    <div className="absolute bottom-full left-0 right-0 z-20 mb-3 overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0e0e1a]/95 backdrop-blur-2xl shadow-2xl shadow-black/70">
      {matches.map((cmd, i) => (
        <button key={cmd.trigger} type="button" onClick={() => onSelect(cmd)}
          className={`flex w-full items-center gap-3 px-4 py-3 text-sm transition-colors ${i === idx ? "bg-violet-600/20 text-white" : "text-white/40 hover:bg-white/[0.04] hover:text-white/70"}`}>
          <Terminal className="h-3.5 w-3.5 shrink-0 opacity-40" />
          <span className="font-mono font-medium">{cmd.trigger}</span>
          {cmd.args && <span className="font-mono text-xs opacity-40">{cmd.args}</span>}
          <span className="ml-auto text-xs opacity-40">{cmd.description}</span>
        </button>
      ))}
    </div>
  );
}

// ─── Sessions sidebar ─────────────────────────────────────────────────────────

function SessionsSidebar({ sessions, activeId, onNew, onSwitch, onDelete }: {
  sessions: ChatSession[]; activeId: string | null;
  onNew: () => void; onSwitch: (id: string) => void; onDelete: (id: string) => void;
}) {
  return (
    <aside className="hidden md:flex w-[210px] shrink-0 flex-col border-r border-white/[0.05]" style={{ background: "linear-gradient(180deg, #0d0d18 0%, #0a0a14 100%)" }}>
      {/* New chat */}
      <div className="p-3 pb-2">
        <button onClick={onNew}
          className="group flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13px] font-medium text-white/30 transition-all duration-150 hover:bg-white/[0.06] hover:text-white/80">
          <div className="flex h-5 w-5 items-center justify-center rounded-lg bg-white/[0.06] transition-colors group-hover:bg-white/[0.1]">
            <PenLine className="h-3 w-3" />
          </div>
          New chat
        </button>
      </div>

      {sessions.length > 0 && (
        <p className="px-5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/[0.15]">Recents</p>
      )}

      <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-0.5">
        {sessions.length === 0 ? (
          <p className="px-3 py-8 text-center text-[12px] text-white/[0.15] leading-relaxed">No conversations yet</p>
        ) : sessions.map((s) => (
          <div key={s.id} className="group relative">
            <button onClick={() => onSwitch(s.id)}
              className={`w-full flex flex-col items-start gap-0.5 rounded-lg px-3 py-2 pr-7 text-left transition-all duration-150 ${s.id === activeId ? "bg-violet-500/[0.12] text-white" : "text-white/[0.28] hover:bg-white/[0.04] hover:text-white/60"}`}>
              <span className="line-clamp-1 text-[12px] font-medium w-full">{s.title}</span>
              <span className="text-[10px] opacity-50">{relDate(s.updatedAt)}</span>
            </button>
            <button onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center justify-center rounded-md p-1 text-white/[0.15] hover:text-rose-400 transition-colors">
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}
      </div>

      {/* Subtle bottom gradient */}
      <div className="h-px w-full" style={{ background: "linear-gradient(90deg, transparent, rgba(124,58,237,0.25), transparent)" }} />
    </aside>
  );
}

// ─── Message bubble ───────────────────────────────────────────────────────────

function Bubble({ m }: { m: ChatMessage }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[76%]">
          <div className="rounded-2xl rounded-br-sm px-4 py-3 text-sm text-white leading-relaxed"
            style={{ background: "linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%)", boxShadow: "0 4px 24px rgba(109,40,217,0.25)" }}>
            {m.text}
          </div>
          <p className="mt-1 text-right text-[10px] text-white/[0.2]">{fmt(m.timestamp)}</p>
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
          <p className="mt-1 text-[10px] text-white/[0.18]">{fmt(m.timestamp)}</p>
        </div>
      </div>
    );
  }
  return (
    <div className="flex gap-3">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.png" alt="" className="shrink-0 mt-0.5 h-7 w-7 rounded-lg object-cover" style={{ filter: "drop-shadow(0 0 6px rgba(124,58,237,0.4))" }} />
      <div className="flex-1 min-w-0">
        <div className="text-sm text-white/80 leading-relaxed">{renderMarkdown(m.text)}</div>
        <p className="mt-1 text-[10px] text-white/[0.2]">{fmt(m.timestamp)}</p>
      </div>
    </div>
  );
}

// ─── Suggestion chips ─────────────────────────────────────────────────────────

const CHIPS = [
  { label: "Your capabilities", q: "What can you do? Give me a quick overview of your capabilities." },
  { label: "Set up Telegram", q: "How do I set up a Telegram channel integration?" },
  { label: "How Memory works", q: "Explain how the Memory system works and how I can use it." },
  { label: "Available commands", q: "/help" },
];

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const { sessions, activeSessionId, pendingId, newSession, switchSession, deleteSession, addMessage, upsertAgentChunk, finalizeMessage, addErrorMessage, setPendingId, clearMessages } = useChatStore();

  const messages = sessions.find((s) => s.id === activeSessionId)?.messages ?? [];
  const [input, setInput] = useState("");
  const [cmdMatches, setCmdMatches] = useState<Command[]>([]);
  const [cmdIdx, setCmdIdx] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const autoResize = useCallback(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, []);

  useEffect(() => { gatewayWS.connect(); return () => { gatewayWS.disconnect(); }; }, []);

  useEffect(() => {
    return gatewayWS.subscribe((msg: WSMessage) => {
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
  }, [pendingId, upsertAgentChunk, finalizeMessage, addErrorMessage, setPendingId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  useEffect(() => {
    if (input.startsWith("/")) { setCmdMatches(matchCommands(input.split(" ")[0])); setCmdIdx(0); }
    else setCmdMatches([]);
  }, [input]);

  function applyCmd(cmd: Command) { setInput(cmd.args ? `${cmd.trigger} ` : cmd.trigger); setCmdMatches([]); taRef.current?.focus(); }

  function handleKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (cmdMatches.length > 0) {
      if (e.key === "ArrowDown") { e.preventDefault(); setCmdIdx((p) => (p + 1) % cmdMatches.length); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setCmdIdx((p) => (p - 1 + cmdMatches.length) % cmdMatches.length); return; }
      if (e.key === "Tab" || e.key === "Enter") { e.preventDefault(); applyCmd(cmdMatches[cmdIdx]); return; }
      if (e.key === "Escape") { setCmdMatches([]); return; }
    }
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
  }

  async function send(override?: string) {
    if (!override && cmdMatches.length > 0) { applyCmd(cmdMatches[cmdIdx]); return; }
    const text = (override ?? input).trim();
    if (!text || pendingId) return;

    const cmd = findCommand(text);
    if (cmd?.scope === "local") {
      setInput(""); setCmdMatches([]);
      if (cmd.name === "reset") {
        clearMessages();
        addMessage({ id: crypto.randomUUID(), role: "agent", text: "Conversation cleared.", timestamp: Date.now() / 1000 });
      } else if (cmd.name === "help") {
        addMessage({ id: crypto.randomUUID(), role: "agent", text: buildHelpText(), timestamp: Date.now() / 1000 });
      } else if (cmd.name === "info") {
        void api.get<{ version: string; uptime_seconds: number; active_sessions: number; runtime_available: boolean; init_phase?: string }>("/status")
          .then(({ data: s }) => { const m = Math.floor(s.uptime_seconds / 60), sec = Math.floor(s.uptime_seconds % 60); addMessage({ id: crypto.randomUUID(), role: "agent", text: `**NeuralCleave v${s.version}**\nUptime: ${m}m ${sec}s\nRuntime: ${s.runtime_available ? "ready" : (s.init_phase ?? "initializing")}\nSessions: ${s.active_sessions}`, timestamp: Date.now() / 1000 }); })
          .catch(() => addMessage({ id: crypto.randomUUID(), role: "error", text: "Cannot reach gateway — check that the backend is running.", timestamp: Date.now() / 1000 }));
      } else if (cmd.name === "privacy") {
        const arg = text.split(" ")[1]?.toLowerCase();
        if (arg !== "on" && arg !== "off") { addMessage({ id: crypto.randomUUID(), role: "agent", text: "Usage: `/privacy on` or `/privacy off`", timestamp: Date.now() / 1000 }); }
        else { const en = arg === "on"; void api.post("/settings/model", { privacy_mode: en }).then(() => addMessage({ id: crypto.randomUUID(), role: "agent", text: en ? "Privacy mode **enabled**." : "Privacy mode **disabled**.", timestamp: Date.now() / 1000 })).catch(() => addMessage({ id: crypto.randomUUID(), role: "error", text: "Failed — gateway unreachable.", timestamp: Date.now() / 1000 })); }
      }
      return;
    }

    const id = crypto.randomUUID();
    addMessage({ id, role: "user", text, timestamp: Date.now() / 1000 });
    setInput(""); setCmdMatches([]);
    if (taRef.current) taRef.current.style.height = "auto";
    if (!gatewayWS.send({ type: "message", id, text })) {
      addErrorMessage(`${id}-error`, "Not connected to gateway. Check WebSocket URL in Settings.");
      return;
    }
    setPendingId(id);
  }

  const replyStarted = pendingId !== null && messages.some((m) => m.id === `${pendingId}-reply`);

  return (
    /* Full-bleed: cancel parent's p-4 sm:p-6 */
    <div className="flex h-full -m-4 sm:-m-6 overflow-hidden" style={{ background: "#08080f" }}>
      <SessionsSidebar sessions={sessions} activeId={activeSessionId} onNew={newSession} onSwitch={switchSession} onDelete={deleteSession} />

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            /* ── Empty state ── */
            <div className="flex h-full flex-col items-center justify-center gap-7 px-6 text-center">
              {/* Logo + glow */}
              <div className="relative">
                <div className="absolute inset-0 scale-150 rounded-full blur-3xl" style={{ background: "radial-gradient(circle, rgba(124,58,237,0.3) 0%, rgba(6,182,212,0.1) 60%, transparent 100%)" }} />
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/logo.png" alt="NeuralCleave" className="relative h-16 w-16 rounded-2xl z-10" style={{ filter: "drop-shadow(0 0 20px rgba(124,58,237,0.6)) drop-shadow(0 0 40px rgba(6,182,212,0.2))" }} />
              </div>

              {/* Headline with gradient */}
              <div>
                <h2 className="text-[22px] font-semibold tracking-tight" style={{ background: "linear-gradient(135deg, #c4b5fd 0%, #67e8f9 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                  What can I help with?
                </h2>
                <p className="mt-2 text-[13px]" style={{ color: "rgba(255,255,255,0.28)" }}>
                  Type a message below, or start from a suggestion
                </p>
              </div>

              {/* Suggestion chips */}
              <div className="flex flex-wrap justify-center gap-2 max-w-[480px]">
                {CHIPS.map((c) => (
                  <button key={c.label} onClick={() => void send(c.q)}
                    className="rounded-xl border px-4 py-2.5 text-[13px] font-medium transition-all duration-150"
                    style={{ borderColor: "rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.03)", color: "rgba(255,255,255,0.45)" }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(124,58,237,0.12)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(124,58,237,0.3)"; (e.currentTarget as HTMLButtonElement).style.color = "rgba(255,255,255,0.85)"; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,0.03)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(255,255,255,0.08)"; (e.currentTarget as HTMLButtonElement).style.color = "rgba(255,255,255,0.45)"; }}
                  >{c.label}</button>
                ))}
              </div>

              {/* Mobile new chat */}
              <button onClick={newSession}
                className="flex md:hidden items-center gap-2 rounded-xl border px-4 py-2 text-sm transition-colors"
                style={{ borderColor: "rgba(255,255,255,0.07)", color: "rgba(255,255,255,0.35)" }}>
                <Plus className="h-4 w-4" /> New chat
              </button>
            </div>
          ) : (
            /* ── Messages list ── */
            <div className="mx-auto w-full max-w-[660px] px-5 py-8 space-y-5">
              {messages.map((m, idx) => {
                const showSep = idx === 0 || !sameDay(messages[idx - 1].timestamp, m.timestamp);
                return (
                  <div key={m.id}>
                    {showSep && (
                      <div className="flex items-center gap-3 mb-4">
                        <div className="flex-1 h-px" style={{ background: "rgba(255,255,255,0.05)" }} />
                        <span className="text-[10px] uppercase tracking-[0.1em]" style={{ color: "rgba(255,255,255,0.2)" }}>{daySep(m.timestamp)}</span>
                        <div className="flex-1 h-px" style={{ background: "rgba(255,255,255,0.05)" }} />
                      </div>
                    )}
                    <Bubble m={m} />
                  </div>
                );
              })}

              {/* Thinking dots */}
              {pendingId && !replyStarted && (
                <div className="flex gap-3">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/logo.png" alt="" className="shrink-0 mt-1 h-7 w-7 rounded-lg object-cover opacity-60" />
                  <div className="flex items-center gap-1 pt-2">
                    {[0, 160, 320].map((d) => (
                      <span key={d} className="h-1.5 w-1.5 rounded-full bg-violet-500/60 animate-bounce" style={{ animationDelay: `${d}ms`, animationDuration: "1.1s" }} />
                    ))}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* ── Glass input bar ── */}
        <div className="shrink-0 px-5 pb-5 pt-2">
          <div className="mx-auto w-full max-w-[660px]">
            <div className="relative">
              <CmdPalette matches={cmdMatches} idx={cmdIdx} onSelect={applyCmd} />
              <form onSubmit={(e: FormEvent) => { e.preventDefault(); void send(); }}>
                <div
                  className="rounded-2xl px-4 pt-4 pb-3 transition-all duration-200"
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.07)",
                    backdropFilter: "blur(20px)",
                    boxShadow: "0 8px 40px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05)",
                  }}
                  onFocus={() => {}} // handled via CSS
                >
                  <textarea ref={taRef} value={input}
                    onChange={(e) => { setInput(e.target.value); autoResize(); }}
                    onKeyDown={handleKey}
                    placeholder="Message NeuralCleave…"
                    disabled={!!pendingId} rows={1}
                    className="w-full resize-none bg-transparent text-[14px] outline-none disabled:opacity-40 leading-relaxed placeholder:text-white/20"
                    style={{ color: "rgba(255,255,255,0.88)", maxHeight: "160px", overflowY: "auto" }}
                  />
                  <div className="mt-3 flex items-center justify-between">
                    <div className="flex gap-1">
                      {messages.length > 0 && (
                        <button type="button" onClick={() => exportMd(messages)} title="Export chat"
                          className="rounded-lg p-2 transition-colors"
                          style={{ color: "rgba(255,255,255,0.2)" }}
                          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "rgba(255,255,255,0.55)"; (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,0.05)"; }}
                          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "rgba(255,255,255,0.2)"; (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}>
                          <Download className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-[11px] select-none" style={{ color: "rgba(255,255,255,0.12)" }}>Shift+Enter for new line</span>
                      <button type="submit" disabled={!input.trim() || !!pendingId}
                        className="flex h-8 w-8 items-center justify-center rounded-xl transition-all disabled:opacity-20 disabled:cursor-not-allowed"
                        style={{ background: "linear-gradient(135deg, #7c3aed, #6d28d9)", boxShadow: "0 4px 16px rgba(109,40,217,0.4)" }}>
                        {pendingId && !replyStarted ? <Loader2 className="h-3.5 w-3.5 text-white animate-spin" /> : <Send className="h-3.5 w-3.5 text-white" />}
                      </button>
                    </div>
                  </div>
                </div>
              </form>
              <p className="mt-2 text-center text-[11px]" style={{ color: "rgba(255,255,255,0.1)" }}>
                NeuralCleave can make mistakes. Verify important information.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
