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
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-slate-800 bg-slate-950 transition-transform duration-200 lg:static lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Brand */}
        <div className="flex h-16 items-center gap-2 border-b border-slate-800 px-6">
          {/* eslint-disable-next-line @next/next/no-img-element -- next/image needs the
              optimization server, which doesn't exist in the Tauri static export build */}
          <img src="/logo.png" alt="" className="h-7 w-7 rounded-md" />
          <span className="text-lg font-bold tracking-tight text-white">
            CortexFlow-AI
          </span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-4">
          <ul className="space-y-1 px-3">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const active = pathname === href || pathname.startsWith(`${href}/`);
              return (
                <li key={href}>
                  <Link
                    href={href}
                    onClick={onClose}
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      active
                        ? "bg-indigo-600 text-white"
                        : "text-slate-400 hover:bg-slate-800 hover:text-white"
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Footer */}
        <div className="border-t border-slate-800 px-6 py-4">
          <p className="text-xs text-slate-500">
            CortexFlow-AI {status?.version ? `v${status.version}` : ""}
          </p>
        </div>
      </aside>
    </>
  );
}
