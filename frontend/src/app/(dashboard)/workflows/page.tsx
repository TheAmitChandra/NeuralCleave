import { GitBranch, Plus } from "lucide-react";

const STATUS_COLORS: Record<string, string> = {
  RUNNING: "bg-emerald-500/20 text-emerald-400",
  PAUSED: "bg-amber-500/20 text-amber-400",
  FAILED: "bg-rose-500/20 text-rose-400",
  COMPLETED: "bg-slate-500/20 text-slate-400",
};

export default function WorkflowsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Workflows</h1>
          <p className="mt-1 text-sm text-slate-400">
            DAG-based workflow execution engine
          </p>
        </div>
        <button className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500">
          <Plus className="h-4 w-4" />
          New Workflow
        </button>
      </div>

      {/* Status legend */}
      <div className="flex gap-3">
        {Object.entries(STATUS_COLORS).map(([status, cls]) => (
          <span
            key={status}
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
          >
            {status}
          </span>
        ))}
      </div>

      {/* React Flow canvas placeholder */}
      <div className="flex h-96 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-900/50">
        <div className="text-center">
          <GitBranch className="mx-auto h-10 w-10 text-slate-600" />
          <p className="mt-3 text-sm text-slate-400">
            Workflow DAG canvas — React Flow integration in Phase 2
          </p>
        </div>
      </div>

      {/* Workflow list */}
      <div className="rounded-xl border border-slate-800 bg-slate-900">
        <div className="border-b border-slate-800 px-6 py-4">
          <h2 className="text-sm font-semibold text-white">Recent Workflows</h2>
        </div>
        <div className="p-6 text-center text-sm text-slate-500">
          No workflows found. Create one to get started.
        </div>
      </div>
    </div>
  );
}
