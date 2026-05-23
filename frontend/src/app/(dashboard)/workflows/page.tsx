"use client";

import { useState, FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  GitBranch,
  Plus,
  Play,
  Pause,
  RotateCcw,
  Loader2,
  X,
} from "lucide-react";
import api from "@/lib/api";
import type { Workflow, WorkflowStatus } from "@/store/workflows";
import { WorkflowBuilder } from "@/components/WorkflowBuilder";

const STATUS_COLORS: Record<WorkflowStatus, string> = {
  PENDING: "bg-slate-500/20 text-slate-400",
  RUNNING: "bg-emerald-500/20 text-emerald-400",
  PAUSED: "bg-amber-500/20 text-amber-400",
  COMPLETED: "bg-indigo-500/20 text-indigo-400",
  FAILED: "bg-rose-500/20 text-rose-400",
  ROLLED_BACK: "bg-orange-500/20 text-orange-400",
};

export default function WorkflowsPage() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: workflows = [], isLoading } = useQuery<Workflow[]>({
    queryKey: ["workflows"],
    queryFn: async () => {
      const { data } = await api.get<Workflow[]>("/workflows/");
      return data;
    },
    refetchInterval: 10_000,
  });

  const createMutation = useMutation({
    mutationFn: (name: string) =>
      api.post<Workflow>("/workflows/run", { name, trigger_source: "manual" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      setShowCreate(false);
      setNewName("");
    },
  });

  const actionMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "pause" | "resume" | "rollback" }) =>
      api.post(`/workflows/${id}/${action}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workflows"] }),
  });

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    createMutation.mutate(newName.trim());
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Workflows</h1>
          <p className="mt-1 text-sm text-slate-400">
            DAG-based workflow execution engine
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
        >
          <Plus className="h-4 w-4" />
          New Workflow
        </button>
      </div>

      {/* Status legend */}
      <div className="flex flex-wrap gap-3">
        {(Object.entries(STATUS_COLORS) as [WorkflowStatus, string][]).map(([status, cls]) => (
          <span
            key={status}
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
          >
            {status}
          </span>
        ))}
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold text-white">Run Workflow</h2>
              <button onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm text-slate-300">Name</label>
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  required
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500"
                  placeholder="e.g. Data Pipeline v1"
                />
              </div>
              {createMutation.isError && (
                <p className="text-xs text-rose-400">Failed to create workflow.</p>
              )}
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
              >
                {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Run
              </button>
            </form>
          </div>
        </div>
      )}

      {/* DAG builder */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-indigo-400" />
          <h2 className="text-sm font-semibold text-white">Workflow Builder</h2>
          {selectedId && (
            <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-xs text-indigo-300">
              editing {workflows.find((w) => w.id === selectedId)?.name ?? selectedId}
            </span>
          )}
        </div>
        <p className="text-xs text-slate-400">
          Drag nodes from the palette onto the canvas, connect them, then click
          &ldquo;Save DAG&rdquo;. Select a workflow from the list below to link the graph.
        </p>
        <WorkflowBuilder
          workflowId={selectedId}
          onSaved={() => queryClient.invalidateQueries({ queryKey: ["workflows"] })}
        />
      </div>

      {/* Workflow list */}
      <div className="rounded-xl border border-slate-800 bg-slate-900">
        <div className="border-b border-slate-800 px-6 py-4">
          <h2 className="text-sm font-semibold text-white">Recent Workflows</h2>
        </div>
        {isLoading ? (
          <div className="space-y-2 p-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-800" />
            ))}
          </div>
        ) : workflows.length === 0 ? (
          <div className="p-6 text-center text-sm text-slate-500">
            No workflows found. Create one to get started.
          </div>
        ) : (
          <ul className="divide-y divide-slate-800">
            {workflows.map((wf) => (
              <li
                key={wf.id}
                onClick={() => setSelectedId((prev) => (prev === wf.id ? null : wf.id))}
                className={`flex cursor-pointer items-center justify-between px-5 py-4 transition-colors hover:bg-slate-800/60 ${
                  selectedId === wf.id ? "bg-slate-800/80" : ""
                }`}
              >
                <div>
                  <p className="text-sm font-medium text-white">{wf.name}</p>
                  <p className="text-xs text-slate-500">
                    v{wf.version} · {wf.trigger_source ?? "manual"}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[wf.status] ?? STATUS_COLORS.PENDING}`}>
                    {wf.status}
                  </span>
                  {/* Resume */}
                  <button
                    onClick={() => actionMutation.mutate({ id: wf.id, action: "resume" })}
                    title="Resume"
                    disabled={wf.status !== "PAUSED"}
                    className="rounded p-1 text-slate-400 hover:text-emerald-400 disabled:opacity-30"
                  >
                    <Play className="h-4 w-4" />
                  </button>
                  {/* Pause */}
                  <button
                    onClick={() => actionMutation.mutate({ id: wf.id, action: "pause" })}
                    title="Pause"
                    disabled={wf.status !== "RUNNING"}
                    className="rounded p-1 text-slate-400 hover:text-amber-400 disabled:opacity-30"
                  >
                    <Pause className="h-4 w-4" />
                  </button>
                  {/* Rollback */}
                  <button
                    onClick={() => actionMutation.mutate({ id: wf.id, action: "rollback" })}
                    title="Rollback"
                    disabled={!["FAILED", "PAUSED"].includes(wf.status)}
                    className="rounded p-1 text-slate-400 hover:text-orange-400 disabled:opacity-30"
                  >
                    <RotateCcw className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

