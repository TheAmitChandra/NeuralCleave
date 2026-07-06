"use client";

import { useEffect, useRef, useState, FormEvent, KeyboardEvent } from "react";
import { MessageSquare, Send, Loader2, Terminal } from "lucide-react";
import { gatewayWS, type WSMessage } from "@/lib/websocket";
import { useChatStore } from "@/store/chat";
import {
  COMMANDS,
  matchCommands,
  findCommand,
  buildHelpText,
  type Command,
} from "@/lib/commands";

// ---------------------------------------------------------------------------
// Lightweight markdown renderer (no external dependency)
// Handles: **bold**, *italic*, `inline code`, ```code blocks```, headings,
// bullet lists, and bare URLs.  Renders to a <div> with safe whitespace.
// ---------------------------------------------------------------------------

function renderMarkdown(text: string): React.ReactNode {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
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
          className="my-2 overflow-x-auto rounded-lg bg-slate-950 p-3 text-xs text-emerald-300"
          data-lang={lang || undefined}
        >
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      i++; // skip closing ```
      continue;
    }

    // Heading
    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const cls =
        level === 1
          ? "text-base font-bold mt-2"
          : level === 2
            ? "text-sm font-semibold mt-1"
            : "text-sm font-medium mt-1";
      elements.push(
        <p key={i} className={cls}>
          {inlineMarkdown(headingMatch[2])}
        </p>
      );
      i++;
      continue;
    }

    // Bullet list item
    if (/^[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s/, ""));
        i++;
      }
      elements.push(
        <ul key={i} className="my-1 list-disc pl-4 text-sm">
          {items.map((item, j) => (
            <li key={j}>{inlineMarkdown(item)}</li>
          ))}
        </ul>
      );
      continue;
    }

    // Blank line → spacing
    if (line.trim() === "") {
      elements.push(<div key={i} className="h-1" />);
      i++;
      continue;
    }

    // Normal paragraph
    elements.push(
      <p key={i} className="text-sm leading-relaxed">
        {inlineMarkdown(line)}
      </p>
    );
    i++;
  }

  return <>{elements}</>;
}

function inlineMarkdown(text: string): React.ReactNode {
  // Split on **bold**, *italic*, `code`
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**"))
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*"))
      return <em key={i}>{part.slice(1, -1)}</em>;
    if (part.startsWith("`") && part.endsWith("`"))
      return (
        <code
          key={i}
          className="rounded bg-slate-950 px-1 py-0.5 font-mono text-xs text-emerald-300"
        >
          {part.slice(1, -1)}
        </code>
      );
    return part;
  });
}

