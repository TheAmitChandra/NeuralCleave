"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Menu } from "lucide-react";
import api from "@/lib/api";

interface GatewayStatus {
  status: string; // "ok" | …
  uptime_seconds?: number;
}

interface TopbarProps {
  onMenuClick: () => void;
}

export function Topbar({ onMenuClick }: TopbarProps) {
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
    <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-950 px-4 sm:px-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white lg:hidden"
          aria-label="Open navigation menu"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="hidden text-sm text-slate-400 sm:inline">
          Personal AI Assistant Gateway
        </span>
      </div>

      <div className="flex items-center gap-3">
        <Activity className="h-4 w-4 text-slate-500" />
        <span
          className={`hidden text-xs font-medium sm:inline ${online ? "text-emerald-400" : "text-slate-500"}`}
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
