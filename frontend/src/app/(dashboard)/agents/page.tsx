import { Bot, Plus } from "lucide-react";

const AGENT_TYPES = [
  "planner", "router", "executor", "validator", "critic", "memory", "security", "observer",
];

export default function AgentsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Agents</h1>
          <p className="mt-1 text-sm text-slate-400">
            Manage autonomous agent instances
          </p>
        </div>
        <button className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500">
          <Plus className="h-4 w-4" />
          New Agent
        </button>
      </div>

      {/* Agent type cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {AGENT_TYPES.map((type) => (
          <div
            key={type}
            className="rounded-xl border border-slate-800 bg-slate-900 p-5 transition-colors hover:border-indigo-600"
          >
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-slate-800">
              <Bot className="h-5 w-5 text-indigo-400" />
            </div>
            <h3 className="text-sm font-semibold capitalize text-white">{type}</h3>
            <p className="mt-1 text-xs text-slate-400">0 instances</p>
            <div className="mt-3 inline-flex items-center rounded-full bg-slate-800 px-2.5 py-0.5 text-xs text-slate-400">
              IDLE
            </div>
          </div>
        ))}
      </div>

      {/* Empty state */}
      <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/50 p-12 text-center">
        <Bot className="mx-auto h-10 w-10 text-slate-600" />
        <p className="mt-3 text-sm text-slate-400">
          No agents running. Create one to get started.
        </p>
      </div>
    </div>
  );
}
