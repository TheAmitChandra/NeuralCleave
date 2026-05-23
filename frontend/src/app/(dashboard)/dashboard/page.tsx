"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, GitBranch, Brain, ShieldCheck, Activity, Zap } from "lucide-react";
import api from "@/lib/api";
import type { Agent } from "@/store/agents";
import type { Workflow } from "@/store/workflows";
import type { MemoryEntry } from "@/store/memory";

interface Metrics {
  tool_calls_total: number;
  active_agents: number;
  avg_latency_ms: number;
  error_rate: number;
  [key: string]: number;
}

interface AuditLog {
  id: string;
  event_type: string;
  action: string;
  outcome: string;
  created_at: string;
}

function StatCard({
  label,
  value,
  icon: Icon,
  color,
  isLoading,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  isLoading?: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <Icon className={`mb-3 h-5 w-5 ${color}`} />
      <p className="text-2xl font-semibold text-white">
        {isLoading ? (
          <span className="inline-block h-7 w-10 animate-pulse rounded bg-slate-700" />
        ) : (
          value
        )}
      </p>
      <p className="mt-1 text-xs text-slate-400">{label}</p>
    </div>
  );
}

export default function DashboardPage() {
  const { data: agents, isLoading: agentsLoading } = useQuery<Agent[]>({
    queryKey: ["agents"],
    queryFn: async () => {
      const { data } = await api.get<Agent[]>("/agents/");
      return data;
    },
  });

  const { data: workflows, isLoading: workflowsLoading } = useQuery<Workflow[]>({
    queryKey: ["workflows"],
    queryFn: async () => {
      const { data } = await api.get<Workflow[]>("/workflows/");
      return data;
    },
  });

  const { data: memoryData, isLoading: memoryLoading } = useQuery<{ results: MemoryEntry[] }>({
    queryKey: ["memory", "all"],
    queryFn: async () => {
      const { data } = await api.get<{ results: MemoryEntry[] }>("/memory/search?q=&limit=1000");
      return data;
    },
  });

  const { data: metrics, isLoading: metricsLoading } = useQuery<Metrics>({
    queryKey: ["metrics"],
    queryFn: async () => {
      const { data } = await api.get<Metrics>("/observability/metrics");
      return data;
    },
    refetchInterval: 15_000,
  });

  const { data: auditLogs, isLoading: auditLoading } = useQuery<AuditLog[]>({
    queryKey: ["audit-logs", "recent"],
    queryFn: async () => {
      const { data } = await api.get<AuditLog[]>("/observability/logs?limit=5");
      return data;
    },
    refetchInterval: 30_000,
  });

  const activeAgents =
    agents?.filter((a) =>
      ["PLANNING", "EXECUTING", "VALIDATING", "REFLECTING"].includes(a.status)
    ).length ?? 0;

  const runningWorkflows =
    workflows?.filter((w) => w.status === "RUNNING").length ?? 0;

  const memoryCount = memoryData?.results?.length ?? 0;
  const securityEvents = metrics?.security_events_total ?? 0;
  const toolCallsTotal = metrics?.tool_calls_total ?? 0;
  const llmCalls = metrics?.llm_calls_total ?? 0;

  const stats = [
    {
      label: "Active Agents",
      value: activeAgents,
      icon: Bot,
      color: "text-indigo-400",
      isLoading: agentsLoading,
    },
    {
      label: "Running Workflows",
      value: runningWorkflows,
      icon: GitBranch,
      color: "text-emerald-400",
      isLoading: workflowsLoading,
    },
    {
      label: "Memory Entries",
      value: memoryCount,
      icon: Brain,
      color: "text-violet-400",
      isLoading: memoryLoading,
    },
    {
      label: "Security Events",
      value: securityEvents,
      icon: ShieldCheck,
      color: "text-rose-400",
      isLoading: metricsLoading,
    },
    {
      label: "Tool Calls",
      value: toolCallsTotal,
      icon: Activity,
      color: "text-amber-400",
      isLoading: metricsLoading,
    },
    {
      label: "LLM Calls",
      value: llmCalls,
      icon: Zap,
      color: "text-sky-400",
      isLoading: metricsLoading,
    },
  ];

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
        {stats.map((s) => (
          <StatCard key={s.label} {...s} />
        ))}
      </div>

      {/* Live panels */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Recent agents */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Recent Agent Activity
          </h2>
          {agentsLoading ? (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-8 animate-pulse rounded bg-slate-800" />
              ))}
            </div>
          ) : agents && agents.length > 0 ? (
            <ul className="space-y-2">
              {agents.slice(0, 5).map((agent) => (
                <li
                  key={agent.id}
                  className="flex items-center justify-between rounded-lg bg-slate-800/50 px-3 py-2"
                >
                  <span className="text-sm text-white">{agent.name}</span>
                  <span className="text-xs text-slate-400">
                    {agent.agent_type} · {agent.status}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">
              No agents yet. Create one on the Agents page.
            </p>
          )}
        </div>

        {/* Audit log */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Recent Audit Events
          </h2>
          {auditLoading ? (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-8 animate-pulse rounded bg-slate-800" />
              ))}
            </div>
          ) : auditLogs && auditLogs.length > 0 ? (
            <ul className="space-y-2">
              {auditLogs.map((log) => (
                <li
                  key={log.id}
                  className="flex items-center justify-between rounded-lg bg-slate-800/50 px-3 py-2"
                >
                  <span className="text-sm text-white">{log.action}</span>
                  <span
                    className={`text-xs font-medium ${
                      log.outcome === "success"
                        ? "text-emerald-400"
                        : "text-rose-400"
                    }`}
                  >
                    {log.outcome}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">
              No audit events yet.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
