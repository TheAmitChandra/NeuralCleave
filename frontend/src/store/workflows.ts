import { create } from "zustand";

export type WorkflowStatus =
  | "PENDING"
  | "RUNNING"
  | "PAUSED"
  | "COMPLETED"
  | "FAILED"
  | "ROLLED_BACK";

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  status: WorkflowStatus;
  version: number;
  trigger_source: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

interface WorkflowsState {
  selectedWorkflowId: string | null;
  setSelectedWorkflowId: (id: string | null) => void;
}

export const useWorkflowsStore = create<WorkflowsState>()((set) => ({
  selectedWorkflowId: null,
  setSelectedWorkflowId: (id) => set({ selectedWorkflowId: id }),
}));
