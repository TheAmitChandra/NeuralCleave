"use client";

import { useQuery } from "@tanstack/react-query";
import {
  GitBranch,
  CircleCheck,
  CircleDot,
  Loader2,
  Brain,
  Trash2,
  RefreshCw,
} from "lucide-react";
import api from "@/lib/api";

interface AgentNode {
  name: string;
  description: string;
  enabled: boolean;
  priority: number;
  task_types: string[];
  routing_keywords: string[];
  memory_namespace: string;
  effective_memory_namespace: string;
  model_override?: string | null;
  max_concurrent: number;
}

interface OrchestratorStatus {
  status: string;
  nodes: AgentNode[];
  total_nodes: number;
  enabled_nodes: number;
  namespaces: Record<string, string>;
}

interface NodeMemory {
  node: string;
  memory_namespace: string;
  configured_namespace: string;
  stats: { count: number; max_entries: number } | null;
}

function NodeCard({ node }: { node: AgentNode }) {
  const { data: memData } = useQuery<NodeMemory>({
    queryKey: ["orchestrator", "node-memory", node.name],
    queryFn: async () => {
      const { data } = await api.get<NodeMemory>(
        `/orchestrator/nodes/${node.name}/memory`
      );
      return data;
    },
    refetchInterval: 15_000,
  });

  const clearMemory = async () => {
    await api.delete(`/orchestrator/nodes/${node.name}/memory`);
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {node.enabled ? (
            <CircleCheck className="h-4 w-4 shrink-0 text-emerald-400" />
          ) : (
            <CircleDot className="h-4 w-4 shrink-0 text-slate-600" />
          )}
          <span className="truncate font-semibold text-white">{node.name}</span>
          {node.model_override && (
            <span className="shrink-0 rounded bg-indigo-900/40 px-2 py-0.5 text-xs text-indigo-300">
              {node.model_override.split("/").pop()}
            </span>
          )}
        </div>
        <span className="shrink-0 rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
          p{node.priority}
        </span>
      </div>

      {node.description && (
        <p className="mt-2 text-xs text-slate-500 line-clamp-1">{node.description}</p>
      )}

      {/* Task types */}
      {node.task_types.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {node.task_types.map((t) => (
            <span
              key={t}
              className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-400"
            >
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Memory namespace */}
      <div className="mt-3 flex items-center justify-between rounded-lg bg-slate-800/60 px-3 py-2">
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Brain className="h-3.5 w-3.5 text-violet-400" />
          <span>
            <span className="text-slate-600">ns: </span>
            <span className="text-white">{node.effective_memory_namespace}</span>
          </span>
          {memData?.stats && (
            <span className="text-slate-500 ml-2">
              {memData.stats.count}/{memData.stats.max_entries} entries
            </span>
          )}
        </div>
        <button
          onClick={clearMemory}
          title="Clear memory namespace"
          className="text-slate-600 hover:text-red-400 transition"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

export default function OrchestratorPage() {
  const { data, isLoading, isError, refetch, isFetching } =
    useQuery<OrchestratorStatus>({
      queryKey: ["orchestrator", "status"],
      queryFn: async () => {
        const { data } = await api.get<OrchestratorStatus>("/orchestrator/status");
        return data;
      },
      refetchInterval: 20_000,
    });

  const nodes = data?.nodes ?? [];
  const nsMap = data?.namespaces ?? {};

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            <GitBranch className="h-6 w-6 text-indigo-400" />
            Orchestrator
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Agent nodes, routing rules, and per-node memory namespaces
          </p>
        </div>
        <button
          onClick={() => void refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 transition hover:border-indigo-500 hover:text-white disabled:opacity-40"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Summary */}
      {data && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-3">
            <p className="text-xl font-semibold text-white">{data.total_nodes}</p>
            <p className="mt-0.5 text-xs text-slate-500">Total nodes</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-3">
            <p className="text-xl font-semibold text-emerald-400">{data.enabled_nodes}</p>
            <p className="mt-0.5 text-xs text-slate-500">Enabled</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-3">
            <p className="text-xl font-semibold text-violet-400">
              {Object.keys(nsMap).length}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">Namespaces</p>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading orchestrator…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-900/40 bg-red-900/10 p-6 text-sm text-red-400">
          Orchestrator unavailable — gateway may not be running.
        </div>
      )}

      {!isLoading && !isError && nodes.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-10 text-center">
          <GitBranch className="mx-auto mb-3 h-10 w-10 text-slate-600" />
          <p className="text-sm text-slate-400">No agent nodes registered.</p>
          <p className="mt-2 text-xs text-slate-600">
            POST to{" "}
            <code className="rounded bg-slate-800 px-1.5 py-0.5">
              /api/v1/orchestrator/nodes
            </code>{" "}
            to register one.
          </p>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {nodes.map((node) => (
          <NodeCard key={node.name} node={node} />
        ))}
      </div>
    </div>
  );
}
