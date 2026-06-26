"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Activity, Cpu, Clock, RefreshCcw } from "lucide-react";
import api from "@/lib/api";

interface MetricsSnapshot {
  llm_calls_total?: number;
  tool_calls_total?: number;
  avg_latency_ms?: number;
  memory_operations_total?: number;
  channel_messages_total?: number;
  reflection_corrections_total?: number;
  [key: string]: number | undefined;
}

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
    data: snapshot,
    isLoading,
    refetch,
    dataUpdatedAt,
  } = useQuery<MetricsSnapshot>({
    queryKey: ["metrics", "snapshot"],
    queryFn: async () => {
      const { data } = await api.get<MetricsSnapshot>("/metrics/snapshot");
      return data;
    },
    refetchInterval: 15_000,
  });

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : null;

  const fmt = (v: number | undefined) =>
    v != null ? v.toLocaleString() : "—";

  const fmtMs = (v: number | undefined) =>
    v != null ? `${v.toFixed(1)} ms` : "—";

  const metricCards = [
    {
      title: "LLM Calls",
      icon: Cpu,
      value: fmt(snapshot?.llm_calls_total),
      subtitle: "Claude · Gemini · DeepSeek · GPT-4 · Ollama",
    },
    {
      title: "Tool Calls",
      icon: Activity,
      value: fmt(snapshot?.tool_calls_total),
      subtitle: "Plugin tool executions",
    },
    {
      title: "Avg Latency",
      icon: Clock,
      value: fmtMs(snapshot?.avg_latency_ms),
      subtitle: "Average response time",
    },
    {
      title: "Memory Ops",
      icon: BarChart3,
      value: fmt(snapshot?.memory_operations_total),
      subtitle: "Reads + writes across all tiers",
    },
    {
      title: "Channel Messages",
      icon: Activity,
      value: fmt(snapshot?.channel_messages_total),
      subtitle: "Inbound messages processed",
    },
    {
      title: "Reflection Fixes",
      icon: RefreshCcw,
      value: fmt(snapshot?.reflection_corrections_total),
      subtitle: "Low-quality responses auto-corrected",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Observability</h1>
          <p className="mt-1 text-sm text-slate-400">
            Prometheus metrics snapshot · Structured JSON logs via{" "}
            <code className="rounded bg-slate-800 px-1 py-0.5 text-xs">
              cortex status
            </code>
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:text-white"
        >
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh
          {lastUpdated && (
            <span className="text-slate-600">· {lastUpdated}</span>
          )}
        </button>
      </div>

      {/* Metric panels */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {metricCards.map((card) => (
          <MetricCard key={card.title} {...card} isLoading={isLoading} />
        ))}
      </div>

      {/* All raw metrics */}
      {snapshot && Object.keys(snapshot).length > 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900">
          <div className="border-b border-slate-800 px-6 py-4">
            <h2 className="text-sm font-semibold text-white">
              All Metrics
            </h2>
          </div>
          <ul className="divide-y divide-slate-800 font-mono text-xs">
            {Object.entries(snapshot).map(([key, val]) => (
              <li
                key={key}
                className="flex items-center justify-between px-6 py-3"
              >
                <span className="text-slate-400">{key}</span>
                <span className="text-white">{val ?? "—"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
