import { create } from "zustand";

export interface MemoryEntry {
  id: number;
  session_id: string;
  content: string;
  importance_score: number;
  memory_type: string; // "general" | "summary" | …
  tags: string; // comma-separated raw string from SQLite
  created_at: string;
  last_accessed_at: string;
}

interface MemoryState {
  searchQuery: string;
  setSearchQuery: (q: string) => void;
}

export const useMemoryStore = create<MemoryState>()((set) => ({
  searchQuery: "",
  setSearchQuery: (q) => set({ searchQuery: q }),
}));
