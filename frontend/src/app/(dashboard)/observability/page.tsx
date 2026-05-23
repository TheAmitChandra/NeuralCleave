"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Activity, Cpu, Clock, RefreshCcw, Network } from "lucide-react";
import api from "@/lib/api";
import { AgentGraph } from "@/components/AgentGraph";

interface Metrics {
  tool_calls_total: number;
  active_agents: number;
  avg_latency_ms: number;
  error_rate: number;
  llm_calls_total: number;
  workflow_executions_total: number;
  security_events_total: number;
  [key: string]: number;
}

interface LogEntry {
  id: string;
  level: string;
  message: string;
  agent_id: string | null;
  trace_id: string | null;
  created_at: string;
}

const LEVEL_COLOR: Record<string, string> = {
  DEBUG: "text-slate-400",
  INFO: "text-sky-400",
  WARNING: "text-amber-400",
  ERROR: "text-rose-400",
  CRITICAL: "text-red-400",
};

function MetricCard({
  title,
  icon: Icon,
  value,
  subtitle,
  isLoading,
}: {
  title: string;
  icon: React.ElementType;
  value: string | number;
  subtitle: string;
  isLoading?: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
      <div className="mb-3 flex items-center gap-2">
        <Icon className="h-4 w-4 text-indigo-400" />
        <h3 className="text-sm font-semibold text-white">{title}</h3>
      </div>
      <div className="flex h-24 items-center justify-center rounded-lg bg-slate-800/50">
        {isLoading ? (
          <div className="h-8 w-24 animate-pulse rounded bg-slate-700" />
        ) : (
          <div className="text-center">
            <p className="text-3xl font-bold text-white">{value}</p>
            <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ObservabilityPage() {
  const {
    data: metrics,
    isLoading: metricsLoading,
    refetch: refetchMetrics,
    dataUpdatedAt,
  } = useQuery<Metrics>({
    queryKey: ["metrics"],
    queryFn: async () => {
      const { data } = await api.get<Metrics>("/observability/metrics");
      return data;
    },
    refetchInterval: 15_000,
  });

  const { data: logs = [], isLoading: logsLoading } = useQuery<LogEntry[]>({
    queryKey: ["logs"],
    queryFn: async () => {
      const { data } = await api.get<LogEntry[]>("/observability/logs?limit=20");
      return data;
    },
    refetchInterval: 10_000,
  });

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : null;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Observability</h1>
          <p className="mt-1 text-sm text-slate-400">
            Prometheus metrics · OpenTelemetry traces · Structured logs
          </p>
        </div>
        <button
          onClick={() => refetchMetrics()}
          className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:text-white"
        >
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh
          {lastUpdated && <span className="text-slate-600">· {lastUpdated}</span>}
        </button>
      </div>

      {/* Live Agent Graph */}
      <div className="rounded-xl border border-slate-800 bg-slate-900">
        <div className="flex items-center gap-2 border-b border-slate-800 px-6 py-4">
          <Network className="h-4 w-4 text-indigo-400" />
          <h2 className="text-sm font-semibold text-white">Live Agent Graph</h2>
          <span className="ml-auto text-xs text-slate-500">
            Drag to reposition · Scroll to zoom
          </span>
        </div>
        <div className="p-4">
          <AgentGraph />
        </div>
      </div>

      {/* Metric panels */}
      <div className="grid gap-4 lg:grid-cols-2">
        <MetricCard
          title="Tool Calls"
          icon={Activity}
          value={metrics?.tool_calls_total ?? "—"}
          subtitle="Total tool executions"
          isLoading={metricsLoading}
        />
        <MetricCard
          title="LLM Calls"
          icon={Cpu}
          value={metrics?.llm_calls_total ?? "—"}
          subtitle="Requests to Gemini / DeepSeek / Ollama"
          isLoading={metricsLoading}
        />
        <MetricCard
          title="Avg Latency"
          icon={Clock}
          value={
            metrics?.avg_latency_ms != null
              ? `${metrics.avg_latency_ms.toFixed(1)} ms`
              : "—"
          }
          subtitle="Average agent execution time"
          isLoading={metricsLoading}
        />
        <MetricCard
          title="Workflow Executions"
          icon={BarChart3}
          value={metrics?.workflow_executions_total ?? "—"}
          subtitle="Total DAG executions"
          isLoading={metricsLoading}
        />
      </div>

      {/* Structured logs */}
      <div className="rounded-xl border border-slate-800 bg-slate-900">
        <div className="border-b border-slate-800 px-6 py-4">
          <h2 className="text-sm font-semibold text-white">Structured Logs</h2>
        </div>
        {logsLoading ? (
          <div className="space-y-2 p-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-slate-800" />
            ))}
          </div>
        ) : logs.length === 0 ? (
          <div className="p-6 text-center text-sm text-slate-500">
            No log entries yet.
          </div>
        ) : (
          <ul className="divide-y divide-slate-800 font-mono text-xs">
            {logs.map((log) => (
              <li key={log.id} className="flex items-start gap-3 px-5 py-3">
                <span
                  className={`shrink-0 font-semibold ${LEVEL_COLOR[log.level] ?? "text-slate-400"}`}
                >
                  {log.level.padEnd(8)}
                </span>
                <span className="shrink-0 text-slate-600">
                  {new Date(log.created_at).toLocaleTimeString()}
                </span>
                <span className="text-slate-300">{log.message}</span>
                {log.trace_id && (
                  <span className="ml-auto shrink-0 text-slate-600">
                    {log.trace_id.slice(0, 8)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

