"use client";

import { useQuery } from "@tanstack/react-query";
import { Wifi, Brain, Activity, Zap, Clock, Server } from "lucide-react";
import api from "@/lib/api";
import type { MemoryEntry } from "@/store/memory";

interface GatewayStatus {
  status: string;
  uptime_seconds?: number;
  version?: string;
}

interface Channel {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
}

interface MetricsSnapshot {
  llm_calls_total?: number;
  tool_calls_total?: number;
  avg_latency_ms?: number;
  [key: string]: number | undefined;
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
  const { data: status, isLoading: statusLoading } = useQuery<GatewayStatus>({
    queryKey: ["gateway-status"],
    queryFn: async () => {
      const { data } = await api.get<GatewayStatus>("/status");
      return data;
    },
    refetchInterval: 15_000,
  });

  const { data: channels, isLoading: channelsLoading } = useQuery<Channel[]>({
    queryKey: ["channels"],
    queryFn: async () => {
      const { data } = await api.get<Channel[]>("/channels");
      return data;
    },
  });

  const { data: memoryEntries, isLoading: memoryLoading } = useQuery<MemoryEntry[]>({
    queryKey: ["memory", "entries"],
    queryFn: async () => {
      const { data } = await api.get<MemoryEntry[]>("/memory/entries");
      return data;
    },
  });

  const { data: snapshot, isLoading: metricsLoading } = useQuery<MetricsSnapshot>({
    queryKey: ["metrics", "snapshot"],
    queryFn: async () => {
      const { data } = await api.get<MetricsSnapshot>("/metrics/snapshot");
      return data;
    },
    refetchInterval: 15_000,
  });

  const enabledChannels = channels?.filter((c) => c.enabled).length ?? 0;
  const memoryCount = memoryEntries?.length ?? 0;

  const uptime = status?.uptime_seconds
    ? status.uptime_seconds < 3600
      ? `${Math.floor(status.uptime_seconds / 60)}m`
      : `${Math.floor(status.uptime_seconds / 3600)}h`
    : "—";

  const stats = [
    {
      label: "Gateway Status",
      value: status?.status === "ok" ? "Online" : "—",
      icon: Server,
      color: "text-emerald-400",
      isLoading: statusLoading,
    },
    {
      label: "Active Channels",
      value: enabledChannels,
      icon: Wifi,
      color: "text-indigo-400",
      isLoading: channelsLoading,
    },
    {
      label: "Memory Entries",
      value: memoryCount,
      icon: Brain,
      color: "text-violet-400",
      isLoading: memoryLoading,
    },
    {
      label: "LLM Calls",
      value: snapshot?.llm_calls_total ?? "—",
      icon: Zap,
      color: "text-sky-400",
      isLoading: metricsLoading,
    },
    {
      label: "Tool Calls",
      value: snapshot?.tool_calls_total ?? "—",
      icon: Activity,
      color: "text-amber-400",
      isLoading: metricsLoading,
    },
    {
      label: "Uptime",
      value: uptime,
      icon: Clock,
      color: "text-slate-400",
      isLoading: statusLoading,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-400">
          Real-time overview of your CortexFlow-AI gateway
          {status?.version && (
            <span className="ml-2 text-slate-600">v{status.version}</span>
          )}
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
        {/* Connected channels */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Connected Channels
          </h2>
          {channelsLoading ? (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-8 animate-pulse rounded bg-slate-800" />
              ))}
            </div>
          ) : channels && channels.length > 0 ? (
            <ul className="space-y-2">
              {channels.slice(0, 6).map((ch) => (
                <li
                  key={ch.id}
                  className="flex items-center justify-between rounded-lg bg-slate-800/50 px-3 py-2"
                >
                  <span className="text-sm text-white capitalize">{ch.name}</span>
                  <span
                    className={`text-xs font-medium ${
                      ch.enabled ? "text-emerald-400" : "text-slate-500"
                    }`}
                  >
                    {ch.enabled ? "enabled" : "disabled"}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">
              No channels configured. Run{" "}
              <code className="rounded bg-slate-800 px-1 py-0.5 text-xs">
                cortex channels add
              </code>{" "}
              to add one.
            </p>
          )}
        </div>

        {/* Recent memory */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Recent Memory
          </h2>
          {memoryLoading ? (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-8 animate-pulse rounded bg-slate-800" />
              ))}
            </div>
          ) : memoryEntries && memoryEntries.length > 0 ? (
            <ul className="space-y-2">
              {[...memoryEntries]
                .sort(
                  (a, b) =>
                    new Date(b.created_at).getTime() -
                    new Date(a.created_at).getTime()
                )
                .slice(0, 5)
                .map((entry) => (
                  <li
                    key={entry.id}
                    className="flex items-start gap-2 rounded-lg bg-slate-800/50 px-3 py-2"
                  >
                    <span className="min-w-0 flex-1 truncate text-sm text-white">
                      {entry.content}
                    </span>
                    <span className="shrink-0 text-xs text-slate-500">
                      {entry.importance_score.toFixed(1)}
                    </span>
                  </li>
                ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">No memory entries yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}
