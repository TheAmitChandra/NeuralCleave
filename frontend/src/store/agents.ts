import { create } from "zustand";

export type AgentStatus =
  | "IDLE"
  | "PLANNING"
  | "EXECUTING"
  | "VALIDATING"
  | "REFLECTING"
  | "PAUSED"
  | "TERMINATED";

export interface Agent {
  id: string;
  name: string;
  agent_type: string;
  status: AgentStatus;
  description: string | null;
  trust_score: number;
  created_at: string;
  updated_at: string;
}

interface AgentsState {
  selectedAgentId: string | null;
  setSelectedAgentId: (id: string | null) => void;
}

export const useAgentsStore = create<AgentsState>()((set) => ({
  selectedAgentId: null,
  setSelectedAgentId: (id) => set({ selectedAgentId: id }),
}));
