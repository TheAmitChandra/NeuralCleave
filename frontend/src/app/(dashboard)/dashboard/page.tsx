"use client";

import { useQuery } from "@tanstack/react-query";
import { Wifi, Brain, Coins, Zap, Clock, Server } from "lucide-react";
import api from "@/lib/api";
import type { MemoryEntry } from "@/store/memory";
import { sumMetric, type MetricsSnapshot } from "@/lib/metrics";

interface GatewayStatus {
  status: string;
  uptime_seconds?: number;
  version?: string;
}

interface Channel {
  channel_id: string;
  type: string;
  connected: boolean;
}

interface ChannelsResponse {
  channels: Channel[];
  count: number;
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

  const { data: channelsResponse, isLoading: channelsLoading } = useQuery<ChannelsResponse>({
    queryKey: ["channels"],
    queryFn: async () => {
      const { data } = await api.get<ChannelsResponse>("/channels");
      return data;
    },
  });
  const channels = channelsResponse?.channels;

  const { data: memoryEntriesResponse, isLoading: memoryLoading } = useQuery<{
    entries: MemoryEntry[];
    count: number;
  }>({
    queryKey: ["memory", "entries"],
    queryFn: async () => {
      const { data } = await api.get<{ entries: MemoryEntry[]; count: number }>(
        "/memory/entries"
      );
      return data;
    },
  });
  const memoryEntries = memoryEntriesResponse?.entries;

  const { data: snapshot, isLoading: metricsLoading } = useQuery<MetricsSnapshot>({
    queryKey: ["metrics", "snapshot"],
    queryFn: async () => {
      const { data } = await api.get<MetricsSnapshot>("/metrics/snapshot");
      return data;
    },
    refetchInterval: 15_000,
  });

  const connectedChannels = channels?.filter((c) => c.connected).length ?? 0;
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
      value: connectedChannels,
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
      value: sumMetric(snapshot, "generation_requests_total"),
      icon: Zap,
      color: "text-sky-400",
      isLoading: metricsLoading,
    },
    {
      label: "Tokens Used",
      value: sumMetric(snapshot, "tokens_total").toLocaleString(),
      icon: Coins,
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
                  key={ch.channel_id}
                  className="flex items-center justify-between rounded-lg bg-slate-800/50 px-3 py-2"
                >
                  <span className="text-sm text-white">{ch.channel_id}</span>
                  <span
                    className={`text-xs font-medium ${
                      ch.connected ? "text-emerald-400" : "text-slate-500"
                    }`}
                  >
                    {ch.connected ? "connected" : "not connected"}
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
