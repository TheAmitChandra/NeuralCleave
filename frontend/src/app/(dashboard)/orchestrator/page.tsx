"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  GitBranch,
  CircleCheck,
  CircleDot,
  Loader2,
  Brain,
  Trash2,
  RefreshCw,
  HelpCircle,
  X,
  Plus,
  AlertCircle,
} from "lucide-react";
import axios from "axios";
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

// ---------------------------------------------------------------------------
// Guide modal
// ---------------------------------------------------------------------------

function GuideModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-violet-400" />
            <h2 className="text-base font-semibold text-white">How the Orchestrator Works</h2>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-500 hover:bg-slate-800 hover:text-white transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-6 space-y-4 text-sm text-slate-300">
          <p>
            The <strong className="text-white">Orchestrator</strong> routes every AI message to the most
            suitable <em>agent node</em>. Each node is a named specialist — e.g.{" "}
            <span className="font-mono text-violet-300">coding-agent</span> or{" "}
            <span className="font-mono text-violet-300">research-agent</span> — with its own task types,
            priority, and isolated memory namespace.
          </p>

          <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Quick Start</p>
            <ol className="list-decimal pl-4 space-y-1.5 text-slate-300">
              <li>Click <strong className="text-white">Register Node</strong> and give it a name + task types (e.g. <code className="rounded bg-slate-700 px-1 text-violet-300">coding, debugging</code>).</li>
              <li>Set a <strong className="text-white">priority</strong> — higher priority nodes are preferred when multiple match.</li>
              <li>Optionally assign a <strong className="text-white">model override</strong> (e.g. <code className="rounded bg-slate-700 px-1 text-violet-300">deepseek/coder</code>) so that node uses a specific LLM.</li>
              <li>Send a message in Chat — NeuralCleave routes it to the best matching node automatically.</li>
            </ol>
          </div>

          <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4 space-y-1.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Memory Namespaces</p>
            <p className="text-slate-400">
              Each node keeps its long-term memory separate. A{" "}
              <span className="font-mono text-violet-300">coding-agent</span> remembers your code preferences
              without mixing them into the general assistant&apos;s memory.
            </p>
          </div>

          <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">CLI equivalent</p>
            <code className="block text-xs text-violet-300 font-mono">neuralcleave orchestrator register --name coding-agent --tasks coding,debugging</code>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Register node modal
// ---------------------------------------------------------------------------

function RegisterNodeModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("50");
  const [taskTypes, setTaskTypes] = useState("");
  const [keywords, setKeywords] = useState("");
  const [namespace, setNamespace] = useState("");
  const [modelOverride, setModelOverride] = useState("");
  const [maxConcurrent, setMaxConcurrent] = useState("5");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        name: name.trim(),
        description: description.trim(),
        enabled: true,
        priority: parseInt(priority) || 50,
        task_types: taskTypes.split(",").map(s => s.trim()).filter(Boolean),
        routing_keywords: keywords.split(",").map(s => s.trim()).filter(Boolean),
        max_concurrent: parseInt(maxConcurrent) || 5,
      };
      if (namespace.trim()) payload.memory_namespace = namespace.trim();
      if (modelOverride.trim()) payload.model_override = modelOverride.trim();
      const { data } = await api.post("/orchestrator/nodes", payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orchestrator"] });
      onClose();
    },
    onError: (err) => {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail ?? "Registration failed");
      } else {
        setError("Registration failed");
      }
    },
  });

  function submit() {
    setError(null);
    if (!name.trim()) { setError("Name is required"); return; }
    mutation.mutate();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-y-auto max-h-[90vh]">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <h2 className="text-base font-semibold text-white">Register Agent Node</h2>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-500 hover:bg-slate-800 hover:text-white transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {[
            { label: "Node Name *", value: name, set: setName, placeholder: "e.g. coding-agent", hint: "Unique identifier" },
            { label: "Description", value: description, set: setDescription, placeholder: "What this node specialises in" },
          ].map(({ label, value, set, placeholder, hint }) => (
            <div key={label}>
              <label className="mb-1 block text-xs font-medium text-slate-400">{label}{hint && <span className="ml-1 text-slate-600">— {hint}</span>}</label>
              <input type="text" value={value} onChange={e => set(e.target.value)} placeholder={placeholder}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500 placeholder:text-slate-600" />
            </div>
          ))}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Priority <span className="text-slate-600">— higher = preferred</span></label>
              <input type="number" value={priority} onChange={e => setPriority(e.target.value)} min={1} max={100}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Max Concurrent</label>
              <input type="number" value={maxConcurrent} onChange={e => setMaxConcurrent(e.target.value)} min={1}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500" />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Task Types <span className="text-slate-600">— comma-separated</span></label>
            <input type="text" value={taskTypes} onChange={e => setTaskTypes(e.target.value)} placeholder="coding, debugging, analysis"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500 placeholder:text-slate-600" />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Routing Keywords <span className="text-slate-600">— optional, comma-separated</span></label>
            <input type="text" value={keywords} onChange={e => setKeywords(e.target.value)} placeholder="python, code, bug"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500 placeholder:text-slate-600" />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Memory Namespace <span className="text-slate-600">— defaults to node name</span></label>
            <input type="text" value={namespace} onChange={e => setNamespace(e.target.value)} placeholder="Leave blank to use node name"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500 placeholder:text-slate-600" />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Model Override <span className="text-slate-600">— optional, e.g. deepseek/coder</span></label>
            <input type="text" value={modelOverride} onChange={e => setModelOverride(e.target.value)} placeholder="Leave blank for auto-routing"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500 placeholder:text-slate-600" />
          </div>

          {error && (
            <p className="flex items-center gap-1.5 text-xs text-rose-400">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />{error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-800 px-6 py-4">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-white transition-colors">Cancel</button>
          <button onClick={submit} disabled={mutation.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40 transition-colors">
            {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Register
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Node card
// ---------------------------------------------------------------------------

function NodeCard({ node }: { node: AgentNode }) {
  const queryClient = useQueryClient();

  const { data: memData } = useQuery<NodeMemory>({
    queryKey: ["orchestrator", "node-memory", node.name],
    queryFn: async () => {
      const { data } = await api.get<NodeMemory>(`/orchestrator/nodes/${node.name}/memory`);
      return data;
    },
    refetchInterval: 15_000,
  });

  const toggleMutation = useMutation({
    mutationFn: () => api.patch(`/orchestrator/nodes/${node.name}`, { enabled: !node.enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["orchestrator"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/orchestrator/nodes/${node.name}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["orchestrator"] }),
  });

  const clearMemory = () => api.delete(`/orchestrator/nodes/${node.name}/memory`)
    .then(() => queryClient.invalidateQueries({ queryKey: ["orchestrator", "node-memory", node.name] }));

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {node.enabled ? (
            <CircleCheck className="h-4 w-4 shrink-0 text-emerald-400" />
          ) : (
            <CircleDot className="h-4 w-4 shrink-0 text-slate-600" />
          )}
          <span className="truncate font-semibold text-white">{node.name}</span>
          {node.model_override && (
            <span className="shrink-0 rounded bg-violet-900/40 px-2 py-0.5 text-xs text-violet-300">
              {node.model_override.split("/").pop()}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">p{node.priority}</span>
          <button
            onClick={() => toggleMutation.mutate()}
            disabled={toggleMutation.isPending}
            title={node.enabled ? "Disable node" : "Enable node"}
            className={`rounded-full px-2 py-0.5 text-xs font-medium transition-colors ${node.enabled ? "bg-emerald-900/30 text-emerald-400 hover:bg-rose-900/20 hover:text-rose-400" : "bg-slate-800 text-slate-500 hover:bg-emerald-900/20 hover:text-emerald-400"}`}
          >
            {node.enabled ? "enabled" : "disabled"}
          </button>
          <button
            onClick={() => deleteMutation.mutate()}
            disabled={deleteMutation.isPending}
            title="Remove node"
            className="text-slate-600 hover:text-rose-400 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {node.description && (
        <p className="text-xs text-slate-500 line-clamp-2">{node.description}</p>
      )}

      {node.task_types.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {node.task_types.map((t) => (
            <span key={t} className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-400">{t}</span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between rounded-lg bg-slate-800/60 px-3 py-2">
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Brain className="h-3.5 w-3.5 text-violet-400" />
          <span>
            <span className="text-slate-600">ns: </span>
            <span className="text-white">{node.effective_memory_namespace}</span>
          </span>
          {memData?.stats && (
            <span className="text-slate-500 ml-2">{memData.stats.count}/{memData.stats.max_entries}</span>
          )}
        </div>
        <button onClick={clearMemory} title="Clear memory namespace" className="text-slate-600 hover:text-rose-400 transition">
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function OrchestratorPage() {
  const [showGuide, setShowGuide] = useState(false);
  const [showRegister, setShowRegister] = useState(false);

  const { data, isLoading, isError, refetch, isFetching } = useQuery<OrchestratorStatus>({
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
      {showGuide && <GuideModal onClose={() => setShowGuide(false)} />}
      {showRegister && <RegisterNodeModal onClose={() => setShowRegister(false)} />}

      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
              <GitBranch className="h-6 w-6 text-violet-400" />
              Orchestrator
            </h1>
            <p className="mt-1 text-sm text-slate-400">Agent nodes, routing rules, and per-node memory namespaces</p>
          </div>
          <button
            onClick={() => setShowGuide(true)}
            className="relative mt-1 rounded-full p-1.5 text-slate-600 hover:bg-slate-800 hover:text-violet-400 transition-colors"
            title="How does this work?"
          >
            <HelpCircle className="h-4 w-4" />
            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-violet-500 animate-pulse" />
          </button>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setShowRegister(true)}
            className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-violet-500 transition-colors"
          >
            <Plus className="h-4 w-4" /> Register Node
          </button>
          <button
            onClick={() => void refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 transition hover:border-violet-500 hover:text-white disabled:opacity-40"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>
      </div>

      {data && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Total nodes", value: data.total_nodes, color: "text-white" },
            { label: "Enabled", value: data.enabled_nodes, color: "text-emerald-400" },
            { label: "Namespaces", value: Object.keys(nsMap).length, color: "text-violet-400" },
          ].map(({ label, value, color }) => (
            <div key={label} className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-3">
              <p className={`text-xl font-semibold ${color}`}>{value}</p>
              <p className="mt-0.5 text-xs text-slate-500">{label}</p>
            </div>
          ))}
        </div>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading orchestrator…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-900/40 bg-red-900/10 p-6 text-sm text-red-400">
          Orchestrator unavailable — gateway may not be running.
        </div>
      )}

      {!isLoading && !isError && nodes.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-10 text-center">
          <GitBranch className="mx-auto mb-3 h-10 w-10 text-slate-700" />
          <p className="text-sm font-medium text-slate-400">No agent nodes registered yet.</p>
          <p className="mt-2 text-xs text-slate-600">
            Click{" "}
            <button onClick={() => setShowRegister(true)} className="text-violet-400 hover:text-violet-300 underline">
              Register Node
            </button>{" "}
            above, or click the{" "}
            <button onClick={() => setShowGuide(true)} className="text-violet-400 hover:text-violet-300 underline">
              guide
            </button>{" "}
            to learn how the orchestrator works.
          </p>
        </div>
      )}

      {nodes.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {nodes.map((node) => (
            <NodeCard key={node.name} node={node} />
          ))}
        </div>
      )}
    </div>
  );
}
