"use client";

import { useState, FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Brain, Search, Trash2, Loader2, Pencil, Check, X } from "lucide-react";
import api from "@/lib/api";
import { useMemoryStore, type MemoryEntry } from "@/store/memory";

interface SearchResponse {
  results: MemoryEntry[];
}

interface EntriesResponse {
  entries: MemoryEntry[];
  count: number;
}

const TIER_META: Record<
  string,
  { label: string; store: string; description: string; color: string; badge: string }
> = {
  short_term: {
    label: "Short-Term",
    store: "Redis",
    description: "Working memory — active task context, TTL: 1 h",
    color: "border-cyan-500/30 bg-cyan-500/[0.06]",
    badge: "bg-cyan-500/15 text-cyan-400",
  },
  semantic: {
    label: "Semantic",
    store: "Qdrant",
    description: "Vector-embedded memories for similarity search",
    color: "border-emerald-500/30 bg-emerald-500/[0.06]",
    badge: "bg-emerald-500/15 text-emerald-400",
  },
  long_term: {
    label: "Long-Term",
    store: "SQLite",
    description: "Persistent facts, scored by importance, auto-pruned",
    color: "border-violet-500/30 bg-violet-500/[0.06]",
    badge: "bg-violet-500/15 text-violet-400",
  },
};

function inferTier(entry: MemoryEntry): string {
  const mt = entry.memory_type.toLowerCase();
  if (mt === "summary" || mt === "general") return "long_term";
  if (mt === "semantic") return "semantic";
  return "long_term"; // safe default for unknown values
}

interface EditState {
  content: string;
  importance_score: string;
}

function scoreBg(score: number): string {
  if (score >= 0.8) return "bg-emerald-500/15 text-emerald-400";
  if (score >= 0.5) return "bg-amber-500/15 text-amber-400";
  return "bg-white/[0.06] text-white/40";
}

