"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Cpu, Coins, Clock, MessageSquare, Mic, Volume2, RefreshCcw, ChevronLeft, ChevronRight } from "lucide-react";
import api from "@/lib/api";
import {
  sumMetric,
  avgHistogram,
  tokensByModel,
  type MetricsSnapshot,
} from "@/lib/metrics";

const METRICS_PAGE_SIZE = 10;
const LIFETIME_KEY = "nc_obs_lifetime_v1";

interface LifetimeStore {
  historical: Record<string, number>; // banked from past sessions
  prev: Record<string, number>;       // last-seen values per metric key
}

function flattenCounters(snapshot: MetricsSnapshot): Record<string, number> {
  const flat: Record<string, number> = {};
  for (const [name, metric] of Object.entries(snapshot)) {
    if (metric.type === "histogram") continue;
    for (const [labelKey, value] of Object.entries(metric.values)) {
      if (typeof value === "number") flat[`${name}||${labelKey}`] = value;
    }
  }
  return flat;
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

  const [filterMode, setFilterMode] = useState<"session" | "alltime">("session");
  const [metricsPage, setMetricsPage] = useState(1);
  const lifetimeRef = useRef<LifetimeStore>({ historical: {}, prev: {} });

  // Hydrate from localStorage once on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem(LIFETIME_KEY);
      if (raw) lifetimeRef.current = JSON.parse(raw) as LifetimeStore;
    } catch { /* storage unavailable or corrupt */ }
  }, []);

  // Track cumulative totals across gateway restarts.
  // Prometheus counters reset when the gateway restarts (they reset to 0).
  // When a counter value drops significantly vs. the last-seen value we bank
  // the previous high-water mark into `historical` so "All Time" survives
  // gateway restarts without needing backend storage.
  useEffect(() => {
    if (!snapshot) return;
    const current = flattenCounters(snapshot);
    const { prev, historical } = lifetimeRef.current;
    const newHistorical = { ...historical };

    for (const [key, prevVal] of Object.entries(prev)) {
      const currVal = current[key] ?? 0;
      if (prevVal > 0 && currVal < prevVal * 0.5) {
        newHistorical[key] = (newHistorical[key] ?? 0) + prevVal;
      }
    }

    lifetimeRef.current = { historical: newHistorical, prev: current };
    try { localStorage.setItem(LIFETIME_KEY, JSON.stringify(lifetimeRef.current)); } catch { /* full */ }
  }, [snapshot]);

  function lifetimeSum(name: string): number {
    const { historical } = lifetimeRef.current;
    const prefix = `${name}||`;
    let total = 0;
    for (const [key, val] of Object.entries(historical)) {
      if (key.startsWith(prefix)) total += val;
    }
    total += sumMetric(snapshot, name);
    return total;
  }

  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;
  const isAllTime = filterMode === "alltime";
  const getCount = (name: string) => isAllTime ? lifetimeSum(name) : sumMetric(snapshot, name);

  const avgLatency = avgHistogram(snapshot, "generation_latency_ms");
  const tokenRows = tokensByModel(snapshot);
  const totalTokens = tokenRows.reduce((sum, r) => sum + r.input + r.output, 0);

  const metricCards = [
    {
      title: "LLM Calls",
      icon: Cpu,
      value: getCount("generation_requests_total").toLocaleString(),
      subtitle: isAllTime ? "All-time · across all sessions" : "Since gateway start",
    },
    {
      title: "Tokens Used",
      icon: Coins,
      value: (isAllTime ? lifetimeSum("tokens_total") : totalTokens).toLocaleString(),
      subtitle: isAllTime ? "All-time · input + output" : "Input + output, all models",
    },
    {
      title: "Avg Latency",
      icon: Clock,
      value: avgLatency != null ? `${avgLatency.toFixed(1)} ms` : "—",
      subtitle: "Current session average",
    },
    {
      title: "Messages",
      icon: MessageSquare,
      value: getCount("messages_total").toLocaleString(),
      subtitle: isAllTime ? "All-time · all channels" : "Inbound messages across channels",
    },
    {
      title: "Voice Transcriptions",
      icon: Mic,
      value: getCount("voice_transcriptions_total").toLocaleString(),
      subtitle: isAllTime ? "All-time · STT requests" : "STT requests processed",
    },
    {
      title: "Voice Synthesis",
      icon: Volume2,
      value: getCount("voice_synthesis_total").toLocaleString(),
      subtitle: isAllTime ? "All-time · TTS requests" : "TTS requests processed",
    },
  ];

  function switchFilter(mode: "session" | "alltime") {
    setFilterMode(mode);
    setMetricsPage(1);
  }

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
        <div className="flex items-center gap-2">
          {/* Session / All Time toggle */}
          <div className="flex overflow-hidden rounded-xl border border-white/[0.07] bg-white/[0.03]">
            <button
              onClick={() => switchFilter("session")}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                filterMode === "session"
                  ? "bg-cyan-500/20 text-cyan-300"
                  : "text-white/40 hover:text-white/70 hover:bg-white/[0.04]"
              }`}
            >
              This Session
            </button>
            <button
              onClick={() => switchFilter("alltime")}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                filterMode === "alltime"
                  ? "bg-cyan-500/20 text-cyan-300"
                  : "text-white/40 hover:text-white/70 hover:bg-white/[0.04]"
              }`}
            >
              All Time
            </button>
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
      </div>

      {isAllTime && (
        <p className="rounded-xl border border-cyan-500/20 bg-cyan-500/[0.06] px-4 py-2 text-xs text-cyan-300/80">
          All Time totals are tracked locally in your browser across gateway restarts.
          Clearing browser storage resets the history.
        </p>
      )}

      {/* Metric panels */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {metricCards.map((card) => (
          <MetricCard key={card.title} {...card} isLoading={isLoading} />
        ))}
      </div>

      {/* Token usage by model */}
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
        <div className="border-b border-white/[0.06] px-6 py-4">
          <h2 className="text-sm font-semibold text-white">
            Token Usage by Model
            {isAllTime && (
              <span className="ml-2 text-xs font-normal text-white/30">· this session</span>
            )}
          </h2>
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

      {/* All raw metrics — paginated 10 per page */}
      {snapshot && Object.keys(snapshot).length > 0 && (() => {
        const allEntries = Object.entries(snapshot);
        const totalMetricPages = Math.max(1, Math.ceil(allEntries.length / METRICS_PAGE_SIZE));
        const pagedEntries = allEntries.slice(
          (metricsPage - 1) * METRICS_PAGE_SIZE,
          metricsPage * METRICS_PAGE_SIZE
        );
        return (
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
            <div className="flex items-center justify-between border-b border-white/[0.06] px-6 py-4">
              <h2 className="text-sm font-semibold text-white">
                All Metrics
                <span className="ml-1.5 text-xs font-normal text-white/30">
                  ({allEntries.length})
                </span>
              </h2>
              {totalMetricPages > 1 && (
                <span className="text-xs tabular-nums text-white/25">
                  Page {metricsPage} of {totalMetricPages}
                </span>
              )}
            </div>
            <ul className="divide-y divide-white/[0.05]">
              {pagedEntries.map(([name, metric]) => (
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
            {totalMetricPages > 1 && (
              <div className="flex items-center justify-between border-t border-white/[0.06] px-5 py-3">
                <button
                  onClick={() => setMetricsPage((p) => Math.max(1, p - 1))}
                  disabled={metricsPage === 1}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs text-white/40 hover:text-white/70 hover:bg-white/[0.05] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                  Prev
                </button>
                <span className="text-xs tabular-nums text-white/25">
                  Showing {(metricsPage - 1) * METRICS_PAGE_SIZE + 1}–
                  {Math.min(metricsPage * METRICS_PAGE_SIZE, allEntries.length)} of {allEntries.length}
                </span>
                <button
                  onClick={() => setMetricsPage((p) => Math.min(totalMetricPages, p + 1))}
                  disabled={metricsPage === totalMetricPages}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs text-white/40 hover:text-white/70 hover:bg-white/[0.05] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  Next
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}
