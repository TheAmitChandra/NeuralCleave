"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  MessageSquare,
  Brain,
  Wifi,
  BarChart3,
  Settings,
  Terminal,
  Package,
  GitBranch,
  Layout,
} from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";

interface GatewayStatus {
  status: string;
  version?: string;
}

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/channels", label: "Channels", icon: Wifi },
  { href: "/orchestrator", label: "Orchestrator", icon: GitBranch },
  { href: "/skills", label: "Skills", icon: Package },
  { href: "/canvas", label: "Canvas", icon: Layout },
  { href: "/terminal", label: "Terminal", icon: Terminal },
  { href: "/observability", label: "Observability", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
];

interface SidebarProps {
  /** Whether the mobile drawer is open. Ignored at lg+ where the sidebar is always visible. */
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const pathname = usePathname();
  // Shares the "gateway-status" query key with Topbar — React Query
  // dedupes this into a single network call, not a duplicate poll.
  const { data: status } = useQuery<GatewayStatus>({
    queryKey: ["gateway-status"],
    queryFn: async () => {
      const { data } = await api.get<GatewayStatus>("/status");
      return data;
    },
    refetchInterval: 30_000,
    retry: false,
  });

  return (
    <>
      {/* Mobile backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-60 flex-col border-r border-white/[0.05] transition-transform duration-200 lg:static lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
        style={{ background: "linear-gradient(180deg, #0e0e1c 0%, #0a0a15 100%)" }}
      >
        {/* Subtle top brand accent */}
        <div className="absolute top-0 left-0 right-0 h-40 pointer-events-none" style={{ background: "radial-gradient(ellipse at 50% 0%, rgba(124,58,237,0.1) 0%, transparent 70%)" }} />

        {/* Brand */}
        <div className="relative flex h-14 items-center gap-2.5 border-b border-white/[0.05] px-5">
          {/* eslint-disable-next-line @next/next/no-img-element -- next/image needs the
              optimization server, which doesn't exist in the Tauri static export build */}
          <img src="/logo.png" alt="" className="h-6 w-6 rounded-lg" />
          <span className="text-[15px] font-semibold tracking-tight text-white">
            NeuralCleave
          </span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-3">
          <ul className="space-y-0.5 px-2">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const active = pathname === href || pathname.startsWith(`${href}/`);
              return (
                <li key={href}>
                  <Link
                    href={href}
                    onClick={onClose}
                    className={cn(
                      "flex items-center gap-3 rounded-xl px-3 py-2 text-[13px] font-medium transition-all duration-150",
                      active
                        ? "bg-white/[0.08] text-white"
                        : "text-white/30 hover:bg-white/[0.04] hover:text-white/70"
                    )}
                  >
                    <Icon className={cn("h-4 w-4 shrink-0", active ? "text-violet-400" : "opacity-60")} />
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Footer */}
        <div className="border-t border-white/[0.05] px-5 py-3.5">
          <div className="flex items-center gap-2">
            <div className={cn(
              "h-1.5 w-1.5 rounded-full",
              status?.status === "ok" ? "bg-emerald-500 animate-pulse" : "bg-slate-700"
            )} />
            <p className="text-[11px] text-white/20">
              {status?.status === "ok" ? "Gateway online" : "Gateway offline"} {status?.version ? `· v${status.version}` : ""}
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
