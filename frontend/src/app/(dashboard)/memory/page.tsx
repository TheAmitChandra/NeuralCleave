import { Brain } from "lucide-react";

const MEMORY_TIERS = [
  {
    tier: "Short-Term",
    store: "Redis",
    description: "Working memory — active task context, expiry: 1h",
    color: "border-sky-600 bg-sky-600/10",
    badge: "bg-sky-500/20 text-sky-400",
    count: "—",
  },
  {
    tier: "Long-Term",
    store: "PostgreSQL",
    description: "Persistent facts and learned behaviors",
    color: "border-violet-600 bg-violet-600/10",
    badge: "bg-violet-500/20 text-violet-400",
    count: "—",
  },
  {
    tier: "Episodic",
    store: "Qdrant",
    description: "Vector-embedded conversation history and episodes",
    color: "border-emerald-600 bg-emerald-600/10",
    badge: "bg-emerald-500/20 text-emerald-400",
    count: "—",
  },
  {
    tier: "Knowledge Graph",
    store: "Neo4j",
    description: "Entity relationships and causal chains",
    color: "border-amber-600 bg-amber-600/10",
    badge: "bg-amber-500/20 text-amber-400",
    count: "—",
  },
];

export default function MemoryPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Memory</h1>
        <p className="mt-1 text-sm text-slate-400">
          Hierarchical 4-tier memory architecture
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {MEMORY_TIERS.map(({ tier, store, description, color, badge, count }) => (
          <div
            key={tier}
            className={`rounded-xl border p-6 ${color}`}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <Brain className="h-5 w-5 text-white/70" />
                <div>
                  <h3 className="font-semibold text-white">{tier}</h3>
                  <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs ${badge}`}>
                    {store}
                  </span>
                </div>
              </div>
              <span className="text-2xl font-bold text-white">{count}</span>
            </div>
            <p className="mt-4 text-sm text-slate-300">{description}</p>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-center text-sm text-slate-500">
        Memory retrieval pipeline and semantic search coming in Phase 2.
      </div>
    </div>
  );
}
