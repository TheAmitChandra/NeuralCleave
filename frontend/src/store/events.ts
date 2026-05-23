/**
 * Zustand store for real-time WebSocket events.
 *
 * Usage:
 *   const { connect, agentEvents, systemEvents } = useEventsStore();
 *   useEffect(() => { connect(accessToken); return disconnect; }, []);
 */

import { create } from "zustand";
import { agentsWS, workflowsWS, eventsWS, type WSMessage } from "@/lib/websocket";

export type AgentEvent = {
  agent_id: string;
  status: string;
  [key: string]: unknown;
};

export type WorkflowEvent = {
  workflow_id: string;
  status: string;
  [key: string]: unknown;
};

export type SystemEvent = WSMessage;

const MAX_BUFFER = 100; // keep last N events per channel

type EventsState = {
  connected: boolean;
  agentEvents: AgentEvent[];
  workflowEvents: WorkflowEvent[];
  systemEvents: SystemEvent[];
  /** Open all three WS connections authenticated with the given JWT. */
  connect: (token: string) => void;
  /** Close all WS connections. */
  disconnect: () => void;
  /** Clear all buffered events (useful on logout). */
  clearEvents: () => void;
};

export const useEventsStore = create<EventsState>((set) => {
  // Keep unsubscribe handles so we can clean up on disconnect.
  let unsubAgents: (() => void) | null = null;
  let unsubWorkflows: (() => void) | null = null;
  let unsubEvents: (() => void) | null = null;

  return {
    connected: false,
    agentEvents: [],
    workflowEvents: [],
    systemEvents: [],

    connect(token: string) {
      agentsWS.connect(token);
      workflowsWS.connect(token);
      eventsWS.connect(token);

      unsubAgents = agentsWS.subscribe((msg) => {
        set((s) => ({
          connected: true,
          agentEvents: [msg.payload as AgentEvent, ...s.agentEvents].slice(0, MAX_BUFFER),
        }));
      });

      unsubWorkflows = workflowsWS.subscribe((msg) => {
        set((s) => ({
          connected: true,
          workflowEvents: [msg.payload as WorkflowEvent, ...s.workflowEvents].slice(0, MAX_BUFFER),
        }));
      });

      unsubEvents = eventsWS.subscribe((msg) => {
        set((s) => ({
          connected: true,
          systemEvents: [msg, ...s.systemEvents].slice(0, MAX_BUFFER),
        }));
      });

      set({ connected: true });
    },

    disconnect() {
      unsubAgents?.();
      unsubWorkflows?.();
      unsubEvents?.();
      agentsWS.disconnect();
      workflowsWS.disconnect();
      eventsWS.disconnect();
      set({ connected: false });
    },

    clearEvents() {
      set({ agentEvents: [], workflowEvents: [], systemEvents: [] });
    },
  };
});
