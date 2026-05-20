import { Bot, GitBranch, Brain, ShieldCheck, Activity, Zap } from "lucide-react";

const stats = [
  { label: "Active Agents", value: "—", icon: Bot, color: "text-indigo-400" },
  { label: "Running Workflows", value: "—", icon: GitBranch, color: "text-emerald-400" },
  { label: "Memory Entries", value: "—", icon: Brain, color: "text-violet-400" },
  { label: "Security Events", value: "—", icon: ShieldCheck, color: "text-rose-400" },
  { label: "Tasks / min", value: "—", icon: Activity, color: "text-amber-400" },
  { label: "LLM Calls", value: "—", icon: Zap, color: "text-sky-400" },
];

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-400">
          Real-time overview of the CortexFlow cognitive OS
        </p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
        {stats.map(({ label, value, icon: Icon, color }) => (
          <div
            key={label}
            className="rounded-xl border border-slate-800 bg-slate-900 p-4"
          >
            <Icon className={`mb-3 h-5 w-5 ${color}`} />
            <p className="text-2xl font-semibold text-white">{value}</p>
            <p className="mt-1 text-xs text-slate-400">{label}</p>
          </div>
        ))}
      </div>

      {/* Placeholder panels */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Recent Agent Activity
          </h2>
          <p className="text-sm text-slate-500">
            Agent telemetry will appear here once agents are running.
          </p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Workflow Execution Graph
          </h2>
          <p className="text-sm text-slate-500">
            Live workflow DAG visualization coming in Phase 2.
          </p>
        </div>
      </div>
    </div>
  );
}
