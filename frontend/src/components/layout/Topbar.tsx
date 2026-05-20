"use client";

import { Bell, User } from "lucide-react";
import { useAuthStore } from "@/store/auth";

export function Topbar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-950 px-6">
      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-400">
          Autonomous Cognitive Operating System
        </span>
      </div>

      <div className="flex items-center gap-4">
        {/* Notification bell */}
        <button
          className="relative rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-800 hover:text-white"
          aria-label="Notifications"
        >
          <Bell className="h-5 w-5" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-indigo-500" />
        </button>

        {/* User menu */}
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-white">
            <User className="h-4 w-4" />
          </div>
          <div className="hidden md:block">
            <p className="text-sm font-medium text-white">
              {user?.full_name ?? "Guest"}
            </p>
            <p className="text-xs text-slate-400 capitalize">
              {user?.role ?? "—"}
            </p>
          </div>
          <button
            onClick={logout}
            className="ml-2 rounded-lg px-3 py-1.5 text-xs text-slate-400 transition-colors hover:bg-slate-800 hover:text-white"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
