"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import api from "@/lib/api";

interface GatewayStatus {
  status: string; // "ok" | …
  uptime_seconds?: number;
}

export function Topbar() {
  const { data, isError } = useQuery<GatewayStatus>({
    queryKey: ["gateway-status"],
    queryFn: async () => {
      const { data } = await api.get<GatewayStatus>("/status");
      return data;
    },
    refetchInterval: 30_000,
    retry: false,
  });

  const online = !isError && data?.status === "ok";

  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-950 px-6">
      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-400">
          Personal AI Assistant Gateway
        </span>
      </div>

      <div className="flex items-center gap-3">
        <Activity className="h-4 w-4 text-slate-500" />
        <span
          className={`text-xs font-medium ${online ? "text-emerald-400" : "text-slate-500"}`}
        >
          {online ? "Gateway online" : "Connecting…"}
        </span>
        <span
          className={`h-2 w-2 rounded-full ${online ? "bg-emerald-400" : "bg-slate-600"}`}
        />
      </div>
    </header>
  );
}
