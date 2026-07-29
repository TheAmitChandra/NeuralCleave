import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface ChatMessage {
  id: string;
  role: "user" | "agent" | "error";
  text: string;
  timestamp: number;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  pendingId: string | null;

  newSession: () => void;
  switchSession: (id: string) => void;
  deleteSession: (id: string) => void;
  addMessage: (message: ChatMessage) => void;
  upsertAgentChunk: (replyId: string, delta: string, timestamp: number) => void;
  finalizeMessage: (replyId: string, text: string, timestamp: number) => void;
  addErrorMessage: (id: string, text: string) => void;
  setPendingId: (id: string | null) => void;
  clearMessages: () => void;
}

const MAX_SESSIONS = 30;
const MAX_MESSAGES = 200;

function makeSession(): ChatSession {
  return {
    id: crypto.randomUUID(),
    title: "New conversation",
    messages: [],
    createdAt: Date.now() / 1000,
    updatedAt: Date.now() / 1000,
  };
}

function deriveTitle(messages: ChatMessage[], current: string): string {
  if (current !== "New conversation") return current;
  const first = messages.find((m) => m.role === "user");
  if (!first) return current;
  const t = first.text.trim();
  return t.length > 60 ? t.slice(0, 60) + "…" : t;
}

function mapActive(
  sessions: ChatSession[],
  activeId: string | null,
  fn: (s: ChatSession) => ChatSession,
): ChatSession[] {
  return sessions.map((s) => (s.id === activeId ? fn(s) : s));
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      sessions: [],
      activeSessionId: null,
      pendingId: null,

      newSession: () => {
        const session = makeSession();
        set((state) => ({
          sessions: [session, ...state.sessions].slice(0, MAX_SESSIONS),
          activeSessionId: session.id,
          pendingId: null,
        }));
      },

      switchSession: (id) => set({ activeSessionId: id, pendingId: null }),

      deleteSession: (id) =>
        set((state) => {
          const remaining = state.sessions.filter((s) => s.id !== id);
          const newActive =
            state.activeSessionId === id
              ? (remaining[0]?.id ?? null)
              : state.activeSessionId;
          return { sessions: remaining, activeSessionId: newActive };
        }),

      addMessage: (message) =>
        set((state) => {
          let { sessions, activeSessionId } = state;
          if (!activeSessionId || !sessions.find((s) => s.id === activeSessionId)) {
            const session = makeSession();
            sessions = [session, ...sessions].slice(0, MAX_SESSIONS);
            activeSessionId = session.id;
          }
          return {
            sessions: mapActive(sessions, activeSessionId, (s) => {
              const msgs = [...s.messages, message];
              return {
                ...s,
                messages: msgs,
                title: deriveTitle(msgs, s.title),
                updatedAt: Date.now() / 1000,
              };
            }),
            activeSessionId,
          };
        }),

      upsertAgentChunk: (replyId, delta, timestamp) =>
        set((state) => ({
          sessions: mapActive(state.sessions, state.activeSessionId, (s) => {
            const idx = s.messages.findIndex((m) => m.id === replyId);
            const msgs =
              idx === -1
                ? [...s.messages, { id: replyId, role: "agent" as const, text: delta, timestamp }]
                : s.messages.map((m, i) =>
                    i === idx ? { ...m, text: m.text + delta } : m,
                  );
            return { ...s, messages: msgs, updatedAt: Date.now() / 1000 };
          }),
        })),

      finalizeMessage: (replyId, text, timestamp) =>
        set((state) => ({
          sessions: mapActive(state.sessions, state.activeSessionId, (s) => {
            const idx = s.messages.findIndex((m) => m.id === replyId);
            const msgs =
              idx === -1
                ? [...s.messages, { id: replyId, role: "agent" as const, text, timestamp }]
                : s.messages.map((m, i) => (i === idx ? { ...m, text } : m));
            return { ...s, messages: msgs, updatedAt: Date.now() / 1000 };
          }),
        })),

      addErrorMessage: (id, text) =>
        set((state) => ({
          sessions: mapActive(state.sessions, state.activeSessionId, (s) => ({
            ...s,
            messages: [
              ...s.messages,
              { id, role: "error" as const, text, timestamp: Date.now() / 1000 },
            ],
            updatedAt: Date.now() / 1000,
          })),
        })),

      setPendingId: (id) => set({ pendingId: id }),

      clearMessages: () =>
        set((state) => ({
          sessions: mapActive(state.sessions, state.activeSessionId, (s) => ({
            ...s,
            messages: [],
            title: "New conversation",
            updatedAt: Date.now() / 1000,
          })),
        })),
    }),
    {
      name: "NeuralCleave_chat_v2",
      partialize: (state) => ({
        sessions: state.sessions
          .map((s) => ({ ...s, messages: s.messages.slice(-MAX_MESSAGES) }))
          .slice(0, MAX_SESSIONS),
        activeSessionId: state.activeSessionId,
      }),
    },
  ),
);
