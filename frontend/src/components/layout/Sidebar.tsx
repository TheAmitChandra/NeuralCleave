"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Brain,
  Wifi,
  BarChart3,
  Settings,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/channels", label: "Channels", icon: Wifi },
  { href: "/observability", label: "Observability", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 flex-col border-r border-slate-800 bg-slate-950">
      {/* Brand */}
      <div className="flex h-16 items-center gap-2 border-b border-slate-800 px-6">
        <Zap className="h-6 w-6 text-indigo-400" />
        <span className="text-lg font-bold tracking-tight text-white">
          CortexFlow
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
        <p className="text-xs text-slate-500">CortexFlow v0.1.0</p>
      </div>
    </aside>
  );
}
