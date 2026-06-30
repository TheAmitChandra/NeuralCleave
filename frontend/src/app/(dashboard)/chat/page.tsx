"use client";

import { useEffect, useRef, useState, FormEvent } from "react";
import { MessageSquare, Send, Loader2 } from "lucide-react";
import { gatewayWS, type WSMessage } from "@/lib/websocket";

interface ChatMessage {
  id: string;
  role: "user" | "agent" | "error";
  text: string;
  timestamp: number;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const unsubscribe = gatewayWS.subscribe((msg: WSMessage) => {
      if (msg.type === "message_chunk" && msg.message_id && msg.delta) {
        // Streams in: first delta creates the agent's bubble, every
        // subsequent delta for the same message_id appends to it.
        const replyId = `${msg.message_id}-reply`;
        setMessages((prev) => {
          const idx = prev.findIndex((m) => m.id === replyId);
          if (idx === -1) {
            return [
              ...prev,
              { id: replyId, role: "agent", text: msg.delta!, timestamp: Date.now() / 1000 },
            ];
          }
          const updated = [...prev];
          updated[idx] = { ...updated[idx], text: updated[idx].text + msg.delta };
          return updated;
        });
      } else if (msg.type === "message_done" && msg.message_id) {
        // Reconciles with the authoritative full text — also covers slash
        // commands, which skip message_chunk entirely and arrive as a
        // single message_done with no prior bubble to update.
        const replyId = `${msg.message_id}-reply`;
        const finalText = msg.text ?? "";
        setPendingId((current) => (current === msg.message_id ? null : current));
        setMessages((prev) => {
          const idx = prev.findIndex((m) => m.id === replyId);
          if (idx === -1) {
            return [
              ...prev,
              { id: replyId, role: "agent", text: finalText, timestamp: msg.timestamp ?? Date.now() / 1000 },
            ];
          }
          const updated = [...prev];
          updated[idx] = { ...updated[idx], text: finalText };
          return updated;
        });
      } else if (msg.type === "error" && msg.message_id) {
        setPendingId((current) => (current === msg.message_id ? null : current));
        setMessages((prev) => [
          ...prev,
          {
            id: `${msg.message_id}-error`,
            role: "error",
            text: msg.message ?? "Something went wrong.",
            timestamp: Date.now() / 1000,
          },
        ]);
      }
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || pendingId) return;

    const id = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id, role: "user", text, timestamp: Date.now() / 1000 },
    ]);
    setInput("");

    const sent = gatewayWS.send({ type: "message", id, text });
    if (!sent) {
      setMessages((prev) => [
        ...prev,
        {
          id: `${id}-error`,
          role: "error",
          text: "Not connected to the gateway. Check the WebSocket URL in Settings.",
          timestamp: Date.now() / 1000,
        },
      ]);
      return;
    }
    setPendingId(id);
  }

  // The streaming reply bubble itself (created on the first message_chunk)
  // replaces this placeholder — only show it while waiting for the very
  // first chunk to arrive.
  const replyHasStarted = pendingId !== null && messages.some((m) => m.id === `${pendingId}-reply`);

  return (
    <div className="flex h-full flex-col space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-white">Chat</h1>
        <p className="mt-1 text-sm text-slate-400">
          Talk to the agent directly over the gateway WebSocket
        </p>
      </div>

      <div className="flex flex-1 flex-col rounded-xl border border-slate-800 bg-slate-900">
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center text-slate-500">
              <MessageSquare className="h-8 w-8 text-slate-600" />
              <p className="mt-2 text-sm">Send a message to start the conversation.</p>
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[75%] rounded-xl px-4 py-2 text-sm ${
                    m.role === "user"
                      ? "bg-indigo-600 text-white"
                      : m.role === "error"
                        ? "bg-rose-950/60 text-rose-300"
                        : "bg-slate-800 text-slate-100"
                  }`}
                >
                  {m.text}
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

        <form
          onSubmit={handleSubmit}
          className="flex items-center gap-2 border-t border-slate-800 p-4"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Message the agent…"
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
  );
}