// ---------------------------------------------------------------------------
// Command palette popup
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
    <div className="absolute bottom-full left-0 right-0 z-20 mb-1 rounded-xl border border-slate-700 bg-slate-900 shadow-xl">
      {matches.map((cmd, idx) => (
        <button
          key={cmd.trigger}
          type="button"
          onClick={() => onSelect(cmd)}
          className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors first:rounded-t-xl last:rounded-b-xl ${
            idx === selectedIdx
              ? "bg-indigo-600 text-white"
              : "text-slate-300 hover:bg-slate-800"
          }`}
        >
          <Terminal className="h-3.5 w-3.5 shrink-0 opacity-60" />
          <span className="font-mono font-medium">{cmd.trigger}</span>
          {cmd.args && (
            <span className="font-mono text-xs opacity-60">{cmd.args}</span>
          )}
          <span className="ml-auto text-xs opacity-60">{cmd.description}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main chat page
// ---------------------------------------------------------------------------

export default function ChatPage() {
  const {
    messages,
    pendingId,
    addMessage,
    upsertAgentChunk,
    finalizeMessage,
    addErrorMessage,
    setPendingId,
    clearMessages,
  } = useChatStore();

  const [input, setInput] = useState("");
  const [cmdMatches, setCmdMatches] = useState<Command[]>([]);
  const [cmdIdx, setCmdIdx] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Open the WebSocket on mount; close it when the user leaves the page.
  useEffect(() => {
    gatewayWS.connect();
    return () => { gatewayWS.disconnect(); };
  }, []);

  useEffect(() => {
    const unsubscribe = gatewayWS.subscribe((msg: WSMessage) => {
      if (msg.type === "message_chunk" && msg.message_id && msg.delta) {
        upsertAgentChunk(
          `${msg.message_id}-reply`,
          msg.delta,
          Date.now() / 1000,
        );
      } else if (msg.type === "message_done" && msg.message_id) {
        const replyId = `${msg.message_id}-reply`;
        const finalText = msg.text ?? "";
        setPendingId(pendingId === msg.message_id ? null : pendingId);
        finalizeMessage(replyId, finalText, msg.timestamp ?? Date.now() / 1000);
      } else if (msg.type === "error" && msg.message_id) {
        setPendingId(pendingId === msg.message_id ? null : pendingId);
        addErrorMessage(
          `${msg.message_id}-error`,
          msg.message ?? "Something went wrong.",
        );
      }
    });
    return unsubscribe;
  }, [pendingId, upsertAgentChunk, finalizeMessage, addErrorMessage, setPendingId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Update command palette matches whenever input changes
  useEffect(() => {
    if (input.startsWith("/")) {
      const matches = matchCommands(input.split(" ")[0]);
      setCmdMatches(matches);
      setCmdIdx(0);
    } else {
      setCmdMatches([]);
    }
  }, [input]);

  function applyCommand(cmd: Command) {
    // Fill in the trigger (plus a space for commands that take args)
    setInput(cmd.args ? `${cmd.trigger} ` : cmd.trigger);
    setCmdMatches([]);
    inputRef.current?.focus();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (cmdMatches.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCmdIdx((prev) => (prev + 1) % cmdMatches.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCmdIdx((prev) => (prev - 1 + cmdMatches.length) % cmdMatches.length);
    } else if (e.key === "Tab" || e.key === "Enter") {
      if (cmdMatches.length > 0) {
        e.preventDefault();
        applyCommand(cmdMatches[cmdIdx]);
      }
    } else if (e.key === "Escape") {
      setCmdMatches([]);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();

    // If command palette is open and Enter pressed, apply highlighted command
    if (cmdMatches.length > 0) {
      applyCommand(cmdMatches[cmdIdx]);
      return;
    }

    const text = input.trim();
    if (!text || pendingId) return;

    // ── Local command handling ───────────────────────────────────────────
    const cmd = findCommand(text);
    if (cmd?.scope === "local") {
      setInput("");
      setCmdMatches([]);
      if (cmd.name === "reset") {
        clearMessages();
        addMessage({
          id: crypto.randomUUID(),
          role: "agent",
          text: "Conversation cleared.",
          timestamp: Date.now() / 1000,
        });
      } else if (cmd.name === "help") {
        addMessage({
          id: crypto.randomUUID(),
          role: "agent",
          text: buildHelpText(),
          timestamp: Date.now() / 1000,
        });
      }
      return;
    }

    // ── Remote: forward to backend via WebSocket ─────────────────────────
    const id = crypto.randomUUID();
    addMessage({ id, role: "user", text, timestamp: Date.now() / 1000 });
    setInput("");
    setCmdMatches([]);

    const sent = gatewayWS.send({ type: "message", id, text });
    if (!sent) {
      addErrorMessage(
        `${id}-error`,
        "Not connected to the gateway. Check the WebSocket URL in Settings.",
      );
      return;
    }
    setPendingId(id);
  }

  // Show spinner only while waiting for the very first chunk.
  const replyHasStarted =
    pendingId !== null && messages.some((m) => m.id === `${pendingId}-reply`);

  return (
    <div className="flex h-full flex-col space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-white">Chat</h1>
        <p className="mt-1 text-sm text-slate-400">
          Talk to the agent — type <code className="rounded bg-slate-800 px-1 text-xs">/</code> for commands
        </p>
      </div>

      <div className="flex flex-1 flex-col rounded-xl border border-slate-800 bg-slate-900">
        {/* Message list */}
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center text-slate-500">
              <MessageSquare className="h-8 w-8 text-slate-600" />
              <p className="mt-2 text-sm">Send a message to start the conversation.</p>
              <p className="mt-1 text-xs text-slate-600">
                Type <span className="font-mono">/help</span> to see available commands.
              </p>
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[75%] rounded-xl px-4 py-2 ${
                    m.role === "user"
                      ? "bg-indigo-600 text-white text-sm"
                      : m.role === "error"
                        ? "bg-rose-950/60 text-rose-300 text-sm"
                        : "bg-slate-800 text-slate-100"
                  }`}
                >
                  {m.role === "agent"
                    ? renderMarkdown(m.text)
                    : m.text}
                </div>
              </div>
            ))
          )}
          {pendingId && !replyHasStarted && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 rounded-xl bg-slate-800 px-4 py-2 text-sm text-slate-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Thinking…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input + command palette */}
        <div className="relative border-t border-slate-800">
          <CommandPalette
            matches={cmdMatches}
            selectedIdx={cmdIdx}
            onSelect={applyCommand}
          />
          <form
            onSubmit={handleSubmit}
            className="flex items-center gap-2 p-4"
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message the agent… (type / for commands)"
              disabled={!!pendingId}
              className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!input.trim() || !!pendingId}
              className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
