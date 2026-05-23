import { create } from "zustand";

export interface MemoryEntry {
  id: string;
  memory_type: "short_term" | "semantic" | "episodic" | "knowledge_graph";
  content: string;
  summary: string | null;
  importance_score: number;
  access_count: number;
  tags: string[] | null;
  agent_id: string | null;
  created_at: string;
  last_accessed_at: string | null;
  expires_at: string | null;
}

interface MemoryState {
  searchQuery: string;
  setSearchQuery: (q: string) => void;
}

export const useMemoryStore = create<MemoryState>()((set) => ({
  searchQuery: "",
  setSearchQuery: (q) => set({ searchQuery: q }),
}));
