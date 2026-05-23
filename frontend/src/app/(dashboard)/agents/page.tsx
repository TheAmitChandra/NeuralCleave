"use client";

import { useState, FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Plus,
  Play,
  Pause,
  StopCircle,
  Loader2,
  X,
} from "lucide-react";
import api from "@/lib/api";
import type { Agent, AgentStatus } from "@/store/agents";

const STATUS_BADGE: Record<AgentStatus, string> = {
  IDLE: "bg-slate-700 text-slate-300",
  PLANNING: "bg-indigo-500/20 text-indigo-300",
  EXECUTING: "bg-emerald-500/20 text-emerald-300",
  VALIDATING: "bg-amber-500/20 text-amber-300",
  REFLECTING: "bg-violet-500/20 text-violet-300",
  PAUSED: "bg-orange-500/20 text-orange-300",
  TERMINATED: "bg-red-500/20 text-red-400",
};

const AGENT_TYPES = [
  "planner",
  "router",
  "executor",
  "validator",
  "critic",
  "memory",
  "security",
  "observer",
] as const;

type AgentType = (typeof AGENT_TYPES)[number];

export default function AgentsPage() {
  const queryClient = useQueryClient();

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<AgentType>("executor");
  const [executeTarget, setExecuteTarget] = useState<string | null>(null);
  const [taskInput, setTaskInput] = useState("");

  const { data: agents = [], isLoading } = useQuery<Agent[]>({
    queryKey: ["agents"],
    queryFn: async () => {
      const { data } = await api.get<Agent[]>("/agents/");
      return data;
    },
    refetchInterval: 10_000,
  });

  const createMutation = useMutation({
    mutationFn: (payload: { name: string; agent_type: AgentType }) =>
      api.post<Agent>("/agents/create", payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      setShowCreate(false);
      setNewName("");
      setNewType("executor");
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "PAUSED" | "TERMINATED" }) =>
      api.patch(`/agents/${id}/status`, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agents"] }),
  });

  const executeMutation = useMutation({
    mutationFn: ({ id, task }: { id: string; task: string }) =>
      api.post(`/agents/${id}/execute`, { task }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      setExecuteTarget(null);
      setTaskInput("");
    },
  });

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    createMutation.mutate({ name: newName.trim(), agent_type: newType });
  }

  function handleExecute(e: FormEvent) {
    e.preventDefault();
    if (!executeTarget || !taskInput.trim()) return;
    executeMutation.mutate({ id: executeTarget, task: taskInput.trim() });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Agents</h1>
          <p className="mt-1 text-sm text-slate-400">
            Manage autonomous agent instances
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
        >
          <Plus className="h-4 w-4" />
          New Agent
        </button>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold text-white">Create Agent</h2>
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
                  placeholder="e.g. Alpha Planner"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm text-slate-300">Type</label>
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value as AgentType)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500"
                >
                  {AGENT_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              {createMutation.isError && (
                <p className="text-xs text-rose-400">Failed to create agent.</p>
              )}
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
              >
                {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Create
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Execute task modal */}
      {executeTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold text-white">Execute Task</h2>
              <button onClick={() => setExecuteTarget(null)} className="text-slate-400 hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleExecute} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm text-slate-300">Task description</label>
                <textarea
                  value={taskInput}
                  onChange={(e) => setTaskInput(e.target.value)}
                  required
                  rows={3}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500"
                  placeholder="Describe the task…"
                />
              </div>
              {executeMutation.isError && (
                <p className="text-xs text-rose-400">Failed to execute.</p>
              )}
              <button
                type="submit"
                disabled={executeMutation.isPending}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
              >
                {executeMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Execute
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Agent list */}
      <div className="rounded-xl border border-slate-800 bg-slate-900">
        {isLoading ? (
          <div className="space-y-2 p-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-14 animate-pulse rounded-lg bg-slate-800" />
            ))}
          </div>
        ) : agents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Bot className="mb-3 h-10 w-10 text-slate-600" />
            <p className="text-sm text-slate-400">No agents yet. Create one to get started.</p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-800">
            {agents.map((agent) => (
              <li key={agent.id} className="flex items-center justify-between px-5 py-4">
                <div className="flex items-center gap-3">
                  <Bot className="h-5 w-5 text-indigo-400" />
                  <div>
                    <p className="text-sm font-medium text-white">{agent.name}</p>
                    <p className="text-xs text-slate-500">{agent.agent_type}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_BADGE[agent.status] ?? STATUS_BADGE.IDLE}`}>
                    {agent.status}
                  </span>
                  <button onClick={() => setExecuteTarget(agent.id)} title="Execute task" className="rounded p-1 text-slate-400 hover:text-emerald-400">
                    <Play className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => statusMutation.mutate({ id: agent.id, status: "PAUSED" })}
                    title="Pause"
                    disabled={agent.status === "PAUSED" || agent.status === "TERMINATED"}
                    className="rounded p-1 text-slate-400 hover:text-amber-400 disabled:opacity-30"
                  >
                    <Pause className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => statusMutation.mutate({ id: agent.id, status: "TERMINATED" })}
                    title="Terminate"
                    disabled={agent.status === "TERMINATED"}
                    className="rounded p-1 text-slate-400 hover:text-rose-400 disabled:opacity-30"
                  >
                    <StopCircle className="h-4 w-4" />
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

