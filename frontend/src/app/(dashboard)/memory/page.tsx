"use client";

import { useState, FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Brain, Search, Trash2, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { useMemoryStore, type MemoryEntry } from "@/store/memory";

interface SearchResponse {
  results: MemoryEntry[];
}

const TIER_META: Record<
  string,
  { label: string; store: string; description: string; color: string; badge: string }
> = {
  short_term: {
    label: "Short-Term",
    store: "Redis",
    description: "Working memory — active task context, expiry: 1h",
    color: "border-sky-600 bg-sky-600/10",
    badge: "bg-sky-500/20 text-sky-400",
  },
  semantic: {
    label: "Long-Term",
    store: "PostgreSQL",
    description: "Persistent facts and learned behaviors",
    color: "border-violet-600 bg-violet-600/10",
    badge: "bg-violet-500/20 text-violet-400",
  },
  episodic: {
    label: "Episodic",
    store: "Qdrant",
    description: "Vector-embedded conversation history and episodes",
    color: "border-emerald-600 bg-emerald-600/10",
    badge: "bg-emerald-500/20 text-emerald-400",
  },
  knowledge_graph: {
    label: "Knowledge Graph",
    store: "Neo4j",
    description: "Entity relationships and causal chains",
    color: "border-amber-600 bg-amber-600/10",
    badge: "bg-amber-500/20 text-amber-400",
  },
};

export default function MemoryPage() {
  const queryClient = useQueryClient();
  const { searchQuery, setSearchQuery } = useMemoryStore();
  const [inputValue, setInputValue] = useState(searchQuery);

  const { data, isLoading } = useQuery<SearchResponse>({
    queryKey: ["memory", searchQuery],
    queryFn: async () => {
      const { data } = await api.get<SearchResponse>(
        `/memory/search?q=${encodeURIComponent(searchQuery)}&limit=50`
      );
      return data;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/memory/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["memory"] }),
  });

  function handleSearch(e: FormEvent) {
    e.preventDefault();
    setSearchQuery(inputValue);
  }

  const results = data?.results ?? [];

  // Count per tier
  const tierCounts = results.reduce<Record<string, number>>((acc, entry) => {
    acc[entry.memory_type] = (acc[entry.memory_type] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Memory</h1>
        <p className="mt-1 text-sm text-slate-400">
          Hierarchical 4-tier memory architecture
        </p>
      </div>

      {/* Tier cards */}
      <div className="grid gap-4 sm:grid-cols-2">
        {Object.entries(TIER_META).map(([type, meta]) => (
          <div key={type} className={`rounded-xl border p-6 ${meta.color}`}>
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <Brain className="h-5 w-5 text-white/70" />
                <div>
                  <h3 className="font-semibold text-white">{meta.label}</h3>
                  <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs ${meta.badge}`}>
                    {meta.store}
                  </span>
                </div>
              </div>
              <span className="text-2xl font-bold text-white">
                {isLoading ? (
                  <span className="inline-block h-7 w-8 animate-pulse rounded bg-white/20" />
                ) : (
                  tierCounts[type] ?? 0
                )}
              </span>
            </div>
            <p className="mt-4 text-sm text-slate-300">{meta.description}</p>
          </div>
        ))}
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Search memory entries…"
            className="w-full rounded-lg border border-slate-700 bg-slate-800 py-2 pl-9 pr-3 text-sm text-white outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <button
          type="submit"
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          <Search className="h-4 w-4" />
          Search
        </button>
      </form>

      {/* Results */}
      <div className="rounded-xl border border-slate-800 bg-slate-900">
        <div className="border-b border-slate-800 px-6 py-4">
          <h2 className="text-sm font-semibold text-white">
            Memory Entries{" "}
            {!isLoading && (
              <span className="ml-1 text-slate-500">({results.length})</span>
            )}
          </h2>
        </div>
        {isLoading ? (
          <div className="space-y-2 p-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-14 animate-pulse rounded-lg bg-slate-800" />
            ))}
          </div>
        ) : results.length === 0 ? (
          <div className="p-6 text-center text-sm text-slate-500">
            {searchQuery
              ? `No results for "${searchQuery}".`
              : "No memory entries yet."}
          </div>
        ) : (
          <ul className="divide-y divide-slate-800">
            {results.map((entry) => (
              <li key={entry.id} className="flex items-start justify-between px-5 py-4">
                <div className="flex-1 min-w-0">
                  <p className="truncate text-sm text-white">
                    {entry.summary ?? entry.content}
                  </p>
                  <div className="mt-1 flex gap-2">
                    <span className="text-xs text-slate-500">{entry.memory_type}</span>
                    <span className="text-xs text-slate-600">·</span>
                    <span className="text-xs text-slate-500">
                      score {entry.importance_score.toFixed(2)}
                    </span>
                    {entry.tags && entry.tags.length > 0 && (
                      <>
                        <span className="text-xs text-slate-600">·</span>
                        <span className="text-xs text-slate-500">
                          {entry.tags.join(", ")}
                        </span>
                      </>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => deleteMutation.mutate(entry.id)}
                  disabled={deleteMutation.isPending}
                  title="Delete"
                  className="ml-3 shrink-0 rounded p-1 text-slate-500 hover:text-rose-400 disabled:opacity-30"
                >
                  {deleteMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

