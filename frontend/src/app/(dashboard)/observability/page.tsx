"use client";

import { useQuery } from "@tanstack/react-query";
import { Cpu, Coins, Clock, MessageSquare, Mic, Volume2, RefreshCcw } from "lucide-react";
import api from "@/lib/api";
import {
  sumMetric,
  avgHistogram,
  tokensByModel,
  type MetricsSnapshot,
} from "@/lib/metrics";

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
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-6">
      <div className="mb-3 flex items-center gap-2">
        <Icon className="h-4 w-4 text-cyan-400" />
        <h3 className="text-sm font-semibold text-white">{title}</h3>
      </div>
      <div className="flex h-24 items-center justify-center rounded-xl bg-white/[0.04] px-4 py-3">
        {isLoading ? (
          <div className="h-8 w-24 bg-white/[0.06] animate-pulse rounded" />
        ) : (
          <div className="text-center">
            <p className="text-3xl font-bold text-white">{value}</p>
            <p className="mt-1 text-xs text-white/50">{subtitle}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function formatLabelKey(key: string): string {
  if (!key) return "(unlabelled)";
  return key
    .split(",")
    .map((pair) => pair.replace("=", ": "))
    .join(", ");
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

  const avgLatency = avgHistogram(snapshot, "generation_latency_ms");
  const tokenRows = tokensByModel(snapshot);
  const totalTokens = tokenRows.reduce((sum, r) => sum + r.input + r.output, 0);

  const metricCards = [
    {
      title: "LLM Calls",
      icon: Cpu,
      value: sumMetric(snapshot, "generation_requests_total").toLocaleString(),
      subtitle: "Across all configured providers",
    },
    {
      title: "Tokens Used",
      icon: Coins,
      value: totalTokens.toLocaleString(),
      subtitle: "Input + output, all models",
    },
    {
      title: "Avg Latency",
      icon: Clock,
      value: avgLatency != null ? `${avgLatency.toFixed(1)} ms` : "—",
      subtitle: "Average LLM response time",
    },
    {
      title: "Messages",
      icon: MessageSquare,
      value: sumMetric(snapshot, "messages_total").toLocaleString(),
      subtitle: "Inbound messages across channels",
    },
    {
      title: "Voice Transcriptions",
      icon: Mic,
      value: sumMetric(snapshot, "voice_transcriptions_total").toLocaleString(),
      subtitle: "STT requests processed",
    },
    {
      title: "Voice Synthesis",
      icon: Volume2,
      value: sumMetric(snapshot, "voice_synthesis_total").toLocaleString(),
      subtitle: "TTS requests processed",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Observability</h1>
          <p className="text-sm text-white/40 mt-1">
            Prometheus metrics snapshot · Structured JSON logs via{" "}
            <code className="rounded-lg bg-white/[0.06] px-2 py-0.5 text-xs text-white/60">
              neuralcleave status
            </code>
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 rounded-xl border border-white/[0.07] bg-white/[0.03] px-3 py-2 text-sm text-white/40 hover:bg-white/[0.06] hover:text-white/80 transition-colors"
        >
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh
          {lastUpdated && (
            <span className="text-white/[0.2]">· {lastUpdated}</span>
          )}
        </button>
      </div>

      {/* Metric panels */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {metricCards.map((card) => (
          <MetricCard key={card.title} {...card} isLoading={isLoading} />
        ))}
      </div>

      {/* Token usage by model */}
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
        <div className="border-b border-white/[0.06] px-6 py-4">
          <h2 className="text-sm font-semibold text-white">Token Usage by Model</h2>
        </div>
        {isLoading ? (
          <div className="space-y-2 p-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-10 bg-white/[0.06] animate-pulse rounded" />
            ))}
          </div>
        ) : tokenRows.length === 0 ? (
          <div className="p-6 text-center text-sm text-white/50">
            No LLM generations recorded yet.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-left text-xs font-semibold uppercase tracking-widest text-white/[0.25]">
                <th className="px-6 py-3">Model</th>
                <th className="px-6 py-3 text-right">Input</th>
                <th className="px-6 py-3 text-right">Output</th>
                <th className="px-6 py-3 text-right">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {tokenRows.map((row) => (
                <tr key={row.model}>
                  <td className="px-6 py-3 font-mono text-xs text-white">{row.model}</td>
                  <td className="px-6 py-3 text-right text-white/50">
                    {row.input.toLocaleString()}
                  </td>
                  <td className="px-6 py-3 text-right text-white/50">
                    {row.output.toLocaleString()}
                  </td>
                  <td className="px-6 py-3 text-right font-semibold text-white">
                    {(row.input + row.output).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* All raw metrics */}
      {snapshot && Object.keys(snapshot).length > 0 && (
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
          <div className="border-b border-white/[0.06] px-6 py-4">
            <h2 className="text-sm font-semibold text-white">All Metrics</h2>
          </div>
          <ul className="divide-y divide-white/[0.05]">
            {Object.entries(snapshot).map(([name, metric]) => (
              <li key={name} className="px-6 py-3">
                <div className="flex items-center gap-2">
                  <code className="rounded-lg bg-white/[0.06] px-2 py-0.5 text-xs text-white/60 font-mono">
                    {name}
                  </code>
                  <span className="rounded-lg bg-white/[0.06] px-2.5 py-1 text-xs text-white/40 uppercase">
                    {metric.type}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-white/50">{metric.description}</p>
                {Object.keys(metric.values).length > 0 && (
                  <div className="mt-1.5 space-y-0.5 font-mono text-[11px] text-white/[0.25]">
                    {Object.entries(metric.values).map(([labelKey, value]) => (
                      <div key={labelKey} className="flex justify-between">
                        <span>{formatLabelKey(labelKey)}</span>
                        <span className="text-white/60">
                          {typeof value === "number"
                            ? value.toLocaleString()
                            : `sum=${value.sum} count=${value.count}`}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