function relativeDate(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function stripConversationPrefix(content: string): string {
  // Memory entries stored as "User: ... Assistant: ..." — strip the labels
  return content
    .replace(/^User:\s*/i, "")
    .replace(/\s*Assistant:\s*/i, " → ");
}

function EntryRow({
  entry,
  onDelete,
  onPatch,
}: {
  entry: MemoryEntry;
  onDelete: () => void;
  onPatch: (id: number, patch: Partial<Pick<MemoryEntry, "content" | "importance_score">>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState<EditState>({
    content: entry.content,
    importance_score: String(entry.importance_score),
  });

  function commitEdit() {
    const score = parseFloat(draft.importance_score);
    if (!draft.content.trim() || isNaN(score)) return;
    onPatch(entry.id, {
      content: draft.content.trim(),
      importance_score: score,
    });
    setEditing(false);
  }

  function cancelEdit() {
    setDraft({ content: entry.content, importance_score: String(entry.importance_score) });
    setEditing(false);
  }

  const tagsArr = entry.tags ? entry.tags.split(",").filter(Boolean) : [];
  const tier = inferTier(entry);
  const tierMeta = TIER_META[tier];
  const displayContent = stripConversationPrefix(entry.content);
  const isLong = displayContent.length > 200;

  return (
    <li className="group flex items-start gap-3 px-5 py-4 hover:bg-white/[0.02] transition-colors border-l-2 border-transparent hover:border-l-violet-500/30">
      <div className="flex-1 min-w-0">
        {editing ? (
          <div className="space-y-2">
            <textarea
              value={draft.content}
              onChange={(e) => setDraft((d) => ({ ...d, content: e.target.value }))}
              rows={4}
              className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm resize-none"
            />
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <label className="text-xs text-white/[0.25] font-medium uppercase tracking-widest">
                  Score:
                </label>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={draft.importance_score}
                  onChange={(e) => setDraft((d) => ({ ...d, importance_score: e.target.value }))}
                  className="w-20 rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 focus:border-violet-500/50 outline-none px-3 py-1.5 text-sm"
                />
              </div>
              <span className="text-xs text-white/25">{draft.content.length} chars</span>
            </div>
          </div>
        ) : (
          <>
            {/* Content */}
            <p
              className={`text-sm text-white/85 leading-relaxed break-words ${!expanded && isLong ? "line-clamp-3" : ""}`}
            >
              {displayContent}
            </p>
            {isLong && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="mt-1 text-xs text-violet-400 hover:text-violet-300 transition-colors"
              >
                {expanded ? "Show less" : `Show more (${displayContent.length} chars)`}
              </button>
            )}

            {/* Metadata row */}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tierMeta.badge}`}>
                {tierMeta.label}
              </span>
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${scoreBg(entry.importance_score)}`}>
                {entry.importance_score.toFixed(2)}
              </span>
              {tagsArr.map((tag) => (
                <span key={tag} className="inline-flex items-center rounded-full bg-white/[0.06] px-2 py-0.5 text-xs text-white/50">
                  {tag.trim()}
                </span>
              ))}
              <span className="text-xs text-white/30 ml-auto">
                {relativeDate(entry.created_at)}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Actions */}
      <div className="flex shrink-0 items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
        {editing ? (
          <>
            <button
              onClick={commitEdit}
              className="rounded-lg p-1.5 text-white/30 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors"
              title="Save"
            >
              <Check className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={cancelEdit}
              className="rounded-lg p-1.5 text-white/30 hover:text-white/60 hover:bg-white/[0.05] transition-colors"
              title="Cancel"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="rounded-lg p-1.5 text-white/30 hover:text-violet-400 hover:bg-violet-500/10 transition-colors"
            title="Edit"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          onClick={onDelete}
          title="Delete"
          className="rounded-lg p-1.5 text-white/30 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </li>
  );
}

export default function MemoryPage() {
  const queryClient = useQueryClient();
  const { searchQuery, setSearchQuery } = useMemoryStore();
  const [inputValue, setInputValue] = useState(searchQuery);

  const { data: results = [], isLoading } = useQuery<MemoryEntry[]>({
    queryKey: ["memory", searchQuery],
    queryFn: async () => {
      if (searchQuery) {
        const { data } = await api.get<SearchResponse>(
          `/memory/search?q=${encodeURIComponent(searchQuery)}&limit=50`
        );
        return data.results;
      }
      const { data } = await api.get<EntriesResponse>(`/memory/entries?limit=50`);
      return data.entries;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/memory/entries/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["memory"] }),
  });

  const patchMutation = useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: number;
      patch: Partial<Pick<MemoryEntry, "content" | "importance_score">>;
    }) => {
      // The REST API's body key is "importance", not "importance_score" —
      // translated here so the rest of this component can keep using the
      // GET response's field name consistently.
      const { importance_score, ...rest } = patch;
      const body: Record<string, unknown> = { ...rest };
      if (importance_score !== undefined) body.importance = importance_score;
      return api.patch(`/memory/entries/${id}`, body);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["memory"] }),
  });

  function handleSearch(e: FormEvent) {
    e.preventDefault();
    setSearchQuery(inputValue);
  }

  const tierCounts = results.reduce<Record<string, number>>((acc, entry) => {
    const tier = inferTier(entry);
    acc[tier] = (acc[tier] ?? 0) + 1;
    return acc;
  }, {});

  // Timeline: sorted newest first
  const sorted = [...results].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Memory</h1>
        <p className="mt-1 text-sm text-white/50">
          3-tier memory pipeline — Redis · Qdrant · SQLite
        </p>
      </div>

      {/* Tier cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        {Object.entries(TIER_META).map(([type, meta]) => (
          <div key={type} className={`rounded-2xl border p-6 ${meta.color}`}>
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <Brain className="h-5 w-5 text-white/70" />
                <div>
                  <h3 className="font-semibold text-white">{meta.label}</h3>
                  <span
                    className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs ${meta.badge}`}
                  >
                    {meta.store}
                  </span>
                </div>
              </div>
              <span className="text-2xl font-bold text-white">
                {isLoading ? (
                  <span className="inline-block h-7 w-8 bg-white/[0.06] animate-pulse rounded" />
                ) : (
                  tierCounts[type] ?? 0
                )}
              </span>
            </div>
            <p className="mt-4 text-sm text-white/50">{meta.description}</p>
          </div>
        ))}
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/[0.2]" />
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Search memory entries…"
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none py-2 pl-9 pr-3 text-sm"
          />
        </div>
        <button
          type="submit"
          className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 text-white rounded-xl px-4 py-2 text-sm font-medium transition-colors"
        >
          <Search className="h-4 w-4" />
          Search
        </button>
      </form>

      {/* Timeline / results */}
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
        <div className="border-b border-white/[0.06] px-6 py-4">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-white/[0.25]">
            Memory Entries{" "}
            {!isLoading && (
              <span className="normal-case tracking-normal font-normal text-white/50">
                ({results.length}) — newest first
              </span>
            )}
          </h2>
        </div>
        {isLoading ? (
          <div className="space-y-2 p-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-14 bg-white/[0.06] animate-pulse rounded" />
            ))}
          </div>
        ) : sorted.length === 0 ? (
          <div className="p-6 text-center text-sm text-white/50">
            {searchQuery
              ? `No results for "${searchQuery}".`
              : "No memory entries yet."}
          </div>
        ) : (
          <ul className="divide-y divide-white/[0.05]">
            {sorted.map((entry) => (
              <EntryRow
                key={entry.id}
                entry={entry}
                onDelete={() => {
                  if (!deleteMutation.isPending) deleteMutation.mutate(entry.id);
                }}
                onPatch={(id, patch) => patchMutation.mutate({ id, patch })}
              />
            ))}
          </ul>
        )}
        {(deleteMutation.isPending || patchMutation.isPending) && (
          <div className="flex items-center gap-2 border-t border-white/[0.06] px-5 py-3 text-xs text-white/50">
            <Loader2 className="h-3 w-3 animate-spin" />
            Saving…
          </div>
        )}
      </div>
    </div>
  );
}
